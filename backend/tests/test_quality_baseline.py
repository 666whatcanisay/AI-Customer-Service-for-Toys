from __future__ import annotations

import json
from pathlib import Path


def _write_report(root: Path, report_id: str, payload: dict) -> None:
    path = root / "docs" / "rag" / "evaluations" / report_id / "a-t03-evaluation.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_quality_baseline_uses_live_report_and_hides_raw_evaluation_content(api_client):
    client, vector_path = api_client
    root = Path(vector_path).parent
    _write_report(
        root,
        "fixture-report",
        {
            "evidence_mode": "fixture",
            "total": 28,
            "passed": 28,
            "records": [],
        },
    )
    _write_report(
        root,
        "live-quality-baseline",
        {
            "evidence_mode": "live_c_api",
            "dataset_version": "V0.3.1",
            "executed_at": "2026-07-27T01:00:00+00:00",
            "total": 4,
            "passed": 0,
            "check_pass_counts": {
                "action": 4,
                "source_ids": 2,
                "key_facts": 3,
                "forbidden_claims": 4,
                "required_fields": 4,
                "risk_level": 3,
                "scope": 4,
            },
            "records": [
                {
                    "case_id": "CASE-DATA",
                    "passed": False,
                    "question": "private evaluation question",
                    "answer": "private evaluation answer",
                    "expected_source_ids": ["SRC-PRIVATE"],
                    "missing_source_ids": ["SRC-PRIVATE"],
                    "expected_key_facts": [],
                    "failure_classes": ["metadata_loss"],
                    "checks": {"source_ids": False},
                },
                {
                    "case_id": "CASE-RETRIEVAL",
                    "passed": False,
                    "expected_source_ids": ["SRC-RETRIEVAL"],
                    "missing_source_ids": ["SRC-RETRIEVAL"],
                    "expected_key_facts": [],
                    "failure_classes": ["retrieval_miss"],
                    "checks": {"source_ids": False},
                },
                {
                    "case_id": "CASE-PROMPT",
                    "passed": False,
                    "expected_source_ids": [],
                    "missing_source_ids": [],
                    "expected_key_facts": ["private expected fact"],
                    "failure_classes": ["model_expression_error"],
                    "checks": {"key_facts": False},
                },
                {
                    "case_id": "CASE-RULE",
                    "passed": False,
                    "expected_source_ids": [],
                    "missing_source_ids": [],
                    "expected_key_facts": [],
                    "failure_classes": ["structured_decision_error"],
                    "checks": {"risk_level": False},
                },
            ],
        },
    )

    response = client.get("/api/admin/ai/quality-baseline/latest")

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert data["schema_version"] == "ai-quality-baseline.v1"
    assert data["status"] == "AVAILABLE"
    assert data["summary"] == {
        "evaluation_id": "live-quality-baseline",
        "executed_at": "2026-07-27T01:00:00+00:00",
        "dataset_version": "V0.3.1",
        "total_case_count": 4,
        "passed_case_count": 0,
        "failed_case_count": 4,
        "pass_rate_percent": 0.0,
        "checks": data["summary"]["checks"],
    }
    findings = {finding["category"]: finding for finding in data["cause_findings"]}
    assert findings["DATA_PROBLEM"]["affected_case_count"] == 1
    assert findings["RETRIEVAL_PROBLEM"]["affected_case_count"] == 1
    assert findings["PROMPT_OR_MODEL_PROBLEM"]["affected_case_count"] == 1
    assert findings["KNOWLEDGE_PROBLEM"]["affected_case_count"] == 1
    assert findings["RULE_DECISION_PROBLEM"]["affected_case_count"] == 1
    assert all(item["automatic_change_allowed"] is False for item in data["recommendations"])
    assert data["raw_content_exposed"] is False
    assert data["model_or_prompt_changed"] is False
    serialized = response.text
    assert "private evaluation question" not in serialized
    assert "private evaluation answer" not in serialized
    assert "private expected fact" not in serialized
    assert "SRC-PRIVATE" not in serialized

    openapi = client.get("/openapi.json").json()
    route = openapi["paths"]["/api/admin/ai/quality-baseline/latest"]["get"]
    assert route["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/QualityBaselineResponse")


def test_quality_baseline_returns_explicit_no_data_state(api_client):
    client, _ = api_client

    data = client.get("/api/admin/ai/quality-baseline/latest").json()["data"]

    assert data["status"] == "NOT_AVAILABLE"
    assert data["summary"] is None
    assert data["failed_cases"] == []
    assert data["raw_content_exposed"] is False
    assert data["model_or_prompt_changed"] is False
