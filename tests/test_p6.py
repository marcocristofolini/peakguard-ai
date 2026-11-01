import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('p6work', Path(__file__).parents[1] / 'local/p6/workload.py')
work = importlib.util.module_from_spec(spec)
spec.loader.exec_module(work)


def test_queue_limits_processing_and_metrics():
    queue = work.Workload(capacity=1, work_seconds=0)
    assert queue.submit() is True
    assert queue.submit() is False
    assert queue.process_one() is True
    assert queue.process_one() is False
    metrics = queue.metrics()
    assert 'documents_submitted_total 1' in metrics
    assert 'documents_processed_total 1' in metrics
    assert 'documents_rejected_total 1' in metrics
    assert 'documents_backlog 0' in metrics


def test_observation_validation_rejects_zero_prometheus_targets():
    import pytest
    spec = importlib.util.spec_from_file_location('p6experiment', Path(__file__).parents[1] / 'local/p6/experiment.py')
    experiment = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(experiment)
    def sample(targets):
        return {'ready_replicas': 4, 'queries': {k: {'data': {'result': [{'value': [0, str(v)]}]}}
                 for k, v in [('targets', targets), ('processed', 10)]}}
    good = {'load': [{}] * 13, 'samples': [sample(1)]}
    experiment.verify(good)
    with pytest.raises(AssertionError, match='Prometheus'):
        experiment.verify({'load': [{}] * 13, 'samples': [sample(0)]})
