"""Diff de manifesto HPA/ScaledObject para PR. Só gera texto: nada é aplicado nem consultado no cluster."""

import difflib
import math
import re
from datetime import datetime, timedelta, timezone

import yaml

KINDS = ("hpa", "scaledobject")
DNS_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")


def _document(kind: str, name: str, namespace: str, config: dict) -> dict:
    meta = {"name": name, "namespace": namespace}
    low, high = config["min_replicas"], config["max_replicas"]
    percent = round(config["target_utilization"] * 100)
    if kind == "hpa":
        return {"apiVersion": "autoscaling/v2", "kind": "HorizontalPodAutoscaler", "metadata": meta,
                "spec": {"scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": name},
                         "minReplicas": low, "maxReplicas": high,
                         "metrics": [{"type": "Resource", "resource": {"name": "cpu",
                                      "target": {"type": "Utilization", "averageUtilization": percent}}}]}}
    return {"apiVersion": "keda.sh/v1alpha1", "kind": "ScaledObject", "metadata": meta,
            "spec": {"scaleTargetRef": {"name": name}, "minReplicaCount": low, "maxReplicaCount": high,
                     "triggers": [{"type": "cpu", "metricType": "Utilization", "metadata": {"value": str(percent)}}]}}


def _minute(moment: datetime, up: bool) -> datetime:
    floor = moment.replace(second=0, microsecond=0)
    return floor + timedelta(minutes=1) if up and floor < moment else floor


def cron_windows(predicted: list, config: dict, start: datetime) -> list[dict]:
    """Janelas do calendário previsto (ticks que exigem > min réplicas), antecipadas em `forecast_horizon_ticks`.
    O cron do KEDA tem resolução de minuto: início arredondado para baixo, fim para cima."""
    dt = timedelta(minutes=config["tick_minutes"])
    unit = config["capacity_docs_per_minute_per_replica"] * config["target_utilization"]
    need = [min(config["max_replicas"], max(config["min_replicas"], math.ceil(p / unit))) for p in predicted]
    windows, tick = [], 0
    while tick < len(need):
        if need[tick] <= config["min_replicas"]:
            tick += 1
            continue
        end = tick
        while end < len(need) and need[end] > config["min_replicas"]:
            end += 1
        begin = _minute(start + tick * dt - config["forecast_horizon_ticks"] * dt, up=False)
        finish = max(_minute(start + end * dt, up=True), begin + timedelta(minutes=1))
        windows.append({"start": begin.isoformat(), "end": finish.isoformat(), "desired_replicas": max(need[tick:end]),
                        "first_tick": tick, "end_tick": end})
        tick = end
    return windows


def _cron(moment: str) -> str:
    m = datetime.fromisoformat(moment)
    return f"{m.minute} {m.hour} {m.day} {m.month} *"


def manifest_diff(result: dict, comparison: dict, *, kind: str, name: str, namespace: str = "default",
                  current: str | None = None, schedule_start: datetime | None = None) -> dict:
    """`result`: saída de `explain` (proposta já validada pelas regras). `current`: manifesto atual do repositório.
    `schedule_start` (com fuso): instante do tick 0; acrescenta ao ScaledObject gatilhos `cron` do calendário previsto."""
    if kind not in KINDS:
        raise ValueError(f"kind deve ser um de {KINDS}")
    if schedule_start is not None and (kind != "scaledobject" or schedule_start.utcoffset() is None):
        raise ValueError("schedule_start exige kind scaledobject e data/hora com fuso.")
    if not DNS_LABEL.match(name) or not DNS_LABEL.match(namespace):
        raise ValueError("name e namespace devem ser rótulos DNS-1123.")
    proposal = result.get("proposal")
    if not proposal or not result["audit"][-1]["accepted"]:
        raise ValueError("Sem proposta aprovada pelo validador; nenhum manifesto gerado.")
    document = _document(kind, name, namespace, comparison["results"][proposal["policy"]]["config"])
    windows = None
    if schedule_start is not None:
        # Calendário declarado (previsão) do cenário, igual nas duas políticas; o CPU continua como piso reativo.
        anticipatory = comparison["results"]["anticipatory"]
        windows = cron_windows(anticipatory["input"]["predicted_docs_per_minute"], anticipatory["config"],
                               schedule_start.astimezone(timezone.utc))
        document["spec"]["triggers"] += [{"type": "cron", "metadata": {
            "timezone": "Etc/UTC", "start": _cron(w["start"]), "end": _cron(w["end"]),
            "desiredReplicas": str(w["desired_replicas"])}} for w in windows]
    if current:
        try:
            existing = yaml.safe_load(current)
        except yaml.YAMLError as error:
            raise ValueError("Manifesto atual não é YAML válido.") from error
        if not isinstance(existing, dict) or existing.get("kind") != document["kind"]:
            raise ValueError(f"Manifesto atual deve ser um {document['kind']}.")
    proposed = yaml.safe_dump(document, sort_keys=False)
    before = yaml.safe_dump(existing, sort_keys=False) if current else ""
    path = f"{name}-{kind}.yaml"
    diff = "".join(difflib.unified_diff(before.splitlines(True), proposed.splitlines(True),
                                        fromfile=f"a/{path}" if current else "/dev/null", tofile=f"b/{path}"))
    return {"kind": document["kind"], "path": path, "proposed_manifest": proposed, "diff": diff,
            "source": {"policy": proposal["policy"], "evidence_sha256": result["evidence_sha256"]},
            "schedule": {"windows": windows} if windows is not None else None,
            "applied": False, "requires_human_review": True,
            "labels": {"values": "estimated", "demand": "synthetic",
                       "note": "Proposta de simulação sintética; revisar em PR antes de qualquer aplicação."}}
