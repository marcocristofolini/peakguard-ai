"""Modelo FinOps estendido, pós-processado sobre uma execução (não altera a simulação). Preços HIPOTÉTICOS."""

import math
from dataclasses import asdict, dataclass

# Tabela hipotética: não reflete preços de nenhum provedor.
PRICE_TABLE = {"label": "hypothetical", "currency": "BRL", "on_demand_brl_per_node_hour": 2.4,
               "spot_brl_per_node_hour": 0.84}


@dataclass(frozen=True)
class FinopsModel:
    node_vcpu: float = 4
    node_mem_gib: float = 16
    pod_vcpu: float = 0.5          # request de CPU por réplica
    pod_mem_gib: float = 1.0       # request de memória por réplica
    spot_fraction: float = 0.0     # fração dos nós em spot
    interruption_per_node_hour: float = 0.05   # probabilidade de interrupção por nó spot-hora
    interruption_replace_minutes: float = 3    # nó substituído on-demand durante este tempo, por interrupção
    scale_to_zero_below_docs_per_minute: float | None = None  # zera réplicas se demanda <= limiar e sem backlog

    def __post_init__(self):
        for name, v in asdict(self).items():
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)):
                raise ValueError(f"{name} deve ser um número finito.")
        if min(self.node_vcpu, self.node_mem_gib, self.pod_vcpu, self.pod_mem_gib) <= 0:
            raise ValueError("vCPU e memória devem ser positivos.")
        if not 0 <= self.spot_fraction <= 1:
            raise ValueError("spot_fraction deve estar em [0, 1].")
        if self.interruption_per_node_hour < 0 or self.interruption_replace_minutes < 0:
            raise ValueError("interrupção não pode ser negativa.")
        if self.scale_to_zero_below_docs_per_minute is not None and self.scale_to_zero_below_docs_per_minute < 0:
            raise ValueError("limiar de scale-to-zero não pode ser negativo.")
        if self.pods_per_node < 1:
            raise ValueError("A réplica não cabe em um nó.")

    @property
    def pods_per_node(self) -> int:
        return int(min(self.node_vcpu // self.pod_vcpu, self.node_mem_gib // self.pod_mem_gib))


def extended_cost(run: dict, model: FinopsModel = FinopsModel(), prices: dict = PRICE_TABLE) -> dict:
    """Bin-packing de réplicas idênticas: nós = ceil(réplicas / pods_por_nó). Custos em valores esperados (estimated)."""
    hours = run["config"]["tick_minutes"] / 60
    per_node = model.pods_per_node
    nodes_total = used = idle = 0.0
    zero_ticks = cold_starts = 0
    was_zero = False
    for t in run["ticks"]:
        replicas = t["provisioned_replicas"]
        zero = (model.scale_to_zero_below_docs_per_minute is not None and t["backlog_docs"] == 0
                and t["demand_docs_per_minute"] <= model.scale_to_zero_below_docs_per_minute)
        if zero:
            replicas = 0
            zero_ticks += 1
        elif was_zero:
            cold_starts += 1
        was_zero = zero
        nodes = math.ceil(replicas / per_node)
        nodes_total += nodes * hours
        used += replicas / per_node * hours
    od, spot = prices["on_demand_brl_per_node_hour"], prices["spot_brl_per_node_hour"]
    blended = model.spot_fraction * spot + (1 - model.spot_fraction) * od
    node_cost = nodes_total * blended
    idle_cost = (nodes_total - used) * blended
    interruptions = nodes_total * model.spot_fraction * model.interruption_per_node_hour
    interruption_cost = interruptions * model.interruption_replace_minutes / 60 * od
    return {"labels": {"prices": "hypothetical", "cost": "estimated", "demand": "synthetic",
                       "note": "pós-processamento da execução simulada; não é faturamento"},
            "model": asdict(model), "prices": dict(prices), "policy": run["policy"], "pods_per_node": per_node,
            "node_hours": nodes_total, "used_node_hours": used, "idle_node_hours": nodes_total - used,
            "node_cost_brl": node_cost, "idle_cost_brl": idle_cost,
            "expected_interruptions": interruptions, "interruption_cost_brl": interruption_cost,
            "total_cost_brl": node_cost + interruption_cost, "zero_ticks": zero_ticks, "cold_starts": cold_starts}
