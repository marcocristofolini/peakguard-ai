import json
import math
from dataclasses import replace

import pytest

from peakguard.scenarios import SCENARIOS, Scenario, load_scenario
from peakguard.simulator import Config, compare, simulate


def scenario(demand, prediction=None):
    return Scenario("test", 7, tuple(demand), tuple(demand if prediction is None else prediction))


def fixed(**kwargs):
    return Config(min_replicas=1, max_replicas=1, initial_replicas=1, **kwargs)


def test_cost_uses_replica_hours_and_tick_duration():
    result = simulate(scenario([40, 40]), "reactive", fixed(tick_minutes=30, price_brl_per_replica_hour=6))
    assert result["summary"]["cost_brl"] == pytest.approx(6)
    assert result["summary"]["replica_hours"] == pytest.approx(1)
    assert result["summary"]["processed_docs"] == 2400
    assert result["summary"]["cost_brl_per_1000_docs"] == pytest.approx(2.5)
    assert result["ticks"][0]["throughput_docs_per_minute"] == 40


def test_queue_conserves_documents_and_drains_in_fifo_order():
    result = simulate(scenario([200, 0, 0]), "reactive", fixed(capacity_docs_per_minute_per_replica=100))
    assert [t["backlog_docs"] for t in result["ticks"]] == [100, 0, 0]
    assert [t["processed_docs"] for t in result["ticks"]] == [100, 100, 0]
    assert [t["saturated"] for t in result["ticks"]] == [True, True, False]
    assert result["summary"]["demand_docs"] == 200
    assert result["summary"]["processed_docs"] == 200
    assert result["ticks"][1]["queue_wait_minutes"] >= 1


def test_subminute_intervals_convert_rates_to_document_counts():
    result = simulate(scenario([300, 0]), "reactive", fixed(tick_minutes=0.5))
    assert [t["backlog_docs"] for t in result["ticks"]] == [100, 50]
    assert result["summary"]["processed_docs"] == 100
    assert result["summary"]["demand_docs"] == 150
    assert result["summary"]["cost_brl"] == pytest.approx(0.02)


def test_zero_load_keeps_availability_and_has_no_cost_per_volume():
    result = simulate(scenario([0, 0]), "anticipatory", fixed())
    assert result["summary"]["processed_docs"] == 0
    assert result["summary"]["cost_brl_per_1000_docs"] is None
    assert all(t["active_replicas"] == 1 and t["queue_wait_minutes"] == 0 for t in result["ticks"])
    json.dumps(result, allow_nan=False)


def test_activation_delay_and_billing_include_pending_replicas():
    config = Config(activation_delay_ticks=2, cooldown_ticks=0, forecast_horizon_ticks=3)
    result = simulate(scenario([40, 40, 320, 320], [40, 40, 320, 320]), "anticipatory", config)
    assert [t["active_replicas"] for t in result["ticks"][:3]] == [1, 1, 4]
    assert result["ticks"][0]["pending_replicas"] == 3
    assert result["ticks"][0]["cost_brl"] == pytest.approx(0.08)
    assert result["ticks"][2]["backlog_docs"] == 0


def test_reactive_never_sees_current_or_future_demand():
    config = Config(activation_delay_ticks=0, cooldown_ticks=0)
    result = simulate(scenario([400, 400, 0]), "reactive", config)
    assert result["ticks"][0]["active_replicas"] == 1
    assert result["ticks"][1]["active_replicas"] > 1


def test_cooldown_limits_resize_frequency():
    result = simulate(scenario([40] * 8, [400, 40, 40, 400, 40, 40, 400, 40]), "anticipatory",
                      Config(activation_delay_ticks=0, cooldown_ticks=3, forecast_horizon_ticks=1))
    changes = [t["tick"] for t in result["ticks"] if "scale" in t["events"]]
    assert len(changes) >= 2
    assert all(b - a >= 3 for a, b in zip(changes, changes[1:]))


def test_budget_and_max_replicas_block_unsafe_forecast():
    result = simulate(scenario([10000] * 10), "anticipatory",
                      Config(max_replicas=3, budget_brl=0.4, activation_delay_ticks=0))
    assert all(1 <= t["provisioned_replicas"] <= 2 for t in result["ticks"])
    assert result["summary"]["cost_brl"] <= 0.4 + 1e-12
    assert any("budget_limit" in t["events"] for t in result["ticks"])
    assert any("max_replicas_limit" in t["events"] for t in result["ticks"])
    assert any("slo_unachievable" in t["events"] for t in result["ticks"][1:])


def test_slo_guard_prevents_downscale_when_observed_demand_requires_capacity():
    result = simulate(scenario([300] * 4, [300, 0, 0, 0]), "anticipatory",
                      Config(initial_replicas=4, activation_delay_ticks=0, cooldown_ticks=0, forecast_horizon_ticks=1))
    assert result["ticks"][1]["active_replicas"] >= 3
    assert "slo_guard" in result["ticks"][1]["events"]


