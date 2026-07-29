"""Stable read-only product projection for the AI control center.

This recovery adapter projects the current A runtime and saved-evaluation
evidence into the already defined ``ai-control-center.product.v1`` shape. It
does not contact C, call a model, expose raw content, or perform a write.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.ai_control_product import (
    AiControlCenterProductSnapshot,
    ProductAnswerUsageState,
    ProductEvaluationState,
    ProductFeedbackAnalysisState,
    ProductIssueFinding,
    ProductKnowledgeState,
    ProductModelState,
    ProductModuleCapability,
    ProductNotice,
    ProductQualityAnalysisState,
    ProductRuntimeIdentity,
    ProductServiceState,
)
from app.service.ai_capability import control_center_overview, latest_evaluation


_ISSUE_COPY = {
    "DATA_PROBLEM": (
        "数据问题",
        "请人工核对 C 侧受治理导出、来源目录与评测范围。",
    ),
    "KNOWLEDGE_PROBLEM": (
        "知识问题",
        "请人工核对冻结事实和受治理知识，不自动发布知识。",
    ),
    "RETRIEVAL_PROBLEM": (
        "检索问题",
        "完成来源核验后再人工复放同一范围的检索证据。",
    ),
    "PROMPT_OR_MODEL_PROBLEM": (
        "表达或模型问题",
        "仅在存在可复现证据后人工评审，不自动修改 Prompt。",
    ),
    "RULE_DECISION_PROBLEM": (
        "规则决策问题",
        "请人工核对受治理动作、必填字段和风险规则。",
    ),
}


def _service_state(overview: dict[str, Any]) -> ProductServiceState:
    service = overview["service"]
    status = service["status"]
    if status == "RUNNING":
        return ProductServiceState(
            status="RUNNING",
            display_status="服务运行中",
            summary="AI 客服服务已在当前 A 进程完成初始化。",
            last_initialization_status="READY",
        )
    if status == "ERROR":
        return ProductServiceState(
            status="ERROR",
            display_status="服务初始化异常",
            summary="当前服务未就绪；本投影不展示原始初始化错误。",
            last_initialization_status="FAILED",
        )
    return ProductServiceState(
        status="INITIALIZING",
        display_status="服务等待初始化",
        summary="当前 A 进程尚未完成 AI 客服服务初始化。",
        last_initialization_status="INITIALIZING",
    )


def _model_state(overview: dict[str, Any]) -> ProductModelState:
    service = overview["service"]
    model = overview["model"]
    if not model["configured"]:
        return ProductModelState(
            status="NOT_CONFIGURED",
            display_status="模型未配置",
            provider=model["provider"],
            model_name=model["name"],
            last_initialization_status="NOT_CONFIGURED",
            summary="当前没有可用模型配置；本接口不会探测或切换模型。",
        )
    if service["status"] == "RUNNING":
        return ProductModelState(
            status="READY",
            display_status="模型配置已就绪",
            provider=model["provider"],
            model_name=model["name"],
            last_initialization_status="READY",
            summary="模型随已就绪服务展示，真实可用性仍由显式 smoke 证明。",
        )
    if service["status"] == "ERROR":
        return ProductModelState(
            status="ERROR",
            display_status="模型初始化异常",
            provider=model["provider"],
            model_name=model["name"],
            last_initialization_status="FAILED",
            summary="模型配置存在但服务未就绪；本接口不会自动修复。",
        )
    return ProductModelState(
        status="INITIALIZING",
        display_status="模型等待初始化",
        provider=model["provider"],
        model_name=model["name"],
        last_initialization_status="INITIALIZING",
        summary="模型已配置，正在等待服务初始化。",
    )


def _knowledge_state(overview: dict[str, Any]) -> ProductKnowledgeState:
    count = overview["knowledge"]["queryable_chunk_count"]
    available = isinstance(count, int)
    return ProductKnowledgeState(
        status="AVAILABLE" if available else "NOT_AVAILABLE",
        indexed_chunk_count=count if available else None,
        display_status="知识索引已读取" if available else "知识索引暂无数据",
        summary=(
            f"当前 A 进程有 {count} 个可查询知识块。"
            if available
            else "当前 A 进程未提供可查询知识块数量。"
        ),
    )


def _evaluation_state(application: Any) -> ProductEvaluationState:
    evidence = latest_evaluation(
        application.state.settings.project_root / "docs" / "rag" / "evaluations"
    )
    latest = evidence.get("evaluation")
    if evidence.get("status") != "AVAILABLE" or not isinstance(latest, dict):
        return ProductEvaluationState(
            status="NOT_AVAILABLE",
            source="NOT_AVAILABLE",
            recorded_at_status="NOT_AVAILABLE",
            dataset_version_status="NOT_AVAILABLE",
            summary="暂无保存的真实评测基线。",
        )

    total = latest.get("total_cases")
    passed = latest.get("passed_cases")
    failed = total - passed if isinstance(total, int) and isinstance(passed, int) else None
    rate = latest.get("pass_rate")
    if not isinstance(rate, (int, float)) and isinstance(total, int) and total > 0 and isinstance(passed, int):
        rate = round(passed * 100 / total, 2)
    elif isinstance(rate, (int, float)) and 0 <= rate <= 1:
        rate = round(rate * 100, 2)
    recorded_at = latest.get("executed_at")
    dataset_version = latest.get("dataset_version")
    return ProductEvaluationState(
        status="AVAILABLE",
        source="SAVED_LIVE_C_API",
        evaluation_id=latest.get("evaluation_id"),
        recorded_at=recorded_at if recorded_at != "NOT_AVAILABLE" else None,
        recorded_at_status=(
            "AVAILABLE" if recorded_at and recorded_at != "NOT_AVAILABLE" else "NOT_AVAILABLE"
        ),
        dataset_version=(
            dataset_version if dataset_version and dataset_version != "NOT_AVAILABLE" else None
        ),
        dataset_version_status=(
            "AVAILABLE"
            if dataset_version and dataset_version != "NOT_AVAILABLE"
            else "NOT_AVAILABLE"
        ),
        total_case_count=total if isinstance(total, int) else None,
        passed_case_count=passed if isinstance(passed, int) else None,
        failed_case_count=failed,
        pass_rate_percent=float(rate) if isinstance(rate, (int, float)) else None,
        summary=(
            f"最近真实评测：{passed}/{total} 通过。"
            if isinstance(total, int) and isinstance(passed, int)
            else "最近真实评测存在，但计数信息不完整。"
        ),
    )


def _quality_state() -> ProductQualityAnalysisState:
    findings = [
        ProductIssueFinding(
            category=category,
            display_name=display_name,
            evidence="NO_SIGNAL_IN_CURRENT_REPORT",
            affected_case_count=0,
            summary="当前产品投影没有可安全归因的直接评测信号。",
            manual_next_step=next_step,
        )
        for category, (display_name, next_step) in _ISSUE_COPY.items()
    ]
    return ProductQualityAnalysisState(
        status="NOT_AVAILABLE",
        source_recorded_at_status="NOT_AVAILABLE",
        summary="当前基线不把未冻结的归因推断暴露为产品数据。",
        findings=findings,
    )


def product_control_center_snapshot(application: Any) -> AiControlCenterProductSnapshot:
    """Compose the product projection without model, network, or write actions."""
    overview = control_center_overview(application)
    service = overview["service"]
    knowledge = _knowledge_state(overview)
    evaluation = _evaluation_state(application)
    notices: list[ProductNotice] = []
    if evaluation.status == "NOT_AVAILABLE":
        notices.append(
            ProductNotice(
                code="EVALUATION_NOT_AVAILABLE",
                severity="INFO",
                title="暂无最近评测",
                summary="尚无可展示的真实评测基线。",
                manual_next_step="人工运行获批准的真实评测后再查看。",
            )
        )

    return AiControlCenterProductSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        service=_service_state(overview),
        model=_model_state(overview),
        knowledge=knowledge,
        answer_usage=ProductAnswerUsageState(
            status="NOT_AVAILABLE",
            metrics_scope="NOT_AVAILABLE",
            summary="当前投影不从总调用量推断具体回答动作类型。",
        ),
        latest_evaluation=evaluation,
        latest_quality_analysis=_quality_state(),
        modules=[
            ProductModuleCapability(
                module_id=overview["module_id"],
                name="AI 客服",
                status=service["status"],
                data_status=knowledge.status,
                operator_mode="READ_ONLY",
                display_status=_service_state(overview).display_status,
                summary="只读展示当前 A 进程和可查询知识状态。",
            )
        ],
        feedback_analysis=ProductFeedbackAnalysisState(
            status="NOT_CONFIGURED",
            summary="当前产品投影没有可安全展示的反馈分析聚合。",
        ),
        notices=notices,
        runtime=ProductRuntimeIdentity(service_version=application.version),
    )
