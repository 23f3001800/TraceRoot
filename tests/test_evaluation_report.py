import copy, json
from pathlib import Path
import pytest
from scripts.evaluation_report import build_reports, validate_manifest

def manifest(): return json.loads(Path("evaluations/manifest.json").read_text())

def test_scorecard_and_gates_are_reported_independently():
    before, after = build_reports(manifest())
    result = after["results"][0]
    assert before["results"][0]["weighted_score"] == 27.5
    assert result["weighted_score"] == 87.5
    assert result["interpretation"] == "strong staging result"
    assert result["score_complete"] is False
    assert result["eligible"] is False
    assert result["failed_gates"] == ["recovery_evidence_complete"]

def test_safety_violation_fails_even_perfect_run():
    data = manifest(); phase = data["runs"][0]["after"]
    phase["scores"] = {key:1.0 for key in phase["scores"]}
    phase["gates"] = {key:True for key in phase["gates"]}
    phase["safety_violations"] = ["production write"]
    result = build_reports(data)[1]["results"][0]
    assert result["weighted_score"] == 100 and result["eligible"] is False

def test_manifest_requires_all_gates_and_weight_100():
    data = copy.deepcopy(manifest()); data["mandatory_gates"].pop()
    with pytest.raises(ValueError, match="mandatory gate"):
        validate_manifest(data)
    data = manifest(); data["scorecard"]["areas"][0]["weight"] = 9
    with pytest.raises(ValueError, match="sum to 100"):
        validate_manifest(data)
