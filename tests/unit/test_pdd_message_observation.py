from __future__ import annotations

from datetime import datetime, timezone

import pytest

from channel_engine.pdd_adapter import (
    FakePDDMessageReader,
    PDDCapturedMessage,
    PDDMessageObservationSafetyViolation,
    PDDObservationMessageMapper,
    PDDPrivacyCategory,
    PDDPrivacyFilter,
)


NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def captured(*, store_id: str = "store-observe-001") -> PDDCapturedMessage:
    return PDDCapturedMessage(
        store_id=store_id,
        conversation_id="conversation-observe-001",
        external_message_id="message-observe-001",
        sender="张三",
        content=(
            "我叫张三；手机号 138-0013-8000；"
            "地址：上海市浦东新区世纪大道100号；"
            "银行卡号 6222-0202-0202-0202；请问几天发货？"
        ),
        timestamp=NOW,
        captured_at=NOW,
    )


def test_privacy_filter_redacts_name_phone_address_and_payment_before_mapping() -> None:
    filtered = PDDPrivacyFilter().apply(captured())
    mapped = PDDObservationMessageMapper(store_id="store-observe-001").map(filtered)

    assert set(filtered.redaction_categories) == {
        PDDPrivacyCategory.NAME,
        PDDPrivacyCategory.PHONE,
        PDDPrivacyCategory.ADDRESS,
        PDDPrivacyCategory.PAYMENT,
    }
    assert filtered.redaction_count == 4
    assert mapped.sender == "customer"
    assert "张三" not in mapped.content
    assert "138" not in mapped.content
    assert "世纪大道" not in mapped.content
    assert "6222" not in mapped.content
    assert "请问几天发货" in mapped.content


def test_mapper_fails_closed_when_store_binding_does_not_match() -> None:
    filtered = PDDPrivacyFilter().apply(captured(store_id="store-other"))

    with pytest.raises(PDDMessageObservationSafetyViolation) as raised:
        PDDObservationMessageMapper(store_id="store-observe-001").map(filtered)

    assert raised.value.error_code == "PDD_MESSAGE_STORE_MISMATCH"


def test_reader_contract_exposes_capture_only_surface() -> None:
    reader = FakePDDMessageReader(store_id="store-observe-001", clock=lambda: NOW)

    assert reader.read_only is True
    assert reader.browser_write_operations == 0
    assert hasattr(reader, "capture")
    assert not hasattr(reader, "send_message")
    assert not hasattr(reader, "execute")
    assert not hasattr(reader, "approve")
