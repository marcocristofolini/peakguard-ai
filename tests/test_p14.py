import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local" / "p14"))
import results  # noqa: E402


def test_committed_results_are_reproducible():
    assert json.loads((ROOT / "evidence/p14/results.json").read_text()) == json.loads(json.dumps(results.build(), sort_keys=True))
