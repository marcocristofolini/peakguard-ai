import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from peakguard import explanations
from peakguard.api import app
from peakguard.explanations import check_fidelity, evidence, explain, validate_proposal
from peakguard.manifest import manifest_diff
from peakguard.rules import RULES, load_rules
from peakguard.scenarios import load_scenario
from peakguard.simulator import Config, compare

INJECTIONS = json.loads((Path(__file__).parent / "fixtures" / "prompt_injection.json").read_text())


def comparison(name="stable", **config):
    return compare(load_scenario(name, 42), Config(**config))


def proposal(policy="reactive", rationale=None):
    p = {"policy": policy, "claims": [{"id": policy + ".cost_brl", "value": 0.48000000000000015}], "hypotheses": []}
    return {**p, "rationale": rationale} if rationale is not None else p


# 1. regras YAML
def test_default_rules_loaded_and_validated():
    assert RULES.replicas.min == 1 and RULES.slo.violation_minutes_max == 0 and RULES.evidence.min_policy_claims == 1


@pytest.mark.parametrize("text", ["version: 1\n", "[]", "version: 1\nreplicas: {min: 0, max: 5}\nbudget_brl_max: 1\nslo: {violation_minutes_max: 0}\nevidence: {min_policy_claims: 1}",
                                  "version: 1\nreplicas: {min: 5, max: 2}\nbudget_brl_max: 1\nslo: {violation_minutes_max: 0}\nevidence: {min_policy_claims: 1}",
                                  "version: 1\nextra: 1\nreplicas: {min: 1, max: 2}\nbudget_brl_max: 1\nslo: {violation_minutes_max: 0}\nevidence: {min_policy_claims: 1}",
                                  "version: 1\nreplicas: {min: 1, max: 2}\nbudget_brl_max: -1\nslo: {violation_minutes_max: 0}\nevidence: {min_policy_claims: 1}",
                                  "a: [unclosed"])
def test_invalid_rules_fail_fast(text, tmp_path):
    path = tmp_path / "r.yaml"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_rules(path)
    with pytest.raises(ValueError):
        load_rules(tmp_path / "missing.yaml")


def rules_from(tmp_path, replicas="{min: 1, max: 1000}", budget=1e9, slo=0, claims=1):
    path = tmp_path / "r.yaml"
    path.write_text(f"version: 1\nreplicas: {replicas}\nbudget_brl_max: {budget}\nslo: {{violation_minutes_max: {slo}}}\nevidence: {{min_policy_claims: {claims}}}\n")
    return load_rules(path)


def test_rules_drive_validator(tmp_path):
    c = comparison()
    assert validate_proposal(proposal(), c)["accepted"]
    assert "replicas" in validate_proposal(proposal(), c, rules_from(tmp_path, replicas="{min: 1, max: 5}"))["reasons"]
    assert "budget" in validate_proposal(proposal(), c, rules_from(tmp_path, budget=0.01))["reasons"]
    assert "missing_policy_evidence" in validate_proposal(proposal(), c, rules_from(tmp_path, claims=2))["reasons"]
    wrong = comparison("unexpected_peak")
    prop = proposal("anticipatory")
    prop["claims"] = [{"id": "anticipatory.slo_violation_minutes", "value": wrong["results"]["anticipatory"]["summary"]["slo_violation_minutes"]}]
    assert "slo" in validate_proposal(prop, wrong)["reasons"]
    assert "slo" not in validate_proposal(prop, wrong, rules_from(tmp_path, slo=100))["reasons"]


# 3. fidelidade
def test_fidelity_accepts_evidence_numbers_and_rounding():
    ctx = evidence(comparison())
    cost = ctx["facts"]["reactive.cost_brl"]["value"]
    assert check_fidelity(f"Custo estimado de BRL {cost:.2f} (reactive.cost_brl_per_1000_docs).", ctx) == []
    assert check_fidelity(f"Custo {str(round(cost, 2)).replace('.', ',')} até o passo 23", ctx) == []
    assert check_fidelity("Sem números.", ctx) == []


def test_fidelity_flags_invented_numbers():
    ctx = evidence(comparison())
    assert check_fidelity("Economia de 87% e custo 12345,67.", ctx) == ["87", "12345,67"]


def test_invented_number_in_llm_text_falls_back_to_deterministic():
    result = explain(comparison(), provider=lambda _: proposal(rationale="Economia de 87% garantida."), use_llm=True)
    assert result["mode"] == "fallback"
    assert "unfaithful_numbers" in result["audit"][0]["reasons"]
    assert result["execution_allowed"] is False and result["audit"][-1]["source"] == "deterministic"
    assert "rationale" not in result


def test_faithful_rationale_is_accepted_and_returned():
    cost = comparison()["results"]["reactive"]["summary"]["cost_brl"]
    result = explain(comparison(), provider=lambda _: proposal(rationale=f"Custo estimado BRL {cost:.2f}."), use_llm=True)
    assert result["mode"] == "llm" and result["rationale"].startswith("Custo estimado")


@pytest.mark.parametrize("text", INJECTIONS["invented_number"] + INJECTIONS["exfiltration"])
def test_prompt_injection_fixtures_rejected(text):
    result = explain(comparison(), provider=lambda _: proposal(rationale=text), use_llm=True)
    assert result["mode"] == "fallback" and result["audit"][0]["accepted"] is False
    assert result["execution_allowed"] is False and result["human_approval_required"] is True


