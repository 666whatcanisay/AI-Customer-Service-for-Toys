from __future__ import annotations

from pathlib import Path


def test_operations_overview_exposes_only_safe_process_metrics(api_client):
    client, _ = api_client
    rag = client.app.state.rag_service
    for action in (
        "DIRECT_ANSWER",
        "CONTROLLED_ANSWER",
        "TRANSFER_HUMAN",
        "REFUSE",
    ):
        rag.runtime_metrics.record(12.5, answer_action=action)

    response = client.get("/api/admin/ai/operations/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["schema_version"] == "ai-operations.v1"
    assert data["answer_volume"] == {
        "status": "AVAILABLE",
        "metrics_scope": "since_start",
        "processed_request_count": 4,
        "direct_answer_count": 1,
        "controlled_answer_count": 1,
        "transfer_human_count": 1,
        "other_outcome_count": 1,
        "durable": False,
        "explanation": data["answer_volume"]["explanation"],
    }
    assert data["badcase"]["status"] == "NOT_AVAILABLE"
    assert data["badcase"]["raw_content_exposed"] is False
    assert data["external_data"] == [
        {
            "source_id": "feedback",
            "status": "NOT_CONFIGURED",
            "read_attempted": False,
            "explanation": data["external_data"][0]["explanation"],
            "operator_action": data["external_data"][0]["operator_action"],
        },
        {
            "source_id": "efficiency",
            "status": "NOT_REGISTERED",
            "read_attempted": False,
            "explanation": data["external_data"][1]["explanation"],
            "operator_action": data["external_data"][1]["operator_action"],
        },
    ]
    assert {notice["code"] for notice in data["notices"]} >= {
        "BADCASE_AGGREGATE_NOT_AVAILABLE",
        "C_FEEDBACK_NOT_CONFIGURED",
        "C_EFFICIENCY_CONTRACT_NOT_REGISTERED",
    }
    serialized = response.text.lower()
    assert "feedback_id" not in serialized
    assert "platform_api_base_url" not in serialized
    assert "private customer content" not in serialized

    openapi = client.get("/openapi.json").json()
    overview = openapi["paths"]["/api/admin/ai/operations/overview"]["get"]
    assert overview["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/AiOperationsOverviewResponse")


def test_rag_query_records_safe_action_distribution(api_client):
    client, _ = api_client
    rag = client.app.state.rag_service
    original_query = rag._query
    actions = iter(
        ["DIRECT_ANSWER", "CONTROLLED_ANSWER", "TRANSFER_HUMAN", "REFUSE"]
    )

    def controlled_query(*args, **kwargs):
        del args, kwargs
        return {"answer": "safe test answer", "action": next(actions)}

    rag._query = controlled_query
    try:
        for _ in range(4):
            rag.query("private customer content")
    finally:
        rag._query = original_query

    data = client.get("/api/admin/ai/operations/overview").json()["data"]
    assert data["answer_volume"]["direct_answer_count"] == 1
    assert data["answer_volume"]["controlled_answer_count"] == 1
    assert data["answer_volume"]["transfer_human_count"] == 1
    assert data["answer_volume"]["other_outcome_count"] == 1
    assert "private customer content" not in str(data)


def test_operations_quality_and_coverage_use_saved_live_evaluation_only(api_client):
    client, vector_path = api_client
    report_path = (
        Path(vector_path).parent
        / "docs"
        / "rag"
        / "evaluations"
        / "live-operations-evaluation"
        / "a-t03-evaluation.json"
    )
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        """{
  "evidence_mode": "live_c_api",
  "dataset_version": "V0.3.1",
  "executed_at": "2026-07-27T00:00:00+00:00",
  "total": 3,
  "passed": 2,
  "check_pass_counts": {"source_ids": 2},
  "records": []
}""",
        encoding="utf-8",
    )

    data = client.get("/api/admin/ai/operations/overview").json()["data"]

    assert data["answer_quality"] == {
        "status": "AVAILABLE",
        "evaluation_id": "live-operations-evaluation",
        "evaluated_case_count": 3,
        "passed_case_count": 2,
        "pass_rate_percent": 66.67,
        "measured_at": "2026-07-27T00:00:00+00:00",
        "explanation": data["answer_quality"]["explanation"],
    }
    assert data["knowledge_coverage"]["status"] == "AVAILABLE"
    assert data["knowledge_coverage"]["source_attribution_checked_case_count"] == 2
    assert data["knowledge_coverage"]["source_attribution_pass_rate_percent"] == 66.67
    assert {notice["code"] for notice in data["notices"]} >= {
        "EVALUATION_QUALITY_ATTENTION",
        "KNOWLEDGE_EVIDENCE_COVERAGE_ATTENTION",
    }
