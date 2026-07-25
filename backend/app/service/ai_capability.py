from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any


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

    def record(self, latency_ms: float, error_summary: str | None = None) -> None:
        with self._lock:
            self._call_count += 1
            self._total_latency_ms += max(0.0, latency_ms)
            self._last_called_at = datetime.now(timezone.utc).isoformat()
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
