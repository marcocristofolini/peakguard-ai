import json

import pytest
from fastapi.testclient import TestClient

from peakguard.api import app
from peakguard.finops import PRICE_TABLE, FinopsModel, extended_cost
from peakguard.scenarios import load_scenario
from peakguard.simulator import Config, simulate
from peakguard.sweep import MAX_COMBINATIONS, dominates, grid, pareto_front, sweep


def test_ewma_window_one_is_identity_and_smooths_reactive_only():
    s = load_scenario("unexpected_peak", 42)
    base = simulate(s, "reactive", Config())
    assert simulate(s, "reactive", Config(), ewma_window=1) == base
    assert simulate(s, "reactive", Config(), ewma_window=6)["ticks"] != base["ticks"]
    a = simulate(s, "anticipatory", Config())
    assert simulate(s, "anticipatory", Config(), ewma_window=6)["ticks"] == a["ticks"]
    for bad in (0, -1, 1.5, True):
        with pytest.raises(ValueError):
            simulate(s, "reactive", Config(), ewma_window=bad)


def test_dominance_and_front():
    a, b, c = (1.0, 2), (1.5, 2), (0.5, 5)
    assert dominates(a, b) and not dominates(b, a) and not dominates(a, a)
    assert not dominates(a, c) and not dominates(c, a)
    pts = [{"cost_brl": x, "slo_violation_ticks": y} for x, y in (a, b, c)]
    assert [(p["cost_brl"], p["slo_violation_ticks"]) for p in pareto_front(pts)] == [a, c]


def test_grid_limit():
    assert len(grid()) <= MAX_COMBINATIONS
    with pytest.raises(ValueError):
        grid(utilizations=[0.5 + i / 1000 for i in range(120)], ewma_windows=[1, 2], risk_appetites=[0.5])


def test_sweep_points_and_reactive_dominates_proactive(tmp_path):
    result = sweep("stable", 42, Config(), cache=tmp_path / "c.json")
    pts = result["points"]
    assert {p["policy"] for p in pts} == {"reactive", "anticipatory"}
    assert result["labels"]["cost"] == "estimated" and result["labels"]["demand"] == "synthetic"
    assert all(p["pareto"] == (p in result["front"]) for p in pts)
    reactive = [p for p in pts if p["policy"] == "reactive"]
    proactive = [p for p in pts if p["policy"] == "anticipatory"]
    assert any(dominates((r["cost_brl"], r["slo_violation_ticks"]), (a["cost_brl"], a["slo_violation_ticks"]))
               for r in reactive for a in proactive)


def test_sweep_cache(tmp_path):
    cache = tmp_path / "c.json"
    first = sweep("stable", 42, Config(), cache=cache)
    assert first["cache"]["misses"] == len(first["points"]) and first["cache"]["hits"] == 0
    second = sweep("stable", 42, Config(), cache=cache)
    assert second["cache"]["hits"] == len(second["points"]) and second["points"] == first["points"]
    assert len(json.loads(cache.read_text())) == len(first["points"])
    other = sweep("stable", 7, Config(), cache=cache)
    assert other["cache"]["hits"] == 0


def test_finops_bin_packing_idle_and_labels():
    s = load_scenario("predictable_peak", 42)
    run = simulate(s, "reactive", Config())
    m = FinopsModel()
    r = extended_cost(run, m)
    assert r["labels"]["prices"] == "hypothetical" and PRICE_TABLE["label"] == "hypothetical"
    assert r["pods_per_node"] == min(int(m.node_vcpu // m.pod_vcpu), int(m.node_mem_gib // m.pod_mem_gib))
    assert r["node_hours"] >= r["used_node_hours"] > 0 and r["idle_cost_brl"] >= 0
    assert r["total_cost_brl"] == pytest.approx(r["node_cost_brl"] + r["interruption_cost_brl"])


def test_finops_spot_cheaper_in_expectation_but_has_interruptions():
    run = simulate(load_scenario("predictable_peak", 42), "reactive", Config())
    od = extended_cost(run, FinopsModel(spot_fraction=0))
    spot = extended_cost(run, FinopsModel(spot_fraction=1))
    assert od["expected_interruptions"] == 0 and spot["expected_interruptions"] > 0
    assert spot["total_cost_brl"] < od["total_cost_brl"]
    # prêmio de interrupção alto inverte a vantagem do spot
    assert extended_cost(run, FinopsModel(spot_fraction=1, interruption_per_node_hour=50))["total_cost_brl"] > od["total_cost_brl"]


def test_finops_scale_to_zero():
    run = simulate(load_scenario("fiscal_ancillary_obligations", 42), "reactive", Config())
    off = extended_cost(run, FinopsModel(scale_to_zero_below_docs_per_minute=None))
    on = extended_cost(run, FinopsModel(scale_to_zero_below_docs_per_minute=1000))
    assert off["zero_ticks"] == 0 and on["zero_ticks"] > 0 and on["cold_starts"] >= 1
    assert on["node_cost_brl"] < off["node_cost_brl"]
    # backlog > 0 impede zerar
    for t in run["ticks"]:
        t["backlog_docs"] = 1.0
    assert extended_cost(run, FinopsModel(scale_to_zero_below_docs_per_minute=1000))["zero_ticks"] == 0


def test_finops_validation():
    for kw in ({"spot_fraction": 1.5}, {"pod_vcpu": 0}, {"pod_vcpu": 99}, {"interruption_per_node_hour": -1}):
        with pytest.raises(ValueError):
            FinopsModel(**kw)


def test_api_pareto():
    c = TestClient(app)
    r = c.post("/pareto", json={"scenario": "stable", "seed": 42})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["front"] and body["labels"]["cost"] == "estimated"
    assert c.post("/finops", json={"scenario": "stable", "finops": {"spot_fraction": 2}}).status_code == 422
    r = c.post("/finops", json={"scenario": "stable", "policy": "reactive", "finops": {"spot_fraction": 0.5}})
    assert r.status_code == 200 and r.json()["labels"]["prices"] == "hypothetical"
