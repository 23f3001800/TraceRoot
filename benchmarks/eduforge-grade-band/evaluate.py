"""Deterministic quality evaluation for incident b57b4ab4fc21.

Run against an EduForge checkout/image. The model is stubbed; the real
ClassificationStage and contract validation are exercised.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from contracts.llm import LLMUsage, ModelSpec, ProviderRouting
from core.llm.base import RawCompletion
from core.llm.client import LLMClient
from stages.base import StageContext
from stages.s2_classification.stage import ClassificationStage


class StubAdapter:
    name = "openrouter"

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    async def complete(self, *, spec: ModelSpec, system: str, user_content: str,
                       output_model: type[BaseModel], extra=None) -> RawCompletion:
        return RawCompletion(text=json.dumps(self.payload), model=spec.model,
                             usage=LLMUsage(tokens_in=100, tokens_out=50, cost_usd=0.0))


def payload(grade_band: str) -> dict[str, Any]:
    return {"subject": "Biology", "grade_band": grade_band,
            "difficulty": "intermediate", "topic": "Photosynthesis",
            "category": "handout", "language": "en", "pedagogy_profile": "conceptual",
            "confidences": {"subject": 0.9, "grade_band": 0.3},
            "low_confidence_fields": ["grade_band"]}


CASES = [
    ("explicit-grade", "Grade 9 Biology: photosynthesis and chlorophyll.", "6-8", "9"),
    ("explicit-class", "Class 10 lesson: factors affecting photosynthesis.", "Unknown", "10"),
    ("ambiguous", "A short source document about photosynthesis.", "9-10", "Unknown"),
]


async def evaluate() -> dict[str, Any]:
    results = []
    for name, text, model_grade, expected in CASES:
        adapter = StubAdapter(payload(model_grade))
        client = LLMClient(routing=ProviderRouting(
            default=ModelSpec(provider="openrouter", model="stub-model")),
            adapters={"openrouter": adapter})
        records = []
        output = await ClassificationStage(client).run(
            StageContext(job_id=uuid4(), options={}, emit=None,
                         record=lambda **item: records.append(item)),
            {"structured_document": {"metadata": {"page_count": 1, "word_count": len(text.split())},
                                     "stats": {}, "blocks": [{"type": "paragraph", "text": text}]}})
        actual = output["classification"]["grade_band"]
        results.append({"case": name, "model_grade": model_grade, "expected": expected,
                        "actual": actual, "passed": actual == expected,
                        "warnings": records[0]["warnings"]})
    passed = sum(item["passed"] for item in results)
    return {"metric": "low_confidence_grade_resolution_accuracy",
            "passed": passed, "total": len(results), "accuracy": passed / len(results),
            "cases": results}


def test_low_confidence_grade_resolution_quality() -> None:
    result = asyncio.run(evaluate())
    assert result["passed"] == result["total"], json.dumps(result, sort_keys=True)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(evaluate()), indent=2, sort_keys=True))
