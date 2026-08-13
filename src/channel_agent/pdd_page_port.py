from __future__ import annotations

import json
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class PDDPageReadPortError(RuntimeError):
    """Fail-closed page-read boundary shared by Live and Replay inputs."""


@runtime_checkable
class PDDPageReadPort(Protocol):
    """Narrow page read port; intentionally has no navigate/click/input API."""

    source_kind: Literal["LIVE_PDD", "OFFLINE_REPLAY"]
    pdd_network_requests: int

    def read(
        self,
        operation: Literal["SCAN", "CAPTURE"],
        expression: str,
    ) -> object: ...


class PDDReadReplayFixture(BaseModel):
    """Sanitized DOM-extraction fixture, not a prebuilt CustomerContext."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["pdd-readonly-page-fixture.v1"]
    fixture_id: str = Field(min_length=1, max_length=160)
    source: Literal["SYNTHETIC_SANITIZED"]
    sanitized: Literal[True]
    captured_at: AwareDatetime
    page_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    selector_contract_version: Literal["pdd-replay.v1"] = "pdd-replay.v1"
    role_map: dict[str, Literal["CUSTOMER", "OPERATOR", "BOT", "SYSTEM"]]
    scan: dict[str, Any]
    capture: dict[str, Any]
    pdd_network_requests: Literal[0] = 0

    @model_validator(mode="after")
    def validate_raw_page_results(self) -> "PDDReadReplayFixture":
        if self.scan.get("fingerprint") != self.page_fingerprint:
            raise ValueError("replay scan fingerprint is inconsistent")
        if self.capture.get("fingerprint") != self.page_fingerprint:
            raise ValueError("replay capture fingerprint is inconsistent")
        if not isinstance(self.scan.get("conversations"), list):
            raise ValueError("replay scan must contain raw conversation rows")
        if not isinstance(self.capture.get("messages"), list):
            raise ValueError("replay capture must contain raw message rows")
        _reject_sensitive_fixture_keys(self.model_dump(mode="json"))
        return self


def load_pdd_replay_fixture(path: str | Path) -> PDDReadReplayFixture:
    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise PDDPageReadPortError("PDD replay fixture cannot be read") from exc
    if len(payload) > 1024 * 1024:
        raise PDDPageReadPortError("PDD replay fixture exceeds one MiB")
    try:
        fixture = PDDReadReplayFixture.model_validate_json(payload)
    except Exception as exc:
        raise PDDPageReadPortError("PDD replay fixture is invalid") from exc
    if fixture.fixture_id.startswith("real-pdd-sanitized:"):
        try:
            from .pdd_replay_approval import validate_real_fixture_from_environment

            validate_real_fixture_from_environment(source)
        except Exception as exc:
            raise PDDPageReadPortError(
                "real-derived PDD replay fixture is not approved"
            ) from exc
    return fixture


_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ID_CARD = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\w)")
_PAYMENT = re.compile(r"(?<!\d)\d{12,19}(?!\d)")
_EMAIL = re.compile(r"(?<![\w.])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.])")


def build_sanitized_pdd_replay_fixture(
    *,
    scan: dict[str, Any],
    capture: dict[str, Any],
    role_map: dict[str, Literal["CUSTOMER", "OPERATOR", "BOT", "SYSTEM"]],
    target_conversation_id: str,
    allowed_message_ids: tuple[str, ...],
    captured_at: datetime | None = None,
) -> PDDReadReplayFixture:
    """Build a minimal replay without retaining real identifiers or credentials."""

    if not target_conversation_id.strip():
        raise PDDPageReadPortError("target conversation id is required")
    if not allowed_message_ids or len(allowed_message_ids) > 100:
        raise PDDPageReadPortError("an explicit bounded test-message allowlist is required")
    if len(allowed_message_ids) != len(set(allowed_message_ids)):
        raise PDDPageReadPortError("allowed replay message ids must be unique")
    rows = scan.get("conversations")
    messages = capture.get("messages")
    if not isinstance(rows, list) or not isinstance(messages, list):
        raise PDDPageReadPortError("raw PDD read result is invalid")
    selected_rows = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("conversation_id") == target_conversation_id
    ]
    if len(selected_rows) != 1 or capture.get("active_conversation_id") != target_conversation_id:
        raise PDDPageReadPortError("target PDD conversation is not unique and active")
    allowed = set(allowed_message_ids)
    selected_messages = [
        row
        for row in messages
        if isinstance(row, dict) and row.get("message_id") in allowed
    ]
    if len(selected_messages) != len(allowed):
        raise PDDPageReadPortError("one or more explicitly allowed messages are unavailable")

    synthetic_fingerprint = "sha256:" + hashlib.sha256(
        json.dumps(
            {
                "conversation_count": 1,
                "message_roles": [item.get("role") for item in selected_messages],
                "message_count": len(selected_messages),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    row = selected_rows[0]
    synthetic_conversation = "replay-conversation-001"
    synthetic_customer = "replay-customer-001"
    message_map = {
        raw_id: f"replay-message-{index:03d}"
        for index, raw_id in enumerate(allowed_message_ids, start=1)
    }
    safe_messages = []
    for item in selected_messages:
        raw_id = str(item["message_id"])
        safe_messages.append(
            {
                "message_id": message_map[raw_id],
                "role": str(item.get("role") or ""),
                "content": _sanitize_fixture_text(item.get("content")),
                "timestamp": item.get("timestamp"),
                "sequence": item.get("sequence"),
            }
        )
    product = capture.get("product") if isinstance(capture.get("product"), dict) else {}
    safe_product = {
        "product_id": "replay-product-001" if product.get("product_id") else None,
        "product_name": _sanitize_fixture_text(product.get("product_name"), optional=True),
        "sku_id": "replay-sku-001" if product.get("sku_id") else None,
        "sku_name": _sanitize_fixture_text(product.get("sku_name"), optional=True),
        "attributes_text": _sanitize_fixture_text(
            product.get("attributes_text"), optional=True
        ),
    }
    safe_scan = {
        "fingerprint": synthetic_fingerprint,
        "conversations": [
            {
                "conversation_id": synthetic_conversation,
                "customer_reference": synthetic_customer,
                "unread_count": row.get("unread_count"),
                "last_activity": row.get("last_activity"),
                "latest_sequence": row.get("latest_sequence"),
            }
        ],
    }
    safe_capture = {
        "fingerprint": synthetic_fingerprint,
        "active_conversation_id": synthetic_conversation,
        "customer_reference": synthetic_customer,
        "store_name": "脱敏测试店铺",
        "product": safe_product,
        "order": {
            "order_reference": None,
            "order_status": None,
            "logistics_status": None,
            "aftersales_status": None,
        },
        "messages": safe_messages,
    }
    material = json.dumps(
        [synthetic_fingerprint, safe_scan, safe_capture],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return PDDReadReplayFixture(
        schema_version="pdd-readonly-page-fixture.v1",
        fixture_id="real-pdd-sanitized:" + hashlib.sha256(material.encode("utf-8")).hexdigest(),
        source="SYNTHETIC_SANITIZED",
        sanitized=True,
        captured_at=(captured_at or datetime.now(UTC)).astimezone(UTC),
        page_fingerprint=synthetic_fingerprint,
        role_map=role_map,
        scan=safe_scan,
        capture=safe_capture,
    )


def _sanitize_fixture_text(value: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise PDDPageReadPortError("replay text field is invalid")
    safe = _PHONE.sub("[手机号已脱敏]", value)
    safe = _ID_CARD.sub("[证件号已脱敏]", safe)
    safe = _PAYMENT.sub("[支付信息已脱敏]", safe)
    safe = _EMAIL.sub("[邮箱已脱敏]", safe)
    safe = " ".join(safe.split()).strip()
    if not safe and not optional:
        raise PDDPageReadPortError("replay text field is empty")
    return safe or None


class ReplayPDDPageReadPort:
    """Deterministic zero-network implementation of ``PDDPageReadPort``."""

    source_kind: Literal["OFFLINE_REPLAY"] = "OFFLINE_REPLAY"
    pdd_network_requests = 0
    page_write_operations = 0
    execution_calls = 0
    transport_calls = 0

    def __init__(self, fixture: PDDReadReplayFixture) -> None:
        self.fixture = fixture
        self.read_calls = 0

    def read(
        self,
        operation: Literal["SCAN", "CAPTURE"],
        expression: str,
    ) -> object:
        if not expression or len(expression.encode("utf-8")) > 262_144:
            raise PDDPageReadPortError("PDD replay read expression is invalid")
        self.read_calls += 1
        value = self.fixture.scan if operation == "SCAN" else self.fixture.capture
        # Copy through JSON so tests and callers cannot mutate the frozen fixture.
        return json.loads(json.dumps(value, ensure_ascii=False))


def _reject_sensitive_fixture_keys(value: object, path: str = "fixture") -> None:
    forbidden = ("authorization", "cookie", "credential", "password", "secret", "token")
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key).casefold()
            if any(part in key for part in forbidden):
                raise ValueError(f"sensitive field is forbidden at {path}")
            _reject_sensitive_fixture_keys(child, f"{path}.{raw_key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_fixture_keys(child, f"{path}[{index}]")


__all__ = [
    "PDDPageReadPort",
    "PDDPageReadPortError",
    "PDDReadReplayFixture",
    "ReplayPDDPageReadPort",
    "build_sanitized_pdd_replay_fixture",
    "load_pdd_replay_fixture",
]
