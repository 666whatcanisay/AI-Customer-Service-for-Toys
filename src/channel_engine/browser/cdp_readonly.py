from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

import websocket
from pydantic import AwareDatetime

from channel_engine.models.entities import new_id, utc_now

from .models import BrowserPageContext
from .observer import (
    BrowserObservationMechanism,
    BrowserObservationUnavailable,
    BrowserPageCapture,
    BrowserPageReadAttachment,
    ReadOnlyBrowserPageCapturePort,
    SequencedRawBrowserMessage,
)
from .selectors import (
    LocatorEngine,
    SelectorBinding,
    SelectorCapability,
    SelectorContract,
    SelectorContractState,
    SelectorKey,
    SelectorProbeResult,
)


_MAX_CDP_RESPONSE_BYTES = 1_048_576
_MAX_DOM_MESSAGES = 1_000


class CDPReadOnlyError(RuntimeError):
    pass


class CDPTargetUnavailable(CDPReadOnlyError):
    pass


class CDPSelectorRejected(CDPReadOnlyError):
    pass


class CDPResultInvalid(CDPReadOnlyError):
    pass


@dataclass(frozen=True, slots=True)
class CDPPageTarget:
    target_id: str
    websocket_url: str
    location_origin: str


@runtime_checkable
class CDPTargetResolver(Protocol):
    def resolve(self) -> CDPPageTarget: ...


@runtime_checkable
class CDPEvaluator(Protocol):
    def evaluate(self, target: CDPPageTarget, expression: str) -> object: ...


