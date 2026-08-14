from __future__ import annotations

import json
import time
from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from typing import Protocol
from urllib.parse import urlsplit

from .pdd_login import EdgePDDTargetResolver, PDDCDPPageTarget
from .pdd_observer import (
    PDDConversationNavigationError,
    PDDConversationSummary,
)


class PDDNavigationEvaluator(Protocol):
    def evaluate(self, target: PDDCDPPageTarget, expression: str) -> object: ...


class WebSocketPDDConversationNavigationPort:
    """One narrowly-scoped CDP click port for verified conversation rows.

    It can neither focus/fill the composer nor submit a reply.  Every click is
    guarded by the official page identity, an empty/non-composing reply input
    and an exact conversation-row match.  PDD focuses its empty composer by
    default, so focus alone is not treated as evidence of human typing.
    """

    def __init__(
        self,
        *,
        profile_path: str | Path,
        applicable_path: str,
        selectors: Mapping[str, Mapping[str, object]],
        resolver: EdgePDDTargetResolver,
        evaluator: PDDNavigationEvaluator,
        timeout_seconds: float = 2.0,
    ) -> None:
        self._profile_path = Path(profile_path).resolve()
        self._applicable_path = applicable_path
        self._selectors = json.dumps(selectors, ensure_ascii=False, separators=(",", ":"))
        self._resolver = resolver
        self._evaluator = evaluator
        self._timeout = max(0.25, min(timeout_seconds, 5.0))
        self._lock = RLock()

    def navigate(
        self,
        summary: PDDConversationSummary,
        *,
        allow_attention_missing: bool = False,
    ) -> None:
        expected = json.dumps(summary.conversation_id, ensure_ascii=False)
        allow_missing = "true" if allow_attention_missing else "false"
        expression = rf"""
(() => {{
  const s = {self._selectors};
  const expected = {expected};
  const allowAttentionMissing = {allow_missing};
  const reject = (error_code) => ({{triggered:false,error_code}});
  const normalize = (value) => {{
    const text = String(value || '').trim();
    const match = text.match(/^(\d{{8,20}})(?:\D|$)/);
    return match ? match[1] : text;
  }};
  const nodes = (root, name) => {{
    const binding = s[name];
    if (!binding) return [];
    const scope = root || document;
    const result = [];
    if (scope !== document && scope.matches?.(binding.selector)) result.push(scope);
    result.push(...Array.from(scope.querySelectorAll(binding.selector)));
    return result;
  }};
  const text = (node, name) => {{
    const binding = s[name];
    if (!node || !binding) return '';
    return String(binding.attribute ? (node.getAttribute(binding.attribute) || '') : (node.textContent || '')).trim();
  }};
  if (location.origin !== 'https://mms.pinduoduo.com' || location.pathname !== {json.dumps(self._applicable_path)}) {{
    return reject('PDD_NAVIGATION_PAGE_CHANGED');
  }}
  const inputs = nodes(document, 'reply_input');
  if (inputs.length !== 1) return reject('PDD_NAVIGATION_REPLY_INPUT_AMBIGUOUS');
  const input = inputs[0];
  const inputText = String(input.value ?? input.innerText ?? input.textContent ?? '').trim();
  const composing = input.isComposing === true || input.getAttribute('data-composing') === 'true';
  if (inputText.length > 0 || composing) {{
    return reject('PDD_NAVIGATION_HUMAN_INPUT_ACTIVE');
  }}
  const rows = nodes(document, 'conversation_item').filter((row) => {{
    const ids = nodes(row, 'conversation_id');
    return ids.length === 1 && normalize(text(ids[0], 'conversation_id')) === expected;
  }});
  if (rows.length !== 1) return reject('PDD_NAVIGATION_TARGET_AMBIGUOUS');
  const row = rows[0];
  const attention = nodes(row, 'conversation_attention');
  if (!allowAttentionMissing && attention.length !== 1) return reject('PDD_NAVIGATION_ATTENTION_MISSING');
  if (attention.length > 1) return reject('PDD_NAVIGATION_ATTENTION_AMBIGUOUS');
  const targets = nodes(row, 'conversation_select_target');
  if (targets.length !== 1) return reject('PDD_NAVIGATION_CLICK_TARGET_AMBIGUOUS');
  targets[0].click();
  return {{triggered:true,error_code:null}};
}})()
""".strip()
        with self._lock:
            target = self._target()
            value = self._evaluator.evaluate(target, expression)
            if not isinstance(value, dict) or value.get("triggered") is not True:
                code = (
                    str(value.get("error_code"))
                    if isinstance(value, dict) and value.get("error_code")
                    else "PDD_NAVIGATION_REJECTED"
                )
                raise PDDConversationNavigationError(
                    "PDD conversation navigation was rejected",
                    error_code=code,
                    manual_review=code
                    not in {
                        "PDD_NAVIGATION_ATTENTION_MISSING",
                        "PDD_NAVIGATION_HUMAN_INPUT_ACTIVE",
                    },
                )
            deadline = time.monotonic() + self._timeout
            while time.monotonic() < deadline:
                if self._active_conversation_id() == summary.conversation_id:
                    return
                time.sleep(0.1)
        raise PDDConversationNavigationError(
            "PDD target conversation did not become stable",
            error_code="PDD_NAVIGATION_TARGET_NOT_STABLE",
            manual_review=False,
        )

    def _active_conversation_id(self) -> str | None:
        expression = rf"""
(() => {{
  const s = {self._selectors};
  if (location.origin !== 'https://mms.pinduoduo.com' || location.pathname !== {json.dumps(self._applicable_path)}) return null;
  const binding = s.active_conversation_id;
  const active = Array.from(document.querySelectorAll(binding.selector));
  const containers = Array.from(document.querySelectorAll(s.message_container.selector));
  const maximum = Number(binding.maximum_matches || 1);
  if (active.length === 0 || active.length > maximum || containers.length !== 1) return null;
  const normalized = active.map((node) => {{
    const raw = String(binding.attribute ? (node.getAttribute(binding.attribute) || '') : (node.textContent || '')).trim();
    const match = raw.match(/^(\d{{8,20}})(?:\D|$)/);
    return match ? match[1] : raw;
  }}).filter(Boolean);
  const unique = Array.from(new Set(normalized));
  return unique.length === 1 ? unique[0] : null;
}})()
""".strip()
        value = self._evaluator.evaluate(self._target(), expression)
        return value if isinstance(value, str) and value else None

    def _target(self) -> PDDCDPPageTarget:
        target = self._resolver.resolve(self._profile_path)
        parsed = urlsplit(target.page_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "mms.pinduoduo.com"
            or parsed.path != self._applicable_path
        ):
            raise PDDConversationNavigationError(
                "PDD navigation target escaped the verified customer-service page",
                error_code="PDD_NAVIGATION_PAGE_CHANGED",
                manual_review=True,
            )
        return target


__all__ = ["PDDNavigationEvaluator", "WebSocketPDDConversationNavigationPort"]
