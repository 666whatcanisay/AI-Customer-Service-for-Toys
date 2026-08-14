from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from channel_agent.assistant_bridge import (
    ApprovedReplyBridgeError,
    ApprovedReplyRequest,
    ApprovedReplyService,
)
from channel_agent.controlled_send_grant import (
    ControlledAutoPolicyGrantV1,
    ControlledPilotSendWindowStore,
    ControlledPilotSendWindowV1,
    ControlledSendGrantError,
    ControlledSendGrantV1,
    normalize_pilot_question,
    normalized_question_sha256,
)

NOW = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)
STORE = "c-store-pilot"
BUYER = "sha256:" + "b" * 64
CONVERSATION = "conversation-pilot-1"
QUESTION = "  这个规格\u3000适合几岁？  "
REPLY = "这款商品建议五岁以上使用。"
KNOWLEDGE_HASH = hashlib.sha256(b"knowledge-scope").hexdigest()


def _window(
    *, mode: str = "AUTO_POLICY", issued_at: datetime = NOW
) -> ControlledPilotSendWindowV1:
    return ControlledPilotSendWindowV1.issue(
        mode=mode,
        store_id=STORE,
        test_buyer_hash=BUYER,
        conversation_id=CONVERSATION,
        question=QUESTION,
        approved_reply=REPLY,
        product_id="product-1",
        sku_id="sku-1",
        policy_revision=7,
        whitelist_revision="allowlist-3",
        knowledge_scope_sha256=KNOWLEDGE_HASH,
        issued_at=issued_at,
    )


def _auto_grant(
    window: ControlledPilotSendWindowV1,
    *, question: str = QUESTION,
    reply: str = REPLY,
    approved_reply_sha256: str | None = None,
) -> ControlledAutoPolicyGrantV1:
    return ControlledAutoPolicyGrantV1.issue(
        pilot_window_id=window.window_id,
        store_id=STORE,
        test_buyer_hash=BUYER,
        conversation_id=CONVERSATION,
        customer_message_id="customer-message-new",
        decision_id="decision-new",
        question=question,
        reply_content=reply,
        approved_reply_sha256=(
            approved_reply_sha256
            or hashlib.sha256(REPLY.encode("utf-8")).hexdigest()
        ),
        product_id="product-1",
        sku_id="sku-1",
        policy_revision=7,
        whitelist_revision="allowlist-3",
        knowledge_scope_sha256=KNOWLEDGE_HASH,
        issued_at=NOW,
    )


def test_question_normalization_is_stable_but_reply_hash_is_exact() -> None:
    assert normalize_pilot_question(QUESTION) == "这个规格 适合几岁?"
    assert normalized_question_sha256(QUESTION) == normalized_question_sha256(
        "这个规格 适合几岁?"
    )

    window = _window()
    with pytest.raises(ValidationError, match="exactly match"):
        _auto_grant(window, reply=REPLY + " ")


def test_manual_grant_without_pilot_keeps_legacy_identity_and_json_shape() -> None:
    grant = ControlledSendGrantV1.issue(
        store_id=STORE,
        test_buyer_hash=BUYER,
        conversation_id=CONVERSATION,
        customer_message_id="message-1",
        decision_id="decision-1",
        reply_content=REPLY,
        operator_reference="operator-1",
        issued_at=NOW,
    )
    legacy_payload = grant.model_dump(exclude={"pilot_window_id"})
    loaded = ControlledSendGrantV1.model_validate(legacy_payload)
    assert loaded.grant_id == grant.grant_id
    assert loaded.pilot_window_id is None


def test_pilot_window_is_single_open_exact_scope_and_one_success(tmp_path) -> None:
    store = ControlledPilotSendWindowStore(tmp_path / "pilot-window.sqlite3")
    window = _window()
    grant = _auto_grant(window)
    store.arm(window, now=NOW)

    assert store.active(now=NOW + timedelta(seconds=1)) == window
    authorized = store.assert_authorized(
        grant,
        question="这个规格 适合几岁?",
        product_id="product-1",
        sku_id="sku-1",
        knowledge_scope_sha256=KNOWLEDGE_HASH,
        now=NOW + timedelta(seconds=1),
    )
    assert authorized.window_id == window.window_id

    with pytest.raises(ControlledSendGrantError, match="another"):
        store.arm(_window(issued_at=NOW + timedelta(seconds=2)), now=NOW + timedelta(seconds=2))

    store.consume_success(window.window_id, now=NOW + timedelta(seconds=3))
    assert store.active(now=NOW + timedelta(seconds=4)) is None
    with pytest.raises(ControlledSendGrantError, match="already"):
        store.consume_success(window.window_id, now=NOW + timedelta(seconds=5))


@pytest.mark.parametrize(
    ("question", "product_id", "sku_id", "knowledge_hash"),
    [
        ("不同问题", "product-1", "sku-1", KNOWLEDGE_HASH),
        (QUESTION, "product-2", "sku-1", KNOWLEDGE_HASH),
        (QUESTION, "product-1", "sku-2", KNOWLEDGE_HASH),
        (QUESTION, "product-1", "sku-1", hashlib.sha256(b"changed").hexdigest()),
    ],
)
def test_pilot_window_rejects_any_scope_drift(
    tmp_path, question, product_id, sku_id, knowledge_hash
) -> None:
    store = ControlledPilotSendWindowStore(tmp_path / "pilot-window.sqlite3")
    window = _window()
    store.arm(window, now=NOW)
    with pytest.raises(ControlledSendGrantError, match="scope"):
        store.assert_authorized(
            _auto_grant(window),
            question=question,
            product_id=product_id,
            sku_id=sku_id,
            knowledge_scope_sha256=knowledge_hash,
            now=NOW + timedelta(seconds=1),
        )


def test_pilot_window_ttl_fails_closed(tmp_path) -> None:
    store = ControlledPilotSendWindowStore(tmp_path / "pilot-window.sqlite3")
    store.arm(_window(), now=NOW)
    assert store.active(now=NOW + timedelta(minutes=5)) is None


def test_intent_mismatch_closes_armed_window_before_any_sender_call(tmp_path) -> None:
    windows = ControlledPilotSendWindowStore(tmp_path / "pilot-window.sqlite3")
    window = _window()
    windows.arm(window, now=NOW)
    grant = _auto_grant(window)
    request = ApprovedReplyRequest(
        decision_id=grant.decision_id,
        conversation_id=grant.conversation_id,
        customer_message_id=grant.customer_message_id,
        reply_text=REPLY,
        operator_reference="operator-1",
        confirmation_phrase=f"CONFIRM SEND {grant.decision_id}",
        idempotency_key=f"pdd-controlled-send:{grant.decision_id}",
        confirmed_at=NOW,
        controlled_send_grant=grant,
    )
    service = ApprovedReplyService(
        feed_path=tmp_path / "unused.json",
        buffer=SimpleNamespace(),
        uow_factory=lambda: None,
        observer=SimpleNamespace(),
        browser_sender=SimpleNamespace(),
        controlled_send_grant_store=SimpleNamespace(),
        controlled_send_enabled=True,
        controlled_pilot_window_store=windows,
        clock=lambda: NOW + timedelta(seconds=1),
    )

    with pytest.raises(ApprovedReplyBridgeError) as captured:
        service.approve_and_send(request, intent="HUMAN_CONFIRMED_SEND")
    assert captured.value.error_code == "PDD_SEND_INTENT_GRANT_MISMATCH"
    assert windows.active(now=NOW + timedelta(seconds=2)) is None
