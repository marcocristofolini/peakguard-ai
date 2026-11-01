import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from peakguard.api import app

client = TestClient(app)


def test_scenarios_and_openapi():
    assert set(client.get('/scenarios').json()) == {'stable', 'predictable_peak', 'unexpected_peak', 'wrong_forecast'}
    assert client.get('/openapi.json').status_code == 200
    assert client.get('/docs').status_code == 200


@pytest.mark.parametrize('policy', ['reactive', 'anticipatory'])
def test_simulation_matches_cli(policy):
    response = client.post('/simulations', json={'scenario': 'wrong_forecast', 'seed': 42, 'policy': policy})
    assert response.status_code == 200, response.text
    cli = subprocess.check_output([sys.executable, '-m', 'peakguard', 'run', 'wrong_forecast', '--seed', '42', '--policy', policy])
    assert response.json() == json.loads(cli)


def test_comparison_matches_cli_with_parameters():
    request = {'scenario': 'predictable_peak', 'seed': 3, 'config': {'max_replicas': 3, 'tick_minutes': 0.5}}
    response = client.post('/comparisons', json=request)
    assert response.status_code == 200, response.text
    cli = subprocess.check_output([sys.executable, '-m', 'peakguard', 'compare', 'predictable_peak', '--seed', '3', '--max-replicas', '3', '--tick-minutes', '0.5'])
    assert response.json() == json.loads(cli)


@pytest.mark.parametrize('payload', [
    {'scenario': 'missing'}, {'scenario': 'stable', 'policy': 'invalid'},
    {'scenario': 'stable', 'config': {'tick_minutes': -1}},
    {'scenario': 'stable', 'config': {'max_replicas': 100000000}},
    {'scenario': 'stable', 'config': {'budget_brl': 0}},
    {'scenario': 'stable', 'config': {'min_replicas': 2}},
    {'scenario': 'stable', 'config': {'unexpected': 1}},
    {'scenario': 'stable', 'seed': True},
])
def test_reject_invalid_requests(payload):
    assert client.post('/simulations', json=payload).status_code == 422


def test_offline_explanations_and_read_only_evidence():
    payload = {'scenario': 'stable', 'seed': 42}
    result = client.post('/explanations', json=payload)
    assert result.status_code == 200
    data = result.json()
    assert data['mode'] == 'offline'
    assert data['execution_allowed'] is False
    facts = client.post('/evidence', json=payload)
    assert facts.status_code == 200
    assert facts.json() == data['evidence']
    assert facts.json()['observed'] == []


def test_explanations_reject_client_supplied_results():
    assert client.post('/explanations', json={'scenario': 'stable', 'results': {}}).status_code == 422
