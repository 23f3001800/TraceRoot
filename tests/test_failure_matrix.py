import json
from pathlib import Path

def test_controlled_failure_matrix_covers_detection_boundaries():
    matrix = json.loads(Path("evaluations/failure-matrix.json").read_text())
    failures = matrix["failures"]
    assert matrix["schema_version"] == 1
    assert {item["expected_signal"] for item in failures} == {"model","provider","tool","application","runtime"}
    assert all(item["containment"] for item in failures)
