from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol, runtime_checkable

import websocket
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from channel_engine.browser.selectors import (
    LocatorEngine,
    SelectorCapability,
    SelectorContract,
    SelectorContractDrift,
    SelectorContractState,
    SelectorEvidenceEnvironment,
    SelectorKey,
)

from channel_engine.channel.execution_boundary import (
    LedgerExecutionAuthorizationService,
)
from channel_engine.execution import (
    ClaimedExecutionContext,
    ExecutionCommand,
    ExecutionResult,
)
from channel_engine.models import ReceiptOutcome

from .pdd_login import EdgePDDTargetResolver, PDDCDPPageTarget
from .pdd_workspace import (
    ExistingPDDWorkspaceObserver,
    PDD_WORKSPACE_URL,
    PDDWorkspaceSnapshot,
)


PDD_WORKSPACE_SEND_VERSION = "1.0"


class PDDWorkspaceSendError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        trigger_may_have_occurred: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.trigger_may_have_occurred = trigger_may_have_occurred


class PDDWorkspaceSendState(StrEnum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class PDDWorkspaceSendModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class PDDWorkspaceOutboundSelectorContract(PDDWorkspaceSendModel):
    """Selectors observed and explicitly verified on the current PDD workspace.

    Business code consumes this contract instead of embedding selectors.  The
    contract is deliberately limited to one text reply action; it exposes no
    refund, order, after-sales, login, or bulk operation.
    """

    contract_version: Literal["1.0"] = PDD_WORKSPACE_SEND_VERSION
    selector_contract: SelectorContract
    runtime_environment: SelectorEvidenceEnvironment
    platform: Literal["pdd"] = "pdd"
    page: Literal["merchant_chat"] = "merchant_chat"
    state: Literal["VERIFIED"] = "VERIFIED"
    page_url: Literal[
        "https://mms.pinduoduo.com/chat-merchant/index.html#/"
    ] = PDD_WORKSPACE_URL
    conversation_marker: Literal["[currentuid]"] = "[currentuid]"
    reply_input: Literal["#replyTextarea"] = "#replyTextarea"
    send_button: Literal[".reply-footer .send-btn"] = (
        ".reply-footer .send-btn"
    )
    send_button_text: Literal["发送"] = "发送"
    allowed_action: Literal["SEND_MESSAGE"] = "SEND_MESSAGE"

    @model_validator(mode="after")
    def validate_evidence_boundary(self) -> PDDWorkspaceOutboundSelectorContract:
        contract = self.selector_contract
        evidence = contract.verification_evidence
        if (
            contract.platform != "pdd"
            or contract.page != "merchant_chat"
            or contract.state is not SelectorContractState.VERIFIED
            or SelectorCapability.SEND_MESSAGE not in contract.capabilities
            or evidence is None
            or evidence.environment is not self.runtime_environment
        ):
            raise ValueError("PDD send requires matching verified selector evidence")
        expected = {
            SelectorKey.CONVERSATION_ITEM: self.conversation_marker,
            SelectorKey.COMPOSER: self.reply_input,
            SelectorKey.SEND_CONTROL: self.send_button,
            SelectorKey.SEND_CONFIRMATION: self.send_button_text,
        }
        for key, locator in expected.items():
            binding = next((item for item in contract.bindings if item.key is key), None)
            if (
                binding is None
                or binding.engine not in {LocatorEngine.CSS, LocatorEngine.TEXT}
                or binding.locator != locator
            ):
                raise ValueError(
                    f"PDD send selector is not covered by evidence: {key.value}"
                )
        return self

    @property
    def evidence_hash(self) -> str:
        evidence = self.selector_contract.verification_evidence
        if evidence is None:
            raise ValueError("PDD send selector evidence unavailable")
        return evidence.evidence_hash

    @property
    def page_fingerprint(self) -> str:
        evidence = self.selector_contract.verification_evidence
        if evidence is None:
            raise ValueError("PDD send selector evidence unavailable")
        return evidence.page_fingerprint


class PDDWorkspaceSendProbe(PDDWorkspaceSendModel):
    page_url: str
    current_uid: str = Field(min_length=1, repr=False)
    input_count: int = Field(ge=0)
    send_button_count: int = Field(ge=0)
    input_text_length: int = Field(ge=0)
    send_button_text: str
    page_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class PDDWorkspaceActionResult(PDDWorkspaceSendModel):
    triggered: bool
    error_code: str | None = None


class PDDWorkspaceSendResult(PDDWorkspaceSendModel):
    state: PDDWorkspaceSendState
    outcome: ReceiptOutcome
    external_message_id: str | None = None
    error_code: str | None = None
    trigger_may_have_occurred: bool
    customer_message_sent: bool | None
    confirmed_at: AwareDatetime


@runtime_checkable
class PDDWorkspaceActionPort(Protocol):
    def probe(
        self,
        target: PDDCDPPageTarget,
        contract: PDDWorkspaceOutboundSelectorContract,
    ) -> PDDWorkspaceSendProbe: ...

    def fill_and_submit(
        self,
        target: PDDCDPPageTarget,
        contract: PDDWorkspaceOutboundSelectorContract,
        *,
        expected_current_uid: str,
        content: str,
    ) -> PDDWorkspaceActionResult: ...


class WebSocketPDDWorkspaceActionPort:
    """One narrowly-scoped, loopback-only CDP action port.

    A command is accepted only when the exact PDD page, current conversation,
    empty input, verified input selector and verified send selector still
    match.  Once a click might have reached the page, transport failure is
    classified UNKNOWN and callers must never retry automatically.
    """

    def __init__(self, *, timeout_seconds: float = 3.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("PDD workspace action timeout must be positive")
        self._timeout = timeout_seconds
        self._lock = RLock()
        self._sequence = 0

    def probe(
        self,
        target: PDDCDPPageTarget,
        contract: PDDWorkspaceOutboundSelectorContract,
    ) -> PDDWorkspaceSendProbe:
        selector = json.dumps(contract.model_dump(mode="json"), ensure_ascii=False)
        expression = f"""
(async () => {{
  const s = {selector};
  const inputs = Array.from(document.querySelectorAll(s.reply_input));
  const sends = Array.from(document.querySelectorAll(s.send_button));
  const scope = document.querySelector(s.conversation_marker);
  const signature = JSON.stringify({{
    url: String(location.href || ''),
    input_tags: inputs.map((node) => String(node.tagName || '')),
    send_tags: sends.map((node) => String(node.tagName || '')),
    conversation_tags: scope ? [String(scope.tagName || '')] : []
  }});
  const bytes = new TextEncoder().encode(signature);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const pageFingerprint = 'sha256:' + Array.from(new Uint8Array(digest))
    .map((value) => value.toString(16).padStart(2, '0')).join('');
  return {{
    page_url: String(location.href || ''),
    current_uid: scope ? String(scope.getAttribute('currentuid') || '') : '',
    input_count: inputs.length,
    send_button_count: sends.length,
    input_text_length: inputs.length === 1 ? String(inputs[0].value || '').length : 0,
    send_button_text: sends.length === 1 ? String(sends[0].innerText || '').trim() : '',
    page_fingerprint: pageFingerprint
  }};
}})()
""".strip()
        value = self._evaluate(target, expression, action=False)
        if not isinstance(value, dict):
            raise PDDWorkspaceSendError(
                "PDD send probe returned an invalid payload",
                error_code="PDD_SEND_PROBE_INVALID",
            )
        return PDDWorkspaceSendProbe.model_validate(value)

    def fill_and_submit(
        self,
        target: PDDCDPPageTarget,
        contract: PDDWorkspaceOutboundSelectorContract,
        *,
        expected_current_uid: str,
        content: str,
    ) -> PDDWorkspaceActionResult:
        if not content.strip() or len(content) > 8_000:
            raise PDDWorkspaceSendError(
                "PDD reply content is empty or too long",
                error_code="PDD_SEND_CONTENT_INVALID",
            )
        selector = json.dumps(contract.model_dump(mode="json"), ensure_ascii=False)
        expected = json.dumps(expected_current_uid, ensure_ascii=False)
        reply = json.dumps(content, ensure_ascii=False)
        expression = f"""
(() => {{
  const s = {selector};
  const expectedUid = {expected};
  const content = {reply};
  const reject = (code) => ({{triggered: false, error_code: code}});
  if (String(location.href || '') !== s.page_url) return reject('PDD_SEND_PAGE_CHANGED');
  const scope = document.querySelector(s.conversation_marker);
  if (!scope || String(scope.getAttribute('currentuid') || '') !== expectedUid) {{
    return reject('PDD_SEND_CONVERSATION_CHANGED');
  }}
  const inputs = Array.from(document.querySelectorAll(s.reply_input));
  const sends = Array.from(document.querySelectorAll(s.send_button));
  if (inputs.length !== 1 || sends.length !== 1) return reject('PDD_SEND_SELECTOR_AMBIGUOUS');
  const input = inputs[0];
  const send = sends[0];
  if (String(send.innerText || '').trim() !== s.send_button_text) {{
    return reject('PDD_SEND_SELECTOR_TEXT_CHANGED');
  }}
  if (input.disabled || String(input.value || '').length !== 0) {{
    return reject('PDD_SEND_INPUT_NOT_EMPTY');
  }}
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
  if (!setter) return reject('PDD_SEND_INPUT_SETTER_UNAVAILABLE');
  setter.call(input, content);
  input.dispatchEvent(new Event('input', {{bubbles: true, composed: true}}));
  input.dispatchEvent(new Event('change', {{bubbles: true, composed: true}}));
  if (String(input.value || '') !== content) {{
    setter.call(input, '');
    input.dispatchEvent(new Event('input', {{bubbles: true, composed: true}}));
    return reject('PDD_SEND_INPUT_CONFIRMATION_FAILED');
  }}
  if (String(scope.getAttribute('currentuid') || '') !== expectedUid) {{
    setter.call(input, '');
    input.dispatchEvent(new Event('input', {{bubbles: true, composed: true}}));
    return reject('PDD_SEND_CONVERSATION_CHANGED');
  }}
  send.click();
  return {{triggered: true, error_code: null}};
}})()
""".strip()
        value = self._evaluate(target, expression, action=True)
        if not isinstance(value, dict):
            raise PDDWorkspaceSendError(
                "PDD send action returned an invalid payload",
                error_code="PDD_SEND_ACTION_INVALID_UNKNOWN",
                trigger_may_have_occurred=True,
            )
        return PDDWorkspaceActionResult.model_validate(value)

    def _evaluate(
        self,
        target: PDDCDPPageTarget,
        expression: str,
        *,
        action: bool,
    ) -> object:
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
                    "awaitPromise": True,
                    "includeCommandLineAPI": False,
                    "silent": True,
                },
            },
            separators=(",", ":"),
        )
        connection = None
        command_sent = False
        try:
            connection = websocket.create_connection(
                target.websocket_url,
                timeout=self._timeout,
                suppress_origin=True,
                http_proxy_host=None,
            )
            connection.send(command)
            command_sent = True
            while True:
                raw = connection.recv()
                if not isinstance(raw, str):
                    raise ValueError("binary CDP response")
                response = json.loads(raw)
                if not isinstance(response, dict) or response.get("id") != command_id:
                    continue
                if "error" in response:
                    raise ValueError("CDP action rejected")
                result = response.get("result")
                if not isinstance(result, dict) or "exceptionDetails" in result:
                    raise ValueError("CDP action failed")
                remote = result.get("result")
                if not isinstance(remote, dict) or "value" not in remote:
                    raise ValueError("CDP action returned no value")
                return remote["value"]
        except (OSError, ValueError, json.JSONDecodeError, websocket.WebSocketException) as exc:
            unknown = action and command_sent
            raise PDDWorkspaceSendError(
                "PDD browser action channel failed",
                error_code=(
                    "PDD_SEND_ACTION_TRANSPORT_UNKNOWN"
                    if unknown
                    else "PDD_SEND_ACTION_TRANSPORT_UNAVAILABLE"
                ),
                trigger_may_have_occurred=unknown,
            ) from exc
        finally:
            if connection is not None:
                connection.close()


