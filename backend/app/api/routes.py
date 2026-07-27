from __future__ import annotations

from ipaddress import ip_address
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config.settings import update_env_values
from app.models.chat import (
    AIOnlineTestRequest,
    ChatRequest,
    ExperienceEvaluationRunRequest,
    FeedbackAnalysisRunRequest,
    ModelConfigUpdate,
    SearchRequest,
)
from app.service.experience_evaluation import (
    ExperienceEvaluationError,
    ExperienceEvaluationService,
)
from app.service.feedback_analysis import (
    FeedbackAnalysisError,
    FeedbackAnalysisService,
)
from app.service.ai_capability import (
    INITIALIZATION_FAILED_CODE,
    MODULE_DEFINITIONS,
    MODULES_BY_ID,
    customer_service_detail,
    knowledge_collection_counts,
    latest_evaluation,
    module_summary,
    not_available_module_detail,
    prompt_metadata,
    safe_initialization_error,
)
from app.service.test_knowledge import (
    PlatformIntegrationUnavailable,
    TestKnowledgeValidationError,
)


router = APIRouter()

RECOMMENDED_QUESTIONS = [
    "党员有哪些义务？",
    "党章的内容有哪些？",
    "如何申请入党？",
    "党费如何缴纳？",
]


def envelope(data: Any, message: str = "ok", success: bool = True) -> dict[str, Any]:
    return {"success": success, "message": message, "data": data}


def get_rag(request: Request):
    if not getattr(request.app.state, "ready", False):
        message = (
            "AI service initialization failed. Check service logs."
            if safe_initialization_error(
                getattr(request.app.state, "initialization_error", None)
            )
            else "AI service is initializing."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=message,
        )
    return request.app.state.rag_service


def get_experience_evaluation_service(request: Request) -> ExperienceEvaluationService:
    service = getattr(request.app.state, "experience_evaluation_service", None)
    if service is None:
        service = ExperienceEvaluationService(request.app.state.settings)
        request.app.state.experience_evaluation_service = service
    return service


def get_feedback_analysis_service(request: Request) -> FeedbackAnalysisService:
    service = getattr(request.app.state, "feedback_analysis_service", None)
    if service is None:
        service = FeedbackAnalysisService(request.app.state.settings)
        request.app.state.feedback_analysis_service = service
    return service


def require_loopback_client(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host == "testclient":
        return
    try:
        is_loopback = ip_address(client_host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="大模型配置仅允许从本机访问",
        )


def model_config_data(rag) -> dict[str, Any]:
    return {
        "provider": rag.settings.llm_provider,
        "model": rag.settings.llm_model,
        "configured": rag.model_configured,
        "storage": "backend/.env",
        "restart_required": False,
    }


def status_data(request: Request) -> dict[str, Any]:
    ready = bool(getattr(request.app.state, "ready", False))
    rag = getattr(request.app.state, "rag_service", None)
    initialization_error = safe_initialization_error(
        getattr(request.app.state, "initialization_error", None)
    )
    return {
        "ready": ready,
        "message": (
            "System ready."
            if ready
            else "AI service initialization failed. Check service logs."
            if initialization_error == INITIALIZATION_FAILED_CODE
            else "AI service is initializing."
        ),
        "model_configured": bool(rag and rag.model_configured),
        "initialization_error": initialization_error,
    }


def statistics_data(request: Request) -> dict[str, Any]:
    rag = get_rag(request)
    settings = request.app.state.settings
    stats = rag.vector_store.get_collection_stats()
    primary_chunk_count, test_knowledge_chunk_count = knowledge_collection_counts(rag)
    document_count = (
        len(list(settings.knowledge_base_path.glob("*.pdf")))
        if settings.knowledge_base_path.exists()
        else 0
    )
    return {
        "document_count": document_count,
        "chunk_count": primary_chunk_count + test_knowledge_chunk_count,
        "embedding_model": stats["model_name"],
        "vector_database": "ChromaDB",
        "collection_name": stats["collection_name"],
        "model_configured": rag.model_configured,
    }


def admin_module_or_404(module_id: str):
    module = MODULES_BY_ID.get(module_id)
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI_MODULE_NOT_FOUND",
        )
    return module


def module_not_testable_response(module_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=envelope(
            {"code": "AI_MODULE_NOT_TESTABLE", "module_id": module_id},
            message="AI module is planned and cannot be tested.",
            success=False,
        ),
    )