def test_fifo_age_reports_slo_violation_even_if_capacity_cannot_drain_queue():
    result = simulate(scenario([1000, 0, 0, 0]), "reactive", fixed(slo_queue_minutes=1))
    assert result["ticks"][2]["queue_wait_minutes"] >= 3
    assert result["summary"]["slo_violation_minutes"] >= 2
    assert result["summary"]["final_backlog_docs"] == 600


@pytest.mark.parametrize("name", SCENARIOS)
def test_comparisons_share_inputs_and_are_fully_reproducible(name):
    workload = load_scenario(name, 42)
    result = compare(workload, Config())
    assert result == compare(workload, Config())
    a, b = result["results"]["reactive"], result["results"]["anticipatory"]
    assert a["input"] == b["input"]
    for run in (a, b):
        summary = run["summary"]
        assert summary["demand_docs"] == pytest.approx(summary["processed_docs"] + summary["final_backlog_docs"])
        assert all(1 <= t["active_replicas"] <= t["provisioned_replicas"] <= 10 for t in run["ticks"])


def test_false_prediction_has_error_and_can_cost_more_than_reactive():
    result = compare(load_scenario("wrong_forecast", 42), Config())["results"]
    assert result["anticipatory"]["summary"]["forecast_mae_docs_per_minute"] > 70
    assert result["anticipatory"]["summary"]["cost_brl"] > result["reactive"]["summary"]["cost_brl"]


def test_predictable_peak_can_reduce_queue_with_same_activation_constraints():
    result = compare(load_scenario("predictable_peak", 42), Config())["results"]
    assert result["anticipatory"]["summary"]["max_backlog_docs"] < result["reactive"]["summary"]["max_backlog_docs"]


@pytest.mark.parametrize("field,value", [
    ("tick_minutes", 0), ("tick_minutes", math.nan),
    ("capacity_docs_per_minute_per_replica", 0), ("price_brl_per_replica_hour", -1),
    ("budget_brl", math.inf), ("min_replicas", 0), ("max_replicas", 0),
    ("initial_replicas", 11), ("activation_delay_ticks", -1),
    ("cooldown_ticks", 1.5), ("forecast_horizon_ticks", 0),
    ("target_utilization", 0), ("target_utilization", 1.1), ("slo_queue_minutes", 0),
    ("base_latency_minutes", -1), ("min_replicas", True),
])
def test_config_rejects_invalid_units_and_limits(field, value):
    with pytest.raises(ValueError):
        replace(Config(), **{field: value})


def test_infeasible_minimum_budget_is_rejected_before_simulation():
    with pytest.raises(ValueError, match="orçamento"):
        simulate(scenario([0] * 60), "reactive", Config(budget_brl=0.01))


def test_unknown_policy_is_rejected():
    with pytest.raises(ValueError, match="política"):
        simulate(scenario([1]), "invalid", Config())


def test_zero_price_needs_no_budget_and_serializes_finitely():
    result = simulate(scenario([100000] * 3), "anticipatory", Config(price_brl_per_replica_hour=0, budget_brl=0))
    assert result["summary"]["cost_brl"] == 0
    json.dumps(result, allow_nan=False)


def test_pending_replicas_can_be_cancelled_without_breaking_minimum_availability():
    result = simulate(scenario([0] * 4, [800, 0, 0, 0]), "anticipatory",
                      Config(min_replicas=2, initial_replicas=2, activation_delay_ticks=3,
                             cooldown_ticks=0, forecast_horizon_ticks=1))
    assert result["ticks"][0]["pending_replicas"] == 8
    assert result["ticks"][1]["pending_replicas"] == 0
    assert all(t["active_replicas"] == 2 for t in result["ticks"])
    assert result["summary"]["cost_brl"] == pytest.approx(0.32)


def test_replicas_pending_beyond_end_are_billed_but_supply_no_capacity():
    result = simulate(scenario([400]), "anticipatory", Config(activation_delay_ticks=5))
    assert result["ticks"][0]["active_replicas"] == 1
    assert result["ticks"][0]["pending_replicas"] == 4
    assert result["summary"]["cost_brl"] == pytest.approx(0.1)
    assert result["summary"]["final_backlog_docs"] == 300


@pytest.mark.parametrize("config,workload", [
    (Config(tick_minutes=1e308, price_brl_per_replica_hour=0), scenario([100])),
    (Config(capacity_docs_per_minute_per_replica=1e-320), scenario([100])),
    (Config(tick_minutes=1e-320, capacity_docs_per_minute_per_replica=1e-320), scenario([0])),
])
def test_arithmetic_overflow_and_underflow_are_rejected(config, workload):
    with pytest.raises(ValueError, match="numéric"):
        simulate(workload, "anticipatory", config)
