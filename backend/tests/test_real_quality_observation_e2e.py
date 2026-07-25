from __future__ import annotations

import os
from dataclasses import replace

import pytest

from app.config.settings import Settings
from app.service.quality_observation import (
    ISSUE_CATEGORIES,
    QualityObservationMetrics,
    QualityObservationService,
)


pytestmark = pytest.mark.real_rag


@pytest.mark.skipif(
    os.getenv("RUN_REAL_RAG_E2E") != "1",
    reason="set RUN_REAL_RAG_E2E=1 for local qwen3.5:9b quality-observation smoke",
)
def test_real_qwen_quality_observation_smoke_uses_synthetic_snapshot_only() -> None:
    settings = replace(
        Settings.from_env(),
        llm_provider="ollama",
        llm_model="qwen3.5:9b",
        llm_base_url="http://127.0.0.1:11434",
        llm_timeout_seconds=180,
    )
    observer = QualityObservationService(settings, QualityObservationMetrics())

    issues = observer.classify(
        question="Synthetic question: can a child use this toy unsupervised?",
        ai_answer="Yes, a child can use it alone with no restrictions.",
        final_answer="Synthetic approved answer: adult supervision is required.",
    )

    assert set(issues) <= set(ISSUE_CATEGORIES)
    snapshot = observer.metrics.record(issues, settings.llm_model)
    assert snapshot["classified_case_count"] == 1
    assert snapshot["model_version"] == "qwen3.5:9b"
