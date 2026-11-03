"""Error budget, burn rate multi-janela e quantis empíricos de resíduos (sintético; valores estimated)."""

import math
from dataclasses import dataclass

# 1 tick = 5 minutos equivalentes do relógio do SLO: 1h/5m -> 12/1 ticks; 6h/30m -> 72/6 ticks.
EQUIVALENT_MINUTES_PER_TICK = 5
BURN_WINDOWS = {"fast": {"long_ticks": 12, "short_ticks": 1, "threshold": 14.4, "label": "1h/5m"},
                "slow": {"long_ticks": 72, "short_ticks": 6, "threshold": 6.0, "label": "6h/30m"}}


@dataclass(frozen=True)
class Slo:
    """SLI: fração de ticks sem violação de `slo_queue_minutes`. Janela = últimos `window_minutes` (padrão: execução inteira)."""
    target: float = 0.99
    window_minutes: float | None = None

    def __post_init__(self):
        if not isinstance(self.target, (int, float)) or not 0 < self.target < 1:
            raise ValueError("target do SLO deve estar em (0, 1).")
        if self.window_minutes is not None and not self.window_minutes > 0:
            raise ValueError("window_minutes deve ser positivo.")


def empirical_quantile(values, p: float) -> float:
    """Postos mais próximos (nearest-rank) sobre a amostra; sem interpolação."""
    if not values:
        raise ValueError("amostra vazia.")
    if not 0 < p < 1:
        raise ValueError("p deve estar em (0, 1).")
    ordered = sorted(values)
    return ordered[math.ceil(p * len(ordered)) - 1]


def _bad_series(run: dict, slo: Slo):
    dt = run["config"]["tick_minutes"]
    bad = [1 if t["slo_violated"] else 0 for t in run["ticks"]]
    if slo.window_minutes is None:
        return bad, dt
    ticks = round(slo.window_minutes / dt)
    if not 1 <= ticks <= len(bad):
        raise ValueError("window_minutes fora da duração da execução.")
    return bad[-ticks:], dt


def error_budget(run: dict, slo: Slo = Slo()) -> dict:
    bad, dt = _bad_series(run, slo)
    window = len(bad) * dt
    budget = (1 - slo.target) * window
    consumed = sum(bad) * dt
    burn = {}
    for name, w in BURN_WINDOWS.items():
        # Denominador = janela cheia: um tick ruim no início não dispara sozinho o alerta longo.
        rates = [tuple(sum(bad[max(0, i + 1 - w[k]):i + 1]) / w[k] / (1 - slo.target) for k in ("long_ticks", "short_ticks"))
                 for i in range(len(bad))]
        fired = [i for i, (lo, sh) in enumerate(rates) if lo >= w["threshold"] and sh >= w["threshold"]]
        burn[name] = {"windows": w["label"], "long_ticks": w["long_ticks"], "short_ticks": w["short_ticks"],
                      "threshold": w["threshold"], "max_burn_long": max(r[0] for r in rates),
                      "max_burn_short": max(r[1] for r in rates),
                      "first_alert_tick": fired[0] if fired else None}
    return {"labels": {"slo": "synthetic", "consumption": "estimated", "burn_rate": "estimated"},
            "policy": run["policy"], "slo": {"target": slo.target, "window_minutes": window,
                                             "indicator": "ticks sem violação de slo_queue_minutes"},
            "budget_minutes": budget, "consumed_minutes": consumed,
            "consumed_fraction": consumed / budget, "remaining_minutes": budget - consumed,
            "exhausted": consumed > budget, "burn_rate": burn,
            "equivalent_minutes_per_tick": EQUIVALENT_MINUTES_PER_TICK}


def cost_per_budget_minute(run: dict, baseline: dict, slo: Slo = Slo()) -> dict:
    """BRL (estimated) por minuto de budget preservado vs baseline; sem preservação o quociente é indefinido."""
    base, mine = error_budget(baseline, slo), error_budget(run, slo)
    preserved = base["consumed_minutes"] - mine["consumed_minutes"]
    extra_cost = run["summary"]["cost_brl"] - baseline["summary"]["cost_brl"]
    if preserved <= 0:
        return {"value": None, "status": "no_budget_preserved", "extra_cost_brl": extra_cost,
                "preserved_minutes": preserved}
    return {"value": extra_cost / preserved, "status": "ok", "extra_cost_brl": extra_cost,
            "preserved_minutes": preserved}


def forecast_error(run: dict) -> dict:
    """MAE (docs/min) e MAPE (%) da previsão `predicted` contra a demanda `synthetic`; MAPE ignora demanda zero."""
    pairs = list(zip(run["input"]["demand_docs_per_minute"], run["input"]["predicted_docs_per_minute"]))
    nonzero = [(a, p) for a, p in pairs if a > 0]
    return {"mae_docs_per_minute": math.fsum(abs(a - p) for a, p in pairs) / len(pairs),
            "mape_percent": math.fsum(abs(a - p) / a for a, p in nonzero) / len(nonzero) * 100 if nonzero else None,
            "mape_ticks_skipped_zero_demand": len(pairs) - len(nonzero)}


def budget_report(comparison: dict, slo: Slo = Slo()) -> dict:
    """Relatório por política + custo por minuto de budget preservado da antecipativa sobre a reativa."""
    results = comparison["results"]
    return {"schema_version": 1,
            "labels": {"demand": "synthetic", "forecast": "predicted", "budget": "estimated", "cost": "estimated"},
            "policies": {name: {"error_budget": error_budget(run, slo), "forecast_error": forecast_error(run)}
                         for name, run in results.items()},
            "cost_brl_per_budget_minute_preserved_vs_reactive":
                cost_per_budget_minute(results["anticipatory"], results["reactive"], slo)}
