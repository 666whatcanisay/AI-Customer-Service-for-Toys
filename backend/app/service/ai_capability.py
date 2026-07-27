from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any

from app.models.ai_control import (
    AiControlCenterSnapshot,
    AiCustomerServiceState,
    AiOperationalCapability,
    BadcaseCategoryState,
    BadcaseReadOnlyState,
    ControlCenterDataSource,
    EvaluationReadOnlyState,
    EvaluationSummary,
    FeedbackAnalysisReadOnlyState,
    FeedbackAnalysisRunSummary,
    PromptReadOnlyState,
)
from app.models.ai_operations import (
    AiOperationsOverviewSnapshot,
    AnswerQualityMetric,
    AnswerVolumeMetric,
    BadcaseCategoryMetric,
    BadcaseMetric,
    ExternalDataIntegrationMetric,
    KnowledgeCoverageMetric,
    ModelStatusMetric,
    OperationsNotice,
)


AI_MODULE_STATUSES = {
    "PLANNED",
    "DEVELOPING",
    "TESTING",
    "RUNNING",
    "PAUSED",
    "ERROR",
}


@dataclass(frozen=True)
class AIModuleDefinition:
    module_id: str
    name: str
    description: str
    implemented: bool


MODULE_DEFINITIONS = (
    AIModuleDefinition(
        module_id="ai_customer_service",
        name="AI Customer Service",
        description="RAG-backed toy customer-service answer capability.",
        implemented=True,
    ),
    AIModuleDefinition(
        module_id="aftersales_intent",
        name="After-sales Intent Recognition",
        description="Planned after-sales intent classification capability.",
        implemented=False,
    ),
    AIModuleDefinition(
        module_id="shipping_note_extractor",
        name="Shipping Note Extractor",
        description="Planned shipping-note extraction capability.",
        implemented=False,
    ),
    AIModuleDefinition(
        module_id="appeal_writer",
        name="Order Appeal Writer",
        description="Planned order-appeal drafting capability.",
        implemented=False,
    ),
    AIModuleDefinition(
        module_id="risk_checker",
        name="Reply Risk Checker",
        description="Planned reply-risk review capability.",
        implemented=False,
    ),
)
MODULES_BY_ID = {module.module_id: module for module in MODULE_DEFINITIONS}


PROMPT_VERSION = "rag-customer-reply-v1"
PROMPT_SOURCE_TYPE = "code"
PROMPT_SYSTEM_MESSAGE = (
    "你是简洁的电商玩具客服话术助手。只能使用已核实事实，"
    "只输出客户可见话术，禁止暴露任何内部检索或来源信息。"
)
CUSTOMER_ANSWER_PROMPT_TEMPLATE = """
你负责把已核实的玩具商品事实整理成可直接复制给客户的客服话术。
只能使用下方事实，不允许编造；事实不足时简短说明暂时无法确认。

已核实事实：
{context}

授权动作：{answer_action}
风险等级：{risk_level}

问题：
{question}

本次回答范围：{answer_focus}。

硬性要求：
1. 只输出给客户看的最终话术，1～3句话，优先直接回答问题。
2. 只回答本次范围，不附加客户没问的颗粒数、尺寸、包装、玩法等参数。
3. 不得提及资料、证据、依据摘要、检索、来源编号、source_id、评分或距离。
4. 不得列出或复述内部上下文，不得把来源信息拼到话术中。
5. 可自然使用“亲”，但不得夸张承诺。
6. 安全提示只能来自上方明确事实；年龄问题仅保留建议年龄和必要安全提示，
   且事实中已有的小颗粒、低龄限制、成人陪同提示必须保留。
7. 年龄事实包含上下限时必须完整保留，不得泛化为“X岁以上”；成人陪同类提示只表达一次。
""".strip()
PROMPT_HASH = sha256(
    f"{PROMPT_SYSTEM_MESSAGE}\n{CUSTOMER_ANSWER_PROMPT_TEMPLATE}".encode("utf-8")
).hexdigest()


