"""Multi-seed com IC 95% e checagem da Lei de Little; só biblioteca padrão."""

import csv
import io
import math
import statistics
from dataclasses import asdict

from .scenarios import load_scenario
from .simulator import POLICIES, Config, simulate

METRICS = ("cost_brl", "final_backlog_docs", "max_backlog_docs", "slo_violation_minutes",
           "saturated_minutes", "cost_brl_per_1000_docs")
# t de Student bicaudal 95% por graus de liberdade (1..30); acima de 30 usa-se 1,96 (erro < 4%).
_T95 = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131,
        2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042)


def _stats(values: list[float]) -> dict:
    n, mean = len(values), statistics.fmean(values)
    std = statistics.stdev(values)
    half = (_T95[n - 2] if n <= 31 else 1.96) * std / math.sqrt(n)
    return {"n": n, "mean": mean, "std": std, "ci95_low": mean - half, "ci95_high": mean + half}


def multi_seed(scenario: str, config: Config, seeds: int = 20, arrivals: str = "deterministic") -> dict:
    if isinstance(seeds, bool) or not isinstance(seeds, int) or seeds < 2:
        raise ValueError("seeds deve ser inteiro >= 2 para calcular IC.")
    runs = {p: [simulate(load_scenario(scenario, s, arrivals), p, config)["summary"] for s in range(seeds)]
            for p in POLICIES}
    return {
        "schema_version": 1, "scenario": scenario, "arrivals": arrivals, "seeds": list(range(seeds)),
        "data_labels": {"demand": "synthetic", "simulation": "estimated", "cost": "estimated",
                        "observed": "none; no external infrastructure measurements"},
        "config": asdict(config),
        "policies": {p: {m: _stats(v) for m in METRICS
                         if (v := [r[m] for r in runs[p] if r[m] is not None]) and len(v) > 1}
                     for p in POLICIES},
    }


def to_csv(result: dict) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["scenario", "arrivals", "policy", "metric", "n", "mean", "std", "ci95_low", "ci95_high"])
    for policy, metrics in result["policies"].items():
        for metric, s in metrics.items():
            writer.writerow([result["scenario"], result["arrivals"], policy, metric,
                             s["n"], s["mean"], s["std"], s["ci95_low"], s["ci95_high"]])
    return out.getvalue()


def littles_law_check(result: dict, tolerance: float = 1e-6) -> dict:
    """Confere L = λW em execução drenada.

    L: média no tempo de documentos no sistema (fila anterior + chegadas do tick, constante no tick).
    W: tempo médio por documento por casamento FIFO das curvas acumuladas de chegada (início do tick)
    e saída (fim do tick). Métodos distintos; tolerância relativa declarada em `tolerance`.
    """
    ticks, dt = result["ticks"], result["config"]["tick_minutes"]
    if result["summary"]["final_backlog_docs"] > 1e-9:
        raise ValueError("A execução deve estar drenada (fila final zero) para a Lei de Little.")
    horizon = len(ticks) * dt
    arrivals = [t["demand_docs_per_minute"] * dt for t in ticks]
    total = math.fsum(arrivals)
    present, backlog = [], 0.0
    for t, arrived in zip(ticks, arrivals):
        present.append(backlog + arrived)
        backlog = t["backlog_docs"]
    L = math.fsum(n * dt for n in present) / horizon
    lam = total / horizon
    # Casamento FIFO: percorre arrivals e processed em paralelo, acumulando sojourn × docs.
    sojourn, a_i, d_i = 0.0, 0, 0
    a_left, d_left = arrivals[0], ticks[0]["processed_docs"]
    while a_i < len(ticks) and d_i < len(ticks):
        if a_left <= 1e-12:
            a_i += 1
            a_left = arrivals[a_i] if a_i < len(ticks) else 0
            continue
        if d_left <= 1e-12:
            d_i += 1
            d_left = ticks[d_i]["processed_docs"] if d_i < len(ticks) else 0
            continue
        moved = min(a_left, d_left)
        sojourn += moved * ((d_i + 1) - a_i) * dt
        a_left, d_left = a_left - moved, d_left - moved
    W = sojourn / total
    error = abs(L - lam * W) / L if L else 0.0
    return {"L_docs": L, "lambda_docs_per_minute": lam, "W_minutes": W,
            "relative_error": error, "tolerance": tolerance, "ok": error <= tolerance}
