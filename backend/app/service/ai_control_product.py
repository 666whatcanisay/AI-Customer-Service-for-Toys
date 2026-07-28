"""Chinese product projection for the read-only AI control-center interface.

The projection deliberately composes existing safe A snapshots.  It does not
call Qwen, contact C, read customer content, or change Prompt/knowledge/model
state while responding to a GET request.
"""

from __future__ import annotations

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
from app.service.ai_capability import (
    control_center_snapshot,
    operations_overview_snapshot,
)
from app.service.quality_baseline import latest_quality_baseline


_STATUS_COPY = {
    "RUNNING": "运行中",
    "PAUSED": "等待初始化",
    "ERROR": "初始化异常",
    "PLANNED": "规划中",
    "CONFIGURED": "已配置",
    "NOT_CONFIGURED": "未配置",
    "AVAILABLE": "有数据",
    "NOT_AVAILABLE": "暂无数据",
    "MANUAL_ONLY": "仅人工触发",
}

_ISSUE_COPY = {
    "DATA_PROBLEM": (
        "数据问题",
        "请人工核对 C 侧受治理导出、来源目录与评测范围；不要自动修改知识或 Prompt。",
    ),
    "KNOWLEDGE_PROBLEM": (
        "知识问题",
        "请人工将冻结的期望事实与受治理知识内容核对；不要自动发布知识。",
    ),
    "RETRIEVAL_PROBLEM": (
        "检索问题",
        "完成来源核验后，再人工复放同一范围的检索证据。",
    ),
    "PROMPT_OR_MODEL_PROBLEM": (
        "表达或模型问题",
        "仅在有可复现的受证据结果后人工评审；不会自动修改 Prompt 或切换模型。",
    ),
    "RULE_DECISION_PROBLEM": (
        "规则决策问题",
        "请人工核对受治理动作、必填字段和风险规则。",
    ),
}

_NOTICE_COPY = {
    "EVALUATION_NOT_AVAILABLE": (
        "暂无最近评测",
        "尚无可展示的真实评测基线。",
        "人工运行获批准的真实评测后再查看质量趋势。",
    ),
    "EVALUATION_QUALITY_ATTENTION": (
        "评测需要关注",
        "最近一次真实评测存在未通过案例。",
        "先查看评测归因和证据，再由人工提出优化方案。",
    ),
    "KNOWLEDGE_EVIDENCE_COVERAGE_ATTENTION": (
        "知识证据覆盖需关注",
        "最近评测的来源归属校验存在缺口。",
        "人工核对 C 侧来源治理与评测证据；不会自动发布知识。",
    ),
    "BADCASE_AGGREGATE_NOT_AVAILABLE": (
        "Badcase 汇总暂无数据",
        "A 尚未取得可安全展示的去标识化 Badcase 聚合。",
        "完成跨线聚合契约审核后再接入；不要读取原始反馈。",
    ),
    "C_FEEDBACK_NOT_CONFIGURED": (
        "反馈分析未配置",
        "当前 A 进程没有配置隔离的 C 反馈接入。",
        "由运维人工配置隔离接口并完成去标识化确认。",
    ),
    "C_EFFICIENCY_CONTRACT_NOT_REGISTERED": (
        "效率数据尚未接入",
        "A 尚未登记可消费的跨线效率汇总契约。",
        "先完成版本化聚合契约审核，再增加消费者。",
    ),
    "MODEL_NOT_CONFIGURED": (
        "模型未配置",
        "当前 A 进程没有可用的模型客户端配置。",
        "人工核对本地模型配置后运行显式 smoke，不会自动切换模型。",
    ),
}


def _availability(value: str | None) -> tuple[str | None, str]:
    if not value or value == "NOT_AVAILABLE":
        return None, "NOT_AVAILABLE"
    return value, "AVAILABLE"


def _service_state(detail: Any) -> ProductServiceState:
    if detail.status == "RUNNING":
        return ProductServiceState(
            status="RUNNING",
            display_status="服务运行中",
            summary="AI 客服服务已在当前 A 进程中完成初始化。",
            last_initialization_status="READY",
        )
    if detail.status == "ERROR":
        return ProductServiceState(
            status="ERROR",
            display_status="服务初始化异常",
            summary="当前服务未就绪；为保护运行信息，不展示原始初始化错误。",
            last_initialization_status="FAILED",
        )
    return ProductServiceState(
        status="INITIALIZING",
        display_status="服务等待初始化",
        summary="当前 A 进程尚未完成 AI 客服服务初始化。",
        last_initialization_status="INITIALIZING",
    )


