"""Varredura de parâmetros e fronteira de Pareto custo × ticks fora do SLO (comando explícito; fora do CI)."""

import hashlib
import itertools
import json
from dataclasses import asdict, replace
from pathlib import Path

from .scenarios import load_scenario
from .simulator import Config, simulate

MAX_COMBINATIONS = 200
CACHE_SCHEMA = 1


def grid(utilizations=(0.6, 0.7, 0.8, 0.9), ewma_windows=(1, 3, 6), risk_appetites=(None, 0.5, 0.8, 0.9),
         min_replicas=(1, 2)) -> list[dict]:
    """Reativa varia (utilização, EWMA, min); antecipativa varia (utilização, percentil, min). Cada ponto = 1 política."""
    combos = [{"policy": "reactive", "target_utilization": u, "ewma_window": w, "risk_appetite": None, "min_replicas": m}
              for u, w, m in itertools.product(utilizations, ewma_windows, min_replicas)]
    combos += [{"policy": "anticipatory", "target_utilization": u, "ewma_window": None, "risk_appetite": r, "min_replicas": m}
              for u, r, m in itertools.product(utilizations, risk_appetites, min_replicas)]
    if len(combos) > MAX_COMBINATIONS:
        raise ValueError(f"A varredura excede {MAX_COMBINATIONS} combinações ({len(combos)}).")
    return combos


def dominates(a, b) -> bool:
    """a e b = (custo, ticks fora do SLO), ambos minimizados."""
    return a[0] <= b[0] and a[1] <= b[1] and a != b


def pareto_front(points: list[dict]) -> list[dict]:
    key = lambda p: (p["cost_brl"], p["slo_violation_ticks"])
    return [p for p in points if not any(dominates(key(q), key(p)) for q in points)]


def _code_hash() -> str:
    """Invalida o cache quando o motor muda."""
    here = Path(__file__).parent
    return hashlib.sha256(b"".join((here / f).read_bytes() for f in ("simulator.py", "scenarios.py", "budget.py"))).hexdigest()[:16]


def sweep(scenario_name: str, seed: int, base: Config, arrivals: str = "deterministic", combos: list[dict] | None = None,
          cache: Path | None = None) -> dict:
    combos = grid() if combos is None else combos
    if len(combos) > MAX_COMBINATIONS:
        raise ValueError(f"A varredura excede {MAX_COMBINATIONS} combinações ({len(combos)}).")
    scenario = load_scenario(scenario_name, seed, arrivals)
    stored = json.loads(cache.read_text()) if cache and cache.exists() else {}
    code, hits, misses, points = _code_hash(), 0, 0, []
    for combo in combos:
        key = hashlib.sha256(json.dumps([CACHE_SCHEMA, code, scenario_name, seed, arrivals, asdict(base), combo],
                                        sort_keys=True).encode()).hexdigest()
        if key in stored:
            point, hits = stored[key], hits + 1
        else:
            config = replace(base, target_utilization=combo["target_utilization"], min_replicas=combo["min_replicas"],
                             initial_replicas=max(base.initial_replicas, combo["min_replicas"]))
            run = simulate(scenario, combo["policy"], config, combo["risk_appetite"], combo["ewma_window"])
            point = {**combo, "cost_brl": run["summary"]["cost_brl"],
                     "slo_violation_ticks": round(run["summary"]["slo_violation_minutes"] / config.tick_minutes)}
            stored[key], misses = point, misses + 1
        points.append(dict(point))
    if cache and misses:
        cache.write_text(json.dumps(stored, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    front = pareto_front(points)
    for p in points:
        p["pareto"] = any(p is f or p == f for f in front)
    front = [p for p in points if p["pareto"]]
    return {"schema_version": 1, "scenario": scenario_name, "seed": seed, "arrivals": arrivals,
            "labels": {"demand": "synthetic", "cost": "estimated", "slo": "estimated"},
            "axes": {"x": "cost_brl", "y": "slo_violation_ticks"}, "combinations": len(points),
            "cache": {"hits": hits, "misses": misses}, "points": points, "front": front}
