import json
import os
import subprocess
import sys

import pytest


def cli(*args):
    return subprocess.run([sys.executable, "-m", "peakguard", *args], capture_output=True, text=True, env=os.environ.copy())


@pytest.mark.parametrize("args", [(), ("run",), ("compare",), ("multiseed",)])
def test_help_renders_for_every_command(args):
    result = cli(*args, "--help")
    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout


def test_list_exposes_offline_scenarios():
    result = cli("list")
    assert result.returncode == 0, result.stderr
    assert {"stable", "predictable_peak", "unexpected_peak", "wrong_forecast", "fiscal_irpf_april"} <= set(json.loads(result.stdout))


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


def test_multiseed_json_and_csv(tmp_path):
    csv_path = tmp_path / "m.csv"
    result = cli("multiseed", "fiscal_irpf_april", "--seeds", "4", "--arrivals", "poisson", "--csv", str(csv_path))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["seeds"] == [0, 1, 2, 3] and "cost_brl" in data["policies"]["reactive"]
    assert csv_path.read_text().startswith("scenario,arrivals,policy,metric")


def test_run_accepts_arrivals_and_new_scenario():
    a = cli("run", "fiscal_das_day20", "--arrivals", "burst")
    assert a.returncode == 0, a.stderr
    assert a.stdout == cli("run", "fiscal_das_day20", "--arrivals", "burst").stdout
