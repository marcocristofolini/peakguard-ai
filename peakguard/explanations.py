"""Explicações limitadas a evidências calculadas; nenhuma autoridade de execução."""

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .rules import RULES, Rules


class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    id: str = Field(max_length=100)
    value: float


class Proposal(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    policy: Literal['reactive', 'anticipatory']
    claims: list[Claim] = Field(min_length=1, max_length=20)
    hypotheses: list[Literal['forecast_may_be_wrong']] = Field(max_length=1)
    rationale: str | None = Field(None, max_length=600)  # texto livre da LLM; só passa se fiel às evidências


METRICS = {
    'cost_brl': ('BRL', 'estimated'),
    'cost_brl_per_1000_docs': ('BRL/1000 documentos', 'estimated'),
    'max_backlog_docs': ('documentos', 'estimated'),
    'slo_violation_minutes': ('minutos', 'estimated'),
    'saturated_minutes': ('minutos', 'estimated'),
    'forecast_mae_docs_per_minute': ('documentos/minuto', 'estimated'),
    'processed_docs': ('documentos', 'estimated'),
}


def evidence(comparison: dict) -> dict:
    facts, limits, timelines = {}, {}, {}
    for policy, run in comparison['results'].items():
        limits[policy] = {k: run['config'][k] for k in
                          ('min_replicas', 'max_replicas', 'budget_brl', 'slo_queue_minutes')}
        for metric, (unit, label) in METRICS.items():
            facts[f'{policy}.{metric}'] = {'value': run['summary'][metric], 'unit': unit, 'label': label}
        timelines[policy] = [{k: tick[k] for k in ('tick', 'demand_docs_per_minute',
            'predicted_docs_per_minute', 'capacity_docs_per_minute', 'backlog_docs',
            'active_replicas', 'provisioned_replicas', 'slo_violated')} for tick in run['ticks']]
    return {'facts': facts, 'limits': limits, 'timelines': timelines, 'observed': [],
            'labels': {'demand': 'synthetic', 'forecast': 'predicted', 'simulation': 'estimated'},
            'hypotheses': {'forecast_may_be_wrong': 'A previsão pode divergir da demanda futura; hipótese, não observação.'}}


NUMBER = re.compile(r'(?<![\w.,])\d+(?:[.,]\d+)?(?!\w)')
URL = re.compile(r'https?://|www\.', re.I)


def _numbers(node):
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        yield float(node)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _numbers(v)
    elif isinstance(node, list):
        for v in node:
            yield from _numbers(v)


def check_fidelity(text: str, context: dict) -> list[str]:
    """Números do texto ausentes das evidências (arredondamento às casas escritas é aceito)."""
    known = list(_numbers(context))
    missing = []
    for token in NUMBER.findall(text):
        decimals = len(token) - max(token.find('.'), token.find(',')) - 1 if ('.' in token or ',' in token) else 0
        value = float(token.replace(',', '.'))
        if not any(round(k, decimals) == value for k in known):
            missing.append(token)
    return missing


def _safety(run, rules: Rules = None):
    rules = rules or RULES
    config, ticks = run['config'], run['ticks']
    reasons = []
    low, high = rules.replicas.min, rules.replicas.max
    if config['min_replicas'] < low or config['max_replicas'] > high or any(
            not max(config['min_replicas'], low) <= t['active_replicas'] <= t['provisioned_replicas'] <= min(config['max_replicas'], high) for t in ticks):
        reasons.append('replicas')
    if max(run['summary']['cost_brl'], sum(t['cost_brl'] for t in ticks)) > min(config['budget_brl'], rules.budget_brl_max) + 1e-12:
        reasons.append('budget')
    tolerated = rules.slo.violation_minutes_max
    if run['summary']['slo_violation_minutes'] > tolerated or (tolerated == 0 and any(
            t['slo_violated'] or t['queue_wait_minutes'] > config['slo_queue_minutes'] for t in ticks)):
        reasons.append('slo')
    return reasons


def validate_proposal(raw, comparison: dict, rules: Rules = None) -> dict:
    rules = rules or RULES
    try:
        proposal = Proposal.model_validate(raw)
    except (ValidationError, TypeError):
        return {'accepted': False, 'reasons': ['invalid_response']}
    context = evidence(comparison)
    facts = context['facts']
    reasons = _safety(comparison['results'][proposal.policy], rules)
    if any(c.id not in facts or c.value != facts[c.id]['value'] for c in proposal.claims):
        reasons.append('unsupported_evidence')
    if sum(c.id.startswith(proposal.policy + '.') for c in proposal.claims) < rules.evidence.min_policy_claims:
        reasons.append('missing_policy_evidence')
    if proposal.rationale and (check_fidelity(proposal.rationale, context) or URL.search(proposal.rationale)):
        reasons.append('unfaithful_numbers' if check_fidelity(proposal.rationale, context) else 'forbidden_content')
    return {'accepted': not reasons, 'reasons': reasons}


def _fallback(comparison):
    safe = [p for p, run in comparison['results'].items() if not _safety(run)]
    if not safe:
        return None
    policy = min(safe, key=lambda p: (comparison['results'][p]['summary']['cost_brl'], p != 'reactive'))
    return {'policy': policy, 'claims': [{'id': f'{policy}.{key}', 'value': comparison['results'][policy]['summary'][key]}
                                       for key in ('cost_brl', 'slo_violation_minutes')], 'hypotheses': ['forecast_may_be_wrong']}


def explain(comparison: dict, *, provider=None, use_llm: bool = False) -> dict:
    context = evidence(comparison)
    digest = hashlib.sha256(json.dumps(context, sort_keys=True, allow_nan=False).encode()).hexdigest()
    audit, selected, mode = [], None, 'offline'
    if use_llm:
        try:
            if provider is None:
                from .llm import generate
                provider = generate
            raw = provider(context)
            validation = validate_proposal(raw, comparison)
            audit.append({'source': 'llm', 'status': 'accepted' if validation['accepted'] else 'rejected', **validation})
            if validation['accepted']:
                selected, mode = Proposal.model_validate(raw).model_dump(), 'llm'
        except Exception:
            # Falhas externas não expõem corpo de resposta, credenciais ou mensagens do provedor.
            audit.append({'source': 'llm', 'status': 'rejected', 'accepted': False, 'reasons': ['provider_unavailable']})
        if selected is None:
            mode = 'fallback'
    if selected is None:
        selected = _fallback(comparison)
        validation = validate_proposal(selected, comparison) if selected else {'accepted': False, 'reasons': ['no_safe_policy']}
        audit.append({'source': 'deterministic', 'status': 'accepted' if validation['accepted'] else 'abstained', **validation})
    details = []
    for policy, run in comparison['results'].items():
        s = run['summary']
        details.append(f"{policy}: custo estimado BRL {s['cost_brl']:.4f}; saturação {s['saturated_minutes']} min; "
                       f"violação de SLO {s['slo_violation_minutes']} min; backlog máximo {s['max_backlog_docs']} documentos.")
    text = ('Alternativa validada: ' + selected['policy'] + '. Comparar custo, saturação e fila antes de decidir.'
            if selected else 'Nenhuma alternativa segura para todos os limites nesta simulação; revisar parâmetros.')
    justification = [f"{c['id']}: {c['value']} {context['facts'][c['id']]['unit']} "
                     f"({context['facts'][c['id']]['label']})." for c in selected['claims']] if selected else []
    rationale = {'rationale': selected['rationale']} if mode == 'llm' and selected.get('rationale') else {}
    return {**rationale, 'mode': mode, 'proposal': selected, 'explanation': text, 'alternatives': details,
            'justification': justification,
            'evidence': context, 'evidence_sha256': digest, 'audit': audit,
            'execution_allowed': False, 'human_approval_required': True}
