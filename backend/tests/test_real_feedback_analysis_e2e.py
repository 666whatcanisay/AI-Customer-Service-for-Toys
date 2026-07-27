"""Real C feedback -> local qwen -> C writeback evidence.

This test intentionally has no HTTP, model, or feedback-data substitutes.  It
is opt-in because it consumes one already human-confirmed C snapshot and
persists its analysis evidence.  The replay is the required idempotency check
for that same immutable snapshot and analysis_run_id.
"""

from __future__ import annotations

import os

import pytest

from app.config.settings import Settings
from app.service.feedback_analysis import FeedbackAnalysisService


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_FEEDBACK_ANALYSIS_E2E") != "1",
    reason="set RUN_REAL_FEEDBACK_ANALYSIS_E2E=1 with an isolated real C feedback service",
)


def test_real_c_feedback_is_analyzed_written_and_replayed_idempotently() -> None:
    settings = Settings.from_env()
    assert settings.platform_api_base_url, "PLATFORM_API_BASE_URL must target C"
    assert settings.llm_provider == "ollama"
    assert settings.llm_model == "qwen3.5:9b"

    result = FeedbackAnalysisService(settings).run(1, verify_idempotency=True)

    # A missing item is not fabricated.  C must expose a human-confirmed,
    # de-identified ANALYZING snapshot before this real integration can pass.
    assert result["input_feedback_count"] == 1
    assert len(result["analyses"]) == 1
    record = result["analyses"][0]
    assert record["model_version"] == "qwen3.5:9b"
    assert record["prompt_version"] == "ai-quality-feedback-v1"
    assert record["writeback_status"] == "ANALYZED"
    assert record["idempotency_verified"] is True
