from __future__ import annotations

import inspect

from channel_engine.pdd_adapter import (
    PDDCapturedMessage,
    PDDMessageObservationEvidence,
    PDDMessageObservationRuntime,
    PDDMessageObservationSafetySnapshot,
    PDDMessageReader,
    PDDPrivacyFilteredMessage,
)


def test_persistable_observation_models_do_not_expose_sensitive_fields() -> None:
    forbidden = {
        "cookie",
        "token",
        "password",
        "customer_name",
        "phone",
        "address",
        "payment",
        "raw_payload",
    }
    persistable_fields = (
        set(PDDPrivacyFilteredMessage.model_fields)
        | set(PDDMessageObservationEvidence.model_fields)
        | set(PDDMessageObservationSafetySnapshot.model_fields)
    )

    assert forbidden.isdisjoint(persistable_fields)
    assert PDDCapturedMessage.model_fields["content"].repr is False
    assert PDDPrivacyFilteredMessage.model_fields["content"].repr is False


def test_observation_runtime_and_reader_contract_have_no_outbound_surface() -> None:
    protocol_source = inspect.getsource(PDDMessageReader)
    runtime_source = inspect.getsource(PDDMessageObservationRuntime)

    assert "send_message" not in protocol_source
    assert "click_send" not in protocol_source
    assert "approve" not in protocol_source
    assert "send_message" not in runtime_source
    assert "click_send" not in runtime_source
    assert "approve(" not in runtime_source
    assert "execute(" not in runtime_source


def test_safety_snapshot_is_structurally_zero_side_effect() -> None:
    safety = PDDMessageObservationSafetySnapshot()

    assert safety.approval_created == 0
    assert safety.execution_created == 0
    assert safety.receipt_created == 0
    assert safety.send_operations == 0
    assert safety.browser_write_operations == 0
    assert safety.automatic_login_performed is False
    assert safety.auto_reply_enabled is False
