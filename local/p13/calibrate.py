"""P13: calibra o simulador contra o Kind local. Fora do CI; somente leitura no cluster, exceto o Job de carga.

Uso (na raiz, após `bash local/p6/up.sh`):
    python3 local/p13/calibrate.py collect --repetitions 3   # grava evidence/p13/observed.json
    python3 local/p13/calibrate.py analyze                   # grava evidence/p13/calibration.json
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from peakguard.scenarios import Scenario  # noqa: E402
from peakguard.simulator import Config, simulate  # noqa: E402

CMD = ['kubectl', '--kubeconfig', str(ROOT / 'local/p6/.kubeconfig'), '--context', 'kind-peakguard-p6', '-n', 'peakguard-p6']
OUT = ROOT / 'evidence/p13'
BIN_SECONDS = 10
# Parâmetros antigos (referência P6, não calibrados): 300 doc/min/réplica e ativação de 2 ticks de 10 s.
OLD = {'capacity_docs_per_minute_per_replica': 300.0, 'activation_delay_ticks': 2}


def kube(*args, timeout=60):
    return subprocess.check_output(CMD + list(args), text=True, timeout=timeout)


def prom(path, **params):
    url = '/api/v1/namespaces/peakguard-p6/services/prometheus:9090/proxy/api/v1/' + path + '?' + urllib.parse.urlencode(params)
    body = json.loads(kube('get', '--raw', url))
    if body.get('status') != 'success':
        raise RuntimeError(f'Prometheus: {body}')
    return body['data']['result']


def parse_time(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()


def wait_until(check, timeout, step=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return True
        time.sleep(step)
    return False


def replicas():
    return json.loads(kube('get', 'deployment', 'documents', '-o', 'json'))['status'].get('readyReplicas', 0)


def backlog_zero():
    result = prom('query', query='sum(documents_backlog)')
    return bool(result) and float(result[0]['value'][1]) == 0


def repetition(index, require_one_replica=True, at_peak=None):
    """Uma execução da carga P6; métricas coletadas em lote (query_range) após a drenagem.
    require_one_replica=False: P17, em que o cron já pré-escalou antes da carga."""
    if require_one_replica and not wait_until(lambda: replicas() == 1, 420):
        raise RuntimeError('HPA não voltou a 1 réplica; repetição abortada.')
    kube('delete', 'job', 'load', '--ignore-not-found=true', '--wait=true')
    before = {p['metadata']['name'] for p in json.loads(kube('get', 'pods', '-l', 'app=documents', '-o', 'json'))['items']}
    start = time.time()
    kube('apply', '-f', str(ROOT / 'local/p6/load.yaml'))
    if at_peak:  # P17B: amostra pontual no pico (ticks 2–10 de 10 s; ~60 s após o início)
        time.sleep(60)
        at_peak()
    kube('wait', '--for=condition=complete', 'job/load', '--timeout=220s', timeout=240)
    if not wait_until(backlog_zero, 180, step=5):
        raise RuntimeError('Backlog não drenou.')
    end = time.time() + 2 * BIN_SECONDS
    time.sleep(2 * BIN_SECONDS)
    pods = json.loads(kube('get', 'pods', '-l', 'app=documents', '-o', 'json'))['items']
    startups = []
    for pod in pods:
        if pod['metadata']['name'] in before:
            continue
        ready = next((c for c in pod['status'].get('conditions', []) if c['type'] == 'Ready' and c['status'] == 'True'), None)
        if ready:
            created = parse_time(pod['metadata']['creationTimestamp'])
            startups.append({'pod': pod['metadata']['name'], 'created_after_load_seconds': created - start,
                             'startup_seconds': parse_time(ready['lastTransitionTime']) - created})
    load_pod = json.loads(kube('get', 'pods', '-l', 'job-name=load', '-o', 'json'))['items'][0]
    load_started = parse_time(load_pod['status']['startTime'])
    logs = [json.loads(line) for line in kube('logs', 'job/load').splitlines() if line.startswith('{')]
    window = {'start': load_started, 'end': end, 'step': '5s'}
    queries = {
        'per_pod_rate': 'rate(documents_processed_total[15s])',
        'per_pod_backlog': 'documents_backlog',
        'throughput': 'sum(rate(documents_processed_total[15s]))',
        'backlog': 'sum(documents_backlog)',
        'ready_targets': 'count(up{job="documents"} == 1)',
    }
    series = {key: prom('query_range', query=expr, **window) for key, expr in queries.items()}
    print(json.dumps({'repetition': index, 'new_pods': len(startups), 'intervals': len(logs)}), flush=True)
    return {'index': index, 'apply_time': start, 'load_start_time': load_started, 'end_time': end,
            'startups': startups, 'load': logs, 'prometheus': series}


def collect(repetitions):
    OUT.mkdir(parents=True, exist_ok=True)
    version = json.loads(subprocess.check_output(CMD[:5] + ['version', '-o', 'json'], text=True, timeout=30))
    runs = [repetition(i) for i in range(repetitions)]
    report = {'labels': {'metrics': 'observed (local Kind cluster)', 'load': 'synthetic', 'cost': 'hypothetical'},
              'kubernetes_server_version': version['serverVersion']['gitVersion'],
              'collected_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'repetitions': runs}
    (OUT / 'observed.json').write_text(json.dumps(report, indent=1) + '\n')


def _bins(values, start, n):
    """Último valor amostrado em cada bin de 10 s a partir de `start` (sem amostra: valor anterior)."""
    out, last = [], 0.0
    for b in range(n):
        inside = [float(v) for t, v in values if start + b * BIN_SECONDS <= t < start + (b + 1) * BIN_SECONDS]
        last = inside[-1] if inside else last
        out.append(last)
    return out


def service_rate(run):
    """Mediana de rate() por pod enquanto aquele pod tem fila (saturado), em doc/s."""
    backlog = {s['metric']['pod']: dict(s['values']) for s in run['prometheus']['per_pod_backlog']}
    saturated = [float(v) for s in run['prometheus']['per_pod_rate'] for t, v in s['values']
                 if float(backlog.get(s['metric']['pod'], {}).get(t, 0)) > 0 and float(v) > 0]
    return statistics.median(saturated), len(saturated)


def observed_trace(run):
    n_load = len(run['load'])
    n = max(n_load, round((run['end_time'] - run['load_start_time']) / BIN_SECONDS))
    series = {k: (run['prometheus'][k][0]['values'] if run['prometheus'][k] else []) for k in ('throughput', 'backlog')}
    arrivals = [i['accepted'] / BIN_SECONDS * 60 for i in run['load']] + [0.0] * (n - n_load)
    return {'arrivals_docs_per_minute': arrivals,
            'throughput_docs_per_second': _bins([(t, v) for t, v in series['throughput']], run['load_start_time'], n),
            'backlog_docs': _bins([(t, v) for t, v in series['backlog']], run['load_start_time'], n)}


def delay(backlog, throughput):
    """Atraso estimado pela Lei de Little (backlog / throughput, s); None se throughput 0."""
    return [b / t if t > 0 else None for b, t in zip(backlog, throughput)]


def simulated_trace(arrivals, params):
    config = Config(tick_minutes=BIN_SECONDS / 60, max_replicas=4, **params)
    run = simulate(Scenario('p13_observed_trace', 0, tuple(arrivals), tuple(arrivals)), 'reactive', config)
    return {'throughput_docs_per_second': [t['throughput_docs_per_minute'] / 60 for t in run['ticks']],
            'backlog_docs': [t['backlog_docs'] for t in run['ticks']]}


def mae(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    return sum(abs(x - y) for x, y in pairs) / len(pairs) if pairs else None


def errors(obs, sim):
    return {'backlog_docs': mae(obs['backlog_docs'], sim['backlog_docs']),
            'throughput_docs_per_second': mae(obs['throughput_docs_per_second'], sim['throughput_docs_per_second']),
            'delay_seconds_little': mae(delay(obs['backlog_docs'], obs['throughput_docs_per_second']),
                                        delay(sim['backlog_docs'], sim['throughput_docs_per_second']))}


def analyze():
    report = json.loads((OUT / 'observed.json').read_text())
    runs = report['repetitions']
    rates = [service_rate(r) for r in runs]
    startups = [s for r in runs for s in r['startups']]
    first_scale = [min(s['created_after_load_seconds'] for s in r['startups']) for r in runs if r['startups']]
    rate = statistics.median(r for r, _ in rates)
    # Atraso de ativação do motor = criação do pod -> Ready (decisão do HPA já é modelada pela política reativa).
    startup = statistics.median(s['startup_seconds'] for s in startups)
    calibrated = {'capacity_docs_per_minute_per_replica': round(rate * 60, 3),
                  'activation_delay_ticks': max(0, round(startup / BIN_SECONDS))}
    rows = []
    for run in runs:
        obs = observed_trace(run)
        rows.append({'repetition': run['index'],
                     'old': errors(obs, simulated_trace(obs['arrivals_docs_per_minute'], OLD)),
                     'calibrated': errors(obs, simulated_trace(obs['arrivals_docs_per_minute'], calibrated))})
    mean = lambda key, metric: statistics.fmean(r[key][metric] for r in rows if r[key][metric] is not None)
    summary = {key: {m: mean(key, m) for m in rows[0]['old']} for key in ('old', 'calibrated')}
    result = {'labels': {'observed': 'observed local Kind cluster', 'simulation': 'estimated', 'load': 'synthetic',
                         'delay': 'estimated via Little (backlog/throughput)', 'cost': 'hypothetical'},
              'kubernetes_server_version': report['kubernetes_server_version'],
              'measurements': {'service_rate_docs_per_second_per_replica': {'median': rate, 'per_repetition': [r for r, _ in rates],
                                                                             'saturated_samples': [n for _, n in rates]},
                               'startup_seconds': {'median': startup, 'min': min(s['startup_seconds'] for s in startups),
                                                   'max': max(s['startup_seconds'] for s in startups), 'pods': len(startups)},
                               'first_scale_after_load_seconds': first_scale},
              'parameters': {'old': OLD, 'calibrated': calibrated, 'tick_seconds': BIN_SECONDS, 'policy': 'reactive', 'max_replicas': 4},
              'mae_per_repetition': rows, 'mae_mean': summary}
    (OUT / 'calibration.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps({'measurements': result['measurements'], 'parameters': result['parameters'], 'mae_mean': summary}, indent=1))


assert mae([1, None, 3], [2, 5, 1]) == 1.5 and delay([10, 5], [2, 0]) == [5, None]
assert _bins([(0, 1), (5, 2), (25, 7)], 0, 3) == [2.0, 2.0, 7.0]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('collect').add_argument('--repetitions', type=int, default=3)
    sub.add_parser('analyze')
    args = parser.parse_args()
    collect(args.repetitions) if args.command == 'collect' else analyze()
