from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from urllib.parse import urlsplit

import websocket
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .edge_pdd_observe import (
    PDDSelectorRuntimeEvidence,
    PDDWorkspaceMessage,
    PDDWorkspaceOrder,
    PDDWorkspaceProduct,
    PDDWorkspaceSnapshot,
)
from .pdd_conversation_capture import PDDReplyAttentionState
from .pdd_conversation_navigation import (
    WebSocketPDDConversationNavigationPort,
)
from .pdd_login import EdgePDDTargetResolver, PDDCDPPageTarget
from .pdd_observer import (
    PDDConversationNotActive,
    PDDConversationSummary,
    PDDObserverError,
    PDDObserverFatalError,
)
from .pdd_page_port import PDDPageReadPort, PDDReadReplayFixture

_MAX_CDP_BYTES = 1_048_576
_PDD_CONVERSATION_ID_PREFIX = re.compile(r"^(\d{8,20})(?:\D|$)")
_PDD_MESSAGE_ID = re.compile(r"^middlePanel_list_(\d{13})$")
_UNSUPPORTED_NON_TEXT_MESSAGE = "[UNSUPPORTED_NON_TEXT_MESSAGE]"
_REQUIRED_SELECTORS = {
    "conversation_item",
    "conversation_id",
    "customer_reference",
    "unread_count",
    "last_activity",
    "latest_sequence",
    "active_conversation_id",
    "message_item",
    "message_id",
    "message_role",
    "message_content",
    "message_timestamp",
    "message_sequence",
}
_NAVIGATION_SELECTORS = {
    "conversation_attention",
    "conversation_select_target",
    "reply_input",
    "message_container",
}


