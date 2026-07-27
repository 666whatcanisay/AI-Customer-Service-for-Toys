"""Regression coverage for the bounded local qwen feedback-analysis output."""

from __future__ import annotations

import json

import pytest

from app.service.feedback_analysis import (
    FeedbackAnalysisError,
    _MAX_MODEL_OUTPUT_CHARACTERS,
    _parse_model_output,
)


def _valid_payload() -> dict[str, object]:
    return {
        "analysis": {
            "summary": "  Generalized missing information finding.  ",
            "answer_difference": "  The final answer adds a safe clarification.  ",
            "issue_assessment": {
                "FACT_ERROR": "NOT_FOUND",
                "MISSING_INFO": "PRESENT",
                "STYLE_ISSUE": "NOT_FOUND",
                "RISK_ISSUE": "UNCERTAIN",
                "OTHER": "NOT_FOUND",
            },
            "analysis_outcome": "NEEDS_REVIEW",
        },
        "suggestions": [
            {
                "category": "KNOWLEDGE_GAP",
                "description": "  Add a reviewable product-information check.  ",
                "evidence_summary": "  The approved comparison identifies missing context.  ",
            }
        ],
    }


@pytest.mark.parametrize(
    "raw",
    [
        lambda: json.dumps(_valid_payload()),
        lambda: f"```JSON\n{json.dumps(_valid_payload())}\n```",
        lambda: f"```application/json\n{json.dumps(_valid_payload())}\n```",
    ],
)
def test_feedback_analysis_output_accepts_canonical_bounded_json(
    raw,
) -> None:
    analysis, suggestions = _parse_model_output(raw())

    assert analysis == {
        "summary": "Generalized missing information finding.",
        "answer_difference": "The final answer adds a safe clarification.",
        "issue_assessment": {
            "FACT_ERROR": "NOT_FOUND",
            "MISSING_INFO": "PRESENT",
            "OTHER": "NOT_FOUND",
            "RISK_ISSUE": "UNCERTAIN",
            "STYLE_ISSUE": "NOT_FOUND",
        },
        "analysis_outcome": "NEEDS_REVIEW",
    }
    assert suggestions == [
        {
            "category": "KNOWLEDGE_GAP",
            "description": "Add a reviewable product-information check.",
            "evidence_summary": "The approved comparison identifies missing context.",
        }
    ]


@pytest.mark.parametrize(
    "raw",
    [
        lambda: json.dumps({"analysis": _valid_payload()["analysis"], "suggestions": []})
        + " trailing content",
        lambda: json.dumps(
            {
                "analysis": {
                    **_valid_payload()["analysis"],
                    "issue_assessment": {
                        "FACT_ERROR": "PRESENT",
                    },
                },
                "suggestions": [],
            }
        ),
        lambda: "{" + ('"x":"' + ("a" * _MAX_MODEL_OUTPUT_CHARACTERS) + '"}') + "}",
    ],
)
def test_feedback_analysis_output_rejects_noncanonical_or_oversized_json(raw) -> None:
    with pytest.raises(FeedbackAnalysisError) as error:
        _parse_model_output(raw())

    assert error.value.code == "FEEDBACK_ANALYSIS_OUTPUT_INVALID"
    assert error.value.status_code == 422