def module_not_ready_response(module_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=envelope(
            {"code": "AI_MODULE_NOT_READY", "module_id": module_id},
            message="AI module is not ready for an online test.",
            success=False,
        ),
    )


@router.get("/health", tags=["system"])
def health(request: Request) -> dict[str, Any]:
    data = {
        "status": "ok",
        "ready": bool(getattr(request.app.state, "ready", False)),
    }
    return {**envelope(data), "状态": "正常"}


@router.get("/status", tags=["system"])
def service_status(request: Request) -> dict[str, Any]:
    data = status_data(request)
    return {**envelope(data), **data}


@router.get("/knowledge/statistics", tags=["knowledge"])
def knowledge_statistics(request: Request) -> dict[str, Any]:
    data = statistics_data(request)
    return envelope(data)


@router.get("/stats", tags=["knowledge"])
def legacy_statistics(request: Request) -> dict[str, Any]:
    data = statistics_data(request)
    return {
        **envelope(data),
        "文档数量": data["document_count"],
        "向量块数量": data["chunk_count"],
        "嵌入模型": data["embedding_model"],
        "向量数据库": data["vector_database"],
    }


@router.get("/questions/recommended", tags=["chat"])
def recommended_questions() -> dict[str, Any]:
    data = {"questions": RECOMMENDED_QUESTIONS}
    return {**envelope(data), "questions": RECOMMENDED_QUESTIONS}


@router.get("/config/model", tags=["configuration"])
def get_model_config(request: Request) -> dict[str, Any]:
    require_loopback_client(request)
    return envelope(model_config_data(get_rag(request)))


@router.put("/config/model", tags=["configuration"])
def update_model_config(
    request: Request, config: ModelConfigUpdate
) -> dict[str, Any]:
    require_loopback_client(request)
    rag = get_rag(request)
    old_provider = rag.settings.llm_provider
    old_model = rag.settings.llm_model
    old_key = rag.settings.dashscope_api_key
    submitted_key = config.api_key.get_secret_value().strip() if config.api_key else ""

    if config.clear_api_key and submitted_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="清除 Key 与填写新 Key 不能同时操作",
        )
    new_key = "" if config.clear_api_key else (submitted_key or old_key)
    if config.provider != "ollama" and not new_key and not config.clear_api_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="首次配置必须填写 API Key",
        )

    rag.configure_model(config.provider, config.model, new_key)
    try:
        update_env_values(
            rag.settings,
            {
                "LLM_PROVIDER": config.provider,
                "LLM_MODEL": config.model,
                "DASHSCOPE_API_KEY": new_key,
            },
        )
    except Exception as exc:
        rag.configure_model(old_provider, old_model, old_key)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="模型配置保存失败，请检查 backend/.env 是否可写",
        ) from exc

    return envelope(model_config_data(rag), message="大模型配置已保存并即时生效")


@router.post("/retrieval/search", tags=["knowledge"])
def retrieval_search(request: Request, search_request: SearchRequest) -> dict[str, Any]:
    rag = get_rag(request)
    result = rag.retrieve(
        search_request.query,
        search_request.top_k,
        context=search_request.context,
    )
    result.pop("results", None)
    return envelope(result)


@router.post("/chat", tags=["chat"])
def chat(request: Request, chat_request: ChatRequest) -> dict[str, Any]:
    rag = get_rag(request)
    result = rag.query(
        chat_request.resolved_question, context=chat_request.context
    )
    return {**envelope(result), **result}


@router.post("/test-knowledge/sync/{package_id}", tags=["test-knowledge"])
def sync_test_knowledge(request: Request, package_id: str) -> dict[str, Any]:
    require_loopback_client(request)
    try:
        result = get_rag(request).sync_test_knowledge(package_id)
    except PlatformIntegrationUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ENV_BLOCKED: {exc}",
        ) from exc
    except TestKnowledgeValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid V0.3.1 test package: {exc}",
        ) from exc
    return envelope(result, message="V0.3.1 test knowledge synchronized")


@router.get("/admin/ai/modules", tags=["ai-admin"])
def list_ai_modules(request: Request) -> dict[str, Any]:
    details = customer_service_detail(request.app)
    modules = [
        module_summary(module, details["status"])
        if module.implemented
        else module_summary(module, "PLANNED")
        for module in MODULE_DEFINITIONS
    ]
    return envelope({"modules": modules})


