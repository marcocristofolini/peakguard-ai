from copy import deepcopy

import pytest

from peakguard.explanations import explain, evidence, validate_proposal
from peakguard.scenarios import load_scenario
from peakguard.simulator import Config, compare


def comparison(name='stable'):
    return compare(load_scenario(name, 42), Config())


def proposal(policy='reactive'):
    return {'policy': policy, 'claims': [{'id': policy + '.cost_brl', 'value': 0.48000000000000015}], 'hypotheses': []}


def test_offline_is_deterministic_and_never_calls_provider():
    def forbidden(_):
        raise AssertionError('must not call')
    assert explain(comparison()) == explain(comparison(), provider=forbidden, use_llm=False)
    assert explain(comparison())['mode'] == 'offline'
    assert explain(comparison())['proposal']['policy'] == 'reactive'


def test_valid_model_proposal_is_grounded_and_has_no_write_authority():
    source = comparison()
    original = deepcopy(source)
    result = explain(source, provider=lambda _: proposal(), use_llm=True)
    assert result['mode'] == 'llm'
    assert result['proposal']['policy'] == 'reactive'
    assert result['execution_allowed'] is False
    assert source == original


@pytest.mark.parametrize('response', [None, 'not json', {'policy': 'reactive'},
    {**proposal(), 'explanation': 'real savings'},
    {**proposal(), 'claims': [{'id': 'reactive.cost_brl', 'value': 100}]},
    {**proposal(), 'claims': [{'id': 'production.observed', 'value': 1}]},
    {**proposal(), 'replicas': 99999},
])
def test_invalid_or_unsupported_response_falls_back(response):
    result = explain(comparison(), provider=lambda _: response, use_llm=True)
    assert result['mode'] == 'fallback'
    assert result['audit'][0]['status'] == 'rejected'
    assert 'not json' not in str(result)


def test_provider_failure_does_not_leak_exception_or_secret():
    def broken(_):
        raise RuntimeError('secret-token')
    result = explain(comparison(), provider=broken, use_llm=True)
    assert result['mode'] == 'fallback'
    assert 'secret-token' not in str(result)


@pytest.mark.parametrize('kind', ['budget', 'slo', 'replicas'])
def test_deterministic_rules_reject_unsafe_alternative(kind):
    data = comparison()
    run = data['results']['reactive']
    if kind == 'budget':
        run['summary']['cost_brl'] = 11
    elif kind == 'slo':
        run['summary']['slo_violation_minutes'] = 1
    else:
        run['ticks'][0]['provisioned_replicas'] = 11
    p = proposal()
    p['claims'][0]['value'] = run['summary']['cost_brl']
    assert kind in validate_proposal(p, data)['reasons']


def test_no_safe_policy_abstains_even_offline():
    result = explain(comparison('unexpected_peak'))
    assert result['proposal'] is None
    assert 'segura' in result['explanation']


def test_evidence_read_is_detached_and_labels_are_honest():
    data = comparison()
    facts = evidence(data)
    assert facts['observed'] == []
    assert facts['facts']['reactive.cost_brl']['label'] == 'estimated'
    facts['facts']['reactive.cost_brl']['value'] = 999
    assert data['results']['reactive']['summary']['cost_brl'] == pytest.approx(.48)


def test_unsafe_llm_selection_falls_back_to_safe_policy():
    data = comparison('predictable_peak')
    raw = {'policy': 'reactive', 'claims': [{'id': 'reactive.cost_brl', 'value': data['results']['reactive']['summary']['cost_brl']}], 'hypotheses': []}
    result = explain(data, provider=lambda _: raw, use_llm=True)
    assert result['mode'] == 'fallback'
    assert result['proposal']['policy'] == 'anticipatory'
    assert 'slo' in result['audit'][0]['reasons']


def test_missing_configuration_falls_back_without_network(monkeypatch):
    monkeypatch.delenv('PEAKGUARD_LLM_ENABLED', raising=False)
    assert explain(comparison(), use_llm=True)['mode'] == 'fallback'


def test_real_sdk_adapter_uses_structured_output_and_only_whitelisted_context(monkeypatch):
    import json
    import httpx
    openai = pytest.importorskip('openai')
    from peakguard.llm import generate
    monkeypatch.setenv('PEAKGUARD_LLM_ENABLED', 'true')
    monkeypatch.setenv('PEAKGUARD_LLM_MODEL', 'test-model')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-secret')
    requests = []
    def transport(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'test-model',
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps(proposal())}}],
        })
    original = openai.OpenAI
    monkeypatch.setattr(openai, 'OpenAI', lambda **kw: original(**kw, http_client=httpx.Client(transport=httpx.MockTransport(transport))))
    result = explain(comparison(), provider=generate, use_llm=True)
    assert result['mode'] == 'llm'
    assert requests[0]['store'] is False
    assert 'tools' not in requests[0]
    assert requests[0]['response_format']['type'] == 'json_schema'
    assert 'test-secret' not in json.dumps(requests)


def test_compatible_provider_uses_json_object_with_schema_in_prompt(monkeypatch):
    import json
    import httpx
    openai = pytest.importorskip('openai')
    from peakguard.llm import generate
    for k, v in {'PEAKGUARD_LLM_ENABLED': 'true', 'PEAKGUARD_LLM_MODEL': 'test-model', 'OPENAI_API_KEY': 'test-secret',
                 'PEAKGUARD_LLM_BASE_URL': 'https://compat.example'}.items():
        monkeypatch.setenv(k, v)
    requests = []
    def transport(request):
        requests.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json={
            'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'test-model',
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps(proposal())}}],
            'usage': {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10}})
    original = openai.OpenAI
    monkeypatch.setattr(openai, 'OpenAI', lambda **kw: original(**kw, http_client=httpx.Client(transport=httpx.MockTransport(transport))))
    usage = {}
    result = explain(comparison(), provider=lambda ctx: generate(ctx, usage=usage), use_llm=True)
    url, body = requests[0]
    assert result['mode'] == 'llm' and url.startswith('https://compat.example')
    assert body['response_format'] == {'type': 'json_object'} and 'store' not in body and 'tools' not in body
    assert '"properties"' in body['messages'][0]['content'] and 'test-secret' not in json.dumps(body)
    assert usage == {'prompt_tokens': 7, 'completion_tokens': 3}