class PDDReadOnlyDriverError(PDDObserverError):
    """A fail-closed read-only CDP or evidence failure."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class PDDDOMBinding(_StrictModel):
    selector: str = Field(min_length=1, max_length=1024)
    attribute: str | None = Field(default=None, pattern=r"^[A-Za-z_:][-A-Za-z0-9_:.]{0,127}$")
    required: bool = True
    maximum_matches: int = Field(default=1, ge=1, le=500)


class PDDFingerprintProbe(_StrictModel):
    selector: str = Field(min_length=1, max_length=1024)
    expected_tag: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9-]{0,63}$")


class PDDObserverEvidence(_StrictModel):
    schema_version: Literal[
        "channel-agent-pdd-observer-evidence.v2.1",
        "channel-agent-pdd-observer-evidence.v2.2",
    ]
    state: Literal["VERIFIED"]
    environment: Literal["PRODUCTION", "STAGING"]
    platform: Literal["PDD"]
    page: Literal["merchant_chat"]
    capability: Literal["OBSERVE"]
    selector_contract_version: str = Field(min_length=1, max_length=128)
    applicable_path: Literal["/chat-merchant/index.html"]
    selectors: dict[str, PDDDOMBinding]
    fingerprint_probes: tuple[PDDFingerprintProbe, ...] = Field(min_length=1, max_length=32)
    role_map: dict[str, Literal["CUSTOMER", "OPERATOR", "BOT", "SYSTEM"]]
    verified_at: AwareDatetime
    expires_at: AwareDatetime
    verified_by: str = Field(min_length=1, max_length=160)
    page_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    evidence_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_contract(self) -> PDDObserverEvidence:
        if not _REQUIRED_SELECTORS.issubset(self.selectors):
            raise ValueError("verified PDD observer evidence is incomplete")
        unknown = set(self.selectors).difference(
            _REQUIRED_SELECTORS
            | _NAVIGATION_SELECTORS
            | {
                "store_name",
                "product_id",
                "product_name",
                "product_card",
                "sku_id",
                "sku_name",
                "product_attributes",
                "order_reference",
                "order_status",
                "logistics_status",
                "aftersales_status",
                "latest_message_preview",
            }
        )
        if unknown:
            raise ValueError("verified PDD observer evidence contains unknown selectors")
        if (
            self.schema_version == "channel-agent-pdd-observer-evidence.v2.2"
            and not _NAVIGATION_SELECTORS.issubset(self.selectors)
        ):
            raise ValueError("verified PDD conversation navigation evidence is incomplete")
        if self.schema_version == "channel-agent-pdd-observer-evidence.v2.2":
            attention = self.selectors["conversation_attention"]
            if attention.required or attention.maximum_matches != 1:
                raise ValueError(
                    "verified PDD reply-attention selector must be optional and unique per row"
                )
            for selector_name in (
                "conversation_select_target",
                "reply_input",
                "message_container",
            ):
                binding = self.selectors[selector_name]
                if not binding.required or binding.maximum_matches != 1:
                    raise ValueError(
                        "verified PDD conversation navigation selectors must be required and unique"
                    )
            conversation_identity = self.selectors["conversation_id"]
            active_identity = self.selectors["active_conversation_id"]
            if (
                active_identity.maximum_matches != 1
                or active_identity.attribute != conversation_identity.attribute
            ):
                raise ValueError(
                    "verified PDD active conversation identity must be unique and use "
                    "the same attribute as the conversation row"
                )
        if self.expires_at <= self.verified_at:
            raise ValueError("verified PDD observer evidence expiry is invalid")
        canonical = self.model_dump(mode="json", exclude={"evidence_hash"})
        expected = "sha256:" + hashlib.sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        if self.evidence_hash != expected:
            raise ValueError("verified PDD observer evidence hash mismatch")
        return self

    def runtime_evidence(self) -> PDDSelectorRuntimeEvidence:
        return PDDSelectorRuntimeEvidence(
            evidence_hash=self.evidence_hash,
            selector_contract_version=self.selector_contract_version,
            page_fingerprint=self.page_fingerprint,
            capability="OBSERVE",
            verified_at=self.verified_at,
            expires_at=self.expires_at,
        )

    @property
    def navigation_enabled(self) -> bool:
        return (
            self.schema_version == "channel-agent-pdd-observer-evidence.v2.2"
            and _NAVIGATION_SELECTORS.issubset(self.selectors)
        )


def load_pdd_observer_evidence(path: str | Path) -> PDDObserverEvidence:
    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise PDDObserverFatalError(
            "verified PDD observer evidence cannot be read"
        ) from exc
    if len(payload) > 256 * 1024:
        raise PDDObserverFatalError("verified PDD observer evidence is too large")
    try:
        return PDDObserverEvidence.model_validate_json(payload)
    except Exception as exc:
        raise PDDObserverFatalError(
            "verified PDD observer evidence is invalid"
        ) from exc


def build_replay_observer_evidence(
    fixture: PDDReadReplayFixture,
) -> PDDObserverEvidence:
    """Build deterministic synthetic evidence for the zero-network replay port."""

    selectors = {
        key: {
            "selector": f"[data-replay-field='{key}']",
            "attribute": None,
            "required": True,
            "maximum_matches": (
                200 if key == "conversation_item" else 100 if key == "message_item" else 1
            ),
        }
        for key in _REQUIRED_SELECTORS
    }
    provisional = {
        "schema_version": "channel-agent-pdd-observer-evidence.v2.1",
        "state": "VERIFIED",
        "environment": "STAGING",
        "platform": "PDD",
        "page": "merchant_chat",
        "capability": "OBSERVE",
        "selector_contract_version": fixture.selector_contract_version,
        "applicable_path": "/chat-merchant/index.html",
        "selectors": selectors,
        "fingerprint_probes": (
            {"selector": "[data-replay-root]", "expected_tag": "MAIN"},
        ),
        "role_map": fixture.role_map,
        "verified_at": fixture.captured_at,
        "expires_at": fixture.captured_at + timedelta(days=3650),
        "verified_by": "offline-replay-fixture-builder",
        "page_fingerprint": fixture.page_fingerprint,
    }
    # Hash the same Pydantic-normalized JSON representation that
    # ``PDDObserverEvidence.validate_contract`` verifies.  Hashing raw Python
    # datetimes here would emit ``+00:00`` while Pydantic emits ``Z`` and make
    # every otherwise-valid OFFLINE_REPLAY fixture fail initialization.
    unverified = PDDObserverEvidence.model_construct(
        **{
            **provisional,
            "selectors": {
                key: PDDDOMBinding.model_validate(value)
                for key, value in selectors.items()
            },
            "fingerprint_probes": tuple(
                PDDFingerprintProbe.model_validate(value)
                for value in provisional["fingerprint_probes"]
            ),
        },
        evidence_hash="sha256:" + "0" * 64,
    )
    canonical = unverified.model_dump(mode="json", exclude={"evidence_hash"})
    evidence_hash = "sha256:" + hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return PDDObserverEvidence.model_validate(
        {**provisional, "evidence_hash": evidence_hash}
    )


class ReadOnlyCDPEvaluator:
    """Executes a fixed, generated DOM read expression over loopback CDP only."""

    def __init__(self, *, timeout_seconds: float = 2.0) -> None:
        self._timeout = max(0.2, min(timeout_seconds, 10.0))
        self._sequence = 0
        self._lock = RLock()

    def evaluate(self, target: PDDCDPPageTarget, expression: str) -> object:
        if not expression or len(expression.encode("utf-8")) > 262_144:
            raise PDDReadOnlyDriverError("PDD read expression is invalid")
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
                timeout=self._timeout,
                suppress_origin=True,
                http_proxy_host=None,
            )
            connection.send(command)
            while True:
                raw = connection.recv()
                if not isinstance(raw, str) or len(raw.encode("utf-8")) > _MAX_CDP_BYTES:
                    raise PDDReadOnlyDriverError("PDD read response exceeded its safety boundary")
                response = json.loads(raw)
                if not isinstance(response, dict) or response.get("id") != command_id:
                    continue
                if "error" in response:
                    raise PDDReadOnlyDriverError("Edge rejected the PDD read expression")
                result = response.get("result")
                remote = result.get("result") if isinstance(result, dict) else None
                if not isinstance(remote, dict) or "value" not in remote:
                    raise PDDReadOnlyDriverError("PDD read expression returned no value")
                return remote["value"]
        except PDDReadOnlyDriverError:
            raise
        except (OSError, ValueError, json.JSONDecodeError, websocket.WebSocketException) as exc:
            raise PDDReadOnlyDriverError("PDD read-only CDP channel is unavailable") from exc
        finally:
            if connection is not None:
                connection.close()

    def dispatch_mouse_click(
        self,
        target: PDDCDPPageTarget,
        *,
        x: float,
        y: float,
    ) -> None:
        """Dispatch one trusted click for the separately guarded navigation port."""

        if (
            not math.isfinite(x)
            or not math.isfinite(y)
            or x < 0
            or y < 0
            or x > 100_000
            or y > 100_000
        ):
            raise PDDReadOnlyDriverError("PDD navigation coordinates are invalid")
        with self._lock:
            self._sequence += 1
            pressed_id = self._sequence
            self._sequence += 1
            released_id = self._sequence
        connection = None
        try:
            connection = websocket.create_connection(
                target.websocket_url,
                timeout=self._timeout,
                suppress_origin=True,
                http_proxy_host=None,
            )
            for command_id, event_type in (
                (pressed_id, "mousePressed"),
                (released_id, "mouseReleased"),
            ):
                connection.send(
                    json.dumps(
                        {
                            "id": command_id,
                            "method": "Input.dispatchMouseEvent",
                            "params": {
                                "type": event_type,
                                "x": x,
                                "y": y,
                                "button": "left",
                                "clickCount": 1,
                            },
                        },
                        separators=(",", ":"),
                    )
                )
                while True:
                    raw = connection.recv()
                    if not isinstance(raw, str) or len(raw.encode("utf-8")) > _MAX_CDP_BYTES:
                        raise PDDReadOnlyDriverError(
                            "PDD navigation response exceeded its safety boundary"
                        )
                    response = json.loads(raw)
                    if not isinstance(response, dict) or response.get("id") != command_id:
                        continue
                    if "error" in response:
                        raise PDDReadOnlyDriverError(
                            "Edge rejected the PDD navigation input event"
                        )
                    break
        except PDDReadOnlyDriverError:
            raise
        except (OSError, ValueError, json.JSONDecodeError, websocket.WebSocketException) as exc:
            raise PDDReadOnlyDriverError(
                "PDD navigation CDP channel is unavailable"
            ) from exc
        finally:
            if connection is not None:
                connection.close()


class LivePDDPageReadPort:
    """Official-origin CDP implementation of the shared read-only page port."""

    source_kind: Literal["LIVE_PDD"] = "LIVE_PDD"
    page_write_operations = 0
    execution_calls = 0
    transport_calls = 0

    def __init__(
        self,
        *,
        profile_path: str | Path,
        applicable_path: str,
        resolver: EdgePDDTargetResolver | None = None,
        evaluator: ReadOnlyCDPEvaluator | None = None,
    ) -> None:
        self._profile_path = Path(profile_path).resolve()
        self._applicable_path = applicable_path
        self._resolver = resolver or EdgePDDTargetResolver()
        self._evaluator = evaluator or ReadOnlyCDPEvaluator()
        self.pdd_network_requests = 0

    def read(
        self,
        operation: Literal["SCAN", "CAPTURE"],
        expression: str,
    ) -> object:
        del operation
        target = self._target()
        self.pdd_network_requests += 1
        return self._evaluator.evaluate(target, expression)

    def _target(self) -> PDDCDPPageTarget:
        target = self._resolver.resolve(self._profile_path)
        parsed = urlsplit(target.page_url)
        if parsed.scheme != "https" or parsed.hostname != "mms.pinduoduo.com":
            raise PDDReadOnlyDriverError("PDD observer target escaped the official origin")
        if parsed.path != self._applicable_path:
            raise PDDReadOnlyDriverError("PDD customer service page is not active")
        return target


class EvidenceBackedPDDReadOnlyDriver:
    """Production PDD reader with an optional, evidence-gated navigation port.

    Legacy v2.1 evidence can capture only the already-active conversation.  A
    verified v2.2 evidence set may select one reply-attention conversation, but
    the driver still has no composer, reply or send capability.
    """

    observe_only = True
    page_write_operations = 0
    execution_calls = 0
    transport_calls = 0

    def __init__(
        self,
        *,
        profile_path: str | Path | None = None,
        store_id: str,
        platform_store_id: str,
        evidence: PDDObserverEvidence,
        resolver: EdgePDDTargetResolver | None = None,
        evaluator: ReadOnlyCDPEvaluator | None = None,
        page_port: PDDPageReadPort | None = None,
        navigation_port: WebSocketPDDConversationNavigationPort | None = None,
        allow_navigation: bool = False,
        clock: Any = lambda: datetime.now(UTC),
    ) -> None:
        self._store_id = store_id
        self._platform_store_id = platform_store_id
        self._evidence = evidence
        if page_port is None:
            if profile_path is None:
                raise PDDReadOnlyDriverError("live PDD reader requires an Edge profile")
            resolver = resolver or EdgePDDTargetResolver()
            evaluator = evaluator or ReadOnlyCDPEvaluator()
            page_port = LivePDDPageReadPort(
                profile_path=profile_path,
                applicable_path=evidence.applicable_path,
                resolver=resolver,
                evaluator=evaluator,
            )
            if allow_navigation and evidence.navigation_enabled and navigation_port is None:
                navigation_port = WebSocketPDDConversationNavigationPort(
                    profile_path=profile_path,
                    applicable_path=evidence.applicable_path,
                    selectors={
                        key: value.model_dump(mode="json")
                        for key, value in evidence.selectors.items()
                    },
                    resolver=resolver,
                    evaluator=evaluator,
                )
        self._page_port = page_port
        self._navigation_port = navigation_port if allow_navigation else None
        self._allow_navigation = allow_navigation
        self._clock = clock

    @property
    def source_kind(self) -> Literal["LIVE_PDD", "OFFLINE_REPLAY"]:
        return self._page_port.source_kind

    @property
    def pdd_network_requests(self) -> int:
        return self._page_port.pdd_network_requests

    @property
    def navigation_enabled(self) -> bool:
        return (
            self._allow_navigation
            and self._evidence.navigation_enabled
            and self._navigation_port is not None
        )

    def navigate_to_conversation(
        self,
        summary: PDDConversationSummary,
        *,
        allow_attention_missing: bool = False,
    ) -> None:
        if not self.navigation_enabled or self._navigation_port is None:
            raise PDDConversationNotActive(
                "verified PDD conversation navigation evidence is unavailable"
            )
        self._navigation_port.navigate(
            summary, allow_attention_missing=allow_attention_missing
        )

    def selector_evidence(self, capability: str) -> PDDSelectorRuntimeEvidence:
        if capability != "OBSERVE":
            raise PDDReadOnlyDriverError("PDD read-only driver has no requested capability")
        return self._evidence.runtime_evidence()

    def scan_conversations(self) -> tuple[PDDConversationSummary, ...]:
        raw = self._page_port.read("SCAN", self._scan_expression())
        if not isinstance(raw, dict) or not isinstance(raw.get("conversations"), list):
            raise PDDReadOnlyDriverError("PDD conversation list result is invalid")
        self._assert_fingerprint(raw.get("fingerprint"))
        rows = raw["conversations"]
        if len(rows) > 200:
            raise PDDReadOnlyDriverError("PDD conversation list exceeded the safety limit")
        results: list[PDDConversationSummary] = []
        for page_position, item in enumerate(rows):
            if not isinstance(item, dict):
                raise PDDReadOnlyDriverError("PDD conversation row is invalid")
            raw_conversation = _required_text(item, "conversation_id", 255)
            conversation_id = _pdd_conversation_id(raw_conversation)
            raw_customer = _optional_text(item.get("customer_reference"), 512)
            customer_basis = (
                conversation_id
                if raw_customer is None
                else _pdd_customer_reference_basis(raw_customer, conversation_id)
            )
            attention_text = _optional_text(item.get("attention"), 512)
            attention_state, attention_seconds = _reply_attention(attention_text)
            latest_raw = _optional_text(
                item.get("latest_message_id") or item.get("latest_sequence"), 255
            )
            results.append(
                PDDConversationSummary(
                    store_id=self._store_id,
                    platform_store_id=self._platform_store_id,
                    conversation_id=conversation_id,
                    customer_reference="sha256:"
                    + hashlib.sha256(customer_basis.encode("utf-8")).hexdigest(),
                    unread_count=_optional_int(item.get("unread_count"), minimum=0),
                    last_activity_at=_pdd_message_datetime(item.get("last_activity")),
                    latest_sequence=_pdd_message_sequence(item.get("latest_sequence")),
                    latest_message_id=latest_raw,
                    page_position=page_position,
                    attention_state=attention_state,
                    attention_verified=(
                        self._evidence.navigation_enabled and attention_text is not None
                    ),
                    attention_seconds=attention_seconds,
                    attention_evidence_hash=(
                        "sha256:"
                        + hashlib.sha256(
                            (
                                self._evidence.evidence_hash
                                + "\n"
                                + _pdd_conversation_id(
                                    raw_conversation
                                )
                                + "\n"
                                + attention_state.value
                            ).encode("utf-8")
                        ).hexdigest()
                        if attention_text is not None
                        else None
                    ),
                )
            )
        return tuple(results)

    def capture_conversation(self, summary: PDDConversationSummary) -> PDDWorkspaceSnapshot:
        raw = self._page_port.read("CAPTURE", self._capture_expression())
        if not isinstance(raw, dict):
            raise PDDReadOnlyDriverError("PDD conversation capture result is invalid")
        self._assert_fingerprint(raw.get("fingerprint"))
        active = _pdd_conversation_id(
            _required_text(raw, "active_conversation_id", 255)
        )
        if active != summary.conversation_id:
            raise PDDConversationNotActive(
                "PDD conversation requires human selection before read-only capture"
            )
        rows = raw.get("messages")
        if not isinstance(rows, list) or len(rows) > 100:
            raise PDDReadOnlyDriverError("PDD message capture exceeded the safety limit")
        messages: list[PDDWorkspaceMessage] = []
        for item in rows:
            if not isinstance(item, dict):
                raise PDDReadOnlyDriverError("PDD message row is invalid")
            role_key = _required_text(item, "role", 128)
            role = self._evidence.role_map.get(role_key)
            if role is None:
                role = next(
                    (
                        mapped
                        for token in role_key.split()
                        if (mapped := self._evidence.role_map.get(token)) is not None
                    ),
                    "UNKNOWN",
                )
            content = _optional_text(item.get("content"), 8_000)
            if content is None:
                # The real workspace reuses the text wrapper for image, sticker
                # and card rows. Preserve source ordering, but make the row
                # manual-review-only so no fabricated content can reach AI.
                role = "UNKNOWN"
                content = _UNSUPPORTED_NON_TEXT_MESSAGE
            messages.append(
                PDDWorkspaceMessage(
                    external_message_id=_required_text(item, "message_id", 255),
                    sender=role,
                    content=content,
                    timestamp=_pdd_message_datetime(item.get("timestamp")),
                    sequence=_pdd_message_sequence(item.get("sequence")) or 0,
                )
            )
        raw_customer = _optional_text(raw.get("customer_reference"), 512)
        # The production PDD workspace does not consistently expose a separate
        # customer reference.  The scan path already uses the normalized row
        # conversation id as its privacy-safe fallback; capture must use the
        # same basis after the active-row equality check succeeds.
        customer_basis = (
            summary.conversation_id
            if raw_customer is None
            else _pdd_customer_reference_basis(
                raw_customer, summary.conversation_id
            )
        )
        product = raw.get("product") if isinstance(raw.get("product"), dict) else {}
        order = raw.get("order") if isinstance(raw.get("order"), dict) else {}
        return PDDWorkspaceSnapshot(
            store_id=self._store_id,
            platform_store_id=self._platform_store_id,
            store_name=_optional_text(raw.get("store_name"), 160),
            conversation_id=summary.conversation_id,
            customer_reference="sha256:"
            + hashlib.sha256(customer_basis.encode("utf-8")).hexdigest(),
            page_fingerprint=self._evidence.page_fingerprint,
            selector_evidence_hash=self._evidence.evidence_hash,
            page_state="CUSTOMER_SERVICE_RUNNING",
            product=PDDWorkspaceProduct(
                product_id=_optional_text(product.get("product_id"), 160),
                product_name=_optional_text(product.get("product_name"), 512),
                sku_id=_optional_text(product.get("sku_id"), 160),
                sku_name=_optional_text(product.get("sku_name"), 512),
                attributes=(
                    {"visible_specification": attributes}
                    if (attributes := _optional_text(
                        product.get("attributes_text"), 512
                    ))
                    else {}
                ),
            ),
            order=PDDWorkspaceOrder(
                order_reference=_optional_text(order.get("order_reference"), 255),
                order_status=_optional_text(order.get("order_status"), 128),
                logistics_status=_optional_text(order.get("logistics_status"), 128),
                aftersales_status=_optional_text(order.get("aftersales_status"), 128),
            ),
            messages=tuple(messages),
            captured_at=self._clock(),
        )

    def _assert_fingerprint(self, value: object) -> None:
        if value != self._evidence.page_fingerprint:
            raise PDDReadOnlyDriverError("PDD page fingerprint no longer matches evidence")

    def _scan_expression(self) -> str:
        config = self._javascript_config()
        return _read_expression(config, capture=False)

    def _capture_expression(self) -> str:
        config = self._javascript_config()
        return _read_expression(config, capture=True)

    def _javascript_config(self) -> str:
        return json.dumps(
            {
                "selectors": {
                    key: value.model_dump(mode="json")
                    for key, value in self._evidence.selectors.items()
                },
                "probes": [probe.model_dump(mode="json") for probe in self._evidence.fingerprint_probes],
                "path": self._evidence.applicable_path,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


def _read_expression(config_json: str, *, capture: bool) -> str:
    # Selectors are JSON values, never concatenated into executable JavaScript.
    action = "capture" if capture else "scan"
    return rf"""
