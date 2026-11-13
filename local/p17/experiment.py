"""P17: HPA reativo × ScaledObject antecipativo (cron do calendário + CPU como piso) no Kind local. Fora do CI.

Uso (na raiz, após `bash local/p6/up.sh` e `bash local/p17/install-keda.sh`):
    python3 local/p17/experiment.py collect --repetitions 3   # aplica HPA/ScaledObject no cluster de demonstração
    python3 local/p17/experiment.py analyze                   # grava evidence/p17/results.json
P17B (intercalada, com carga do host): collect --order interleaved --repetitions 5 --output evidence/p17b
Nunca deixa HPA `documents` e ScaledObject `documents` ao mesmo tempo; ao final restaura o HPA original.
"""
import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'local' / 'p13'))
import calibrate as c  # noqa: E402
from peakguard.explanations import explain  # noqa: E402
from peakguard.manifest import manifest_diff  # noqa: E402
from peakguard.scenarios import Scenario  # noqa: E402
from peakguard.simulator import Config, compare  # noqa: E402

OUT = ROOT / 'evidence/p17'  # sobrescrito por --output
STRATEGIES = ('reactive', 'anticipatory')
LOAD_LIMIT = 2.0  # loadavg de 1 min antes da carga acima disso marca a repetição como carregada
# Calendário declarado = curva nominal da carga P6 (13 ticks de 10 s; pico de 12 doc/s nos ticks 2–10).
RATES = tuple((12 if 2 <= i < 11 else 1) * 60 for i in range(13))
# Config P13 (294 doc/min, startup 1 tick) com alvo de 70% igual ao HPA do cluster.
CONFIG = Config(tick_minutes=c.BIN_SECONDS / 60, capacity_docs_per_minute_per_replica=294, max_replicas=4,
                target_utilization=0.7, activation_delay_ticks=1)
HPA = next(d for d in yaml.safe_load_all((ROOT / 'local/p6/resources.yaml').read_text())
           if d['kind'] == 'HorizontalPodAutoscaler')
PRICE = 1.2  # BRL/réplica-hora, hipotético


def apply(document):
    subprocess.run(c.CMD + ['apply', '-f', '-'], input=yaml.safe_dump(document), text=True, check=True,
                   capture_output=True, timeout=60)


def names(resource):
    return {i['metadata']['name'] for i in json.loads(c.kube('get', resource, '-o', 'json'))['items']}


def check_single(strategy):
    """Exatamente um controlador no Deployment `documents`."""
    hpas, sos = names('hpa'), names('scaledobject')
    expected = ({'documents'}, set()) if strategy == 'reactive' else ({'keda-hpa-documents'}, {'documents'})
    if (hpas, sos) != expected:
        raise RuntimeError(f'Controladores inesperados: hpa={hpas} scaledobject={sos}')


def remove_controllers():
    c.kube('delete', 'scaledobject', 'documents', '--ignore-not-found=true', '--wait=true')
    c.kube('delete', 'hpa', 'documents', '--ignore-not-found=true', '--wait=true')
    if not c.wait_until(lambda: not names('hpa'), 120, step=5):
        raise RuntimeError('HPA do KEDA não foi removido.')


def reset_to_one():
    """Sem controlador: drena, volta a 1 réplica e espera estabilizar."""
    if not c.wait_until(c.backlog_zero, 300, step=5):
        raise RuntimeError('Backlog não drenou antes do reset.')
    remove_controllers()
    c.kube('scale', 'deployment', 'documents', '--replicas=1')
    if not c.wait_until(lambda: c.replicas() == 1 and len(json.loads(c.kube('get', 'pods', '-l', 'app=documents', '-o', 'json'))['items']) == 1, 180, step=5):
        raise RuntimeError('Deployment não voltou a 1 pod.')


def scaled_object(anchor):
    comparison = compare(Scenario('p6_controlled_peak', 0, RATES, RATES), CONFIG)
    return manifest_diff(explain(comparison), comparison, kind='scaledobject', name='documents',
                         namespace='peakguard-p6', schedule_start=anchor)


def schedule(repetitions, order, strategies=STRATEGIES):
    """Ordem das execuções: em blocos (R,R,R,A,A,A) ou intercalada (R,A,R,A,...)."""
    if order == 'interleaved':
        return [(s, i) for i in range(repetitions) for s in strategies]
    return [(s, i) for s in strategies for i in range(repetitions)]


def loaded(run, limit=LOAD_LIMIT):
    """Repetição com loadavg de 1 min antes da carga acima do limite. Sem registro (P17): não marcada."""
    return run.get('host', {}).get('loadavg_before', {}).get('1m', 0) > limit


