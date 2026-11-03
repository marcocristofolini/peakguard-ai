"""Motor discreto FIFO; todas as decisões alteram somente o estado simulado."""

import math
from collections import deque
from dataclasses import asdict, dataclass

from .budget import empirical_quantile
from .scenarios import Scenario

POLICIES = ("reactive", "anticipatory")


@dataclass(frozen=True)
class Config:
    tick_minutes: float = 1
    capacity_docs_per_minute_per_replica: float = 100
    price_brl_per_replica_hour: float = 1.2
    min_replicas: int = 1
    max_replicas: int = 10
    initial_replicas: int = 1
    activation_delay_ticks: int = 2
    cooldown_ticks: int = 2
    forecast_horizon_ticks: int = 3
    target_utilization: float = 0.8
    budget_brl: float = 10
    slo_queue_minutes: float = 2
    base_latency_minutes: float = 0.1

    def __post_init__(self):
        integer_fields = ("min_replicas", "max_replicas", "initial_replicas",
                          "activation_delay_ticks", "cooldown_ticks", "forecast_horizon_ticks")
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} deve ser um número finito.")
            if name in integer_fields and not isinstance(value, int):
                raise ValueError(f"{name} deve ser inteiro.")
            nonnegative = name in ("activation_delay_ticks", "cooldown_ticks", "price_brl_per_replica_hour",
                                   "budget_brl", "base_latency_minutes")
            if value < 0 or (not nonnegative and value == 0):
                raise ValueError(f"{name} fora do intervalo permitido.")
        if not self.min_replicas <= self.initial_replicas <= self.max_replicas:
            raise ValueError("Réplicas iniciais devem respeitar min/max.")
        if self.target_utilization > 1:
            raise ValueError("target_utilization deve estar em (0, 1].")


def _propose(policy, scenario, tick, previous_demand, backlog, provisioned, config, risk_appetite=None):
    unit = config.capacity_docs_per_minute_per_replica
    if policy == "anticipatory":
        forecast = max(scenario.predicted_docs_per_minute[tick:tick + config.forecast_horizon_ticks])
        if risk_appetite is not None and tick:
            # Quantil empírico causal: só resíduos (real − previsto) de ticks já observados.
            residuals = [a - p for a, p in zip(scenario.demand_docs_per_minute[:tick], scenario.predicted_docs_per_minute[:tick])]
            forecast = max(0.0, forecast + empirical_quantile(residuals, risk_appetite))
        return math.ceil(forecast / (unit * config.target_utilization))
    utilization = previous_demand / (provisioned * unit)
    if utilization > config.target_utilization or backlog > 0:
        return math.ceil((previous_demand + backlog / config.tick_minutes) / (unit * config.target_utilization))
    if utilization < config.target_utilization / 2:
        return math.ceil(previous_demand / (unit * config.target_utilization))
    return provisioned


def _safe_target(proposed, previous_demand, backlog, spent, remaining, config):
    events = []
    unit = config.capacity_docs_per_minute_per_replica
    slo_minimum = math.ceil((previous_demand + backlog / config.slo_queue_minutes) / unit)
    target = max(config.min_replicas, proposed, slo_minimum)
    if proposed < config.min_replicas:
        events.append("min_replicas_limit")
    if proposed < slo_minimum:
        events.append("slo_guard")
    per_replica_tick = config.price_brl_per_replica_hour * config.tick_minutes / 60
    affordable = config.max_replicas
    if per_replica_tick > 0:
        affordable = math.floor(min(config.max_replicas,
                                    (config.budget_brl - spent) / (remaining * per_replica_tick)) + 1e-10)
    if target > config.max_replicas:
        events.append("max_replicas_limit")
    if target > affordable:
        events.append("budget_limit")
    target = max(config.min_replicas, min(target, config.max_replicas, affordable))
    if target < slo_minimum:
        events.append("slo_unachievable")
    return target, events


