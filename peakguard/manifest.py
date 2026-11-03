"""Diff de manifesto HPA/ScaledObject para PR. Só gera texto: nada é aplicado nem consultado no cluster."""

import difflib
import re

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


def manifest_diff(result: dict, comparison: dict, *, kind: str, name: str, namespace: str = "default",
                  current: str | None = None) -> dict:
    """`result`: saída de `explain` (proposta já validada pelas regras). `current`: manifesto atual do repositório."""
    if kind not in KINDS:
        raise ValueError(f"kind deve ser um de {KINDS}")
    if not DNS_LABEL.match(name) or not DNS_LABEL.match(namespace):
        raise ValueError("name e namespace devem ser rótulos DNS-1123.")
    proposal = result.get("proposal")
    if not proposal or not result["audit"][-1]["accepted"]:
        raise ValueError("Sem proposta aprovada pelo validador; nenhum manifesto gerado.")
    document = _document(kind, name, namespace, comparison["results"][proposal["policy"]]["config"])
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
            "applied": False, "requires_human_review": True,
            "labels": {"values": "estimated", "demand": "synthetic",
                       "note": "Proposta de simulação sintética; revisar em PR antes de qualquer aplicação."}}
