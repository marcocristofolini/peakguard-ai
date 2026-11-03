"""P17: HPA reativo × ScaledObject antecipativo (cron do calendário + CPU como piso) no Kind local. Fora do CI.

Uso (na raiz, após `bash local/p6/up.sh` e `bash local/p17/install-keda.sh`):
    python3 local/p17/experiment.py collect --repetitions 3   # aplica HPA/ScaledObject no cluster de demonstração
    python3 local/p17/experiment.py analyze                   # grava evidence/p17/results.json
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

OUT = ROOT / 'evidence/p17'
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


def run(strategy, index):
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
    rep = c.repetition(index, require_one_replica=strategy == 'reactive')
    check_single(strategy)
    pods = json.loads(c.kube('get', 'pods', '-l', 'app=documents', '-o', 'json'))['items']
    created = sorted(c.parse_time(p['metadata']['creationTimestamp']) for p in pods)
    ready = c.prom('query_range', query='count(up{job="documents"} == 1)',
                   start=rep['load_start_time'] - 60, end=rep['end_time'], step='5s')
    rep.update({'strategy': strategy, 'reset_time': reset_time, 'manifest': manifest,
                'pod_created_times': [t for t in created if t > reset_time], 'ready_pods_wide': ready})
    print(json.dumps({'strategy': strategy, 'repetition': index, 'new_pods': len(rep['pod_created_times'])}), flush=True)
    return rep


def collect(repetitions, strategies=('reactive', 'anticipatory')):
    if 'keda' not in {n['metadata']['name'] for n in json.loads(subprocess.check_output(
            c.CMD[:5] + ['get', 'namespaces', '-o', 'json'], text=True, timeout=30))['items']}:
        raise RuntimeError('KEDA não instalado: rode local/p17/install-keda.sh.')
    if 'documents-keda' in names('deployment'):
        raise RuntimeError('Demo documents-keda presente; fora do escopo da P17.')
    previous = json.loads((OUT / 'observed.json').read_text())['runs'] if (OUT / 'observed.json').exists() else []
    runs = [r for r in previous if r['strategy'] not in strategies]  # mantém estratégias já coletadas
    try:
        for strategy in strategies:
            for i in range(repetitions):
                runs.append(run(strategy, i))
                (OUT / 'observed.json').write_text(json.dumps({'runs': runs}, indent=1) + '\n')
    finally:
        # Restaura o estado original: só o HPA no Deployment.
        c.wait_until(c.backlog_zero, 300, step=5)
        remove_controllers()
        apply(HPA)
    version = json.loads(subprocess.check_output(c.CMD[:5] + ['version', '-o', 'json'], text=True, timeout=30))
    report = {'labels': {'metrics': 'observed (local Kind cluster)', 'load': 'synthetic', 'cost': 'hypothetical'},
              'kubernetes_server_version': version['serverVersion']['gitVersion'],
              'collected_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'runs': runs}
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
    summary = {}
    for strategy, policy in (('reactive', 'reactive'), ('anticipatory', 'anticipatory')):
        group = [r for r in rows if r['strategy'] == strategy]
        summary[strategy] = {side: {m: mean([r[side][m] if side == 'observed' else r[side][policy][m] for r in group
                                             if (r[side][m] if side == 'observed' else r[side][policy][m]) is not None])
                                    for m in ('max_backlog_docs', 'first_scale_after_load_seconds', 'replica_minutes',
                                              'cost_brl_hypothetical')}
                             for side in ('observed', 'simulated')}
    windows = [r['manifest']['schedule']['windows'] for r in report['runs'] if r.get('manifest')]
    result = {'labels': {'observed': 'observed local Kind cluster', 'simulation': 'estimated', 'load': 'synthetic',
                         'cost': f'hypothetical (BRL {PRICE}/replica-hour × ready-pod minutes)'},
              'kubernetes_server_version': report.get('kubernetes_server_version'),
              'config': {k: v for k, v in CONFIG.__dict__.items()}, 'cron_windows': windows,
              'per_repetition': rows, 'mean': summary}
    (OUT / 'results.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps(summary, indent=1))


assert replica_minutes([{'values': [[0, '1'], [30, '2'], [60, '2']]}], 0, 60) == 1.5

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    collect_parser = sub.add_parser('collect')
    collect_parser.add_argument('--repetitions', type=int, default=3)
    collect_parser.add_argument('--only', choices=('reactive', 'anticipatory'))
    sub.add_parser('analyze')
    args = parser.parse_args()
    if args.command == 'collect':
        collect(args.repetitions, (args.only,) if args.only else ('reactive', 'anticipatory'))
    else:
        analyze()
