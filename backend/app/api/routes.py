from __future__ import annotations

from ipaddress import ip_address
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.config.settings import update_env_values
from app.models.chat import ChatRequest, ModelConfigUpdate, SearchRequest


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
        message = getattr(request.app.state, "loading_message", "系统正在初始化")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=message,
        )
    return request.app.state.rag_service


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
    return {
        "ready": ready,
        "message": getattr(request.app.state, "loading_message", "未知状态"),
        "model_configured": bool(rag and rag.model_configured),
        "initialization_error": getattr(request.app.state, "initialization_error", None),
    }


def statistics_data(request: Request) -> dict[str, Any]:
    rag = get_rag(request)
    settings = request.app.state.settings
    stats = rag.vector_store.get_collection_stats()
    document_count = (
        len(list(settings.knowledge_base_path.glob("*.pdf")))
        if settings.knowledge_base_path.exists()
        else 0
    )
    return {
        "document_count": document_count,
        "chunk_count": stats["total_chunks"],
        "embedding_model": stats["model_name"],
        "vector_database": "ChromaDB",
        "collection_name": stats["collection_name"],
        "model_configured": rag.model_configured,
    }


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
    if not new_key and not config.clear_api_key:
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
    result = rag.retrieve(search_request.query, search_request.top_k)
    result.pop("results", None)
    return envelope(result)


@router.post("/chat", tags=["chat"])
def chat(request: Request, chat_request: ChatRequest) -> dict[str, Any]:
    rag = get_rag(request)
    result = rag.query(chat_request.message)
    return {**envelope(result), **result}


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
    result = get_rag(request).query(chat_request.message)
    return {"code": 200, "message": "success", "data": result}
