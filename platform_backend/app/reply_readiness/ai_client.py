from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.config import get_settings


class ReplyReadinessAiUnavailable(RuntimeError):
    pass


class ReplyReadinessAiClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ai_service_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.ai_service_timeout_seconds
        self.settings = settings
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def evaluate(self, payload: dict[str, object]) -> dict[str, object]:
        request = urllib.request.Request(
            f"{self.base_url}/api/admin/ai/reply-readiness/evaluate",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
                "X-AI-CS-Service-Token": self.settings.internal_service_token(),
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
            raise ReplyReadinessAiUnavailable("A reply-readiness evaluator is unavailable") from exc
        if not isinstance(decoded, dict):
            raise ReplyReadinessAiUnavailable("A reply-readiness response is invalid")
        return decoded