(() => {{
  const cfg = {config_json};
  const one = (root, name) => {{
    const b = cfg.selectors[name];
    if (!b) return null;
    const scope = root || document;
    const nodes = [];
    if (scope !== document && typeof scope.matches === 'function' && scope.matches(b.selector)) nodes.push(scope);
    nodes.push(...Array.from(scope.querySelectorAll(b.selector)));
    // PDD briefly keeps the outgoing and incoming chat panels in the DOM
    // during a view transition.  Both can retain the `active` class, but the
    // outgoing copy has no rendered boxes.  Ignore only those non-rendered
    // transition copies; if more than one rendered target remains, preserve
    // the strict fail-closed selector boundary.
    const rendered = nodes.filter((candidate) =>
      typeof candidate.getClientRects !== 'function' || candidate.getClientRects().length > 0
    );
    const bounded = rendered.length ? rendered : nodes;
    if (bounded.length > b.maximum_matches || (b.required && bounded.length === 0)) throw new Error('selector boundary');
    const node = bounded[0];
    if (!node) return null;
    return String(b.attribute ? (node.getAttribute(b.attribute) || '') : (node.textContent || '')).trim();
  }};
  const fingerprintSource = {{path: location.pathname, probes: cfg.probes.map((probe) => {{
    const nodes = Array.from(document.querySelectorAll(probe.selector));
    return {{selector: probe.selector, tags: nodes.slice(0, 4).map((n) => String(n.tagName || ''))}};
  }})}};
  const stable = JSON.stringify(fingerprintSource);
  const sha256 = (text) => {{
    // Synchronous SHA-256 implemented only for a small, non-sensitive page-shape value.
    function r(v,n){{return (v>>>n)|(v<<(32-n));}}
    const bytes = new TextEncoder().encode(text), words=[]; let bit=bytes.length*8;
    for(let i=0;i<bytes.length;i++) words[i>>2]|=bytes[i]<<(24-(i%4)*8);
    words[bit>>5]|=0x80<<(24-bit%32); words[((bit+64>>9)<<4)+15]=bit;
    const k=[1116352408,1899447441,3049323471,3921009573,961987163,1508970993,2453635748,2870763221,3624381080,310598401,607225278,1426881987,1925078388,2162078206,2614888103,3248222580,3835390401,4022224774,264347078,604807628,770255983,1249150122,1555081692,1996064986,2554220882,2821834349,2952996808,3210313671,3336571891,3584528711,113926993,338241895,666307205,773529912,1294757372,1396182291,1695183700,1986661051,2177026350,2456956037,2730485921,2820302411,3259730800,3345764771,3516065817,3600352804,4094571909,275423344,430227734,506948616,659060556,883997877,958139571,1322822218,1537002063,1747873779,1955562222,2024104815,2227730452,2361852424,2428436474,2756734187,3204031479,3329325298];
    let h=[1779033703,3144134277,1013904242,2773480762,1359893119,2600822924,528734635,1541459225];
    for(let i=0;i<words.length;i+=16){{let w=words.slice(i,i+16),a=h.slice(); for(let j=16;j<64;j++){{let x=w[j-15],y=w[j-2];w[j]=(((r(x,7)^r(x,18)^(x>>>3))+w[j-16]+(r(y,17)^r(y,19)^(y>>>10))+w[j-7])|0);}} for(let j=0;j<64;j++){{let s1=r(a[4],6)^r(a[4],11)^r(a[4],25),ch=(a[4]&a[5])^(~a[4]&a[6]),t1=(a[7]+s1+ch+k[j]+w[j])|0,s0=r(a[0],2)^r(a[0],13)^r(a[0],22),maj=(a[0]&a[1])^(a[0]&a[2])^(a[1]&a[2]),t2=(s0+maj)|0;a=[(t1+t2)|0,a[0],a[1],a[2],(a[3]+t1)|0,a[4],a[5],a[6]];}} h=h.map((v,j)=>(v+a[j])|0);}}
    return h.map(v=>(v>>>0).toString(16).padStart(8,'0')).join('');
  }};
  const fingerprint = 'sha256:' + sha256(stable);
  const activity = (value) => {{
    const text = String(value || '').trim();
    const clock = text.match(/^(\d{{1,2}}):(\d{{2}})$/);
    if (!clock) return text || null;
    const local = new Date();
    local.setHours(Number(clock[1]), Number(clock[2]), 0, 0);
    return local.toISOString();
  }};
  const sequenceLike = (value) => /^(?:middlePanel_list_\d{{13}}|\d+)$/.test(String(value || '').trim());
  if ('{action}' === 'scan') {{
    const item = cfg.selectors.conversation_item;
    const rows = Array.from(document.querySelectorAll(item.selector));
    if (rows.length > item.maximum_matches) throw new Error('conversation boundary');
    return {{fingerprint, conversations: rows.map((row) => {{
      const conversationId = one(row,'conversation_id');
      const lastActivity = one(row,'last_activity');
      const rawSequence = one(row,'latest_sequence');
      const preview = one(row,'latest_message_preview');
      const latestMessageId = sequenceLike(rawSequence)
        ? rawSequence
        : (preview ? 'preview-sha256:' + sha256([conversationId, preview].join('\n')) : null);
      return {{
        conversation_id: conversationId,
        customer_reference: one(row,'customer_reference'),
        unread_count: one(row,'unread_count'),
        last_activity: activity(lastActivity),
        latest_sequence: sequenceLike(rawSequence) ? rawSequence : null,
        latest_message_id: latestMessageId,
        attention: one(row,'conversation_attention')
      }};
    }})}};
  }}
  const item = cfg.selectors.message_item;
  const rows = Array.from(document.querySelectorAll(item.selector));
  if (rows.length > item.maximum_matches) throw new Error('message boundary');
  const pick = (name) => one(document,name);
  const productCardBinding = cfg.selectors.product_card;
  let cardGoodsInfo = {{}};
  if (productCardBinding) {{
    const productCards = Array.from(document.querySelectorAll(productCardBinding.selector));
    if (productCards.length > productCardBinding.maximum_matches) throw new Error('product card boundary');
    const productCard = productCards.length ? productCards[productCards.length - 1] : null;
    const commonCard = productCard ? productCard.closest('.commonCard') : null;
    const vm = commonCard && commonCard.__vue__;
    const props = vm ? (vm.$props || vm._props || {{}}) : {{}};
    cardGoodsInfo = ((((props.msg || {{}}).info || {{}}).goods_info) || {{}});
  }}
  const cardProductId = String(cardGoodsInfo.goods_id || '').trim();
  const cardProductName = String(cardGoodsInfo.goods_name || '').trim();
  return {{fingerprint, active_conversation_id: pick('active_conversation_id'), customer_reference: pick('customer_reference'),
    store_name: pick('store_name'),
    product: {{
      product_id:/^\d{{6,32}}$/.test(cardProductId) ? cardProductId : pick('product_id'),
      product_name:cardProductName || pick('product_name'),
      sku_id:pick('sku_id'),
      sku_name:pick('sku_name'),
      attributes_text:pick('product_attributes')
    }},
    order: {{order_reference:pick('order_reference'),order_status:pick('order_status'),logistics_status:pick('logistics_status'),aftersales_status:pick('aftersales_status')}},
    messages: rows.map((row) => ({{message_id:one(row,'message_id'),role:one(row,'message_role'),content:one(row,'message_content'),timestamp:one(row,'message_timestamp'),sequence:one(row,'message_sequence')}}))}};
}})()
""".strip()


def _required_text(item: dict[str, object], key: str, maximum: int) -> str:
    value = _optional_text(item.get(key), maximum)
    if value is None:
        raise PDDReadOnlyDriverError(f"PDD read field {key} is missing")
    return value


def _optional_text(value: object, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PDDReadOnlyDriverError("PDD read text field is invalid")
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise PDDReadOnlyDriverError("PDD read text field exceeded its safety limit")
    return normalized


def _optional_int(value: object, *, minimum: int) -> int | None:
    if value in {None, ""}:
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise PDDReadOnlyDriverError("PDD read numeric field is invalid") from exc
    if parsed < minimum:
        raise PDDReadOnlyDriverError("PDD read numeric field is outside its boundary")
    return parsed


def _pdd_conversation_id(value: str) -> str:
    """Return the stable PDD conversation id without a volatile DOM suffix."""

    match = _PDD_CONVERSATION_ID_PREFIX.match(value)
    return match.group(1) if match else value


def _pdd_customer_reference_basis(value: str, conversation_id: str) -> str:
    """Normalize an optional customer reference against the row conversation id.

    Non-PDD replay identifiers remain unchanged.  This keeps scan and capture
    identity checks strict without persisting a public customer name.
    """

    normalized = _pdd_conversation_id(value)
    return conversation_id if normalized == conversation_id else value


def _pdd_message_sequence(value: object) -> int | None:
    if isinstance(value, str):
        match = _PDD_MESSAGE_ID.fullmatch(value.strip())
        if match:
            return int(match.group(1))
    return _optional_int(value, minimum=1)


def _pdd_message_datetime(value: object) -> datetime:
    if isinstance(value, str):
        match = _PDD_MESSAGE_ID.fullmatch(value.strip())
        if match:
            try:
                return datetime.fromtimestamp(int(match.group(1)) / 1_000, tz=UTC)
            except (OverflowError, OSError, ValueError) as exc:
                raise PDDReadOnlyDriverError(
                    "PDD message id timestamp is outside its boundary"
                ) from exc
    return _aware_datetime(value)


def _reply_attention(
    value: str | None,
) -> tuple[PDDReplyAttentionState, int | None]:
    if value is None:
        return PDDReplyAttentionState.NONE, None
    normalized = " ".join(value.split())
    countdown = re.search(r"(\d{1,6})\s*秒后超时", normalized)
    if countdown:
        return PDDReplyAttentionState.COUNTDOWN, min(int(countdown.group(1)), 604_800)
    overdue = re.search(r"(?:(\d{1,6})\s*(秒|分钟|小时))?.*(?:未回|未回复|已超时|超时)", normalized)
    if overdue:
        amount = int(overdue.group(1)) if overdue.group(1) else None
        unit = overdue.group(2)
        if amount is not None:
            amount *= {"秒": 1, "分钟": 60, "小时": 3600}.get(unit or "秒", 1)
        return PDDReplyAttentionState.OVERDUE, min(amount, 604_800) if amount else None
    return PDDReplyAttentionState.UNKNOWN, None


def _aware_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PDDReadOnlyDriverError("PDD timestamp is not an ISO timestamp") from exc
    else:
        raise PDDReadOnlyDriverError("PDD timestamp is missing")
    if parsed.tzinfo is None:
        raise PDDReadOnlyDriverError("PDD timestamp must include a timezone")
    return parsed.astimezone(UTC)


__all__ = [
    "EvidenceBackedPDDReadOnlyDriver",
    "LivePDDPageReadPort",
    "PDDConversationNotActive",
    "PDDDOMBinding",
    "PDDFingerprintProbe",
    "PDDObserverEvidence",
    "PDDReadOnlyDriverError",
    "ReadOnlyCDPEvaluator",
    "build_replay_observer_evidence",
    "load_pdd_observer_evidence",
]