def _serve(queue, available_docs, now, dt):
    """Consome lotes FIFO; idade tem resolução de um tick, sem descartar fila."""
    processed, wait = 0.0, 0.0
    while queue and available_docs > 0:
        arrival, amount = queue[0]
        served = min(amount, available_docs)
        wait = max(wait, now - arrival)
        processed += served
        available_docs -= served
        if served == amount:
            queue.popleft()
        else:
            queue[0] = (arrival, amount - served)
    if queue:
        wait = max(wait, now + dt - queue[0][0])
    return processed, wait


def _validate_numerics(scenario: Scenario, config: Config) -> None:
    """Recusa combinações que excedem a precisão representável do motor float."""
    try:
        dt = config.tick_minutes
        unit = config.capacity_docs_per_minute_per_replica
        total_docs = math.fsum(scenario.demand_docs_per_minute) * dt
        maximum_rate = max(*scenario.demand_docs_per_minute, *scenario.predicted_docs_per_minute)
        upper_target = (maximum_rate + total_docs / min(dt, config.slo_queue_minutes)) / (unit * config.target_utilization)
        capacity_docs = unit * config.max_replicas * dt
        per_tick = config.price_brl_per_replica_hour * dt / 60
        bounds = (total_docs, upper_target, capacity_docs,
                  len(scenario.demand_docs_per_minute) * dt + config.base_latency_minutes,
                  per_tick * len(scenario.demand_docs_per_minute) * config.max_replicas)
        if any(not math.isfinite(v) for v in bounds) or capacity_docs == 0:
            raise ValueError("Limites numéricos excedidos pela combinação de parâmetros.")
        if config.price_brl_per_replica_hour > 0 and per_tick == 0:
            raise ValueError("Precisão numérica insuficiente para calcular custos.")
    except (OverflowError, ZeroDivisionError) as error:
        raise ValueError("Limites numéricos excedidos pela combinação de parâmetros.") from error