def loadavg():
    one, five = Path('/proc/loadavg').read_text().split()[:2]
    return {'1m': float(one), '5m': float(five)}


def node_stats():
    """Amostra pontual do nó do Kind (sem processo em segundo plano)."""
    out = subprocess.check_output(['docker', 'stats', '--no-stream', '--format', '{{json .}}',
                                   'peakguard-p6-control-plane'], text=True, timeout=60)
    s = json.loads(out)
    return {'cpu_percent': float(s['CPUPerc'].rstrip('%')), 'memory': s['MemUsage']}


CURVES = {'nominal': 'local/p6/load.yaml', 'shifted': 'local/p17/load-shifted.yaml'}  # shifted: pico real nos ticks 6–14, calendário declarado 2–10


def run(strategy, index, curve='nominal'):
    reset_to_one()
    reset_time = time.time()
    manifest = None
    if strategy == 'reactive':
        apply(HPA)
        time.sleep(30)  # HPA lê CPU ociosa antes da carga
    else:
        now = datetime.now(timezone.utc)
        boundary = (now + timedelta(seconds=40)).replace(second=0, microsecond=0) + timedelta(minutes=1)
        anchor = boundary + timedelta(seconds=40)  # janela cron começa no minuto `boundary`, 40 s antes da carga
        manifest = scaled_object(anchor)
        apply(yaml.safe_load(manifest['proposed_manifest']))
        time.sleep(max(0, anchor.timestamp() - time.time()))
    check_single(strategy)
    host = {'loadavg_before': loadavg()}
    rep = c.repetition(index, require_one_replica=strategy == 'reactive', load_file=CURVES[curve],
                       at_peak=lambda: host.update(node_at_peak=node_stats()))
    host['loadavg_after'] = loadavg()
    check_single(strategy)
    pods = json.loads(c.kube('get', 'pods', '-l', 'app=documents', '-o', 'json'))['items']
    created = sorted(c.parse_time(p['metadata']['creationTimestamp']) for p in pods)
    ready = c.prom('query_range', query='count(up{job="documents"} == 1)',
                   start=rep['load_start_time'] - 60, end=rep['end_time'], step='5s')
    rep.update({'strategy': strategy, 'curve': curve, 'host': host, 'reset_time': reset_time, 'manifest': manifest,
                'pod_created_times': [t for t in created if t > reset_time], 'ready_pods_wide': ready})
    print(json.dumps({'strategy': strategy, 'repetition': index, 'new_pods': len(rep['pod_created_times'])}), flush=True)
    return rep


