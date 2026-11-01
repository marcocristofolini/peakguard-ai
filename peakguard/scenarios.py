"""Cargas sintéticas e previsões declaradas independentemente da realização."""

import json
import math
import random
from dataclasses import dataclass
from importlib.resources import files

SCENARIOS = ("stable", "predictable_peak", "unexpected_peak", "wrong_forecast")


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


def load_scenario(name: str, seed: int = 42) -> Scenario:
    if name not in SCENARIOS:
        raise ValueError(f"Não existe cenário com nome: {name}")
    spec = json.loads(files("peakguard").joinpath(f"fixtures/{name}.json").read_text())
    rng = random.Random(seed)
    demand, prediction = [], []
    for tick in range(spec["ticks"]):
        in_peak = spec["peak_start"] <= tick < spec["peak_end"]
        actual = spec["actual_peak"] if in_peak else spec["baseline"]
        forecast = spec["forecast_peak"] if in_peak else spec["baseline"]
        demand.append(max(0, actual + rng.randint(-spec["jitter"], spec["jitter"])))
        prediction.append(forecast)
    return Scenario(name, seed, tuple(demand), tuple(prediction))