def simulate(scenario: Scenario, policy: str, config: Config, risk_appetite: float | None = None,
             ewma_window: int | None = None) -> dict:
    """risk_appetite: quantil (0,1) dos resíduos de previsão somado ao lookahead antecipativo; None = sem ajuste.
    ewma_window: janela (ticks, alpha=2/(w+1)) que suaviza a demanda vista pela política reativa; None/1 = sem suavização."""
    if policy not in POLICIES:
        raise ValueError(f"política desconhecida: {policy}")
    if risk_appetite is not None and (isinstance(risk_appetite, bool) or not isinstance(risk_appetite, (int, float))
                                      or not 0 < risk_appetite < 1):
        raise ValueError("risk_appetite deve estar em (0, 1).")
    if ewma_window is not None and (isinstance(ewma_window, bool) or not isinstance(ewma_window, int) or ewma_window < 1):
        raise ValueError("ewma_window deve ser inteiro >= 1.")
    alpha = 2 / ((ewma_window or 1) + 1)
    smoothed = 0.0
    _validate_numerics(scenario, config)
    duration = len(scenario.demand_docs_per_minute)
    per_replica_tick = config.price_brl_per_replica_hour * config.tick_minutes / 60
    if config.initial_replicas * duration * per_replica_tick > config.budget_brl + 1e-12:
        raise ValueError("O orçamento não comporta as réplicas iniciais durante toda a execução.")
    active = config.initial_replicas
    pending = []
    queue = deque()
    backlog, spent, previous_demand = 0.0, 0.0, 0.0
    last_scale = -config.cooldown_ticks
    ticks = []
    for tick, demand in enumerate(scenario.demand_docs_per_minute):
        events = []
        activated = sum(count for ready, count in pending if ready <= tick)
        if activated:
            active += activated
            events.append("activation")
        pending = [(ready, count) for ready, count in pending if ready > tick]
        provisioned = active + sum(count for _, count in pending)
        proposed = _propose(policy, scenario, tick, smoothed, backlog, provisioned, config, risk_appetite)
        target, limits = _safe_target(proposed, previous_demand, backlog, spent, duration - tick, config)
        events.extend(limits)
        if target != provisioned:
            if tick - last_scale < config.cooldown_ticks:
                events.append("cooldown")
            else:
                if target > provisioned:
                    if config.activation_delay_ticks == 0:
                        active += target - provisioned
                    else:
                        pending.append((tick + config.activation_delay_ticks, target - provisioned))
                else:
                    # Cancelar primeiro réplicas ainda em ativação, da mais recente à mais antiga.
                    remove = provisioned - target
                    while pending and remove:
                        ready, count = pending.pop()
                        cancelled = min(count, remove)
                        remove -= cancelled
                        if count > cancelled:
                            pending.append((ready, count - cancelled))
                    active -= remove
                last_scale = tick
                events.append("scale")
        pending_count = sum(count for _, count in pending)
        provisioned = active + pending_count
        capacity = active * config.capacity_docs_per_minute_per_replica
        arrivals = demand * config.tick_minutes
        if arrivals:
            queue.append((tick * config.tick_minutes, arrivals))
        available = backlog + arrivals
        processed, wait = _serve(queue, capacity * config.tick_minutes,
                                 tick * config.tick_minutes, config.tick_minutes)
        backlog = math.fsum(amount for _, amount in queue)
        cost = provisioned * per_replica_tick
        spent = math.fsum([spent, cost])
        violated = wait > config.slo_queue_minutes
        if violated:
            events.append("slo_violation")
        ticks.append({
            "tick": tick, "time_minutes": tick * config.tick_minutes,
            "demand_docs_per_minute": demand,
            "predicted_docs_per_minute": scenario.predicted_docs_per_minute[tick],
            "proposed_replicas": proposed, "safe_target_replicas": target,
            "active_replicas": active, "pending_replicas": pending_count,
            "provisioned_replicas": provisioned, "capacity_docs_per_minute": capacity,
            "processed_docs": processed, "throughput_docs_per_minute": processed / config.tick_minutes,
            "backlog_docs": backlog, "queue_wait_minutes": wait,
            "latency_minutes_estimated": wait + config.base_latency_minutes if available else 0,
            "utilization": processed / (capacity * config.tick_minutes),
            "saturated": available >= capacity * config.tick_minutes,
            "slo_violated": violated, "cost_brl": cost, "cumulative_cost_brl": spent,
            "events": events,
        })
        previous_demand = demand
        smoothed = alpha * demand + (1 - alpha) * smoothed if tick else demand
    processed_total = math.fsum(t["processed_docs"] for t in ticks)
    return {
        "schema_version": 1, "scenario": scenario.name, "seed": scenario.seed, "policy": policy,
        "risk_appetite": risk_appetite,
        "data_labels": {"demand": "synthetic", "forecast": "predicted", "simulation": "estimated",
                        "cost": "estimated", "observed": "none; no external infrastructure measurements"},
        "config": asdict(config),
        "input": {"demand_docs_per_minute": list(scenario.demand_docs_per_minute),
                  "predicted_docs_per_minute": list(scenario.predicted_docs_per_minute)},
        "ticks": ticks,
        "summary": {
            "duration_minutes": duration * config.tick_minutes,
            "demand_docs": math.fsum(scenario.demand_docs_per_minute) * config.tick_minutes,
            "processed_docs": processed_total, "final_backlog_docs": backlog,
            "max_backlog_docs": max(t["backlog_docs"] for t in ticks),
            "cost_brl": spent,
            "replica_hours": math.fsum(t["provisioned_replicas"] for t in ticks) * config.tick_minutes / 60,
            "cost_brl_per_1000_docs": spent / processed_total * 1000 if processed_total else None,
            "slo_violation_minutes": sum(t["slo_violated"] for t in ticks) * config.tick_minutes,
            "saturated_minutes": sum(t["saturated"] for t in ticks) * config.tick_minutes,
            "forecast_mae_docs_per_minute": math.fsum(abs(a - p) for a, p in zip(
                scenario.demand_docs_per_minute, scenario.predicted_docs_per_minute)) / duration,
        },
    }


def compare(scenario: Scenario, config: Config, risk_appetite: float | None = None) -> dict:
    """Executa políticas sobre a mesma realização imutável e a mesma configuração."""
    return {"schema_version": 1, "results": {policy: simulate(scenario, policy, config, risk_appetite) for policy in POLICIES}}
