import random

import pytest

from peakguard.scenarios import SCENARIOS, Scenario, load_scenario


@pytest.mark.parametrize("name", ["stable", "predictable_peak", "unexpected_peak", "wrong_forecast"])
def test_seed_reproduces_synthetic_load_without_global_rng_changes(name):
    state = random.getstate()
    scenario = load_scenario(name, 42)
    assert scenario == load_scenario(name, 42)
    assert scenario.demand_docs_per_minute != load_scenario(name, 43).demand_docs_per_minute
    assert len(scenario.demand_docs_per_minute) == 24
    assert random.getstate() == state
    assert name in SCENARIOS


def test_predictions_follow_declared_schedule_not_realized_future():
    predictable = load_scenario("predictable_peak", 42)
    unexpected = load_scenario("unexpected_peak", 42)
    wrong = load_scenario("wrong_forecast", 42)
    assert predictable.predicted_docs_per_minute[8] == 320
    assert unexpected.predicted_docs_per_minute[8] == 40
    assert unexpected.demand_docs_per_minute[8] > 300
    assert wrong.predicted_docs_per_minute[8] == 320
    assert wrong.demand_docs_per_minute[8] < 50
    assert predictable.predicted_docs_per_minute == load_scenario("predictable_peak", 1).predicted_docs_per_minute


@pytest.mark.parametrize("demand,prediction", [([], []), ([1], []), ([-1], [1]), ([1], [float("nan")]), ([float("inf")], [1]), (["40"], [40]), ([True], [40])])
def test_scenario_rejects_invalid_series(demand, prediction):
    with pytest.raises(ValueError):
        Scenario("invalid", 1, tuple(demand), tuple(prediction))


def test_unknown_scenario_has_clear_error():
    with pytest.raises(ValueError, match="cenário"):
        load_scenario("missing", 1)
