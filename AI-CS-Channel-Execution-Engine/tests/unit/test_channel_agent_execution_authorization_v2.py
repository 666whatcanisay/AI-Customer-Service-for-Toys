from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from channel_agent.edge_execution import (
    AuthorizedEdgeSendCommand,
    EdgeExecutionService,
    EdgeReceiptStore,
    EdgeTransportResult,
)
from channel_agent.execution_authorization import (
    ExecutionAuthorizationClaims,
    ExecutionAuthorizationError,
    ExecutionAuthorizationSigner,
    ExecutionAuthorizationVerifier,
    reply_text_sha256,
)


_SECRET = b"execution-authorization-test-secret-32-bytes"
_EVIDENCE = "sha256:" + "1" * 64
_REPLY = "建议在成人陪同下使用。"


def _claims(now: datetime) -> ExecutionAuthorizationClaims:
    return ExecutionAuthorizationClaims(
        agent_id="agent-001",
        device_id="device-001",
        store_id="store-001",
        conversation_id="conversation-001",
        customer_reference="customer-001",
        message_id="message-001",
        decision_id="decision-001",
        approval_id="approval-001",
        execution_id="execution-001",
        lease_id="lease-001",
        lease_expires_at=now + timedelta(minutes=2),
        reply_sha256=reply_text_sha256(_REPLY),
        send_key="send-key-001",
        policy_version="policy.v2",
        selector_evidence_hash=_EVIDENCE,
        activation_grant_id="activation-grant-001",
        human_approval_verified=True,
        lease_valid=True,
        kill_switch_disabled=True,
        store_allowlisted=True,
        risk_policy_allowed=True,
        rate_limit_allowed=True,
    )


class _Transport:
    def __init__(self, result: EdgeTransportResult | Exception) -> None:
        self.result = result
        self.calls = 0

    def send(self, _command: AuthorizedEdgeSendCommand) -> EdgeTransportResult:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _service(
    tmp_path: Path,
    now: datetime,
    transport: _Transport,
):  # type: ignore[no-untyped-def]
    signer = ExecutionAuthorizationSigner(
        key_id="engine-execution-v2",
        secret=_SECRET,
        clock=lambda: now,
    )
    authorization = signer.issue(_claims(now))
    verifier = ExecutionAuthorizationVerifier(
        key_resolver=lambda key_id: _SECRET if key_id == "engine-execution-v2" else b"",
        clock=lambda: now,
    )
    service = EdgeExecutionService(
        agent_id="agent-001",
        device_id="device-001",
        verifier=verifier,
        receipt_store=EdgeReceiptStore(tmp_path / "receipts.db"),
        transport=transport,
        clock=lambda: now,
    )
    return service, AuthorizedEdgeSendCommand(
        authorization=authorization,
        reply_text=_REPLY,
    )


def _execute(service: EdgeExecutionService, command: AuthorizedEdgeSendCommand):  # type: ignore[no-untyped-def]
    return service.execute(
        command,
        current_store_id="store-001",
        current_conversation_id="conversation-001",
        current_customer_reference="customer-001",
        current_selector_evidence_hash=_EVIDENCE,
    )


def test_signed_authorization_executes_once_and_duplicate_returns_original_receipt(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)
    transport = _Transport(
        EdgeTransportResult(
            outcome="SUCCESS",
            transport_triggered=True,
            customer_message_sent=True,
            confirmation_state="CONFIRMED_SUCCESS",
            external_message_id="external-sent-001",
        )
    )
    service, command = _service(tmp_path, now, transport)
    first = _execute(service, command)
    second = _execute(service, command)

    assert first == second
    assert transport.calls == 1
    assert first.outcome == "SUCCESS"
    assert first.automatic_retry_allowed is False


def test_transport_uncertainty_is_immutable_unknown_and_never_retried(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)
    transport = _Transport(TimeoutError("trigger result unknown"))
    service, command = _service(tmp_path, now, transport)
    receipt = _execute(service, command)
    recovered_service = EdgeExecutionService(
        agent_id="agent-001",
        device_id="device-001",
        verifier=ExecutionAuthorizationVerifier(
            key_resolver=lambda _key_id: _SECRET,
            clock=lambda: now,
        ),
        receipt_store=EdgeReceiptStore(tmp_path / "receipts.db"),
        transport=transport,
        clock=lambda: now,
    )
    recovered = _execute(recovered_service, command)

    assert receipt == recovered
    assert transport.calls == 1
    assert receipt.outcome == "UNKNOWN"
    assert receipt.transport_triggered is None
    assert receipt.customer_message_sent is None
    assert receipt.reconciliation_required is True
    assert receipt.automatic_retry_allowed is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("current_store_id", "store-other", "store mismatch"),
        ("current_conversation_id", "conversation-other", "conversation mismatch"),
        ("current_customer_reference", "customer-other", "customer mismatch"),
        ("current_selector_evidence_hash", "sha256:" + "2" * 64, "selector evidence mismatch"),
    ],
)
def test_page_target_or_selector_change_fails_before_transport(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    now = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)
    transport = _Transport(
        EdgeTransportResult(
            outcome="FAILED",
            transport_triggered=False,
            customer_message_sent=False,
            confirmation_state="CONFIRMED_FAILURE",
        )
    )
    service, command = _service(tmp_path, now, transport)
    arguments = {
        "current_store_id": "store-001",
        "current_conversation_id": "conversation-001",
        "current_customer_reference": "customer-001",
        "current_selector_evidence_hash": _EVIDENCE,
    }
    arguments[field] = value
    with pytest.raises(ExecutionAuthorizationError, match=message):
        service.execute(command, **arguments)
    assert transport.calls == 0


def test_tampered_reply_or_signature_fails_closed(tmp_path: Path) -> None:
    now = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)
    transport = _Transport(RuntimeError("must not run"))
    service, command = _service(tmp_path, now, transport)
    changed = command.model_copy(update={"reply_text": "different reply"})
    with pytest.raises(ExecutionAuthorizationError, match="reply mismatch"):
        _execute(service, changed)
    tampered = command.model_copy(
        update={
            "authorization": command.authorization.model_copy(
                update={"signature": "0" * 64}
            )
        }
    )
    with pytest.raises(ExecutionAuthorizationError, match="signature"):
        _execute(service, tampered)
    assert transport.calls == 0
