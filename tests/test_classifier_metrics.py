import json
import pytest
from scripts.classifier_metrics import compute_metrics, load_cases

def case(expected,predicted,confidence,low=False,fallback=False,latency=10,cost=0.01):
    return {"expected":expected,"predicted":predicted,"confidence":confidence,"low_confidence":low,
        "fallback":fallback,"latency_ms":latency,"cost_usd":cost,"input_tokens":10,"output_tokens":2}

def test_computes_quality_calibration_and_efficiency():
    metrics=compute_metrics([case("K-2","K-2",0.9),case("3-5","K-2",0.6,True,True),case("3-5","3-5",0.8,True)],0.5)
    assert metrics["accuracy"]==0.666667 and metrics["low_confidence_accuracy"]==0.5
    assert metrics["per_grade"]["3-5"]["recall"]==0.5
    assert metrics["confusion_matrix"]["3-5"]["K-2"]==1
    assert metrics["fallback_rate"]==0.333333 and metrics["baseline_delta"]==0.166667
    assert metrics["latency_ms_per_classification"]==10 and metrics["cost_usd_per_classification"]==0.01
    assert metrics["input_tokens"]==30 and metrics["output_tokens"]==6

def test_rejects_incomplete_case(tmp_path):
    path=tmp_path/"cases.jsonl"; path.write_text(json.dumps({"expected":"K-2"}))
    with pytest.raises(ValueError,match="missing"): load_cases(path)
