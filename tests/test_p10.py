import pytest
from fastapi.testclient import TestClient

from peakguard.api import app
from peakguard.budget import (BURN_WINDOWS, Slo, budget_report, cost_per_budget_minute, empirical_quantile,
                              error_budget, forecast_error)
from peakguard.scenarios import load_scenario
from peakguard.simulator import Config, compare, simulate


def fake_run(bad, policy="reactive", cost=1.0, demand=None, predicted=None):
    n = len(bad)
    return {"policy": policy, "config": {"tick_minutes": 1}, "summary": {"cost_brl": cost},
            "ticks": [{"slo_violated": bool(b)} for b in bad],
            "input": {"demand_docs_per_minute": demand or [100] * n, "predicted_docs_per_minute": predicted or [100] * n}}


def test_budget_consumption():
    r = error_budget(fake_run([0] * 90 + [1] * 5 + [0] * 5), Slo(target=0.95))
    assert r["budget_minutes"] == pytest.approx(5) and r["consumed_minutes"] == 5
    assert r["consumed_fraction"] == pytest.approx(1) and r["exhausted"] is False
    assert error_budget(fake_run([1] * 6 + [0] * 94), Slo(target=0.95))["exhausted"] is True
    assert error_budget(fake_run([1, 0, 0, 0]), Slo(target=0.5, window_minutes=2))["consumed_minutes"] == 0  # só os 2 últimos
    for kwargs in ({"target": 1.0}, {"target": 0}, {"window_minutes": 0}):
        with pytest.raises(ValueError):
            Slo(**kwargs)
    with pytest.raises(ValueError):
        error_budget(fake_run([0, 0]), Slo(window_minutes=5))


def test_burn_rate_multiwindow_alerts():
    assert (BURN_WINDOWS["fast"]["long_ticks"], BURN_WINDOWS["fast"]["short_ticks"]) == (12, 1)
    assert (BURN_WINDOWS["slow"]["long_ticks"], BURN_WINDOWS["slow"]["short_ticks"]) == (72, 6)
    burn = error_budget(fake_run([0] * 10 + [1] * 3 + [0] * 20))["burn_rate"]
    # longa 12: 2 ticks ruins = 16,7% / 1% = 16,7 >= 14,4 e curta ruim -> dispara no 2º tick ruim (índice 11)
    assert burn["fast"]["first_alert_tick"] == 11
    assert error_budget(fake_run([0] * 30))["burn_rate"]["fast"]["first_alert_tick"] is None
    # um tick ruim isolado: 8,3 < 14,4, não dispara
    assert error_budget(fake_run([0] * 5 + [1] + [0] * 20))["burn_rate"]["fast"]["first_alert_tick"] is None
    # queima sustentada por 6 ticks: lenta (6h/30m) dispara quando longa 6/72 >= 6%
    slow = error_budget(fake_run([0] * 80 + [1] * 8 + [0] * 12))["burn_rate"]["slow"]
    assert slow["first_alert_tick"] is not None and slow["threshold"] == 6.0


def test_cost_per_budget_minute_and_zero_denominator():
    base = fake_run([1, 1, 1, 0] * 5, cost=1.0)
    safe = fake_run([1, 0, 0, 0] * 5, policy="anticipatory", cost=1.5)
    r = cost_per_budget_minute(safe, base)
    assert r["status"] == "ok" and r["preserved_minutes"] == 10 and r["value"] == pytest.approx(0.05)
    same = cost_per_budget_minute(fake_run([1, 1, 1, 0] * 5, cost=2.0), base)
    assert same["value"] is None and same["status"] == "no_budget_preserved"
    worse = cost_per_budget_minute(fake_run([1] * 20, cost=2.0), base)
    assert worse["value"] is None


def test_forecast_error():
    r = forecast_error(fake_run([0] * 3, demand=[100, 0, 200], predicted=[80, 10, 220]))
    assert r["mae_docs_per_minute"] == pytest.approx(50 / 3)
    assert r["mape_percent"] == pytest.approx((0.2 + 0.1) / 2 * 100) and r["mape_ticks_skipped_zero_demand"] == 1
    assert forecast_error(fake_run([0], demand=[0], predicted=[5]))["mape_percent"] is None


def test_empirical_quantile():
    xs = [5, 1, 3, 2, 4, 6, 7, 8, 9, 10]
    assert [empirical_quantile(xs, p) for p in (0.5, 0.8, 0.9)] == [5, 8, 9]
    for bad in (0, 1):
        with pytest.raises(ValueError):
            empirical_quantile(xs, bad)
    with pytest.raises(ValueError):
        empirical_quantile([], 0.5)


def test_risk_appetite_default_unchanged_and_validated():
    s = load_scenario("unexpected_peak", 1)
    a, b = simulate(s, "anticipatory", Config()), simulate(s, "anticipatory", Config(), risk_appetite=None)
    assert a == b and a["risk_appetite"] is None
    assert simulate(s, "reactive", Config(), risk_appetite=0.9)["ticks"] == simulate(s, "reactive", Config())["ticks"]
    for bad in (0, 1, -0.1, 1.5, True):
        with pytest.raises(ValueError):
            simulate(s, "anticipatory", Config(), risk_appetite=bad)


def test_higher_percentile_costs_more_and_burns_less_budget():
    s, c = load_scenario("unexpected_peak", 1, "burst"), Config(activation_delay_ticks=3)
    p50, p90 = (simulate(s, "anticipatory", c, risk_appetite=p) for p in (0.5, 0.9))
    assert p90["summary"]["cost_brl"] > p50["summary"]["cost_brl"]
    assert error_budget(p90)["consumed_minutes"] < error_budget(p50)["consumed_minutes"]
    cost = cost_per_budget_minute(p90, p50)
    assert cost["status"] == "ok" and cost["value"] > 0


@pytest.mark.parametrize("p", [0.5, 0.8, 0.9])
@pytest.mark.parametrize("name", ["wrong_forecast", "unexpected_peak"])
def test_wrong_forecast_still_covered(name, p):
    run = simulate(load_scenario(name, 42), "anticipatory", Config(), risk_appetite=p)
    assert run["summary"]["final_backlog_docs"] == 0  # guarda SLO determinística drena mesmo com previsão errada
    assert forecast_error(run)["mape_percent"] > 0
    if name == "unexpected_peak":
        assert any("slo_guard" in t["events"] for t in run["ticks"])


def test_api_risk_appetite_and_error_budget():
    client = TestClient(app)
    base = {"scenario": "unexpected_peak", "seed": 1}
    r = client.post("/simulations", json={**base, "policy": "anticipatory", "risk_appetite": 0.9})
    assert r.status_code == 200 and r.json()["risk_appetite"] == 0.9
    assert client.post("/simulations", json={**base, "risk_appetite": 1.5}).status_code == 422
    r = client.post("/error-budget", json={**base, "risk_appetite": 0.8, "slo_target": 0.95})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == budget_report(compare(load_scenario("unexpected_peak", 1), Config(), 0.8), Slo(target=0.95))
    assert body["labels"]["budget"] == "estimated"
    assert client.post("/error-budget", json={**base, "slo_target": 1}).status_code == 422
