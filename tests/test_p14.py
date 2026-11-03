import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local" / "p14"))
import results  # noqa: E402


def test_committed_results_are_reproducible():
    assert json.loads((ROOT / "evidence/p14/results.json").read_text()) == json.loads(json.dumps(results.build(), sort_keys=True))


def test_pareto_reports_distinct_points_of_the_front():
    # Configurações diferentes podem ter o mesmo (custo, ticks) e ficar sobrepostas no gráfico;
    # o artefato precisa dizer quantos pontos distintos a fronteira realmente tem.
    for name, front in results.build()["pareto_seed42"].items():
        assert 1 <= front["front_distinct_points"] <= front["front_size"], name
