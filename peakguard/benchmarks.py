"""Benchmark sintético fixo: python3 -m peakguard.benchmarks --output benchmarks/results."""

import argparse
import hashlib
import json
import math
from dataclasses import asdict, replace
from importlib.resources import files
from pathlib import Path

from .scenarios import SCENARIOS, Scenario, load_scenario
from .simulator import Config, compare

SEEDS = (7, 42, 101)
FORECAST_MULTIPLIERS = (0.5, 1.0, 1.5)
PRICES = (0.6, 1.2, 2.4)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def benchmark() -> dict:
    rows = []
    for name in SCENARIOS:
        for seed in SEEDS:
            source = load_scenario(name, seed)
            for factor in FORECAST_MULTIPLIERS:
                scenario = Scenario(name, seed, source.demand_docs_per_minute,
                                    tuple(v * factor for v in source.predicted_docs_per_minute))
                for price in PRICES:
                    config = replace(Config(), price_brl_per_replica_hour=price)
                    row = {'scenario': name, 'seed': seed, 'forecast_multiplier': factor,
                           'config': asdict(config), 'demand_sha256': _digest(scenario.demand_docs_per_minute),
                           'input': {'demand_docs_per_minute': list(scenario.demand_docs_per_minute),
                                     'predicted_docs_per_minute': list(scenario.predicted_docs_per_minute)}}
                    try:
                        results = compare(scenario, config)['results']
                        a, b = results['reactive'], results['anticipatory']
                        if a['input'] != b['input'] or a['config'] != b['config']:
                            raise ValueError('Condições distintas entre políticas')
                        metrics = {}
                        for policy, run in results.items():
                            summary = dict(run['summary'])
                            summary['throughput_docs_per_minute'] = summary['processed_docs'] / summary['duration_minutes']
                            summary['mean_backlog_docs'] = math.fsum(t['backlog_docs'] for t in run['ticks']) / len(run['ticks'])
                            summary['max_queue_wait_minutes'] = max(t['queue_wait_minutes'] for t in run['ticks'])
                            summary['failures'] = []
                            if summary['slo_violation_minutes'] > 0:
                                summary['failures'].append('slo')
                            if summary['final_backlog_docs'] > 0:
                                summary['failures'].append('residual_backlog')
                            metrics[policy] = summary
                        row.update(status='ok', results=metrics,
                                   delta_anticipatory_minus_reactive={key: metrics['anticipatory'][key] - metrics['reactive'][key]
                                       for key in ('cost_brl', 'slo_violation_minutes', 'max_backlog_docs',
                                                   'saturated_minutes', 'throughput_docs_per_minute')})
                    except (ValueError, ArithmeticError) as error:
                        row.update(status='error', error={'type': type(error).__name__, 'message': str(error)})
                    rows.append(row)
    return {'schema_version': 1, 'labels': {'inputs': 'synthetic', 'forecast': 'predicted', 'results': 'estimated', 'observed': []},
            'design': {'scenarios': list(SCENARIOS), 'seeds': list(SEEDS),
                       'forecast_multipliers': list(FORECAST_MULTIPLIERS), 'prices_brl_per_replica_hour': list(PRICES),
                       'base_config': asdict(Config()),
                       'fixture_sha256': {name: hashlib.sha256(files('peakguard').joinpath(f'fixtures/{name}.json').read_bytes()).hexdigest() for name in SCENARIOS}},
            'failed_experiments': sum(r['status'] == 'error' for r in rows), 'experiments': rows}


def nominal_summary(report):
    """Médias de todas as seeds no ponto nominal, explicitamente separado da matriz."""
    groups = []
    for name in report['design']['scenarios']:
        rows = [r for r in report['experiments'] if r['scenario'] == name and
                r['forecast_multiplier'] == 1 and r['config']['price_brl_per_replica_hour'] == 1.2]
        for policy in ('reactive', 'anticipatory'):
            good = [r for r in rows if r['status'] == 'ok']
            metrics = {k: math.fsum(r['results'][policy][k] for r in good) / len(good)
                       for k in ('cost_brl', 'slo_violation_minutes', 'max_backlog_docs')} if good else None
            groups.append({'scenario': name, 'policy': policy, 'completed': len(good), 'expected': len(rows), 'means': metrics})
    return groups


