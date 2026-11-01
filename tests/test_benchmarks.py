import json

import pytest

from peakguard.benchmarks import benchmark, export


def test_complete_matrix_reproducible_and_fair():
    result = benchmark()
    assert result == benchmark()
    assert len(result['experiments']) == 108
    assert result['failed_experiments'] == 0
    for row in result['experiments']:
        a, b = row['results']['reactive'], row['results']['anticipatory']
        assert a['demand_docs'] == b['demand_docs']
        assert a['duration_minutes'] == b['duration_minutes'] == 24
        for metrics in (a, b):
            assert metrics['throughput_docs_per_minute'] == pytest.approx(metrics['processed_docs'] / 24)
            assert metrics['cost_brl'] == pytest.approx(metrics['replica_hours'] * row['config']['price_brl_per_replica_hour'])
            assert metrics['cost_brl_per_1000_docs'] == pytest.approx(metrics['cost_brl'] * 1000 / metrics['processed_docs'])
            assert metrics['demand_docs'] == pytest.approx(metrics['processed_docs'] + metrics['final_backlog_docs'])
    hashes = {r['demand_sha256'] for r in result['experiments'] if r['scenario'] == 'predictable_peak' and r['seed'] == 42}
    assert len(hashes) == 1


def test_false_positive_negative_and_unexpected_peak_are_reported():
    result = benchmark()
    nominal = [r for r in result['experiments'] if r['seed'] == 42 and r['forecast_multiplier'] == 1 and r['config']['price_brl_per_replica_hour'] == 1.2]
    false = next(r for r in nominal if r['scenario'] == 'wrong_forecast')
    assert false['results']['reactive']['cost_brl'] == pytest.approx(.48)
    assert false['delta_anticipatory_minus_reactive']['cost_brl'] > 0
    unexpected = next(r for r in nominal if r['scenario'] == 'unexpected_peak')
    assert unexpected['results']['anticipatory']['slo_violation_minutes'] > 0
    assert 'slo' in unexpected['results']['anticipatory']['failures']
    assert false['results']['anticipatory']['forecast_mae_docs_per_minute'] > 70


def test_export_is_strict_json_and_includes_tables_and_graphs(tmp_path):
    report = benchmark()
    export(report, tmp_path)
    assert json.loads((tmp_path / 'report.json').read_text()) == report
    assert 'wrong_forecast' in (tmp_path / 'comparison.md').read_text()
    assert '<svg' in (tmp_path / 'comparison.svg').read_text()
    assert 'BRL' in (tmp_path / 'comparison.svg').read_text()


def test_errors_are_retained_not_silently_excluded(monkeypatch):
    import peakguard.benchmarks as module
    def broken(*args):
        raise ValueError('invalid experiment')
    monkeypatch.setattr(module, 'compare', broken)
    result = benchmark()
    assert result['failed_experiments'] == 108
    assert len(result['experiments']) == 108
    assert all(r['status'] == 'error' and 'results' not in r for r in result['experiments'])
