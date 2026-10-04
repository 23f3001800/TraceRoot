from scripts.recovery_receipt import validate_recovery

def clean_receipt():
    return {"quality_job":{"status":"succeeded","completed_stages":10,"progress":100,"package_id":"pkg-1",
        "job_id":"job-1","warnings":[],"grade_band":"6-8"},"production_changed":False,"replay_succeeded":True}

def test_accepts_only_complete_clean_recovery():
    result=validate_recovery(clean_receipt(),"6-8")
    assert result["recovery_evidence_complete"] is True and result["failed_checks"]==[]

def test_rejects_partial_replayed_or_missing_evidence():
    receipt=clean_receipt(); receipt["quality_job"]["status"]="succeeded_partial"
    receipt["quality_job"]["warnings"]=["degraded fallback"]; receipt["replay_succeeded"]=False
    result=validate_recovery(receipt,"6-8")
    assert result["recovery_evidence_complete"] is False
    assert {"terminal_status_succeeded","zero_fallback_warnings","replay_succeeded"}<=set(result["failed_checks"])

def test_accepts_completed_stage_name_list():
    receipt=clean_receipt()
    receipt["quality_job"]["completed_stages"]=[f"stage-{index}" for index in range(10)]
    result=validate_recovery(receipt,"6-8")
    assert result["checks"]["all_stages_completed"] is True

def test_rejects_incomplete_stage_name_list():
    receipt=clean_receipt()
    receipt["quality_job"]["completed_stages"]=[f"stage-{index}" for index in range(9)]
    result=validate_recovery(receipt,"6-8")
    assert result["checks"]["all_stages_completed"] is False
