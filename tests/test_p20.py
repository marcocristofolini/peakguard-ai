import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local" / "p20"))
import perpod  # noqa: E402


def test_per_pod_queues_even_and_sticky():
    # 100 doc/tick de chegada, 60 doc/tick por pod; o 2º pod ativa no tick 1.
    assert perpod.per_pod_backlog([100, 100, 100], [1, 2, 2], 60, "even") == [40, 30, 20]
    # sticky: o pod novo nunca recebe chegadas, então a fila só cresce no pod original.
    assert perpod.per_pod_backlog([100, 100, 100], [1, 2, 2], 60, "sticky") == [40, 80, 120]


def test_committed_p20_results_are_reproducible():
    committed = json.loads((ROOT / "evidence/p20/results.json").read_text())
    assert perpod.compute() == committed
