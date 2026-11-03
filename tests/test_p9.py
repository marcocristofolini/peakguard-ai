import csv
import io
import json
import math
import random
import statistics

import pytest

from peakguard.analysis import littles_law_check, multi_seed, to_csv
from peakguard.scenarios import ALL_SCENARIOS, FISCAL_SCENARIOS, SCENARIOS, load_scenario
from peakguard.simulator import Config, simulate


def test_fiscal_scenarios_are_listed_and_synthetic():
    assert len(FISCAL_SCENARIOS) == 4
    assert ALL_SCENARIOS == SCENARIOS + FISCAL_SCENARIOS
    for name in FISCAL_SCENARIOS:
        s = load_scenario(name, 42)
        assert len(s.demand_docs_per_minute) == 24
        assert simulate(s, "reactive", Config())["data_labels"]["demand"] == "synthetic"


def test_fiscal_shapes():
    das = load_scenario("fiscal_das_day20", 42)
    assert das.predicted_docs_per_minute[8] == 300 and das.demand_docs_per_minute[8] > 380
    anc = load_scenario("fiscal_ancillary_obligations", 42)
    assert anc.predicted_docs_per_minute[5] == 180 and anc.predicted_docs_per_minute[17] == 120
    assert anc.demand_docs_per_minute[17] > 200 and anc.demand_docs_per_minute[10] < 60


@pytest.mark.parametrize("mode", ["poisson", "burst"])
def test_stochastic_arrivals_are_seeded_and_do_not_touch_global_rng(mode):
    state = random.getstate()
    a = load_scenario("stable", 7, arrivals=mode)
    assert a == load_scenario("stable", 7, arrivals=mode)
    assert a.demand_docs_per_minute != load_scenario("stable", 7).demand_docs_per_minute
    assert a.demand_docs_per_minute != load_scenario("stable", 8, arrivals=mode).demand_docs_per_minute
    assert a.predicted_docs_per_minute == load_scenario("stable", 7).predicted_docs_per_minute
    assert random.getstate() == state


def test_poisson_mean_close_to_rate_and_default_unchanged():
    means = [statistics.fmean(load_scenario("stable", s, arrivals="poisson").demand_docs_per_minute) for s in range(30)]
    assert abs(statistics.fmean(means) - 40) < 1.5
    big = load_scenario("fiscal_das_day20", 1, arrivals="poisson")
    assert all(v == int(v) and v >= 0 for v in big.demand_docs_per_minute)
    assert load_scenario("stable", 42) == load_scenario("stable", 42, arrivals="deterministic")


def test_unknown_arrivals_rejected():
    with pytest.raises(ValueError, match="arrivals"):
        load_scenario("stable", 1, arrivals="x")


def test_multi_seed_default_20_with_ci95():
    r = multi_seed("predictable_peak", Config())
    assert r["seeds"] == list(range(20)) and r["data_labels"]["simulation"] == "estimated"
    m = r["policies"]["reactive"]["cost_brl"]
    assert m["n"] == 20 and m["ci95_low"] <= m["mean"] <= m["ci95_high"]
    vals = [simulate(load_scenario("predictable_peak", s), "reactive", Config())["summary"]["cost_brl"] for s in range(20)]
    assert m["mean"] == pytest.approx(statistics.fmean(vals))
    half = 2.093 * statistics.stdev(vals) / math.sqrt(20)  # t(0.975, 19)
    assert m["ci95_high"] - m["mean"] == pytest.approx(half)
    json.dumps(r, allow_nan=False)


def test_multi_seed_configurable_and_csv():
    r = multi_seed("stable", Config(), seeds=3, arrivals="poisson")
    assert r["seeds"] == [0, 1, 2] and r["arrivals"] == "poisson"
    rows = list(csv.DictReader(io.StringIO(to_csv(r))))
    assert {row["policy"] for row in rows} == {"reactive", "anticipatory"}
    assert {"metric", "mean", "std", "ci95_low", "ci95_high", "n"} <= set(rows[0])
    with pytest.raises(ValueError):
        multi_seed("stable", Config(), seeds=1)


@pytest.mark.parametrize("name,arrivals", [("stable", "deterministic"), ("fiscal_das_day20", "poisson"),
                                           ("fiscal_irpf_april", "burst"), ("unexpected_peak", "poisson")])
@pytest.mark.parametrize("policy", ["reactive", "anticipatory"])
def test_littles_law_holds_within_tolerance(name, arrivals, policy):
    cfg = Config(max_replicas=20, budget_brl=100)
    sim = simulate(load_scenario(name, 5, arrivals=arrivals), policy, cfg)
    check = littles_law_check(sim, tolerance=1e-6)
    assert check["ok"], check
    assert check["L_docs"] == pytest.approx(check["lambda_docs_per_minute"] * check["W_minutes"], rel=1e-6)


def test_littles_law_rejects_undrained_run():
    sim = simulate(load_scenario("unexpected_peak", 5), "reactive", Config(max_replicas=1, budget_brl=100))
    assert sim["summary"]["final_backlog_docs"] > 0
    with pytest.raises(ValueError, match="drenad"):
        littles_law_check(sim)
