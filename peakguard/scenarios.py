"""Cargas sintéticas e previsões declaradas independentemente da realização."""

import json
import math
import random
from dataclasses import dataclass
from importlib.resources import files

SCENARIOS = ("stable", "predictable_peak", "unexpected_peak", "wrong_forecast")
# Calendário fiscal brasileiro estilizado, 100% sintético (24 ticks comprimidos, não dados reais).
FISCAL_SCENARIOS = ("fiscal_month_close", "fiscal_das_day20", "fiscal_ancillary_obligations", "fiscal_irpf_april")
ALL_SCENARIOS = SCENARIOS + FISCAL_SCENARIOS
ARRIVALS = ("deterministic", "poisson", "burst")
BURST_PROBABILITY, BURST_FACTOR = 0.15, 3


@dataclass(frozen=True)
class Scenario:
    name: str
    seed: int
    demand_docs_per_minute: tuple[float, ...]
    predicted_docs_per_minute: tuple[float, ...]

    def __post_init__(self):
        for field in ("demand_docs_per_minute", "predicted_docs_per_minute"):
            values = tuple(getattr(self, field))
            if not values or any(isinstance(v, bool) or not isinstance(v, (int, float))
                                 or not math.isfinite(v) or v < 0 for v in values):
                raise ValueError("As séries devem conter taxas finitas e não negativas.")
            object.__setattr__(self, field, values)
        if len(self.demand_docs_per_minute) != len(self.predicted_docs_per_minute):
            raise ValueError("Demanda e previsão devem ter o mesmo número de intervalos.")


def _poisson(rng: random.Random, mean: float) -> int:
    """Knuth em fatias de média <= 30 (exp(-mean) estouraria a precisão para médias grandes)."""
    total = 0
    while mean > 0:
        part, mean = min(mean, 30.0), mean - min(mean, 30.0)
        limit, product = math.exp(-part), rng.random()
        while product > limit:
            total += 1
            product *= rng.random()
    return total


def load_scenario(name: str, seed: int = 42, arrivals: str = "deterministic") -> Scenario:
    if name not in ALL_SCENARIOS:
        raise ValueError(f"Não existe cenário com nome: {name}")
    if arrivals not in ARRIVALS:
        raise ValueError(f"arrivals deve ser um de {ARRIVALS}")
    spec = json.loads(files("peakguard").joinpath(f"fixtures/{name}.json").read_text())
    peaks = spec.get("peaks") or [[spec["peak_start"], spec["peak_end"], spec["actual_peak"], spec["forecast_peak"]]]
    rng = random.Random(seed)
    demand, prediction, means = [], [], []
    for tick in range(spec["ticks"]):
        actual = forecast = spec["baseline"]
        for start, end, peak_actual, peak_forecast in peaks:
            if start <= tick < end:
                actual, forecast = peak_actual, peak_forecast
        means.append(actual)
        demand.append(max(0, actual + rng.randint(-spec["jitter"], spec["jitter"])))
        prediction.append(forecast)
    if arrivals != "deterministic":
        # RNG separado: não altera a série determinística nem o estado global.
        arrival_rng = random.Random(f"{seed}:{arrivals}")
        factor = lambda: BURST_FACTOR if arrivals == "burst" and arrival_rng.random() < BURST_PROBABILITY else 1
        demand = [_poisson(arrival_rng, mean * factor()) for mean in means]
    return Scenario(name, seed, tuple(demand), tuple(prediction))