def _model_state(detail: Any) -> ProductModelState:
    configured = bool(detail.model_configured)
    if not configured:
        return ProductModelState(
            status="NOT_CONFIGURED",
            display_status="模型未配置",
            provider=detail.model_provider,
            model_name=detail.model_name,
            last_initialization_status="NOT_CONFIGURED",
            summary="未检测到可用模型配置；本接口不会发起模型探测或自动切换模型。",
        )
    if detail.status == "RUNNING":
        return ProductModelState(
            status="READY",
            display_status="模型配置已就绪",
            provider=detail.model_provider,
            model_name=detail.model_name,
            last_initialization_status="READY",
            summary="模型配置随已就绪服务展示；真实可用性仅由显式 smoke 证明。",
        )
    if detail.status == "ERROR":
        return ProductModelState(
            status="ERROR",
            display_status="模型初始化异常",
            provider=detail.model_provider,
            model_name=detail.model_name,
            last_initialization_status="FAILED",
            summary="模型配置存在但服务未就绪；本接口不展示原始错误或自动修复。",
        )
    return ProductModelState(
        status="INITIALIZING",
        display_status="模型等待初始化",
        provider=detail.model_provider,
        model_name=detail.model_name,
        last_initialization_status="INITIALIZING",
        summary="模型已配置，正在等待服务初始化；本接口不主动探测模型。",
    )


def _quality_state(application: Any) -> tuple[ProductEvaluationState, ProductQualityAnalysisState]:
    root = application.state.settings.project_root / "docs" / "rag" / "evaluations"
    quality = latest_quality_baseline(root)
    if quality.status != "AVAILABLE" or quality.summary is None:
        evaluation = ProductEvaluationState(
            status="NOT_AVAILABLE",
            source="NOT_AVAILABLE",
            recorded_at_status="NOT_AVAILABLE",
            dataset_version_status="NOT_AVAILABLE",
            summary="暂无保存的真实评测基线。",
        )
        findings = [
            ProductIssueFinding(
                category=category,
                display_name=display_name,
                evidence="NO_SIGNAL_IN_CURRENT_REPORT",
                affected_case_count=0,
                summary="当前没有可归因的真实评测信号。",
                manual_next_step=next_step,
            )
            for category, (display_name, next_step) in _ISSUE_COPY.items()
        ]
        return evaluation, ProductQualityAnalysisState(
            status="NOT_AVAILABLE",
            source_recorded_at_status="NOT_AVAILABLE",
            summary="暂无真实评测，因此不对问题原因作推断。",
            findings=findings,
        )

    summary = quality.summary
    recorded_at, recorded_at_status = _availability(summary.executed_at)
    dataset_version, dataset_version_status = _availability(summary.dataset_version)
    evaluation = ProductEvaluationState(
        status="AVAILABLE",
        source="SAVED_LIVE_C_API",
        evaluation_id=summary.evaluation_id,
        recorded_at=recorded_at,
        recorded_at_status=recorded_at_status,
        dataset_version=dataset_version,
        dataset_version_status=dataset_version_status,
        total_case_count=summary.total_case_count,
        passed_case_count=summary.passed_case_count,
        failed_case_count=summary.failed_case_count,
        pass_rate_percent=summary.pass_rate_percent,
        summary=(
            f"最近真实评测：{summary.passed_case_count}/{summary.total_case_count} 通过，"
            f"通过率 {summary.pass_rate_percent:.2f}%。"
        ),
    )
    findings_by_category = {finding.category: finding for finding in quality.cause_findings}
    findings = []
    for category, (display_name, next_step) in _ISSUE_COPY.items():
        finding = findings_by_category.get(category)
        count = finding.affected_case_count if finding is not None else 0
        evidence = (
            finding.evidence
            if finding is not None
            else "NO_SIGNAL_IN_CURRENT_REPORT"
        )
        findings.append(
            ProductIssueFinding(
                category=category,
                display_name=display_name,
                evidence=evidence,
                affected_case_count=count,
                summary=(
                    f"当前真实评测中有 {count} 个未通过案例出现该类直接归因信号。"
                    if count
                    else "当前真实评测中没有该类直接归因信号。"
                ),
                manual_next_step=next_step,
            )
        )
    return evaluation, ProductQualityAnalysisState(
        status="AVAILABLE",
        source_evaluation_id=summary.evaluation_id,
        source_recorded_at=recorded_at,
        source_recorded_at_status=recorded_at_status,
        failed_case_count=summary.failed_case_count,
        summary=(
            f"最近真实评测有 {summary.failed_case_count} 个未通过案例；"
            "以下仅为证据归因与人工下一步，不会自动修改任何 AI 配置。"
        ),
        findings=findings,
    )