def export(report: dict, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    lines = ['# Comparação sintética P5', '',
             'Matriz completa; delta = antecipativa − reativa. Custos estimados em BRL; não são medições produtivas.', '',
             '| Cenário | Seed | Previsão × | BRL/réplica-h | Política | Throughput doc/min | Backlog máx. doc | Saturação min | Custo BRL | BRL/1.000 doc | SLO min | Falhas |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for row in report['experiments']:
        prefix = f"| {row['scenario']} | {row['seed']} | {row['forecast_multiplier']} | {row['config']['price_brl_per_replica_hour']}"
        if row['status'] != 'ok':
            lines.append(prefix + ' | ERRO | — | — | — | — | — | — | experimento incompleto |')
            continue
        for policy, m in row['results'].items():
            cost_per_volume = '—' if m['cost_brl_per_1000_docs'] is None else f"{m['cost_brl_per_1000_docs']:.6f}"
            lines.append(prefix + f" | {policy} | {m['throughput_docs_per_minute']:.4f} | {m['max_backlog_docs']:.4f} | {m['saturated_minutes']:.4f} | {m['cost_brl']:.6f} | {cost_per_volume} | {m['slo_violation_minutes']:.4f} | {', '.join(m['failures']) or 'nenhuma'} |")
    (output / 'comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    groups = nominal_summary(report)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="650" viewBox="0 0 1000 650" role="img" aria-label="Comparação nominal sintética de custos e SLO">',
           '<rect width="1000" height="650" fill="white"/>',
           '<g font-family="sans-serif" fill="#182c3b"><text x="30" y="30" font-size="20">P5 — médias das três seeds, previsão ×1 e preço 1,2 BRL/réplica-h</text>',
           '<text x="30" y="55">Dados sintéticos; valores estimados. Matriz completa: report.json e comparison.md.</text>',
           '<text x="30" y="80" fill="#3559b5">■ Reativa</text><text x="160" y="80" fill="#16775c">■ Antecipativa</text>']
    for panel, (key, title) in enumerate((('cost_brl', 'Custo estimado (BRL)'), ('slo_violation_minutes', 'Violação de SLO (minutos)'))):
        top = 120 + panel * 260
        maximum = max([g['means'][key] for g in groups if g['means']] + [1])
        svg.append(f'<text x="30" y="{top}">{title} — eixo inicia em zero</text>')
        for i, name in enumerate(report['design']['scenarios']):
            x = 70 + i * 240
            svg.append(f'<text x="{x-25}" y="{top+205}" font-size="12">{name}</text>')
            for j, policy in enumerate(('reactive', 'anticipatory')):
                g = next(g for g in groups if g['scenario'] == name and g['policy'] == policy)
                if g['completed'] != g['expected'] or g['means'] is None:
                    svg.append(f'<text x="{x}" y="{top+80}">INCOMPLETO</text>')
                    continue
                value = g['means'][key]
                height = value / maximum * 140
                barx = x + j * 70
                color = '#3559b5' if j == 0 else '#16775c'
                svg.append(f'<rect x="{barx}" y="{top+180-height:.2f}" width="48" height="{height:.2f}" fill="{color}"/><text x="{barx}" y="{top+170-height:.2f}" font-size="12">{value:.3f}</text>')
    svg.append('</g></svg>')
    (output / 'comparison.svg').write_text('\n'.join(svg) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('benchmarks/results'))
    args = parser.parse_args()
    report = benchmark()
    export(report, args.output)
    print(json.dumps({'experiments': len(report['experiments']), 'errors': report['failed_experiments'],
                      'nominal_means': nominal_summary(report)}, indent=2))
    if report['failed_experiments']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