class ChromeDevToolsTargetResolver:
    """Resolve one allowed real page from Chrome's loopback target endpoint."""

    def __init__(
        self,
        profile_path: Path,
        *,
        allowed_origin: str,
        timeout_seconds: float = 1.0,
        max_response_bytes: int = _MAX_CDP_RESPONSE_BYTES,
    ) -> None:
        self._profile_path = profile_path.expanduser().resolve()
        parsed = urlsplit(allowed_origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("CDP allowed origin must be a credential-free HTTPS origin")
        self._allowed_origin = f"{parsed.scheme}://{parsed.netloc}"
        if timeout_seconds <= 0 or max_response_bytes < 1:
            raise ValueError("CDP resolver limits must be positive")
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def resolve(self) -> CDPPageTarget:
        port = self._read_debugging_port()
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/list",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                payload = response.read(self._max_response_bytes + 1)
        except (OSError, urllib.error.URLError) as exc:
            raise CDPTargetUnavailable("Chrome debugging endpoint is unavailable") from exc
        if len(payload) > self._max_response_bytes:
            raise CDPTargetUnavailable("Chrome target list exceeded the safety limit")
        try:
            targets = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CDPTargetUnavailable("Chrome target list is invalid") from exc
        if not isinstance(targets, list):
            raise CDPTargetUnavailable("Chrome target list must be an array")

        matches: list[CDPPageTarget] = []
        for item in targets:
            if not isinstance(item, dict) or item.get("type") != "page":
                continue
            target_id = item.get("id")
            page_url = item.get("url")
            websocket_url = item.get("webSocketDebuggerUrl")
            if not all(isinstance(value, str) for value in (target_id, page_url, websocket_url)):
                continue
            assert isinstance(target_id, str)
            assert isinstance(page_url, str)
            assert isinstance(websocket_url, str)
            page_parts = urlsplit(page_url)
            page_origin = (
                f"{page_parts.scheme}://{page_parts.netloc}"
                if page_parts.scheme and page_parts.netloc
                else ""
            )
            if page_origin != self._allowed_origin:
                continue
            self._validate_websocket_url(websocket_url, port)
            matches.append(CDPPageTarget(target_id, websocket_url, page_origin))
        if len(matches) != 1:
            raise CDPTargetUnavailable(
                "expected exactly one allowed PDD page target"
            )
        return matches[0]

    def _read_debugging_port(self) -> int:
        try:
            first = (self._profile_path / "DevToolsActivePort").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            port = int(first)
        except (FileNotFoundError, OSError, IndexError, ValueError) as exc:
            raise CDPTargetUnavailable("Chrome debugging port is not ready") from exc
        if not 1 <= port <= 65535:
            raise CDPTargetUnavailable("Chrome debugging port is invalid")
        return port

    @staticmethod
    def _validate_websocket_url(value: str, expected_port: int) -> None:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "ws"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.port != expected_port
            or not parsed.path.startswith("/devtools/page/")
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise CDPTargetUnavailable("Chrome page endpoint escaped loopback policy")


class WebSocketCDPEvaluator:
    """Execute only caller-supplied read expressions over a loopback CDP socket."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 2.0,
        max_response_bytes: int = _MAX_CDP_RESPONSE_BYTES,
    ) -> None:
        if timeout_seconds <= 0 or max_response_bytes < 1:
            raise ValueError("CDP evaluator limits must be positive")
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._sequence = 0
        self._lock = RLock()

    def evaluate(self, target: CDPPageTarget, expression: str) -> object:
        if not expression or len(expression.encode("utf-8")) > 262_144:
            raise CDPSelectorRejected("CDP read expression is empty or too large")
        with self._lock:
            self._sequence += 1
            command_id = self._sequence
        command = json.dumps(
            {
                "id": command_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": False,
                    "includeCommandLineAPI": False,
                    "silent": True,
                },
            },
            separators=(",", ":"),
        )
        connection = None
        try:
            connection = websocket.create_connection(
                target.websocket_url,
                timeout=self._timeout_seconds,
                suppress_origin=True,
                http_proxy_host=None,
            )
            connection.send(command)
            while True:
                raw = connection.recv()
                if not isinstance(raw, str):
                    raise CDPResultInvalid("CDP returned a binary response")
                if len(raw.encode("utf-8")) > self._max_response_bytes:
                    raise CDPResultInvalid("CDP response exceeded the safety limit")
                response = json.loads(raw)
                if not isinstance(response, dict) or response.get("id") != command_id:
                    continue
                if "error" in response:
                    raise CDPResultInvalid("CDP rejected the read expression")
                result = response.get("result")
                if not isinstance(result, dict) or "exceptionDetails" in result:
                    raise CDPResultInvalid("CDP read expression failed")
                remote = result.get("result")
                if not isinstance(remote, dict) or "value" not in remote:
                    raise CDPResultInvalid("CDP read expression returned no value")
                return remote["value"]
        except (OSError, ValueError, json.JSONDecodeError, websocket.WebSocketException) as exc:
            raise CDPTargetUnavailable("CDP read channel is unavailable") from exc
        finally:
            if connection is not None:
                connection.close()


class ChromeDevToolsReadOnlyPagePort:
    """VERIFIED-selector DOM reader. It has no navigation, click, input or send API."""

    read_only = True
    real_page_transport = True
    real_platform_source = True

    def __init__(
        self,
        resolver: CDPTargetResolver,
        evaluator: CDPEvaluator,
        *,
        baseline_existing_messages: bool = True,
        clock: Callable[[], AwareDatetime] = utc_now,
    ) -> None:
        if not isinstance(resolver, CDPTargetResolver):
            raise TypeError("resolver does not implement CDPTargetResolver")
        if not isinstance(evaluator, CDPEvaluator):
            raise TypeError("evaluator does not implement CDPEvaluator")
        self._resolver = resolver
        self._evaluator = evaluator
        self._baseline_existing_messages = baseline_existing_messages
        self._clock = clock
        self._attachments: dict[str, str] = {}
        self._lock = RLock()
        self._page_write_operations = 0

    @property
    def page_write_operations(self) -> int:
        return self._page_write_operations

    def attach(
        self,
        page: BrowserPageContext,
        selector_contract: SelectorContract,
    ) -> BrowserPageReadAttachment:
        self._require_receive_only_contract(selector_contract)
        target = self._resolver.resolve()
        reference = new_id("cdp-page-read")
        with self._lock:
            self._attachments[reference] = target.target_id
        return BrowserPageReadAttachment(
            attachment_ref=reference,
            page_context_id=page.page_context_id,
            page_generation=page.generation,
            selector_contract_id=selector_contract.contract_id,
            selector_fingerprint=selector_contract.fingerprint(),
            read_only=True,
        )

    def capture(
        self,
        attachment: BrowserPageReadAttachment,
        page: BrowserPageContext,
        selector_contract: SelectorContract,
        *,
        cursor: str | None,
        after_sequence: int,
        limit: int,
    ) -> BrowserPageCapture:
        self._require_attachment(attachment, page, selector_contract)
        if not 1 <= limit <= 200:
            raise ValueError("CDP capture limit must be 1..200")
        target = self._resolver.resolve()
        with self._lock:
            expected_target = self._attachments.get(attachment.attachment_ref)
        if expected_target != target.target_id:
            raise BrowserObservationUnavailable(
                "Chrome page target changed after attachment",
                error_code="BROWSER_OBSERVATION_PAGE_TARGET_CHANGED",
            )
        raw = self._evaluator.evaluate(
            target,
            self._message_read_expression(selector_contract),
        )
        records = self._validate_message_records(raw)
        identities = [self._message_cursor(item) for item in records]

        if cursor is None and after_sequence < 0 and self._baseline_existing_messages:
            return self._capture_result(
                attachment,
                page,
                selector_contract,
                requested_cursor=None,
                next_cursor=identities[-1] if identities else None,
                messages=(),
                oldest_sequence=None,
                has_more=False,
            )

        start = 0
        if cursor is not None:
            try:
                start = identities.index(cursor) + 1
            except ValueError as exc:
                raise BrowserObservationUnavailable(
                    "committed browser cursor is no longer present",
                    error_code="BROWSER_OBSERVATION_CURSOR_NOT_FOUND",
                ) from exc
        pending = records[start:]
        selected = pending[:limit]
        messages = tuple(
            self._to_message(item, after_sequence + offset + 1)
            for offset, item in enumerate(selected)
        )
        next_cursor = (
            self._message_cursor(selected[-1]) if selected else cursor
        )
        return self._capture_result(
            attachment,
            page,
            selector_contract,
            requested_cursor=cursor,
            next_cursor=next_cursor,
            messages=messages,
            oldest_sequence=(messages[0].source_sequence if messages else None),
            has_more=len(pending) > len(selected),
        )

    def heartbeat(self, attachment: BrowserPageReadAttachment) -> bool:
        with self._lock:
            target_id = self._attachments.get(attachment.attachment_ref)
        if target_id is None:
            return False
        try:
            return self._resolver.resolve().target_id == target_id
        except CDPReadOnlyError:
            return False

    def detach(self, attachment: BrowserPageReadAttachment) -> None:
        with self._lock:
            self._attachments.pop(attachment.attachment_ref, None)

    def read_values(
        self,
        page: BrowserPageContext,
        bindings: tuple[SelectorBinding, ...],
    ) -> tuple[Mapping[SelectorKey, str], str, AwareDatetime]:
        del page
        keys = {binding.key for binding in bindings}
        if keys != {SelectorKey.STORE_ID, SelectorKey.STORE_NAME}:
            raise CDPSelectorRejected("store identity read requires exactly two bindings")
        self._require_supported_bindings(bindings)
        target = self._resolver.resolve()
        raw = self._evaluator.evaluate(target, self._value_read_expression(bindings))
        if not isinstance(raw, dict):
            raise CDPResultInvalid("store identity result must be an object")
        values: dict[SelectorKey, str] = {}
        for binding in bindings:
            item = raw.get(binding.key.value)
            if not isinstance(item, dict):
                raise CDPResultInvalid("store identity selector result is missing")
            self._validate_match_count(binding, item.get("count"))
            value = item.get("value")
            if not isinstance(value, str) or not value.strip():
                raise CDPResultInvalid("store identity value is blank")
            values[binding.key] = value.strip()
        source_reference = "browser-page-ref://" + hashlib.sha256(
            target.target_id.encode()
        ).hexdigest()
        return values, source_reference, self._clock()

    def probe(
        self,
        page: BrowserPageContext,
        contract: SelectorContract,
    ) -> SelectorProbeResult:
        if contract.state is not SelectorContractState.DISCOVERY:
            raise CDPSelectorRejected("only DISCOVERY selectors can be probed")
        self._require_supported_bindings(contract.bindings)
        target = self._resolver.resolve()
        raw = self._evaluator.evaluate(
            target,
            self._value_read_expression(contract.bindings, include_values=False),
        )
        if not isinstance(raw, dict):
            raise CDPResultInvalid("selector probe result must be an object")
        missing: list[SelectorKey] = []
        ambiguous: list[SelectorKey] = []
        for binding in contract.bindings:
            item = raw.get(binding.key.value)
            count = item.get("count") if isinstance(item, dict) else None
            if not isinstance(count, int) or count < binding.expected_count_min:
                missing.append(binding.key)
            if (
                isinstance(count, int)
                and binding.expected_count_max is not None
                and count > binding.expected_count_max
            ):
                ambiguous.append(binding.key)
        return SelectorProbeResult(
            contract_id=contract.contract_id,
            contract_fingerprint=contract.fingerprint(),
            page_context_id=page.page_context_id,
            passed=not missing and not ambiguous,
            missing_keys=tuple(missing),
            ambiguous_keys=tuple(ambiguous),
            checked_at=self._clock(),
        )

    @staticmethod
    def _require_receive_only_contract(contract: SelectorContract) -> None:
        if (
            contract.state is not SelectorContractState.VERIFIED
            or SelectorCapability.RECEIVE_MESSAGE not in contract.capabilities
            or SelectorCapability.SEND_MESSAGE in contract.capabilities
        ):
            raise CDPSelectorRejected(
                "real observation requires a VERIFIED receive-only selector contract"
            )
        ChromeDevToolsReadOnlyPagePort._require_supported_bindings(contract.bindings)

    @staticmethod
    def _require_supported_bindings(bindings: tuple[SelectorBinding, ...]) -> None:
        if not bindings:
            raise CDPSelectorRejected("selector bindings are required")
        if any(binding.engine is not LocatorEngine.CSS for binding in bindings):
            raise CDPSelectorRejected("real CDP observation supports CSS bindings only")

    def _require_attachment(
        self,
        attachment: BrowserPageReadAttachment,
        page: BrowserPageContext,
        contract: SelectorContract,
    ) -> None:
        self._require_receive_only_contract(contract)
        expected = (
            page.page_context_id,
            page.generation,
            contract.contract_id,
            contract.fingerprint(),
        )
        actual = (
            attachment.page_context_id,
            attachment.page_generation,
            attachment.selector_contract_id,
            attachment.selector_fingerprint,
        )
        with self._lock:
            known = attachment.attachment_ref in self._attachments
        if not known or actual != expected:
            raise BrowserObservationUnavailable(
                "CDP read attachment does not match the active page",
                error_code="BROWSER_OBSERVATION_ATTACHMENT_MISMATCH",
            )

    def _capture_result(
        self,
        attachment: BrowserPageReadAttachment,
        page: BrowserPageContext,
        contract: SelectorContract,
        *,
        requested_cursor: str | None,
        next_cursor: str | None,
        messages: tuple[SequencedRawBrowserMessage, ...],
        oldest_sequence: int | None,
        has_more: bool,
    ) -> BrowserPageCapture:
        return BrowserPageCapture(
            attachment_ref=attachment.attachment_ref,
            page_context_id=page.page_context_id,
            page_generation=page.generation,
            selector_contract_id=contract.contract_id,
            selector_fingerprint=contract.fingerprint(),
            requested_cursor=requested_cursor,
            next_cursor=next_cursor,
            oldest_available_sequence=oldest_sequence,
            messages=messages,
            page_revision=page.page_revision,
            captured_at=self._clock(),
            has_more=has_more,
        )

    @staticmethod
    def _message_cursor(item: Mapping[str, object]) -> str:
        return hashlib.sha256(
            f"{item['conversation_id']}\0{item['external_message_id']}".encode()
        ).hexdigest()

    @staticmethod
    def _to_message(
        item: Mapping[str, object], source_sequence: int
    ) -> SequencedRawBrowserMessage:
        timestamp_value = item["timestamp"]
        assert isinstance(timestamp_value, str)
        try:
            timestamp = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CDPResultInvalid("message timestamp is not ISO-8601") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise CDPResultInvalid("message timestamp must include timezone")
        return SequencedRawBrowserMessage(
            conversation_id=str(item["conversation_id"]),
            external_message_id=str(item["external_message_id"]),
            sender=str(item["sender"]),
            content=str(item["content"]),
            timestamp=timestamp.astimezone(timezone.utc),
            observation_mechanism=BrowserObservationMechanism.DOM_SNAPSHOT,
            source_sequence=source_sequence,
        )

    @staticmethod
    def _validate_message_records(raw: object) -> list[dict[str, object]]:
        if not isinstance(raw, list) or len(raw) > _MAX_DOM_MESSAGES:
            raise CDPResultInvalid("message DOM result is invalid or too large")
        required = {
            "conversation_id",
            "external_message_id",
            "sender",
            "content",
            "timestamp",
        }
        result: list[dict[str, object]] = []
        for item in raw:
            if not isinstance(item, dict) or set(item) != required:
                raise CDPResultInvalid("message DOM record shape is invalid")
            if any(not isinstance(item[key], str) or not item[key].strip() for key in required):
                raise CDPResultInvalid("message DOM record contains a blank field")
            if len(str(item["content"])) > 8_000:
                raise CDPResultInvalid("message content exceeds the observation limit")
            result.append(item)
        return result

    @staticmethod
    def _validate_match_count(binding: SelectorBinding, value: object) -> None:
        if not isinstance(value, int):
            raise CDPResultInvalid("selector count is invalid")
        if value < binding.expected_count_min or (
            binding.expected_count_max is not None
            and value > binding.expected_count_max
        ):
            raise CDPResultInvalid("selector match count violated its contract")

    @staticmethod
    def _spec(binding: SelectorBinding) -> dict[str, object]:
        return {
            "selector": binding.locator,
            "attribute": binding.value_attribute,
        }

    @classmethod
    def _value_read_expression(
        cls,
        bindings: tuple[SelectorBinding, ...],
        *,
        include_values: bool = True,
    ) -> str:
        specs = {binding.key.value: cls._spec(binding) for binding in bindings}
        return (
            "(() => { 'use strict'; const specs = "
            + json.dumps(specs, ensure_ascii=False, separators=(",", ":"))
            + "; const out = {}; for (const [key, spec] of Object.entries(specs)) {"
            " const nodes = Array.from(document.querySelectorAll(spec.selector));"
            " const node = nodes[0] || null;"
            " const value = node ? (spec.attribute ? node.getAttribute(spec.attribute) : node.textContent) : null;"
            f" out[key] = {{count:nodes.length,value:{'value' if include_values else 'null'}}};"
            " } return out; })()"
        )

    @classmethod
    def _message_read_expression(cls, contract: SelectorContract) -> str:
        by_key = {binding.key: binding for binding in contract.bindings}
        required = (
            SelectorKey.MESSAGE_ITEM,
            SelectorKey.CONVERSATION_ID,
            SelectorKey.EXTERNAL_MESSAGE_ID,
            SelectorKey.MESSAGE_SENDER,
            SelectorKey.MESSAGE_CONTENT,
            SelectorKey.MESSAGE_TIMESTAMP,
        )
        if any(key not in by_key for key in required):
            raise CDPSelectorRejected("receive selector contract is incomplete")
        specs = {key.value: cls._spec(by_key[key]) for key in required}
        return (
            "(() => { 'use strict'; const specs = "
            + json.dumps(specs, ensure_ascii=False, separators=(",", ":"))
            + f"; const roots = Array.from(document.querySelectorAll(specs.MESSAGE_ITEM.selector)).slice(0,{_MAX_DOM_MESSAGES});"
            " const read = (root, spec) => { const node = root.matches(spec.selector) ? root : root.querySelector(spec.selector);"
            " if (!node) return null; const value = spec.attribute ? node.getAttribute(spec.attribute) : node.textContent;"
            " return typeof value === 'string' ? value.trim() : null; };"
            " return roots.map(root => ({"
            " conversation_id: read(document.documentElement, specs.CONVERSATION_ID),"
            " external_message_id: read(root, specs.EXTERNAL_MESSAGE_ID),"
            " sender: read(root, specs.MESSAGE_SENDER),"
            " content: read(root, specs.MESSAGE_CONTENT),"
            " timestamp: read(root, specs.MESSAGE_TIMESTAMP)"
            " })); })()"
        )


__all__ = [
    "CDPEvaluator",
    "CDPPageTarget",
    "CDPReadOnlyError",
    "CDPResultInvalid",
    "CDPSelectorRejected",
    "CDPTargetResolver",
    "CDPTargetUnavailable",
    "ChromeDevToolsReadOnlyPagePort",
    "ChromeDevToolsTargetResolver",
    "WebSocketCDPEvaluator",
]
