from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from channel_agent.pdd_page_port import ReplayPDDPageReadPort, load_pdd_replay_fixture
from channel_agent.pdd_readonly_driver import (
    EvidenceBackedPDDReadOnlyDriver,
    PDDDOMBinding,
    PDDObserverEvidence,
    _reply_attention,
    _read_expression,
    build_replay_observer_evidence,
)
from channel_agent.pdd_conversation_capture import PDDReplyAttentionState


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "simulators"
    / "pdd-customer-workspace"
    / "fixtures"
    / "pdd-readonly-page-fixture.v1.json"
)
MESSAGE_ID = "middlePanel_list_1786598806497"


def navigation_evidence_payload(
    *,
    attention_required: bool = False,
    nonunique_selector: str | None = None,
    select_target_selector: str = "[data-pdd='conversation_select_target']",
) -> dict:
    fixture = load_pdd_replay_fixture(FIXTURE)
    base = build_replay_observer_evidence(fixture)
    selectors = dict(base.selectors)
    for key in (
        "conversation_attention",
        "conversation_select_target",
        "reply_input",
        "message_container",
    ):
        selectors[key] = PDDDOMBinding(
            selector=(
                select_target_selector
                if key == "conversation_select_target"
                else f"[data-pdd='{key}']"
            ),
            attribute=None,
            required=attention_required if key == "conversation_attention" else True,
            maximum_matches=2 if key == nonunique_selector else 1,
        )
    provisional = base.model_copy(
        update={
            "schema_version": "channel-agent-pdd-observer-evidence.v2.2",
            "selectors": selectors,
        }
    )
    canonical = provisional.model_dump(mode="json", exclude={"evidence_hash"})
    evidence_hash = "sha256:" + hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return provisional.model_copy(
        update={"evidence_hash": evidence_hash}
    ).model_dump(mode="python")


class RealDOMShapePort:
    source_kind = "LIVE_PDD"
    pdd_network_requests = 0

    def __init__(
        self,
        fingerprint: str,
        *,
        content: str | None = "sanitized real DOM shape",
    ) -> None:
        self._fingerprint = fingerprint
        self._content = content

    def read(self, operation: str, expression: str) -> object:
        del expression
        self.pdd_network_requests += 1
        if operation == "SCAN":
            return {
                "fingerprint": self._fingerprint,
                "conversations": [
                    {
                        "conversation_id": "1234567890-volatile-suffix-1",
                        "customer_reference": "real-dom-customer",
                        "unread_count": "1",
                        "last_activity": MESSAGE_ID,
                        "latest_sequence": MESSAGE_ID,
                    }
                ],
            }
        return {
            "fingerprint": self._fingerprint,
            "active_conversation_id": "1234567890",
            "customer_reference": "real-dom-customer",
            "messages": [
                {
                    "message_id": MESSAGE_ID,
                    "role": "customer isread",
                    "content": self._content,
                    "timestamp": MESSAGE_ID,
                    "sequence": MESSAGE_ID,
                }
            ],
        }


class ConversationRowWithoutCustomerReferencePort(RealDOMShapePort):
    def read(self, operation: str, expression: str) -> object:
        result = super().read(operation, expression)
        if operation == "SCAN":
            result["conversations"][0]["customer_reference"] = None
            result["conversations"][0]["latest_message_id"] = "sha256:" + "b" * 64
        return result


class ConversationWithoutCustomerReferencePort(
    ConversationRowWithoutCustomerReferencePort
):
    def read(self, operation: str, expression: str) -> object:
        result = super().read(operation, expression)
        if operation == "CAPTURE":
            result["customer_reference"] = None
        return result


def test_selector_reader_can_read_an_attribute_from_the_message_row_itself() -> None:
    expression = _read_expression(
        '{"selectors":{},"probes":[],"path":"/chat-merchant/index.html"}',
        capture=True,
    )

    assert "scope.matches(b.selector)" in expression
    assert "nodes.push(scope)" in expression


def test_capture_prefers_latest_verified_product_card_vue_identity() -> None:
    expression = _read_expression(
        '{"selectors":{"product_card":{"selector":".commonCard .good-content","required":false,"maximum_matches":100},"message_item":{"selector":"li.onemsg","required":true,"maximum_matches":500}},"probes":[],"path":"/chat-merchant/index.html"}',
        capture=True,
    )

    assert "productCards[productCards.length - 1]" in expression
    assert "(vm.$props || vm._props || {})" in expression
    assert ".info || {}).goods_info" in expression
    assert "/^\\d{6,32}$/.test(cardProductId)" in expression
    assert "product_name:cardProductName || pick('product_name')" in expression


def test_real_dom_ids_normalize_and_preserve_epoch_ordering() -> None:
    fixture = load_pdd_replay_fixture(FIXTURE)
    evidence = build_replay_observer_evidence(fixture)
    driver = EvidenceBackedPDDReadOnlyDriver(
        store_id="store-001",
        platform_store_id="328616090",
        evidence=evidence,
        page_port=RealDOMShapePort(evidence.page_fingerprint),
    )

    summary = driver.scan_conversations()[0]
    snapshot = driver.capture_conversation(summary)

    assert summary.conversation_id == "1234567890"
    assert summary.latest_sequence == 1786598806497
    assert summary.last_activity_at == datetime(
        2026, 8, 13, 5, 26, 46, 497000, tzinfo=UTC
    )
    assert snapshot.conversation_id == summary.conversation_id
    assert snapshot.messages[0].external_message_id == MESSAGE_ID
    assert snapshot.messages[0].sender == "CUSTOMER"
    assert snapshot.messages[0].sequence == 1786598806497
    assert snapshot.messages[0].timestamp == summary.last_activity_at


