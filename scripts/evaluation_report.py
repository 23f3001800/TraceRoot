"""Validate and score TraceRoot remediation evidence conservatively."""
import argparse
import json
from pathlib import Path

def validate_manifest(manifest):
    if manifest.get("schema_version") != 2: raise ValueError("unsupported evaluation manifest")
    areas = manifest.get("scorecard",{}).get("areas",[])
    if sum(area.get("weight",0) for area in areas) != 100: raise ValueError("scorecard weights must sum to 100")
    area_ids = [area.get("id") for area in areas]
    gate_ids = [gate.get("id") for gate in manifest.get("mandatory_gates",[])]
    if len(area_ids) != len(set(area_ids)) or len(gate_ids) != len(set(gate_ids)): raise ValueError("IDs must be unique")
    if not manifest.get("runs") or not gate_ids: raise ValueError("runs and mandatory gates are required")
    for run in manifest["runs"]:
        for phase in ("before","after"):
            data = run.get(phase,{})
            if set(data.get("scores",{})) != set(area_ids): raise ValueError("every scorecard area must be present")
            if set(data.get("gates",{})) != set(gate_ids): raise ValueError("every mandatory gate must be present")
            for value in data["scores"].values():
                if value is not None and (not isinstance(value,(int,float)) or not 0 <= value <= 1): raise ValueError("scores must be 0..1 or null")
            if any(not isinstance(value,bool) for value in data["gates"].values()): raise ValueError("gates must be boolean")
    return manifest

def threshold_results(profile, metrics):
    output = {}
    for name, threshold in profile.get("thresholds",{}).items():
        metric, direction = name.rsplit("_",1)
        observed = metrics.get(metric)
        passed = None if observed is None else observed >= threshold if direction == "min" else observed <= threshold
        output[name] = {"observed":observed,"threshold":threshold,"status":"NOT_MEASURED" if passed is None else "PASS" if passed else "FAIL"}
    return output

def score_run(manifest, run, phase):
    data = run[phase]; weights = {area["id"]:area["weight"] for area in manifest["scorecard"]["areas"]}
    score = round(sum(weights[key] * (value or 0) for key,value in data["scores"].items()),2)
    measured_weight = sum(weights[key] for key,value in data["scores"].items() if value is not None)
    failed_gates = [key for key,value in data["gates"].items() if not value]
    safety = data.get("safety_violations",[])
    label = next(item["label"] for item in manifest["scorecard"]["interpretation"] if score >= item["minimum"])
    profile = manifest.get("application_profiles",{}).get(run.get("profile"),{})
    return {"id":run["id"],"profile":run.get("profile"),"phase":phase,"weighted_score":score,
        "measured_weight":measured_weight,"score_complete":measured_weight == 100,"interpretation":label,
        "mandatory_gates_passed":not failed_gates,"failed_gates":failed_gates,"safety_violations":safety,
        "eligible":not failed_gates and not safety and measured_weight == 100,"scores":data["scores"],
        "metrics":data.get("metrics",{}),"thresholds":threshold_results(profile,data.get("metrics",{})),
        "evidence_refs":data.get("evidence_refs",[])}

def build_reports(manifest):
    validate_manifest(manifest)
    reports = []
    for phase in ("before","after"):
        results = [score_run(manifest,run,phase) for run in manifest["runs"]]
        reports.append({"schema_version":2,"suite":manifest["suite"],"phase":phase,"run_count":len(results),
            "results":results,"all_eligible":all(item["eligible"] for item in results)})
    return tuple(reports)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest",type=Path,default=Path("evaluations/manifest.json"))
    parser.add_argument("--output",type=Path,default=Path("evaluations/reports"))
    args = parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    reports = build_reports(json.loads(args.manifest.read_text(encoding="utf-8")))
    for name,report in zip(("before","after"),reports):
        (args.output/f"{name}.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0

if __name__ == "__main__": raise SystemExit(main())
