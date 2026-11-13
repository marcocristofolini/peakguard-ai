"""P20: hipótese "filas por pod". Reanalisa evidence/p13/observed.json (sem cluster).

O motor usa uma fila FIFO central drenada por todas as réplicas ativas. No cluster, cada pod tem a própria fila.
Aqui o mesmo calendário de réplicas do motor (política reativa, parâmetros calibrados da P13) alimenta duas
variantes por pod e compara o MAE do backlog contra o observado:
  even:   chegadas divididas igualmente entre os pods ativos; pods novos entram com fila vazia.
  sticky: chegadas só nos pods que já estavam ativos no início (limite superior do efeito de pods novos ficarem ociosos).
Fora do CI. Uso (na raiz): python3 local/p20/perpod.py
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'local' / 'p13'))
import calibrate as c  # noqa: E402
from peakguard.scenarios import Scenario  # noqa: E402
from peakguard.simulator import Config, simulate  # noqa: E402

OUT = ROOT / 'evidence/p20'
PARAMS = {'capacity_docs_per_minute_per_replica': 294.0, 'activation_delay_ticks': 1}  # calibrados na P13


def per_pod_backlog(arrivals, active, capacity_per_tick, mode):
    """Backlog total por tick com uma fila por pod. `active[i]` = réplicas ativas no tick i; arrivals em docs/tick."""
    queues, out = [], []
    for tick, (docs, n) in enumerate(zip(arrivals, active)):
        while len(queues) < n:
            queues.append(0.0)  # pod novo: fila vazia
        del queues[n:]  # redução: o pod removido leva a fila embora (aproximação; só ocorre após a drenagem)
        receivers = queues if mode == 'even' else queues[:max(1, min(n, active[0]))]
        share = docs / len(receivers)
        for i in range(len(receivers)):
            queues[i] += share
        for i in range(len(queues)):
            queues[i] -= min(queues[i], capacity_per_tick)
        out.append(sum(queues))
    return out


def observed_pod_share(run, obs):
    """No tick de maior backlog observado: fração do backlog total no pod mais carregado e nº de pods com fila."""
    n = len(obs['backlog_docs'])
    pods = [c._bins(s['values'], run['load_start_time'], n) for s in run['prometheus']['per_pod_backlog']]
    peak = max(range(n), key=lambda i: obs['backlog_docs'][i])
    values = [p[peak] for p in pods]
    total = sum(values)
    return {'peak_tick': peak, 'pods_with_queue': sum(v > 0 for v in values),
            'busiest_pod_share': max(values) / total if total else None}


def compute():
    report = json.loads((c.OUT / 'observed.json').read_text())
    config = Config(tick_minutes=c.BIN_SECONDS / 60, max_replicas=4, **PARAMS)
    rows = []
    for run in report['repetitions']:
        obs = c.observed_trace(run)
        arrivals = obs['arrivals_docs_per_minute']
        sim = simulate(Scenario('p20_observed_trace', 0, tuple(arrivals), tuple(arrivals)), 'reactive', config)
        active = [t['active_replicas'] for t in sim['ticks']]
        docs = [a * config.tick_minutes for a in arrivals]
        cap = config.capacity_docs_per_minute_per_replica * config.tick_minutes
        row = {'repetition': run['index'], 'central': c.mae(obs['backlog_docs'], [t['backlog_docs'] for t in sim['ticks']]),
               'observed_peak_backlog_docs': max(obs['backlog_docs']), 'observed_pods': observed_pod_share(run, obs)}
        for mode in ('even', 'sticky'):
            series = per_pod_backlog(docs, active, cap, mode)
            row[mode] = c.mae(obs['backlog_docs'], series)
            row[f'{mode}_peak_backlog_docs'] = max(series)
        row['central_peak_backlog_docs'] = max(t['backlog_docs'] for t in sim['ticks'])
        rows.append(row)
    mean = {k: statistics.fmean(r[k] for r in rows) for k in ('central', 'even', 'sticky')}
    result = {'labels': {'observed': 'observed local Kind cluster (evidence/p13)', 'simulation': 'estimated', 'load': 'synthetic'},
              'parameters': {**PARAMS, 'tick_seconds': c.BIN_SECONDS, 'policy': 'reactive', 'max_replicas': 4},
              'mae_backlog_docs_mean': mean, 'per_repetition': rows}
    return result


def analyze():
    result = compute()
    mean, rows = result['mae_backlog_docs_mean'], result['per_repetition']
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'results.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps({'mae_mean': mean, 'rows': [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]}, indent=1))


if __name__ == '__main__':
    analyze()