def render_customer_answer_prompt(
    *,
    context: str,
    answer_action: str,
    risk_level: str,
    question: str,
    answer_focus: str,
) -> str:
    return CUSTOMER_ANSWER_PROMPT_TEMPLATE.format(
        context=context[:3000],
        answer_action=answer_action,
        risk_level=risk_level,
        question=question,
        answer_focus=answer_focus,
    )


def prompt_metadata() -> dict[str, Any]:
    """Return only reviewed prompt metadata, never the full prompt template."""
    return {
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": PROMPT_HASH,
        "updated_at": "code-managed",
        "source_type": PROMPT_SOURCE_TYPE,
        "safe_preview": (
            "Transforms verified product facts into a concise, customer-visible reply; "
            "does not disclose internal retrieval evidence."
        ),
        "answer_style_rules": [
            "One to three customer-visible sentences.",
            "Answer only the requested topic.",
            "Use only verified facts and avoid unsupported promises.",
            "Keep explicit safety constraints and complete age ranges.",
        ],
        "forbidden_internal_markers": [
            "source_id",
            "source_ids",
            "retrieval",
            "evidence",
            "distance",
            "score",
            "internal_context",
        ],
    }


class RuntimeMetrics:
    """Thread-safe, process-local aggregates that contain no request content."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._call_count = 0
        self._success_count = 0
        self._error_count = 0
        self._total_latency_ms = 0.0
        self._last_called_at: str | None = None
        self._last_error_summary: str | None = None
        self._action_counts = {
            "DIRECT_ANSWER": 0,
            "CONTROLLED_ANSWER": 0,
            "TRANSFER_HUMAN": 0,
            "OTHER": 0,
        }

    def record(
        self,
        latency_ms: float,
        error_summary: str | None = None,
        answer_action: str | None = None,
    ) -> None:
        with self._lock:
            self._call_count += 1
            self._total_latency_ms += max(0.0, latency_ms)
            self._last_called_at = datetime.now(timezone.utc).isoformat()
            action_key = (
                answer_action
                if answer_action
                in {"DIRECT_ANSWER", "CONTROLLED_ANSWER", "TRANSFER_HUMAN"}
                else "OTHER"
            )
            self._action_counts[action_key] += 1
            if error_summary:
                self._error_count += 1
                # The caller supplies a controlled category, never exception text.
                self._last_error_summary = error_summary[:80]
            else:
                self._success_count += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            average = (
                round(self._total_latency_ms / self._call_count, 1)
                if self._call_count
                else 0.0
            )
            return {
                "metrics_scope": "since_start",
                "call_count": self._call_count,
                "success_count": self._success_count,
                "error_count": self._error_count,
                "total_latency_ms": round(self._total_latency_ms, 1),
                "average_latency_ms": average,
                "last_called_at": self._last_called_at,
                "last_error_summary": self._last_error_summary,
                "action_counts": dict(self._action_counts),
            }


def module_summary(module: AIModuleDefinition, status: str) -> dict[str, Any]:
    if status not in AI_MODULE_STATUSES:
        raise ValueError(f"unsupported AI module status: {status}")
    return {
        "module_id": module.module_id,
        "name": module.name,
        "description": module.description,
        "status": status,
        "implemented": module.implemented,
    }


def not_available_module_detail(module: AIModuleDefinition) -> dict[str, Any]:
    """Ensure planned modules never resemble active or measured capabilities."""
    unavailable = {
        "model_provider": None,
        "model_name": None,
        "ready": None,
        "model_configured": None,
        "initialization_error": "NOT_AVAILABLE",
        "knowledge_count": None,
        "prompt_version": "NOT_AVAILABLE",
        "prompt_hash": "NOT_AVAILABLE",
        "metrics_scope": "NOT_AVAILABLE",
        "call_count": None,
        "success_count": None,
        "error_count": None,
        "total_latency_ms": None,
        "average_latency_ms": None,
        "last_called_at": None,
        "last_error_summary": "NOT_AVAILABLE",
        "supported_actions": [],
    }
    return {**module_summary(module, "PLANNED"), **unavailable}


def safe_knowledge_count(rag: Any) -> int | None:
    try:
        stats = rag.vector_store.get_collection_stats()
        count = stats.get("total_chunks")
        return int(count) if isinstance(count, int | float) else None
    except Exception:
        return None


def unavailable_metrics() -> dict[str, Any]:
    return {
        "metrics_scope": "NOT_AVAILABLE",
        "call_count": None,
        "success_count": None,
        "error_count": None,
        "total_latency_ms": None,
        "average_latency_ms": None,
        "last_called_at": None,
        "last_error_summary": "NOT_AVAILABLE",
        "action_counts": None,
    }


def customer_service_detail(application: Any) -> dict[str, Any]:
    module = MODULES_BY_ID["ai_customer_service"]
    rag = getattr(application.state, "rag_service", None)
    ready = bool(getattr(application.state, "ready", False) and rag is not None)
    initialization_error = getattr(application.state, "initialization_error", None)
    module_status = "RUNNING" if ready else ("ERROR" if initialization_error else "PAUSED")
    metrics = rag.runtime_metrics.snapshot() if rag is not None else unavailable_metrics()
    return {
        **module_summary(module, module_status),
        "model_provider": rag.settings.llm_provider if rag is not None else None,
        "model_name": rag.settings.llm_model if rag is not None else None,
        "ready": ready,
        "model_configured": rag.model_configured if rag is not None else None,
        "initialization_error": initialization_error,
        "knowledge_count": safe_knowledge_count(rag) if rag is not None else None,
        **prompt_metadata(),
        **metrics,
        "supported_actions": [
            "answer_customer_question",
            "search_knowledge",
            "run_online_test",
        ] if ready else [],
    }


def latest_evaluation(evaluations_root: Path) -> dict[str, Any]:
    """Read the newest saved real evaluation summary without exposing report paths."""
    candidates: list[tuple[float, Path, dict[str, Any]]] = []
    if evaluations_root.exists():
        for path in evaluations_root.glob("*/a-t03-evaluation.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if payload.get("evidence_mode") != "live_c_api":
                continue
            candidates.append((path.stat().st_mtime, path, payload))
    if not candidates:
        return {"status": "NOT_AVAILABLE", "evaluation": None}

    _, path, payload = max(candidates, key=lambda candidate: candidate[0])
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    total_cases = payload.get("total")
    check_counts = payload.get("check_pass_counts")
    return {
        "status": "AVAILABLE",
        "evaluation": {
            "evaluation_id": path.parent.name,
            "executed_at": payload.get("executed_at", "NOT_AVAILABLE"),
            "dataset_version": payload.get("dataset_version", "NOT_AVAILABLE"),
            "total_cases": total_cases if isinstance(total_cases, int) else None,
            "passed_cases": payload.get("passed") if isinstance(payload.get("passed"), int) else None,
            "pass_rate": payload.get("pass_rate") if isinstance(payload.get("pass_rate"), int | float) else None,
            "checks": {
                key: check_counts.get(key) if isinstance(check_counts, dict) else None
                for key in (
                    "action",
                    "source_ids",
                    "key_facts",
                    "required_fields",
                    "risk_level",
                    "scope",
                )
            },
            "failed_case_ids": [
                str(record.get("case_id"))
                for record in records
                if isinstance(record, dict) and record.get("passed") is False
            ],
            "report_available": True,
            "report_path": path.parent.name,
        },
    }


def summarize_feedback_analysis_run(recorded: dict[str, Any]) -> dict[str, Any]:
    """Keep only aggregate writeback evidence for the current A process.

    The source run has already completed its C writeback.  This helper never
    retains question text, answers, feedback IDs, content hashes, analyses, or
    suggestions.  It is intentionally process-local, so a restart produces an
    explicit no-data state rather than an invented history.
    """

    analyses = recorded.get("analyses")
    if not isinstance(analyses, list):
        return {}
    input_count = recorded.get("input_feedback_count")
    if isinstance(input_count, bool) or not isinstance(input_count, int):
        input_count = len(analyses)

    analyzed_writebacks = 0
    idempotency_verified = 0
    model_versions: set[str] = set()
    prompt_versions: set[str] = set()
    for item in analyses:
        if not isinstance(item, dict):
            continue
        if item.get("writeback_status") == "ANALYZED":
            analyzed_writebacks += 1
        if item.get("idempotency_verified") is True:
            idempotency_verified += 1
        model_version = item.get("model_version")
        prompt_version = item.get("prompt_version")
        if isinstance(model_version, str) and model_version.strip():
            model_versions.add(model_version.strip())
        if isinstance(prompt_version, str) and prompt_version.strip():
            prompt_versions.add(prompt_version.strip())

    return FeedbackAnalysisRunSummary(
        completed_at=datetime.now(timezone.utc).isoformat(),
        input_feedback_count=max(0, input_count),
        completed_analysis_count=len(analyses),
        analyzed_writeback_count=analyzed_writebacks,
        idempotency_verified_count=idempotency_verified,
        model_version=next(iter(model_versions)) if len(model_versions) == 1 else None,
        prompt_version=next(iter(prompt_versions)) if len(prompt_versions) == 1 else None,
    ).model_dump()


def _feedback_summary(application: Any) -> FeedbackAnalysisRunSummary | None:
    value = getattr(application.state, "latest_feedback_analysis_summary", None)
    if not isinstance(value, dict):
        return None
    try:
        return FeedbackAnalysisRunSummary.model_validate(value)
    except (TypeError, ValueError):
        return None


def _percent(numerator: int | None, denominator: int | None) -> float | None:
    if (
        isinstance(numerator, bool)
        or isinstance(denominator, bool)
        or not isinstance(numerator, int)
        or not isinstance(denominator, int)
        or denominator <= 0
        or numerator < 0
    ):
        return None
    return round((numerator / denominator) * 100, 2)


def operations_overview_snapshot(application: Any) -> AiOperationsOverviewSnapshot:
    """Build a non-executing AI operations summary from safe local evidence.

    A GET never contacts C or the model. Feedback and efficiency integration
    state is intentionally explicit when a safe, registered aggregate is not
    locally available; the endpoint must not infer counts from raw snapshots.
    """

    settings = application.state.settings
    detail = customer_service_detail(application)
    latest = latest_evaluation(
        settings.project_root / "docs" / "rag" / "evaluations"
    )
    evaluation = latest.get("evaluation")
    evaluation = evaluation if isinstance(evaluation, dict) else None
    total_cases = evaluation.get("total_cases") if evaluation else None
    passed_cases = evaluation.get("passed_cases") if evaluation else None
    checks = evaluation.get("checks") if evaluation else None
    source_attribution_passed = (
        checks.get("source_ids") if isinstance(checks, dict) else None
    )
    action_counts = detail.get("action_counts")
    action_counts = action_counts if isinstance(action_counts, dict) else None
    metrics_available = detail.get("metrics_scope") == "since_start" and action_counts
    platform_configured = bool(settings.platform_api_base_url)
    feedback_summary = _feedback_summary(application)

    quality_rate = _percent(passed_cases, total_cases)
    source_attribution_rate = _percent(source_attribution_passed, total_cases)
    coverage_available = source_attribution_rate is not None
    quality_available = quality_rate is not None

    answer_volume = AnswerVolumeMetric(
        status="AVAILABLE" if metrics_available else "NOT_AVAILABLE",
        metrics_scope=detail.get("metrics_scope") or "NOT_AVAILABLE",
        processed_request_count=detail.get("call_count") if metrics_available else None,
        direct_answer_count=(
            action_counts.get("DIRECT_ANSWER") if metrics_available else None
        ),
        controlled_answer_count=(
            action_counts.get("CONTROLLED_ANSWER") if metrics_available else None
        ),
        transfer_human_count=(
            action_counts.get("TRANSFER_HUMAN") if metrics_available else None
        ),
        other_outcome_count=(action_counts.get("OTHER") if metrics_available else None),
        explanation=(
            "Counts are process-local since A start and include only aggregate "
            "answer actions; they reset when A restarts and are not staff metrics."
        ),
    )
    answer_quality = AnswerQualityMetric(
        status="AVAILABLE" if quality_available else "NOT_AVAILABLE",
        evaluation_id=evaluation.get("evaluation_id") if evaluation else None,
        evaluated_case_count=total_cases if isinstance(total_cases, int) else None,
        passed_case_count=passed_cases if isinstance(passed_cases, int) else None,
        pass_rate_percent=quality_rate,
        measured_at=evaluation.get("executed_at") if evaluation else None,
        explanation=(
            "Quality is the latest saved live_c_api evaluation pass rate. It is "
            "evaluation evidence, not a claim about all production conversations."
        ),
    )
    knowledge_coverage = KnowledgeCoverageMetric(
        status="AVAILABLE" if coverage_available else "NOT_AVAILABLE",
        indexed_chunk_count=(
            detail.get("knowledge_count")
            if isinstance(detail.get("knowledge_count"), int)
            else None
        ),
        source_attribution_checked_case_count=(
            source_attribution_passed
            if isinstance(source_attribution_passed, int)
            else None
        ),
        source_attribution_pass_rate_percent=source_attribution_rate,
        explanation=(
            "Indexed chunks describe the current A process store. Source "
            "attribution coverage is the source_ids check pass rate in the saved "
            "evaluation, not a percentage of all business knowledge."
        ),
    )
    badcase = BadcaseMetric(
        categories=[
            BadcaseCategoryMetric(category="FACT_ERROR"),
            BadcaseCategoryMetric(category="MISSING_INFO"),
            BadcaseCategoryMetric(category="STYLE_ISSUE"),
            BadcaseCategoryMetric(category="RISK_ISSUE"),
        ],
        explanation=(
            "No registered, de-identified Badcase aggregate is available to A. "
            "Counts remain empty; this endpoint never reads or classifies raw feedback."
        ),
    )
    model_configured = bool(detail.get("model_configured"))
    model_status = ModelStatusMetric(
        status="CONFIGURED" if model_configured else "NOT_CONFIGURED",
        provider=detail.get("model_provider"),
        model_version=detail.get("model_name"),
        service_ready=bool(detail.get("ready")),
        average_latency_ms=(
            detail.get("average_latency_ms") if metrics_available else None
        ),
        error_count=detail.get("error_count") if metrics_available else None,
        last_error_category=(
            detail.get("last_error_summary")
            if metrics_available and detail.get("last_error_summary") != "NOT_AVAILABLE"
            else None
        ),
        explanation=(
            "Configuration and process readiness are reported without probing the "
            "model. Use the explicit smoke test to establish live model availability."
        ),
    )
    feedback_status = (
        "AVAILABLE"
        if feedback_summary is not None
        else ("CONFIGURED" if platform_configured else "NOT_CONFIGURED")
    )
    external_data = [
        ExternalDataIntegrationMetric(
            source_id="feedback",
            status=feedback_status,
            explanation=(
                "Feedback integration is manual-only. This read-only overview does "
                "not contact C or expose feedback content; AVAILABLE means only a "
                "safe aggregate of a completed current-process run exists."
            ),
            operator_action=(
                "Provide a reachable isolated C service and a human-confirmed, "
                "de-identified ANALYZING snapshot before running the explicit feedback loop."
                if not platform_configured
                else "Use the explicit loopback feedback-analysis operation; no polling is performed."
            ),
        ),
        ExternalDataIntegrationMetric(
            source_id="efficiency",
            status="NOT_REGISTERED",
            explanation=(
                "No approved de-identified C efficiency-summary contract is "
                "registered in A scope, so no efficiency data is read or inferred."
            ),
            operator_action=(
                "Register a versioned aggregate-only efficiency contract and review "
                "affected lines before A consumes it."
            ),
        ),
    ]
    notices: list[OperationsNotice] = []
    if not quality_available:
        notices.append(
            OperationsNotice(
                code="EVALUATION_NOT_AVAILABLE",
                severity="INFO",
                message="No saved live evaluation is available for the quality metric.",
                operator_action="Run an explicit approved evaluation; do not treat fixture results as live quality.",
            )
        )
    elif quality_rate is not None and quality_rate < 100:
        notices.append(
            OperationsNotice(
                code="EVALUATION_QUALITY_ATTENTION",
                severity="WARNING",
                message="The latest saved evaluation has non-passing cases.",
                operator_action="Review the saved evaluation attribution before proposing a knowledge, rule, or prompt change; no change is automatic.",
            )
        )
    if coverage_available and source_attribution_rate is not None and source_attribution_rate < 100:
        notices.append(
            OperationsNotice(
                code="KNOWLEDGE_EVIDENCE_COVERAGE_ATTENTION",
                severity="WARNING",
                message="The saved evaluation has source-attribution check gaps.",
                operator_action="Inspect evaluation evidence and C knowledge provenance; do not publish knowledge automatically.",
            )
        )
    notices.append(
        OperationsNotice(
            code="BADCASE_AGGREGATE_NOT_AVAILABLE",
            severity="INFO",
            message="Badcase category counts are intentionally unavailable without a safe aggregate contract.",
            operator_action="Obtain a de-identified aggregate-only Badcase interface before displaying category totals.",
        )
    )
    if not platform_configured:
        notices.append(
            OperationsNotice(
                code="C_FEEDBACK_NOT_CONFIGURED",
                severity="WARNING",
                message="C feedback integration is not configured for this A process.",
                operator_action="Configure an isolated C endpoint and confirm de-identification before explicit feedback analysis.",
            )
        )
    notices.append(
        OperationsNotice(
            code="C_EFFICIENCY_CONTRACT_NOT_REGISTERED",
            severity="WARNING",
            message="C efficiency data cannot be consumed because no approved contract is registered in A scope.",
            operator_action="Complete cross-line contract review before adding an efficiency consumer.",
        )
    )
    if not model_configured:
        notices.append(
            OperationsNotice(
                code="MODEL_NOT_CONFIGURED",
                severity="ERROR",
                message="The configured model provider has no usable model client in this A process.",
                operator_action="Check local model configuration, then run the explicit smoke test; do not auto-switch models.",
            )
        )

    return AiOperationsOverviewSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        answer_volume=answer_volume,
        answer_quality=answer_quality,
        knowledge_coverage=knowledge_coverage,
        badcase=badcase,
        model_status=model_status,
        external_data=external_data,
        notices=notices,
    )


def control_center_snapshot(application: Any) -> AiControlCenterSnapshot:
    """Return a safe operational snapshot for the AI control-center UI.

    It only reads A process state and an existing saved evaluation summary.  It
    does not probe C, start a model, run evaluation/analysis, or read raw
    customer feedback as part of a GET request.
    """

    settings = application.state.settings
    detail = customer_service_detail(application)
    latest = latest_evaluation(
        settings.project_root / "docs" / "rag" / "evaluations"
    )
    raw_evaluation = latest.get("evaluation")
    # The legacy module endpoint retains report_path as an internal report
    # identifier.  The public control-center schema deliberately excludes it;
    # project only the shared summary fields before strict validation.
    public_evaluation = (
        {key: value for key, value in raw_evaluation.items() if key != "report_path"}
        if isinstance(raw_evaluation, dict)
        else None
    )
    evaluation = (
        EvaluationSummary.model_validate(public_evaluation)
        if public_evaluation is not None
        else None
    )
    platform_status = "CONFIGURED" if settings.platform_api_base_url else "NOT_CONFIGURED"
    configured_local_model = (
        settings.llm_provider == "ollama" and settings.llm_model == "qwen3.5:9b"
    )
    feedback_summary = _feedback_summary(application)
    prompt = prompt_metadata()

    customer_service = AiCustomerServiceState(
        module_id="ai_customer_service",
        name=detail["name"],
        description=detail["description"],
        status=detail["status"],
        ready=bool(detail["ready"]),
        model_provider=detail["model_provider"],
        model_name=detail["model_name"],
        model_configured=detail["model_configured"],
        knowledge_count=detail["knowledge_count"],
        metrics_scope=detail["metrics_scope"],
        call_count=detail["call_count"],
        success_count=detail["success_count"],
        error_count=detail["error_count"],
        average_latency_ms=detail["average_latency_ms"],
        last_called_at=detail["last_called_at"],
        last_error_summary=detail["last_error_summary"],
        supported_actions=detail["supported_actions"],
    )
    prompt_state = PromptReadOnlyState(
        module_id="ai_customer_service",
        prompt_version=prompt["prompt_version"],
        prompt_hash=prompt["prompt_hash"],
        updated_at=prompt["updated_at"],
        source_type=prompt["source_type"],
        safe_preview=prompt["safe_preview"],
        answer_style_rules=prompt["answer_style_rules"],
    )
    evaluation_state = EvaluationReadOnlyState(
        module_id="ai_customer_service",
        status=latest["status"],
        evaluation=evaluation,
        platform_integration_status=platform_status,
        current_model_version=detail["model_name"],
        current_prompt_version=settings.experience_evaluation_prompt_version,
        version_note=(
            "评测摘要未暴露历史模型或 Prompt 快照；版本字段仅代表当前 A 配置。"
        ),
    )
    badcase_state = BadcaseReadOnlyState(
        reason=(
            "没有面向浏览器的去标识化 Badcase 聚合读接口；控制中心不会读取或推断原始反馈。"
        ),
        categories=[
            BadcaseCategoryState(category="FACT_ERROR"),
            BadcaseCategoryState(category="MISSING_INFO"),
            BadcaseCategoryState(category="STYLE_ISSUE"),
            BadcaseCategoryState(category="RISK_ISSUE"),
        ],
    )
    feedback_state = FeedbackAnalysisReadOnlyState(
        status="MANUAL_ONLY" if platform_status == "CONFIGURED" else "NOT_CONFIGURED",
        platform_integration_status=platform_status,
        configured_model_version=settings.llm_model if configured_local_model else None,
        prompt_version=settings.feedback_analysis_prompt_version,
        latest_run=feedback_summary,
    )

    rag_data_status = "AVAILABLE" if customer_service.ready else "NOT_AVAILABLE"
    model_status = "RUNNING" if customer_service.ready else (
        "CONFIGURED" if configured_local_model else "NOT_CONFIGURED"
    )
    evaluation_data_status = "AVAILABLE" if evaluation is not None else "NOT_AVAILABLE"
    return AiControlCenterSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        customer_service=customer_service,
        prompt=prompt_state,
        evaluation=evaluation_state,
        badcase=badcase_state,
        feedback_analysis=feedback_state,
        capabilities=[
            AiOperationalCapability(
                capability_id="rag",
                name="RAG 客服回答",
                status=customer_service.status,
                data_status=rag_data_status,
                operator_mode="READ_ONLY",
                summary="范围隔离的知识检索与客户回答能力；当前状态来自 A 进程。",
            ),
            AiOperationalCapability(
                capability_id="qwen_local_model",
                name="qwen3.5:9b 本地模型",
                status=model_status,
                data_status=rag_data_status,
                operator_mode="READ_ONLY",
                summary="只显示配置和服务就绪状态；控制中心不会发起模型调用。",
            ),
            AiOperationalCapability(
                capability_id="experience_evaluation",
                name="AI 评测",
                status=latest["status"],
                data_status=evaluation_data_status,
                operator_mode="EXPLICIT_MANUAL",
                summary="仅显示最近保存的评测摘要；运行评测必须由操作人显式触发。",
            ),
            AiOperationalCapability(
                capability_id="badcase_analysis",
                name="Badcase 分类",
                status="NOT_AVAILABLE",
                data_status="NOT_AVAILABLE",
                operator_mode="READ_ONLY",
                summary="未发布浏览器安全的分类聚合数据，因此不读取或展示反馈原文。",
            ),
            AiOperationalCapability(
                capability_id="feedback_analysis",
                name="反馈分析",
                status=feedback_state.status,
                data_status="AVAILABLE" if feedback_summary else "NOT_AVAILABLE",
                operator_mode="EXPLICIT_MANUAL",
                summary="C 确认反馈经本地模型分析后回写 C；控制中心仅保留当前进程的聚合回执。",
            ),
        ],
        data_sources=[
            ControlCenterDataSource(
                source_id="a_runtime",
                read_path="A process state",
                purpose="模型、知识块与进程内调用聚合。",
            ),
            ControlCenterDataSource(
                source_id="saved_evaluation",
                read_path="docs/rag/evaluations/*/a-t03-evaluation.json",
                purpose="最近保存且标记为 live_c_api 的评测摘要。",
            ),
            ControlCenterDataSource(
                source_id="feedback_summary",
                read_path="A process memory",
                purpose="最近一次成功反馈分析的无原文聚合回执；重启后为空。",
            ),
        ],
    )
