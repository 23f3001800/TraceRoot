"""Compute classifier quality and efficiency metrics from JSONL case records."""
import argparse, json
from pathlib import Path

REQUIRED = {"expected","predicted","confidence","low_confidence","fallback","latency_ms","cost_usd","input_tokens","output_tokens"}
def _ratio(a,b): return round(a/b,6) if b else 0.0

def validate_case(case,line):
    missing = REQUIRED-set(case)
    if missing: raise ValueError(f"line {line}: missing {sorted(missing)}")
    if not isinstance(case["expected"],str) or not case["expected"]: raise ValueError(f"line {line}: invalid expected label")
    if case["predicted"] is not None and (not isinstance(case["predicted"],str) or not case["predicted"]): raise ValueError(f"line {line}: invalid predicted label")
    if not isinstance(case["confidence"],(int,float)) or not 0<=case["confidence"]<=1: raise ValueError(f"line {line}: invalid confidence")
    if not isinstance(case["low_confidence"],bool) or not isinstance(case["fallback"],bool): raise ValueError(f"line {line}: flags must be boolean")
    for key in ("latency_ms","cost_usd"):
        if not isinstance(case[key],(int,float)) or case[key]<0: raise ValueError(f"line {line}: invalid {key}")
    for key in ("input_tokens","output_tokens"):
        if not isinstance(case[key],int) or isinstance(case[key],bool) or case[key]<0: raise ValueError(f"line {line}: invalid {key}")
    return case

def load_cases(path):
    cases=[validate_case(json.loads(line),n) for n,line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(),1) if line.strip()]
    if not cases: raise ValueError("at least one classification case is required")
    return cases

def compute_metrics(cases,baseline_accuracy=None,bins=10):
    if not 1<=bins<=100: raise ValueError("calibration bins must be 1..100")
    labels=sorted({c["expected"] for c in cases}|{c["predicted"] for c in cases if c["predicted"] is not None})
    matrix={actual:{predicted:0 for predicted in labels+["ABSTAIN"]} for actual in labels}
    correct=low_total=low_correct=0; bucketed=[[] for _ in range(bins)]
    for case in cases:
        predicted=case["predicted"] or "ABSTAIN"; matrix[case["expected"]][predicted]+=1
        matched=case["predicted"]==case["expected"]; correct+=matched
        if case["low_confidence"]: low_total+=1; low_correct+=matched
        bucketed[min(int(case["confidence"]*bins),bins-1)].append((case["confidence"],int(matched)))
    per_grade={}
    for label in labels:
        tp=matrix[label][label]; fp=sum(matrix[x][label] for x in labels if x!=label)
        fn=sum(matrix[label][x] for x in labels+["ABSTAIN"] if x!=label)
        precision,recall=_ratio(tp,tp+fp),_ratio(tp,tp+fn)
        per_grade[label]={"precision":precision,"recall":recall,"f1":_ratio(2*precision*recall,precision+recall),"support":sum(matrix[label].values())}
    ece=sum(len(b)/len(cases)*abs(sum(x[0] for x in b)/len(b)-sum(x[1] for x in b)/len(b)) for b in bucketed if b)
    accuracy=_ratio(correct,len(cases))
    return {"cases_total":len(cases),"accuracy":accuracy,"per_grade":per_grade,"confusion_matrix":matrix,
        "low_confidence_cases":low_total,"low_confidence_accuracy":_ratio(low_correct,low_total) if low_total else None,
        "fallback_rate":_ratio(sum(c["fallback"] for c in cases),len(cases)),"expected_calibration_error":round(ece,6),
        "baseline_delta":round(accuracy-baseline_accuracy,6) if baseline_accuracy is not None else None,
        "latency_ms_per_classification":round(sum(c["latency_ms"] for c in cases)/len(cases),3),
        "cost_usd_per_classification":round(sum(c["cost_usd"] for c in cases)/len(cases),8),
        "input_tokens":sum(c["input_tokens"] for c in cases),"output_tokens":sum(c["output_tokens"] for c in cases)}

def main():
    p=argparse.ArgumentParser(); p.add_argument("input",type=Path); p.add_argument("--output",type=Path)
    p.add_argument("--baseline-accuracy",type=float); p.add_argument("--bins",type=int,default=10); args=p.parse_args()
    output=json.dumps(compute_metrics(load_cases(args.input),args.baseline_accuracy,args.bins),indent=2)+"\n"
    if args.output: args.output.write_text(output,encoding="utf-8")
    else: print(output,end="")
    return 0
if __name__=="__main__": raise SystemExit(main())