def test_conversation_row_falls_back_to_normalized_private_identity() -> None:
    fixture = load_pdd_replay_fixture(FIXTURE)
    evidence = build_replay_observer_evidence(fixture)
    driver = EvidenceBackedPDDReadOnlyDriver(
        store_id="store-001",
        platform_store_id="328616090",
        evidence=evidence,
        page_port=ConversationRowWithoutCustomerReferencePort(
            evidence.page_fingerprint
        ),
    )

    summary = driver.scan_conversations()[0]

    assert summary.customer_reference == "sha256:" + hashlib.sha256(
        b"1234567890"
    ).hexdigest()
    assert summary.latest_message_id == "sha256:" + "b" * 64


def test_conversation_capture_uses_the_same_private_identity_fallback() -> None:
    fixture = load_pdd_replay_fixture(FIXTURE)
    evidence = build_replay_observer_evidence(fixture)
    driver = EvidenceBackedPDDReadOnlyDriver(
        store_id="store-001",
        platform_store_id="328616090",
        evidence=evidence,
        page_port=ConversationWithoutCustomerReferencePort(
            evidence.page_fingerprint
        ),
    )

    summary = driver.scan_conversations()[0]
    snapshot = driver.capture_conversation(summary)

    expected = "sha256:" + hashlib.sha256(b"1234567890").hexdigest()
    assert summary.customer_reference == expected
    assert snapshot.customer_reference == expected


def test_scan_expression_hashes_preview_without_returning_plaintext() -> None:
    expression = _read_expression(
        '{"selectors":{},"probes":[],"path":"/chat-merchant/index.html"}',
        capture=False,
    )

    assert "latest_message_preview" in expression
    assert "'sha256:' + sha256([conversationId, lastActivity, preview]" in expression
    assert "latest_message_id: latestMessageId" in expression


def test_real_dom_non_text_rows_are_preserved_but_never_forwardable() -> None:
    fixture = load_pdd_replay_fixture(FIXTURE)
    evidence = build_replay_observer_evidence(fixture)
    driver = EvidenceBackedPDDReadOnlyDriver(
        store_id="store-001",
        platform_store_id="328616090",
        evidence=evidence,
        page_port=RealDOMShapePort(evidence.page_fingerprint, content=None),
    )

    summary = driver.scan_conversations()[0]
    snapshot = driver.capture_conversation(summary)

    assert snapshot.messages[0].sender == "UNKNOWN"
    assert snapshot.messages[0].content == "[UNSUPPORTED_NON_TEXT_MESSAGE]"
    assert snapshot.messages[0].sequence == 1786598806497


def test_replay_identifiers_and_iso_timestamps_remain_compatible() -> None:
    fixture = load_pdd_replay_fixture(FIXTURE)
    driver = EvidenceBackedPDDReadOnlyDriver(
        store_id="store-001",
        platform_store_id="synthetic-platform-store-001",
        evidence=build_replay_observer_evidence(fixture),
        page_port=ReplayPDDPageReadPort(fixture),
    )

    summary = driver.scan_conversations()[0]
    snapshot = driver.capture_conversation(summary)

    assert summary.conversation_id == "offline-conversation-001"
    assert summary.latest_sequence == 3
    assert snapshot.messages[0].sequence == 1
    assert snapshot.messages[0].timestamp.tzinfo is not None


def test_navigation_requires_v22_and_an_explicit_navigation_port() -> None:
    fixture = load_pdd_replay_fixture(FIXTURE)
    legacy = build_replay_observer_evidence(fixture)
    assert legacy.navigation_enabled is False

    evidence = PDDObserverEvidence.model_validate(navigation_evidence_payload())
    assert evidence.navigation_enabled is True
    driver = EvidenceBackedPDDReadOnlyDriver(
        store_id="store-001",
        platform_store_id="328616090",
        evidence=evidence,
        page_port=RealDOMShapePort(evidence.page_fingerprint),
    )
    assert driver.navigation_enabled is False


def test_navigation_evidence_rejects_required_attention_on_every_row() -> None:
    with pytest.raises(ValidationError, match="optional and unique"):
        PDDObserverEvidence.model_validate(
            navigation_evidence_payload(attention_required=True)
        )


def test_navigation_evidence_rejects_mismatched_active_identity_source() -> None:
    payload = navigation_evidence_payload()
    payload["selectors"]["conversation_id"]["attribute"] = "data-random"
    payload["selectors"]["active_conversation_id"]["attribute"] = "currentuid"

    with pytest.raises(ValidationError, match="same attribute as the conversation row"):
        PDDObserverEvidence.model_validate(payload)


def test_navigation_evidence_accepts_the_verified_row_local_chat_detail_target() -> None:
    evidence = PDDObserverEvidence.model_validate(
        navigation_evidence_payload(select_target_selector=".chat-detail")
    )

    assert evidence.navigation_enabled is True
    assert evidence.selectors["conversation_select_target"].selector == ".chat-detail"


@pytest.mark.parametrize(
    "selector_name",
    ["conversation_select_target", "reply_input", "message_container"],
)
def test_navigation_evidence_requires_unique_navigation_targets(selector_name) -> None:
    with pytest.raises(ValidationError, match="required and unique"):
        PDDObserverEvidence.model_validate(
            navigation_evidence_payload(nonunique_selector=selector_name)
        )


@pytest.mark.parametrize(
    ("text", "state", "seconds"),
    [
        ("176秒后超时", PDDReplyAttentionState.COUNTDOWN, 176),
        ("已超时", PDDReplyAttentionState.OVERDUE, None),
        ("3分钟未回复", PDDReplyAttentionState.OVERDUE, 180),
        (None, PDDReplyAttentionState.NONE, None),
    ],
)
def test_reply_attention_normalization(text, state, seconds) -> None:
    assert _reply_attention(text) == (state, seconds)
