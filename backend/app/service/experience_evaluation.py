"""Controlled, explicit evaluation of approved customer-experience snapshots.

The service intentionally has no polling loop and no persistence of source
content.  C remains the source of truth for approvals, immutable snapshots,
and recorded evaluation evidence.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

from app.config.settings import Settings
from app.service.quality_observation import QualityObservationService


EXPORT_PATH = "/api/v1/admin/ai-optimization/cases/export"
WRITEBACK_PATH = "/api/v1/admin/ai-optimization/evaluation-results"
_MAX_EXPORT_PAGES = 100
_EVALUATION_OUTCOMES = {"KEEP", "NEEDS_REVIEW", "REJECT"}
_SUGGESTION_CATEGORIES = {
    "PROMPT_HYPOTHESIS",
    "KNOWLEDGE_GAP",
    "POLICY_GAP",
    "COACHING",
}


class ExperienceEvaluationError(RuntimeError):
    """A stable, safe error passed through the A admin endpoint."""

    def __init__(self, code: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message


def _export_unavailable() -> ExperienceEvaluationError:
    return ExperienceEvaluationError(
        "EXPERIENCE_EVALUATION_EXPORT_UNAVAILABLE",
        503,
        "Approved experience-case export is unavailable.",
    )


def _model_unavailable() -> ExperienceEvaluationError:
    return ExperienceEvaluationError(
        "EXPERIENCE_EVALUATION_MODEL_UNAVAILABLE",
        503,
        "The configured local evaluation model is unavailable.",
    )


def _output_invalid() -> ExperienceEvaluationError:
    return ExperienceEvaluationError(
        "EXPERIENCE_EVALUATION_OUTPUT_INVALID",
        422,
        "The model did not return a valid evaluation result.",
    )


def _writeback_failed() -> ExperienceEvaluationError:
    return ExperienceEvaluationError(
        "EXPERIENCE_EVALUATION_WRITEBACK_FAILED",
        502,
        "The evaluation result could not be recorded by the platform.",
    )


@dataclass(frozen=True, slots=True)
class ApprovedExperienceSnapshot:
    case_id: str
    revision: int
    export_revision: str
    content_hash: str
    question: str
    ai_answer: str
    final_answer: str
    context: dict[str, str | None]


class PlatformExperienceCaseClient:
    """Small C API client limited to the frozen experience-case endpoints."""

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.base_url:
            raise _export_unavailable()
        body = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError("platform request failed") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("platform response is not an object")
        return decoded

    def fetch_approved_snapshot(
        self, case_id: str, revision: int
    ) -> ApprovedExperienceSnapshot:
        cursor: str | None = None
        try:
            for _ in range(_MAX_EXPORT_PAGES):
                query = urllib.parse.urlencode(
                    {"size": 100, **({"cursor": cursor} if cursor else {})}
                )
                response = self._request_json("GET", f"{EXPORT_PATH}?{query}")
                items = response.get("items")
                if not isinstance(items, list):
                    raise ValueError("export items are invalid")
                for item in items:
                    snapshot = _parse_snapshot(item)
                    if snapshot.case_id == case_id and snapshot.revision == revision:
                        return snapshot
                next_cursor = response.get("next_cursor")
                if next_cursor is None:
                    break
                if not isinstance(next_cursor, str) or not next_cursor.strip():
                    raise ValueError("export cursor is invalid")
                cursor = next_cursor
        except ExperienceEvaluationError:
            raise
        except (RuntimeError, ValueError, TypeError):
            raise _export_unavailable() from None
        # C only exposes APPROVED immutable snapshots.  A missing requested
        # revision is therefore not evaluated and is not treated as data input.
        raise _export_unavailable()

    def record_evaluation(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._request_json("POST", WRITEBACK_PATH, payload)
        except (RuntimeError, ValueError, TypeError):
            raise _writeback_failed() from None
        return response


def _required_string(payload: dict[str, Any], field: str, limit: int) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    value = value.strip()
    if not value or len(value) > limit:
        raise ValueError(f"{field} is invalid")
    return value


def _parse_snapshot(value: object) -> ApprovedExperienceSnapshot:
    if not isinstance(value, dict):
        raise ValueError("export item must be an object")
    revision = value.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ValueError("revision is invalid")
    raw_context = value.get("context")
    if not isinstance(raw_context, dict):
        raise ValueError("context is invalid")
    context: dict[str, str | None] = {}
    for key in ("store_code", "product_id", "sku_id"):
        context_value = raw_context.get(key)
        if context_value is not None and not isinstance(context_value, str):
            raise ValueError("context is invalid")
        context[key] = context_value
    if not context["store_code"]:
        raise ValueError("context store_code is invalid")
    return ApprovedExperienceSnapshot(
        case_id=_required_string(value, "case_id", 64),
        revision=revision,
        export_revision=_required_string(value, "export_revision", 160),
        content_hash=_required_string(value, "content_hash", 80),
        question=_required_string(value, "question", 8000),
        ai_answer=_required_string(value, "ai_answer", 12000),
        final_answer=_required_string(value, "final_answer", 12000),
        context=context,
    )


def _strip_json_fence(value: str) -> str:
    value = value.strip()
    if value.startswith("```json") and value.endswith("```"):
        return value[7:-3].strip()
    if value.startswith("```") and value.endswith("```"):
        return value[3:-3].strip()
    return value


def _parse_model_output(raw: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    try:
        payload = json.loads(_strip_json_fence(raw))
    except (TypeError, json.JSONDecodeError):
        raise _output_invalid() from None
    if not isinstance(payload, dict):
        raise _output_invalid()
    suggestions = payload.get("suggestions")
    raw_result = payload.get("result")
    if not isinstance(suggestions, list):
        raise _output_invalid()
    # qwen3.5:9b has returned both the requested nested form and the
    # equivalent flat form below.  Accept only these two explicitly bounded
    # shapes, then normalize before the traceable C writeback.
    if isinstance(raw_result, dict):
        outcome = raw_result.get("outcome")
        summary = raw_result.get("summary")
        dimensions = raw_result.get("dimensions")
    elif isinstance(raw_result, str):
        outcome = raw_result
        summary = payload.get("summary")
        dimensions = payload.get("dimensions")
    else:
        raise _output_invalid()
    if (
        not isinstance(outcome, str)
        or outcome not in _EVALUATION_OUTCOMES
        or not isinstance(summary, str)
        or not summary.strip()
        or len(summary.strip()) > 1000
    ):
        raise _output_invalid()
    normalized_result: dict[str, Any] = {
        "outcome": outcome,
        "summary": summary.strip(),
    }
    if dimensions is not None:
        if not isinstance(dimensions, dict) or any(
            not isinstance(key, str)
            or not isinstance(item, str)
            or not key.strip()
            or not item.strip()
            for key, item in dimensions.items()
        ):
            raise _output_invalid()
        normalized_result["dimensions"] = {
            key.strip(): item.strip() for key, item in dimensions.items()
        }
    if len(suggestions) > 5:
        raise _output_invalid()
    normalized_suggestions: list[dict[str, str]] = []
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            raise _output_invalid()
        category = suggestion.get("category")
        description = suggestion.get("description")
        if (
            not isinstance(category, str)
            or category not in _SUGGESTION_CATEGORIES
            or not isinstance(description, str)
            or not description.strip()
            or len(description.strip()) > 1000
        ):
            raise _output_invalid()
        normalized_suggestions.append(
            {"category": category, "description": description.strip()}
        )
    return normalized_result, normalized_suggestions


def _evaluation_prompt(snapshot: ApprovedExperienceSnapshot) -> str:
    context = json.dumps(snapshot.context, ensure_ascii=False, separators=(",", ":"))
    return (
        "Evaluate one human-approved customer-service experience case. "
        "This is analysis only: do not change prompts, publish knowledge, send a "
        "customer message, or take an external action. Compare the AI draft with "
        "the human final answer for faithfulness, safety, and coaching value. "
        "Return JSON only, without Markdown, using exactly this shape: "
        '{"result":{"outcome":"KEEP|NEEDS_REVIEW|REJECT","summary":"short "'
        'safe summary","dimensions":{"faithfulness":"PASS|NEEDS_REVIEW",'
        '"safety":"PASS|NEEDS_REVIEW","coaching_value":"PASS|NEEDS_REVIEW"}},'
        '"suggestions":[{"category":"PROMPT_HYPOTHESIS|KNOWLEDGE_GAP|POLICY_GAP|'
        'COACHING","description":"actionable but non-executing suggestion"}]}. '
        "Use an empty suggestions array when none is warranted.\n"
        f"Context: {context}\n"
        f"Customer question: {snapshot.question}\n"
        f"AI draft: {snapshot.ai_answer}\n"
        f"Human final answer: {snapshot.final_answer}"
    )


class ExperienceEvaluationService:
    """Explicit operator-triggered bridge from C snapshots to real Ollama."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.platform_client = PlatformExperienceCaseClient(
            settings.platform_api_base_url,
            settings.platform_api_timeout_seconds,
        )

    def _call_ollama(self, prompt: str) -> str:
        if self.settings.llm_provider != "ollama" or not self.settings.llm_model:
            raise _model_unavailable()
        request_body = json.dumps(
            {
                "model": self.settings.llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You produce controlled JSON evaluation evidence only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "think": False,
                "options": {
                    "temperature": self.settings.llm_temperature,
                    "top_p": self.settings.llm_top_p,
                    "num_predict": self.settings.llm_max_tokens,
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.llm_base_url}/api/chat",
            data=request_body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.llm_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            raw = str((payload.get("message") or {}).get("content") or "").strip()
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            AttributeError,
        ):
            raise _model_unavailable() from None
        if not raw:
            raise _model_unavailable()
        return raw

    def run(self, case_id: str, revision: int) -> dict[str, Any]:
        return self._run(case_id, revision)

    def run_with_quality_observation(
        self,
        case_id: str,
        revision: int,
        observer: QualityObservationService,
    ) -> dict[str, Any]:
        """Evaluate and aggregate one case within the existing C writeback flow.

        Classification happens before the C writeback, while the immutable
        snapshot is still in memory.  Its aggregate is updated only after the
        platform accepts the evaluation evidence, so a failed run cannot add a
        misleading Badcase count.
        """
        return self._run(case_id, revision, observer=observer)

    def _run(
        self,
        case_id: str,
        revision: int,
        observer: QualityObservationService | None = None,
    ) -> dict[str, Any]:
        snapshot = self.platform_client.fetch_approved_snapshot(case_id, revision)
        raw_output = self._call_ollama(_evaluation_prompt(snapshot))
        result, suggestions = _parse_model_output(raw_output)
        issues = (
            observer.classify(
                question=snapshot.question,
                ai_answer=snapshot.ai_answer,
                final_answer=snapshot.final_answer,
            )
            if observer is not None
            else None
        )
        evaluation_run_id = f"AEC-{uuid.uuid4()}"
        payload = {
            "case_id": snapshot.case_id,
            "revision": snapshot.revision,
            "export_revision": snapshot.export_revision,
            "content_hash": snapshot.content_hash,
            "evaluation_run_id": evaluation_run_id,
            "model_version": self.settings.llm_model,
            "prompt_version": self.settings.experience_evaluation_prompt_version,
            "result": result,
            "suggestions": suggestions,
        }
        recorded = self.platform_client.record_evaluation(payload)
        # Do not surface the source snapshot or prompt.  C returns only the
        # traceable evaluation evidence it recorded.
        if observer is not None and issues is not None:
            metrics = observer.metrics.record(issues, self.settings.llm_model)
            return {
                **recorded,
                "quality_observation": {
                    "issues": issues,
                    "metrics": metrics,
                },
            }
        return recorded
