"""Real C aggregate summary -> local qwen3.5:9b -> local trace evidence.

The test contains no summary fixture, HTTP substitute, or model substitute. It
is opt-in because it reads C's real aggregate endpoint and appends a safe,
aggregate-only trace record to the local runtime log directory.
"""

from __future__ import annotations

import os

import pytest

from app.config.settings import Settings
from app.service.efficiency_analysis import CustomerEfficiencyAnalysisService


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_CUSTOMER_EFFICIENCY_ANALYSIS_E2E") != "1",
    reason="set RUN_REAL_CUSTOMER_EFFICIENCY_ANALYSIS_E2E=1 with an isolated real C efficiency service",
)


def test_real_c_efficiency_summary_is_analyzed_and_recorded() -> None:
    settings = Settings.from_env()
    assert settings.platform_api_base_url, "PLATFORM_API_BASE_URL must target C"
    assert settings.llm_provider == "ollama"
    assert settings.llm_model == "qwen3.5:9b"

    service = CustomerEfficiencyAnalysisService(settings)
    record = service.run()

    assert record["analysis_run_id"].startswith("CEA-")
    assert record["model_version"] == "qwen3.5:9b"
    assert record["prompt_version"] == "customer-efficiency-analysis-v1"
    assert record["summary"]["summary_version"] == "customer-efficiency.v1"
    assert record["analysis"]["adoption_rate"] == record["summary"]["adoption_rate"]
    assert (
        record["analysis"]["not_adoption_reason_status"]
        == "NOT_PROVIDED_BY_SUMMARY"
    )
    assert service.latest() == record
