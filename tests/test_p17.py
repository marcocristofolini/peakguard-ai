from datetime import datetime, timezone

import pytest
import yaml
from fastapi.testclient import TestClient

from peakguard.api import app
from peakguard.explanations import explain
from peakguard.manifest import manifest_diff
from peakguard.scenarios import Scenario
from peakguard.simulator import Config, compare

# Curva nominal da carga P6: 13 ticks de 10 s, pico de 12 doc/s nos ticks 2–10.
RATES = tuple((12 if 2 <= i < 11 else 1) * 60 for i in range(13))
CONFIG = Config(tick_minutes=1 / 6, capacity_docs_per_minute_per_replica=294, max_replicas=4,
                target_utilization=0.7, activation_delay_ticks=1)
START = datetime(2026, 11, 3, 14, 0, 40, tzinfo=timezone.utc)


def comparison():
    return compare(Scenario("p6_controlled_peak", 0, RATES, RATES), CONFIG)


def scaled_object(**kw):
    c = comparison()
    out = manifest_diff(explain(c), c, kind="scaledobject", name="documents", namespace="peakguard-p6", **kw)
    return out, yaml.safe_load(out["proposed_manifest"])


def test_cron_window_from_declared_calendar_keeps_cpu_floor():
    out, doc = scaled_object(schedule_start=START)
    triggers = doc["spec"]["triggers"]
    assert triggers[0] == {"type": "cpu", "metricType": "Utilization", "metadata": {"value": "70"}}
    # Pico previsto 20–110 s após 14:00:40; antecipação de 3 ticks (30 s) → 14:00:30 → 14:00; fim 14:02:30 → 14:03.
    assert triggers[1] == {"type": "cron", "metadata": {"timezone": "Etc/UTC", "start": "0 14 3 11 *",
                                                       "end": "3 14 3 11 *", "desiredReplicas": "4"}}
    assert out["applied"] is False and out["schedule"]["windows"][0]["desired_replicas"] == 4


def test_without_schedule_manifest_is_unchanged():
    _, doc = scaled_object()
    assert [t["type"] for t in doc["spec"]["triggers"]] == ["cpu"]


def test_schedule_rejected_for_hpa_and_naive_datetime():
    c = comparison()
    with pytest.raises(ValueError):
        manifest_diff(explain(c), c, kind="hpa", name="documents", schedule_start=START)
    with pytest.raises(ValueError):
        scaled_object(schedule_start=START.replace(tzinfo=None))


def test_api_accepts_schedule_start():
    body = {"scenario": "predictable_peak", "seed": 42, "kind": "scaledobject", "name": "documents",
            "schedule_start": "2026-11-03T14:00:00Z"}
    r = TestClient(app).post("/manifest-diff", json=body)
    assert r.status_code == 200, r.text
    assert "type: cron" in r.json()["proposed_manifest"] and r.json()["applied"] is False
    assert TestClient(app).post("/manifest-diff", json={**body, "kind": "hpa"}).status_code == 422