def collect(repetitions, strategies=STRATEGIES, order='blocks', curve='nominal'):
    OUT.mkdir(parents=True, exist_ok=True)
    if 'keda' not in {n['metadata']['name'] for n in json.loads(subprocess.check_output(
            c.CMD[:5] + ['get', 'namespaces', '-o', 'json'], text=True, timeout=30))['items']}:
        raise RuntimeError('KEDA não instalado: rode local/p17/install-keda.sh.')
    if 'documents-keda' in names('deployment'):
        raise RuntimeError('Demo documents-keda presente; fora do escopo da P17.')
    previous = json.loads((OUT / 'observed.json').read_text())['runs'] if (OUT / 'observed.json').exists() else []
    runs = [r for r in previous if r['strategy'] not in strategies]  # mantém estratégias já coletadas
    try:
        for strategy, i in schedule(repetitions, order, strategies):
            runs.append(run(strategy, i, curve))
            (OUT / 'observed.json').write_text(json.dumps({'runs': runs}, indent=1) + '\n')
    finally:
        # Restaura o estado original: só o HPA no Deployment.
        c.wait_until(c.backlog_zero, 300, step=5)
        remove_controllers()
        apply(HPA)
    version = json.loads(subprocess.check_output(c.CMD[:5] + ['version', '-o', 'json'], text=True, timeout=30))
    report = {'labels': {'metrics': 'observed (local Kind cluster)', 'load': 'synthetic', 'cost': 'hypothetical'},
              'kubernetes_server_version': version['serverVersion']['gitVersion'],
              'collected_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'order': order, 'curve': curve, 'runs': runs}
    (OUT / 'observed.json').write_text(json.dumps(report, indent=1) + '\n')


def replica_minutes(series, start, end):
    """Integração por retângulos à esquerda de pods prontos (amostras de 5 s) em [start, end]."""
    values = [(float(t), float(v)) for t, v in (series[0]['values'] if series else []) if start <= float(t) <= end]
    return sum(v * (b[0] - a) for (a, v), b in zip(values, values[1:])) / 60


def observed_metrics(run):
    start, end = run['load_start_time'] - 60, run['end_time']
    backlog = [float(v) for _, v in (run['prometheus']['backlog'][0]['values'] if run['prometheus']['backlog'] else [])]
    first = run['pod_created_times'][0] - run['load_start_time'] if run['pod_created_times'] else None
    rm = replica_minutes(run['ready_pods_wide'], start, end)
    return {'max_backlog_docs': max(backlog, default=0.0), 'first_scale_after_load_seconds': first,
            'replica_minutes': rm, 'cost_brl_hypothetical': rm / 60 * PRICE,
            'window_seconds': end - start}


def simulated_metrics(run):
    """Mesmo trace (admissões observadas), calendário nominal como previsão, janela iniciando 60 s antes."""
    arrivals = c.observed_trace(run)['arrivals_docs_per_minute']
    lead = 60 // c.BIN_SECONDS
    demand = [0.0] * lead + arrivals
    predicted = [0.0] * lead + list(RATES) + [0.0] * (len(arrivals) - len(RATES))
    result = compare(Scenario('p17_observed_trace', 0, tuple(demand), tuple(predicted)), CONFIG)['results']
    out = {}
    for policy, sim in result.items():
        ticks = sim['ticks']
        scale = next((t['tick'] for t in ticks if t['provisioned_replicas'] > 1), None)
        rm = sum(t['active_replicas'] for t in ticks) * CONFIG.tick_minutes
        out[policy] = {'max_backlog_docs': sim['summary']['max_backlog_docs'],
                       'first_scale_after_load_seconds': None if scale is None else (scale - lead) * c.BIN_SECONDS,
                       'replica_minutes': rm, 'cost_brl_hypothetical': rm / 60 * PRICE}
    return out


def analyze():
    report = json.loads((OUT / 'observed.json').read_text())
    rows = [{'strategy': r['strategy'], 'repetition': r['index'], 'observed': observed_metrics(r),
             'simulated': simulated_metrics(r)} for r in report['runs']]
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    metrics = ('max_backlog_docs', 'first_scale_after_load_seconds', 'replica_minutes', 'cost_brl_hypothetical')

    def values(group, side, policy, m):
        return [v for r in group if (v := r[side][m] if side == 'observed' else r[side][policy][m]) is not None]

    def table(group, fn):
        return {strategy: {side: {m: fn(values([r for r in group if r['strategy'] == strategy], side, strategy, m))
                                  for m in metrics} for side in ('observed', 'simulated')} for strategy in STRATEGIES}
    flagged = [{'strategy': r['strategy'], 'repetition': r['index'], 'loadavg_1m_before': r['host']['loadavg_before']['1m']}
               for r in report['runs'] if loaded(r)]
    clean = [row for row, r in zip(rows, report['runs']) if not loaded(r)]
    summary = table(rows, mean)
    spread = {'min': table(rows, lambda xs: min(xs, default=None)), 'max': table(rows, lambda xs: max(xs, default=None))}
    without_loaded = table(clean, mean)
    windows = [r['manifest']['schedule']['windows'] for r in report['runs'] if r.get('manifest')]
    result = {'labels': {'observed': 'observed local Kind cluster', 'simulation': 'estimated', 'load': 'synthetic',
                         'cost': f'hypothetical (BRL {PRICE}/replica-hour × ready-pod minutes)'},
              'kubernetes_server_version': report.get('kubernetes_server_version'),
              'config': {k: v for k, v in CONFIG.__dict__.items()}, 'cron_windows': windows,
              'order': report.get('order', 'blocks'), 'curve': report.get('curve', 'nominal'), 'load_limit_loadavg_1m': LOAD_LIMIT,
              'loaded_repetitions': flagged, 'per_repetition': rows, 'mean': summary, 'spread': spread,
              'mean_excluding_loaded': without_loaded}
    (OUT / 'results.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps(summary, indent=1))


assert replica_minutes([{'values': [[0, '1'], [30, '2'], [60, '2']]}], 0, 60) == 1.5

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    collect_parser = sub.add_parser('collect')
    collect_parser.add_argument('--repetitions', type=int, default=3)
    collect_parser.add_argument('--only', choices=STRATEGIES)
    collect_parser.add_argument('--order', choices=('blocks', 'interleaved'), default='blocks')
    collect_parser.add_argument('--curve', choices=tuple(CURVES), default='nominal',
                                help='shifted = previsão errada: pico real atrasado em 4 ticks em relação ao calendário')
    analyze_parser = sub.add_parser('analyze')
    for sp in (collect_parser, analyze_parser):
        sp.add_argument('--output', type=Path, default=OUT, help='diretório das evidências (padrão evidence/p17)')
    args = parser.parse_args()
    OUT = args.output
    if args.command == 'collect':
        collect(args.repetitions, (args.only,) if args.only else STRATEGIES, args.order, args.curve)
    else:
        analyze()
