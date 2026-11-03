import json
from dataclasses import replace

import pytest

from peakguard.scenarios import SCENARIOS, Scenario, load_scenario
from peakguard.simulator import Config, simulate

SPIKE = Scenario("spike", 1, (50,) * 4 + (400,) * 6 + (50,) * 8, (50,) * 18)
CONFIG = Config(max_replicas=8, budget_brl=100)


def run(policy, delay, scenario=SPIKE):
    return simulate(scenario, policy, replace(CONFIG, decision_delay_ticks=delay))


def test_default_is_zero_and_preserves_engine():
    assert Config().decision_delay_ticks == 0
    # Igualdade com o motor anterior é provada por test_benchmarks (resultados commitados) e test_p14.
    for name in SCENARIOS:
        scenario = load_scenario(name)
        for policy in ("reactive", "anticipatory"):
            base = simulate(scenario, policy, Config())
            assert base["config"]["decision_delay_ticks"] == 0
            assert base["ticks"] == simulate(scenario, policy, Config(decision_delay_ticks=0))["ticks"]


def test_delay_never_lowers_max_backlog_on_spike():
    peaks = [run("reactive", d)["summary"]["max_backlog_docs"] for d in range(5)]
    assert peaks == sorted(peaks)
    assert peaks[-1] > peaks[0]


def test_reactive_decides_with_delayed_metrics():
    first = lambda d: next(t["tick"] for t in run("reactive", d)["ticks"] if "scale" in t["events"])
    assert first(2) == first(0) + 2


def test_anticipatory_unaffected():
    assert run("anticipatory", 3)["ticks"] == run("anticipatory", 0)["ticks"]


@pytest.mark.parametrize("bad", [-1, 1.5, True, float("nan")])
def test_validation(bad):
    with pytest.raises(ValueError):
        Config(decision_delay_ticks=bad)


def test_committed_recalibration_is_reproducible():
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "local" / "p15"))
    import recalibrate
    committed = json.loads((root / "evidence/p15/calibration.json").read_text())
    runs = json.loads((root / "evidence/p13/observed.json").read_text())["repetitions"]
    assert committed["derivation"]["low_load_seconds"] == recalibrate.low_load_seconds(runs[0])
    assert committed["derivation"]["derived_extra_decision_delay_ticks"] == recalibrate.derive_delay(
        committed["derivation"]["first_scale_after_load_seconds"], committed["derivation"]["low_load_seconds"])
