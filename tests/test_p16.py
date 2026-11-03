import pytest
from fastapi.testclient import TestClient

from peakguard.api import app

client = TestClient(app)
BASE = {'scenario': 'fiscal_irpf_april', 'seed': 7}
ENDPOINTS = ['/simulations', '/comparisons', '/evidence', '/error-budget', '/pareto', '/finops', '/explanations']


def post(path, **extra):
    body = {**BASE, **extra}
    if path == '/finops':
        body['finops'] = {}
    return client.post(path, json=body)


@pytest.mark.parametrize('arrivals', ['poisson', 'burst'])
def test_same_seed_same_arrivals_same_response(arrivals):
    a, b = post('/comparisons', arrivals=arrivals), post('/comparisons', arrivals=arrivals)
    assert a.status_code == 200, a.text
    assert a.json() == b.json()
    assert a.json() != post('/comparisons').json()


def test_default_equals_explicit_deterministic():
    assert post('/comparisons').json() == post('/comparisons', arrivals='deterministic').json()


@pytest.mark.parametrize('path', ENDPOINTS)
def test_invalid_arrivals_is_422(path):
    response = post(path, arrivals='gaussian')
    assert response.status_code == 422, path


def test_arrivals_matches_cli_loader():
    from peakguard.scenarios import load_scenario
    demand = [t['demand_docs_per_minute'] for t in post('/simulations', arrivals='poisson').json()['ticks']]
    assert demand == list(load_scenario('fiscal_irpf_april', 7, 'poisson').demand_docs_per_minute)


def test_pareto_uses_arrivals():
    assert post('/pareto', arrivals='poisson').json() != post('/pareto').json()


def test_ewma_window_exposed_and_validated():
    assert post('/simulations', ewma_window=3).status_code == 200
    assert post('/simulations', ewma_window=3).json() != post('/simulations').json()
    assert post('/simulations', ewma_window=0).status_code == 422


def test_decision_delay_in_config():
    assert post('/simulations', config={'decision_delay_ticks': 2}).json()['config']['decision_delay_ticks'] == 2
    assert post('/simulations', config={'decision_delay_ticks': -1}).status_code == 422