@pytest.mark.parametrize("text", INJECTIONS["no_authority"])
def test_prompt_injection_without_numbers_gains_no_authority(text):
    c = comparison()
    seen = []
    result = explain(c, provider=lambda ctx: seen.append(ctx) or proposal(rationale=text), use_llm=True)
    assert result["execution_allowed"] is False and result["human_approval_required"] is True
    assert result["proposal"]["policy"] == "reactive" and result["proposal"]["claims"][0]["id"].startswith("reactive.")
    assert text not in json.dumps(seen)  # entrada ao modelo vem só das evidências calculadas


def test_injection_cannot_expand_proposal_fields():
    bad = {**proposal(), "rationale": "ok", "replicas": 5000, "command": "kubectl apply"}
    result = explain(comparison(), provider=lambda _: bad, use_llm=True)
    assert result["mode"] == "fallback"


# 2. manifesto
KW = dict(name="documents", namespace="demo")


@pytest.mark.parametrize("kind,api,key", [("hpa", "autoscaling/v2", "minReplicas"), ("scaledobject", "keda.sh/v1alpha1", "minReplicaCount")])
def test_manifest_diff_from_approved_proposal(kind, api, key):
    c = comparison(min_replicas=2, initial_replicas=2, max_replicas=7, target_utilization=0.7)
    result = explain(c)
    out = manifest_diff(result, c, kind=kind, **KW)
    doc = yaml.safe_load(out["proposed_manifest"])
    assert doc["apiVersion"] == api and doc["metadata"] == {"name": "documents", "namespace": "demo"}
    assert doc["spec"][key] == 2 and doc["spec"][key.replace("min", "max")] == 7
    assert out["applied"] is False and out["requires_human_review"] is True
    assert out["diff"].startswith("--- ") and "+" in out["diff"] and out["source"]["policy"] == result["proposal"]["policy"]
    assert out["labels"]["values"] == "estimated"


def test_manifest_diff_against_current_manifest_changes_only_limits():
    c = comparison(max_replicas=7)
    current = yaml.safe_dump({"apiVersion": "autoscaling/v2", "kind": "HorizontalPodAutoscaler",
                              "metadata": {"name": "documents", "namespace": "demo"},
                              "spec": {"scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": "documents"},
                                       "minReplicas": 1, "maxReplicas": 3,
                                       "metrics": [{"type": "Resource", "resource": {"name": "cpu", "target": {"type": "Utilization", "averageUtilization": 80}}}]}},
                             sort_keys=False)
    out = manifest_diff(explain(c), c, kind="hpa", current=current, **KW)
    changed = [l for l in out["diff"].splitlines() if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    assert changed == ["-  maxReplicas: 3", "+  maxReplicas: 7"]


def test_manifest_requires_approved_proposal_and_valid_names():
    c = comparison("unexpected_peak", budget_brl=1.0)
    result = explain(c)
    if result["proposal"] is None:
        with pytest.raises(ValueError, match="proposta"):
            manifest_diff(result, c, kind="hpa", **KW)
    with pytest.raises(ValueError):
        manifest_diff(explain(comparison()), comparison(), kind="hpa", name="Bad Name; rm -rf", namespace="demo")
    with pytest.raises(ValueError):
        manifest_diff(explain(comparison()), comparison(), kind="deployment", **KW)
    with pytest.raises(ValueError):
        manifest_diff(explain(comparison()), comparison(), kind="hpa", current="kind: Service\n", **KW)


def test_manifest_never_touches_kubernetes_or_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("acesso externo proibido")
    monkeypatch.setitem(sys.modules, "kubernetes", None)  # import levantaria ImportError
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    c = comparison()
    for kind in ("hpa", "scaledobject"):
        assert manifest_diff(explain(c), c, kind=kind, **KW)["applied"] is False
    source = (Path(__file__).parents[1] / "peakguard" / "manifest.py").read_text()
    assert not any(word in source.lower() for word in ("kubernetes", "subprocess", "kubectl", "socket", "requests"))


def test_api_manifest_diff():
    client = TestClient(app)
    body = {"scenario": "predictable_peak", "kind": "scaledobject", "name": "documents", "namespace": "demo"}
    r = client.post("/manifest-diff", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is False and "ScaledObject" in r.json()["proposed_manifest"]
    assert client.post("/manifest-diff", json={**body, "kind": "pod"}).status_code == 422
    assert client.post("/manifest-diff", json={**body, "name": "Ruim!"}).status_code == 422


# 4. usage do adaptador
def test_generate_reports_usage_without_leaking_key(monkeypatch):
    import types
    from peakguard import llm
    class Usage: prompt_tokens, completion_tokens = 11, 7
    class Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        class chat:
            class completions:
                @staticmethod
                def parse(**kw):
                    parsed = types.SimpleNamespace(model_dump=lambda: proposal())
                    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(parsed=parsed))], usage=Usage)
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=Client))
    for k, v in {"PEAKGUARD_LLM_ENABLED": "true", "OPENAI_API_KEY": "sk-secret-test", "PEAKGUARD_LLM_MODEL": "m"}.items():
        monkeypatch.setenv(k, v)
    usage = {}
    out = llm.generate(evidence(comparison()), usage=usage)
    assert out["policy"] == "reactive" and usage == {"prompt_tokens": 11, "completion_tokens": 7}
    assert "sk-secret-test" not in json.dumps(usage)