def _product_notices(operations: Any) -> list[ProductNotice]:
    notices: list[ProductNotice] = []
    for notice in operations.notices:
        title, summary, next_step = _NOTICE_COPY.get(
            notice.code,
            ("运行提示", "存在一项需要人工查看的 AI 运行提示。", "请人工查看该提示的原始只读运维摘要。"),
        )
        notices.append(
            ProductNotice(
                code=notice.code,
                severity=notice.severity,
                title=title,
                summary=summary,
                manual_next_step=next_step,
            )
        )
    return notices


def product_control_center_snapshot(application: Any) -> AiControlCenterProductSnapshot:
    """Compose a stable Chinese UI projection without any external I/O."""
    control = control_center_snapshot(application)
    operations = operations_overview_snapshot(application)
    detail = control.customer_service
    evaluation, quality_analysis = _quality_state(application)

    knowledge_count = operations.knowledge_coverage.indexed_chunk_count
    knowledge_available = isinstance(knowledge_count, int)
    knowledge = ProductKnowledgeState(
        status="AVAILABLE" if knowledge_available else "NOT_AVAILABLE",
        indexed_chunk_count=knowledge_count if knowledge_available else None,
        display_status="知识索引已读取" if knowledge_available else "知识索引暂无数据",
        summary=(
            f"当前 A 进程已同步 {knowledge_count} 个知识块。"
            if knowledge_available
            else "当前 A 进程未提供可展示的知识块数量。"
        ),
    )
    volume = operations.answer_volume
    usage_available = volume.status == "AVAILABLE"
    answer_usage = ProductAnswerUsageState(
        status="AVAILABLE" if usage_available else "NOT_AVAILABLE",
        metrics_scope=("A_PROCESS_SINCE_START" if usage_available else "NOT_AVAILABLE"),
        processed_request_count=volume.processed_request_count if usage_available else None,
        direct_answer_count=volume.direct_answer_count if usage_available else None,
        controlled_answer_count=(volume.controlled_answer_count if usage_available else None),
        transfer_human_count=volume.transfer_human_count if usage_available else None,
        other_outcome_count=volume.other_outcome_count if usage_available else None,
        summary=(
            "当前 A 进程已记录回答动作汇总；重启后会从零开始，不代表人员绩效。"
            if usage_available
            else "暂无当前 A 进程的回答动作汇总。"
        ),
    )
    modules = [
        ProductModuleCapability(
            module_id=capability.capability_id,
            name=capability.name,
            status=capability.status,
            data_status=capability.data_status,
            operator_mode=capability.operator_mode,
            display_status=_STATUS_COPY[capability.status],
            summary=capability.summary,
        )
        for capability in control.capabilities
    ]
    feedback = control.feedback_analysis
    latest_run = feedback.latest_run
    feedback_state = ProductFeedbackAnalysisState(
        status=feedback.status,
        latest_completed_at=latest_run.completed_at if latest_run else None,
        completed_analysis_count=(latest_run.completed_analysis_count if latest_run else None),
        summary=(
            f"当前 A 进程保留 {latest_run.completed_analysis_count} 条已完成的去标识化分析汇总。"
            if latest_run
            else "暂无当前 A 进程可展示的反馈分析汇总；不会读取反馈原文。"
        ),
    )
    return AiControlCenterProductSnapshot(
        generated_at=control.generated_at,
        service=_service_state(detail),
        model=_model_state(detail),
        knowledge=knowledge,
        answer_usage=answer_usage,
        latest_evaluation=evaluation,
        latest_quality_analysis=quality_analysis,
        modules=modules,
        feedback_analysis=feedback_state,
        notices=_product_notices(operations),
        runtime=ProductRuntimeIdentity(service_version=application.version),
    )