class ControlledPDDWorkspaceBrowserSender:
    def __init__(
        self,
        *,
        observer: ExistingPDDWorkspaceObserver,
        profile_path: str | Path,
        resolver: EdgePDDTargetResolver,
        action_port: PDDWorkspaceActionPort,
        contract: PDDWorkspaceOutboundSelectorContract | None = None,
        confirmation_timeout_seconds: float = 8.0,
        poll_seconds: float = 0.25,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if confirmation_timeout_seconds <= 0 or poll_seconds <= 0:
            raise ValueError("PDD send confirmation timing must be positive")
        self._observer = observer
        self._profile_path = Path(profile_path).resolve()
        self._resolver = resolver
        self._actions = action_port
        if contract is None:
            raise PDDWorkspaceSendError(
                "PDD send selector evidence is required",
                error_code="PDD_SEND_SELECTOR_EVIDENCE_REQUIRED",
            )
        self.contract = contract
        self._timeout = confirmation_timeout_seconds
        self._poll = poll_seconds
        self._clock = clock
        self._sleep = sleep
        self._lock = RLock()

    def send(
        self,
        *,
        content: str,
        expected_store_id: str,
        expected_conversation_id: str,
        expected_customer_reference: str,
        expected_customer_message_id: str,
    ) -> PDDWorkspaceSendResult:
        with self._lock:
            before = self._observer.capture()
            self._assert_exact_target(
                before,
                expected_store_id=expected_store_id,
                expected_conversation_id=expected_conversation_id,
                expected_customer_reference=expected_customer_reference,
                expected_customer_message_id=expected_customer_message_id,
            )
            target = self._resolver.resolve(self._profile_path)
            probe = self._actions.probe(target, self.contract)
            self._assert_probe(probe, before)
            before_ids = {item.external_message_id for item in before.visible_history}
            try:
                action = self._actions.fill_and_submit(
                    target,
                    self.contract,
                    expected_current_uid=probe.current_uid,
                    content=content,
                )
            except PDDWorkspaceSendError as exc:
                return self._error_result(exc)
            if not action.triggered:
                return PDDWorkspaceSendResult(
                    state=PDDWorkspaceSendState.REJECTED,
                    outcome=ReceiptOutcome.FAILED,
                    error_code=action.error_code or "PDD_SEND_REJECTED",
                    trigger_may_have_occurred=False,
                    customer_message_sent=False,
                    confirmed_at=self._clock().astimezone(UTC),
                )

            deadline = time.monotonic() + self._timeout
            while time.monotonic() < deadline:
                self._sleep(self._poll)
                try:
                    current = self._observer.capture()
                except Exception:
                    continue
                if (
                    current.store_id != expected_store_id
                    or current.conversation_id != expected_conversation_id
                    or current.customer_reference != expected_customer_reference
                ):
                    return self._unknown("PDD_SEND_TARGET_CHANGED_AFTER_TRIGGER")
                for item in current.visible_history:
                    if (
                        item.external_message_id not in before_ids
                        and item.sender == "operator"
                        and item.content == content
                    ):
                        return PDDWorkspaceSendResult(
                            state=PDDWorkspaceSendState.CONFIRMED,
                            outcome=ReceiptOutcome.SUCCESS,
                            external_message_id=item.external_message_id,
                            trigger_may_have_occurred=True,
                            customer_message_sent=True,
                            confirmed_at=self._clock().astimezone(UTC),
                        )
            return self._unknown("PDD_SEND_CONFIRMATION_TIMEOUT_UNKNOWN")

    @staticmethod
    def _assert_exact_target(
        snapshot: PDDWorkspaceSnapshot,
        *,
        expected_store_id: str,
        expected_conversation_id: str,
        expected_customer_reference: str,
        expected_customer_message_id: str,
    ) -> None:
        if snapshot.store_id != expected_store_id:
            raise PDDWorkspaceSendError(
                "current PDD store does not match the approved reply",
                error_code="PDD_SEND_STORE_MISMATCH",
            )
        if snapshot.conversation_id != expected_conversation_id:
            raise PDDWorkspaceSendError(
                "current PDD conversation does not match the approved reply",
                error_code="PDD_SEND_CONVERSATION_MISMATCH",
            )
        if snapshot.customer_reference != expected_customer_reference:
            raise PDDWorkspaceSendError(
                "current PDD customer does not match the approved reply",
                error_code="PDD_SEND_CUSTOMER_MISMATCH",
            )
        if not any(
            item.external_message_id == expected_customer_message_id
            and item.sender == "customer"
            for item in snapshot.visible_history
        ):
            raise PDDWorkspaceSendError(
                "approved customer message is no longer visible in the target conversation",
                error_code="PDD_SEND_MESSAGE_TARGET_MISSING",
            )

    def _assert_probe(
        self,
        probe: PDDWorkspaceSendProbe,
        snapshot: PDDWorkspaceSnapshot,
    ) -> None:
        try:
            self.contract.selector_contract.assert_runtime_evidence(
                page_fingerprint=probe.page_fingerprint,
                environment=self.contract.runtime_environment,
                now=self._clock().astimezone(UTC),
                capability=SelectorCapability.SEND_MESSAGE,
            )
        except SelectorContractDrift as exc:
            raise PDDWorkspaceSendError(
                "PDD send selector evidence is stale or does not match the page",
                error_code="PDD_SEND_SELECTOR_EVIDENCE_INVALID",
            ) from exc
        if (
            probe.page_url != self.contract.page_url
            or probe.input_count != 1
            or probe.send_button_count != 1
            or probe.send_button_text != self.contract.send_button_text
        ):
            raise PDDWorkspaceSendError(
                "verified PDD send selectors no longer match",
                error_code="PDD_SEND_SELECTOR_MISMATCH",
            )
        if probe.input_text_length != 0:
            raise PDDWorkspaceSendError(
                "PDD reply box contains unsent operator text",
                error_code="PDD_SEND_INPUT_NOT_EMPTY",
            )
        expected = "pdd-conversation:" + hashlib.sha256(
            f"{snapshot.store_id}\0{probe.current_uid}".encode("utf-8")
        ).hexdigest()
        if expected != snapshot.conversation_id:
            raise PDDWorkspaceSendError(
                "PDD conversation changed before the controlled send",
                error_code="PDD_SEND_CONVERSATION_CHANGED",
            )

    def _error_result(self, exc: PDDWorkspaceSendError) -> PDDWorkspaceSendResult:
        if exc.trigger_may_have_occurred:
            return self._unknown(exc.error_code)
        return PDDWorkspaceSendResult(
            state=PDDWorkspaceSendState.REJECTED,
            outcome=ReceiptOutcome.FAILED,
            error_code=exc.error_code,
            trigger_may_have_occurred=False,
            customer_message_sent=False,
            confirmed_at=self._clock().astimezone(UTC),
        )

    def _unknown(self, error_code: str) -> PDDWorkspaceSendResult:
        return PDDWorkspaceSendResult(
            state=PDDWorkspaceSendState.UNKNOWN,
            outcome=ReceiptOutcome.UNKNOWN,
            error_code=error_code,
            trigger_may_have_occurred=True,
            customer_message_sent=None,
            confirmed_at=self._clock().astimezone(UTC),
        )


class ControlledPDDWorkspaceExecutionAdapter:
    """Lease-fenced adapter for one explicitly approved browser reply."""

    def __init__(
        self,
        *,
        authorization_service: LedgerExecutionAuthorizationService,
        sender: ControlledPDDWorkspaceBrowserSender,
        expected_store_id: str,
        expected_conversation_id: str,
        expected_customer_reference: str,
        expected_customer_message_id: str,
        expected_content: str,
    ) -> None:
        self._authorization = authorization_service
        self._sender = sender
        self._store_id = expected_store_id
        self._conversation_id = expected_conversation_id
        self._customer_reference = expected_customer_reference
        self._message_id = expected_customer_message_id
        self._content = expected_content

    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        del command
        return self._failed("PDD_SEND_EXECUTION_LEASE_REQUIRED")

    def execute_claimed(
        self,
        command: ExecutionCommand,
        context: ClaimedExecutionContext,
    ) -> ExecutionResult:
        if (
            command.execution_id != context.execution_id
            or command.decision_id != context.decision_id
            or command.proposed_content != self._content
        ):
            return self._failed("PDD_SEND_EXECUTION_CONTEXT_MISMATCH")
        try:
            authorized = self._authorization.issue(
                execution_id=context.execution_id,
                worker_id=context.worker_id,
                execution_lease_token=context.lease_token,
            )
            self._authorization.verify(authorized)
            if (
                authorized.authorization.approval_id != context.approval_id
                or authorized.authorization.approved_by != context.approved_by
                or authorized.message.content != self._content
            ):
                return self._failed("PDD_SEND_AUTHORIZATION_MISMATCH")
            result = self._sender.send(
                content=self._content,
                expected_store_id=self._store_id,
                expected_conversation_id=self._conversation_id,
                expected_customer_reference=self._customer_reference,
                expected_customer_message_id=self._message_id,
            )
        except PDDWorkspaceSendError as exc:
            if exc.trigger_may_have_occurred:
                return self._unknown(exc.error_code)
            return self._failed(exc.error_code)
        return ExecutionResult(
            outcome=result.outcome,
            external_reference=result.external_message_id,
            error_code=result.error_code,
            details={
                "mode": "PDD_WORKSPACE_CONTROLLED_SEND",
                "selector_contract_version": self._sender.contract.contract_version,
                "manual_approval": True,
                "automatic_reply": False,
                "automatic_retry_allowed": False,
                "real_channel_called": result.trigger_may_have_occurred,
                "customer_message_sent": result.customer_message_sent,
                "store_id": self._store_id,
                "conversation_id": self._conversation_id,
                "refund_performed": False,
                "order_modified": False,
                "send_state": result.state.value,
            },
        )

    @staticmethod
    def _failed(error_code: str) -> ExecutionResult:
        return ExecutionResult(
            outcome=ReceiptOutcome.FAILED,
            error_code=error_code,
            details={
                "mode": "PDD_WORKSPACE_CONTROLLED_SEND",
                "manual_approval": False,
                "automatic_reply": False,
                "automatic_retry_allowed": False,
                "real_channel_called": False,
                "customer_message_sent": False,
                "refund_performed": False,
                "order_modified": False,
            },
        )

    @staticmethod
    def _unknown(error_code: str) -> ExecutionResult:
        return ExecutionResult(
            outcome=ReceiptOutcome.UNKNOWN,
            error_code=error_code,
            details={
                "mode": "PDD_WORKSPACE_CONTROLLED_SEND",
                "manual_approval": True,
                "automatic_reply": False,
                "automatic_retry_allowed": False,
                "real_channel_called": True,
                "customer_message_sent": False,
                "refund_performed": False,
                "order_modified": False,
            },
        )


__all__ = [
    "ControlledPDDWorkspaceBrowserSender",
    "ControlledPDDWorkspaceExecutionAdapter",
    "PDDWorkspaceActionPort",
    "PDDWorkspaceActionResult",
    "PDDWorkspaceOutboundSelectorContract",
    "PDDWorkspaceSendError",
    "PDDWorkspaceSendProbe",
    "PDDWorkspaceSendResult",
    "PDDWorkspaceSendState",
    "WebSocketPDDWorkspaceActionPort",
]
