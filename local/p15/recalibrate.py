"""P15: recalibra o atraso de decisão só com evidence/p13/observed.json (sem cluster). Grava evidence/p15/calibration.json.

Regra do atraso (fixada antes de ver o MAE): extra = max(0, round((mediana(1ª escala) - carga baixa inicial - 1 tick) / tick)).
O tick embutido é o atraso que a reativa já tem por usar a demanda do tick anterior.
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'local' / 'p13'))
import calibrate as c  # noqa: E402

OUT = ROOT / 'evidence/p15'


def low_load_seconds(run):
    base = run['load'][0]['target_docs_per_second']
    return next(i['interval'] for i in run['load'] if i['target_docs_per_second'] > base) * c.BIN_SECONDS


def derive_delay(first_scale, low_load, tick=c.BIN_SECONDS):
    """Ticks extras de decisão além do tick embutido na política reativa."""
    return max(0, round((statistics.median(first_scale) - low_load - tick) / tick))


def main():
    runs = json.loads((c.OUT / 'observed.json').read_text())['repetitions']
    calibration = json.loads((c.OUT / 'calibration.json').read_text())
    first_scale = calibration['measurements']['first_scale_after_load_seconds']
    low_load = {low_load_seconds(r) for r in runs}
    assert len(low_load) == 1, low_load
    low_load = low_load.pop()
    derived = derive_delay(first_scale, low_load)
    p13 = calibration['parameters']['calibrated']
    configs = {'old': c.OLD, 'p13': p13, 'p13_derived_delay': {**p13, 'decision_delay_ticks': derived},
               'sensitivity_delay_1': {**p13, 'decision_delay_ticks': 1},
               'sensitivity_delay_2': {**p13, 'decision_delay_ticks': 2}}
    rows = []
    for run in runs:
        obs = c.observed_trace(run)
        rows.append({'repetition': run['index'],
                     **{name: c.errors(obs, c.simulated_trace(obs['arrivals_docs_per_minute'], p)) for name, p in configs.items()}})
    mean = {name: {m: statistics.fmean(r[name][m] for r in rows) for m in rows[0][name]} for name in configs}
    result = {'labels': {'observed': 'observed local Kind cluster (evidence/p13)', 'simulation': 'estimated',
                         'load': 'synthetic', 'cost': 'hypothetical'},
              'derivation': {'first_scale_after_load_seconds': first_scale, 'low_load_seconds': low_load,
                             'decision_after_step_seconds': [s - low_load for s in first_scale],
                             'builtin_tick_seconds': c.BIN_SECONDS, 'derived_extra_decision_delay_ticks': derived,
                             'note': 'sensitivity_* are NOT derived from data; shown only to bound the effect'},
              'parameters': configs, 'mae_per_repetition': rows, 'mae_mean': mean}
    OUT.mkdir(exist_ok=True)
    (OUT / 'calibration.json').write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps({'derivation': result['derivation'], 'mae_mean': mean}, indent=1))


assert derive_delay([32.0, 21.0, 28.0], 20.0) == 0 and derive_delay([52.0, 51.0, 50.0], 20.0) == 2

if __name__ == '__main__':
    main()
