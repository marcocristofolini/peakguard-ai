import json
import os
import subprocess
import sys

import pytest


def cli(*args):
    return subprocess.run([sys.executable, "-m", "peakguard", *args], capture_output=True, text=True, env=os.environ.copy())


def test_list_exposes_four_offline_scenarios():
    result = cli("list")
    assert result.returncode == 0, result.stderr
    assert set(json.loads(result.stdout)) == {"stable", "predictable_peak", "unexpected_peak", "wrong_forecast"}


def test_run_exports_reproducible_json(tmp_path):
    output = tmp_path / "simulation.json"
    args = ("run", "predictable_peak", "--seed", "12", "--policy", "anticipatory", "--output", str(output))
    first = cli(*args)
    assert first.returncode == 0, first.stderr
    data = json.loads(output.read_text())
    assert data == json.loads(first.stdout)
    assert data["seed"] == 12
    assert data["policy"] == "anticipatory"
    assert data["data_labels"]["demand"] == "synthetic"
    assert cli(*args).stdout == first.stdout


def test_compare_applies_same_parameters_and_input():
    result = cli("compare", "wrong_forecast", "--seed", "3", "--max-replicas", "2", "--tick-minutes", "0.5")
    assert result.returncode == 0, result.stderr
    runs = json.loads(result.stdout)["results"]
    assert runs["reactive"]["input"] == runs["anticipatory"]["input"]
    assert runs["reactive"]["config"] == runs["anticipatory"]["config"]
    assert runs["reactive"]["summary"]["duration_minutes"] == 12
    assert all(t["provisioned_replicas"] <= 2 for t in runs["anticipatory"]["ticks"])


@pytest.mark.parametrize("args", [
    ("run", "missing"), ("run", "stable", "--policy", "llm"),
    ("compare", "stable", "--budget-brl", "-1"),
    ("run", "stable", "--tick-minutes", "nan"),
    ("run", "stable", "--tick-minutes", "inf"),
    ("run", "stable", "--budget-brl", "0"),
    ("run", "stable", "--max-replicas", "0"),
    ("run", "stable", "--seed", "bad"),
])
def test_cli_rejects_invalid_input_without_traceback(args):
    result = cli(*args)
    assert result.returncode == 2
    assert result.stderr
    assert "Traceback" not in result.stderr
    assert not result.stdout


def test_output_failure_is_reported_without_success_json(tmp_path):
    result = cli("run", "stable", "--output", str(tmp_path / "absent" / "run.json"))
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert not result.stdout
