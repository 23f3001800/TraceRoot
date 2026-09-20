"""Measured model usage and explicitly configured, non-billing cost estimates."""
import json
import math
from pathlib import Path


def validate_pricing(data):
    model = data.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > 150:
        raise ValueError("Specify the exact model/deployment name.")
    result = {"model": model.strip()}
    for name in ("input_usd_per_million", "output_usd_per_million"):
        try:
            value = float(data[name])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Both USD per million token rates are required.") from None
        if not math.isfinite(value) or not 0 <= value <= 1000000:
            raise ValueError("Token rates must be finite nonnegative USD amounts.")
        result[name] = value
    return result


def usage_metrics(root, record, events):
    path = Path(root) / "pricing.json"
    prices = json.loads(path.read_text()) if path.exists() else {}
    summary = record.get("summary") or {}
    calls = [e["data"] for e in events if e["type"] == "agent.finished" and "usage" in e["data"]]
    tokens_in = sum(c["usage"].get("input_tokens", 0) for c in calls)
    tokens_out = sum(c["usage"].get("output_tokens", 0) for c in calls)
    latency = sum(c.get("duration_ms", 0) for c in calls)
    # Legacy runs recorded latency in summaries but not per-event.
    if any("duration_ms" not in c for c in calls):
        latency = sum(summary.get("latency_ms_by_role", {}).values()) + sum(
            c.get("duration_ms", 0) for c in calls if c.get("label") == "Remediation Planner")
    if not calls:
        tokens_in = summary.get("usage", {}).get("input_tokens", 0)
        tokens_out = summary.get("usage", {}).get("output_tokens", 0)
    missing, estimate = set(), 0.0
    for call in calls:
        model = call.get("model") or summary.get("model") or "unknown"
        rate = prices.get(model)
        if not rate:
            missing.add(model)
            continue
        usage = call["usage"]
        estimate += (usage.get("input_tokens", 0) * rate["input_usd_per_million"] +
                     usage.get("output_tokens", 0) * rate["output_usd_per_million"]) / 1000000
    failures = sum(e["type"] == "provider.error" for e in events)
    return {"input_tokens": tokens_in, "output_tokens": tokens_out,
            "completed_model_calls": len(calls), "provider_failures": failures,
            "model_latency_ms": round(latency, 2),
            "estimated_cost_usd": round(estimate, 6) if calls and not missing else None,
            "unpriced_models": sorted(missing), "pricing_configured": bool(prices),
            "cost_note": "Estimate for reported input/output tokens at operator-configured USD rates; excludes discounts, unreported failed calls, and infrastructure charges."}
