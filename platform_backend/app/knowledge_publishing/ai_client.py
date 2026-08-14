from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.config import get_settings


class AiKnowledgePublicationUnavailable(RuntimeError):
    pass


class AiKnowledgePublicationClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.ai_service_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.ai_service_timeout_seconds
        self.settings = settings
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-AI-CS-Service-Token": self.settings.internal_service_token(),
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            TimeoutError,
            UnicodeError,
            json.JSONDecodeError,
        ) as exc:
            raise AiKnowledgePublicationUnavailable(
                "A商品知识发布服务不可用"
            ) from exc
        if not isinstance(decoded, dict):
            raise AiKnowledgePublicationUnavailable("A商品知识发布响应无效")
        return decoded

    def publish(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/api/admin/ai/knowledge-publications/products", payload)

    def visibility(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/api/admin/ai/knowledge-publications/visibility", payload)

    def publish_reply_rules(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/api/admin/ai/reply-rule-publications", payload)
