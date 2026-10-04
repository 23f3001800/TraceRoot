"""Validate that a staging receipt is sufficient to close the recovery gate."""
import argparse, json
from pathlib import Path

def validate_recovery(receipt,expected_grade_band):
    job=receipt.get("quality_job") if isinstance(receipt.get("quality_job"),dict) else {}
    warnings=job.get("warnings",receipt.get("warnings")); actual=job.get("grade_band",receipt.get("grade_band"))
    completed=job.get("completed_stages")
    completed_count=len(completed) if isinstance(completed,list) else completed
    checks={"terminal_status_succeeded":job.get("status")=="succeeded",
        "all_stages_completed":completed_count==10 and job.get("progress")==100,
        "package_created":isinstance(job.get("package_id"),str) and bool(job.get("package_id")),
        "zero_fallback_warnings":warnings==[],"expected_grade_band":actual==expected_grade_band,
        "production_unchanged":receipt.get("production_changed") is False,"replay_succeeded":receipt.get("replay_succeeded") is True}
    return {"schema_version":1,"recovery_evidence_complete":all(checks.values()),"checks":checks,
        "failed_checks":[name for name,passed in checks.items() if not passed],"job_id":job.get("job_id"),
        "package_id":job.get("package_id"),"grade_band":actual}

def main():
    p=argparse.ArgumentParser(); p.add_argument("receipt",type=Path); p.add_argument("--expected-grade-band",required=True); p.add_argument("--output",type=Path); args=p.parse_args()
    result=validate_recovery(json.loads(args.receipt.read_text(encoding="utf-8")),args.expected_grade_band); output=json.dumps(result,indent=2)+"\n"
    if args.output: args.output.write_text(output,encoding="utf-8")
    else: print(output,end="")
    return 0 if result["recovery_evidence_complete"] else 1
if __name__=="__main__": raise SystemExit(main())
