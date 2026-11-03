"""Gera evidence/p14/results.json: números v2 citados no README/DEMO (todos synthetic/estimated). Reprodutível e determinístico.

Uso (raiz): PYTHONPATH=. python3 local/p14/results.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from peakguard.analysis import multi_seed  # noqa: E402
from peakguard.budget import cost_per_budget_minute, error_budget  # noqa: E402
from peakguard.scenarios import FISCAL_SCENARIOS, load_scenario  # noqa: E402
from peakguard.simulator import Config, compare, simulate  # noqa: E402
from peakguard.sweep import sweep  # noqa: E402

OUT = ROOT / "evidence/p14/results.json"


def build() -> dict:
    fiscal = {}
    for name in FISCAL_SCENARIOS:
        results = compare(load_scenario(name, 42), Config())["results"]
        fiscal[name] = {p: {"cost_brl": r["summary"]["cost_brl"], "slo_violation_minutes": r["summary"]["slo_violation_minutes"]}
                        for p, r in results.items()}
    seeds = multi_seed("fiscal_irpf_april", Config(), 20, "poisson")["policies"]
    irpf = {p: {k: {key: seeds[p][k][key] for key in ("mean", "ci95_low", "ci95_high")}
                for k in ("cost_brl", "max_backlog_docs")} for p in seeds}
    scenario, config = load_scenario("unexpected_peak", 1, "burst"), Config(activation_delay_ticks=3)
    runs = {p: simulate(scenario, "anticipatory", config, risk_appetite=p) for p in (0.5, 0.9)}
    budget = {f"p{int(p * 100)}": {"cost_brl": r["summary"]["cost_brl"], **{k: error_budget(r)[k] for k in
              ("budget_minutes", "consumed_minutes", "consumed_fraction")},
              "fast_alert_tick": error_budget(r)["burn_rate"]["fast"]["first_alert_tick"]} for p, r in runs.items()}
    budget["p90_vs_p50_cost_per_budget_minute"] = cost_per_budget_minute(runs[0.9], runs[0.5])
    pareto = {}
    for name in ("unexpected_peak", "wrong_forecast"):
        result = sweep(name, 42, Config())
        pareto[name] = {"combinations": result["combinations"], "front_size": len(result["front"]),
                        "front_distinct_points": len({(p["cost_brl"], p["slo_violation_ticks"]) for p in result["front"]}),
                        "front_policies": sorted({p["policy"] for p in result["front"]})}
    return {"labels": {"demand": "synthetic", "simulation": "estimated", "cost": "estimated"},
            "fiscal_seed42": fiscal, "irpf_poisson_20_seeds": irpf,
            "error_budget_unexpected_peak_burst_seed1_activation3": budget, "pareto_seed42": pareto}


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(OUT)