@router.get("/admin/ai/modules/{module_id}", tags=["ai-admin"])
def get_ai_module(request: Request, module_id: str) -> dict[str, Any]:
    module = admin_module_or_404(module_id)
    detail = (
        customer_service_detail(request.app)
        if module.implemented
        else not_available_module_detail(module)
    )
    return envelope(detail)


@router.get("/admin/ai/modules/{module_id}/prompt", tags=["ai-admin"])
def get_ai_module_prompt(request: Request, module_id: str) -> dict[str, Any]:
    module = admin_module_or_404(module_id)
    if not module.implemented:
        return envelope(
            {
                "module_id": module_id,
                "status": "NOT_AVAILABLE",
                "prompt_version": "NOT_AVAILABLE",
                "prompt_hash": "NOT_AVAILABLE",
            }
        )
    del request
    return envelope({"module_id": module_id, **prompt_metadata()})


@router.post(
    "/admin/ai/modules/{module_id}/test",
    tags=["ai-admin"],
    response_model=None,
)
def run_ai_module_test(
    request: Request,
    module_id: str,
    test_request: AIOnlineTestRequest,
):
    module = admin_module_or_404(module_id)
    if not module.implemented:
        return module_not_testable_response(module_id)
    detail = customer_service_detail(request.app)
    if not detail["ready"]:
        return module_not_ready_response(module_id)

    result = get_rag(request).query(
        test_request.question,
        context=test_request.context,
    )
    data = {
        key: result.get(key)
        for key in (
            "answer",
            "action",
            "risk_level",
            "sources",
            "latency_ms",
            "model",
            "request_id",
        )
    }
    if test_request.include_diagnostics:
        data["diagnostics"] = {
            "source_count": len(result.get("sources") or []),
            "warning_codes": result.get("warnings") or [],
            "required_fields": result.get("required_fields") or [],
        }
    return envelope(data)


@router.post(
    "/admin/ai/experience-evaluations/run",
    tags=["ai-admin"],
    response_model=None,
)
def run_experience_evaluation(
    request: Request,
    evaluation_request: ExperienceEvaluationRunRequest,
):
    """Evaluate one C-approved immutable snapshot on explicit operator request."""
    try:
        recorded = get_experience_evaluation_service(request).run(
            evaluation_request.case_id,
            evaluation_request.revision,
        )
    except ExperienceEvaluationError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope({"code": exc.code}, message=exc.message, success=False),
        )
    return envelope(recorded, message="Experience evaluation recorded")


@router.post(
    "/admin/ai/feedback-analysis/run",
    tags=["ai-admin"],
    response_model=None,
)
def run_feedback_analysis(
    request: Request,
    analysis_request: FeedbackAnalysisRunRequest,
):
    """Run one explicit local feedback-analysis batch; no background polling."""
    require_loopback_client(request)
    try:
        recorded = get_feedback_analysis_service(request).run(analysis_request.maximum)
    except FeedbackAnalysisError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope({"code": exc.code}, message=exc.message, success=False),
        )
    return envelope(recorded, message="Feedback analysis recorded")


@router.get("/admin/ai/modules/{module_id}/evaluations/latest", tags=["ai-admin"])
def get_latest_ai_module_evaluation(
    request: Request, module_id: str
) -> dict[str, Any]:
    module = admin_module_or_404(module_id)
    if not module.implemented:
        return envelope(
            {
                "module_id": module_id,
                "status": "NOT_AVAILABLE",
                "evaluation": None,
            }
        )
    return envelope(
        {
            "module_id": module_id,
            **latest_evaluation(
                request.app.state.settings.project_root
                / "docs"
                / "rag"
                / "evaluations"
            ),
        }
    )


@router.get("/ai/status", tags=["compatibility"])
def java_proxy_status_compatibility(request: Request) -> dict[str, Any]:
    data = status_data(request)
    data["aiUrl"] = str(request.base_url).rstrip("/")
    return {"code": 200, "message": "success", "data": data}


@router.get("/ai/stats", tags=["compatibility"])
def java_proxy_stats_compatibility(request: Request) -> dict[str, Any]:
    return {"code": 200, "message": "success", "data": statistics_data(request)}


@router.post("/ai/chat", tags=["compatibility"])
def java_proxy_chat_compatibility(
    request: Request, chat_request: ChatRequest
) -> dict[str, Any]:
    result = get_rag(request).query(
        chat_request.resolved_question, context=chat_request.context
    )
    return {"code": 200, "message": "success", "data": result}
