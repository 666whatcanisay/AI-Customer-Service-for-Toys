from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import websocket
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from channel_engine.channel import ExecutionBoundaryDenied, LedgerExecutionAuthorizationService
from channel_engine.customer_assistant import (
    BufferedCustomerMessage,
    ContextPageState,
    ConversationHistoryEntry,
    HumanSendConfirmation,
    PageContext,
    ProductContext,
    SQLiteConversationBuffer,
    TransactionContext,
)
from channel_engine.execution import (
    AdapterIdempotencyConflict,
    AdapterOutcomeUnknown,
    ClaimedExecutionContext,
    ExecutionCommand,
    ExecutionResult,
)
from channel_engine.models import ReceiptOutcome
from channel_engine.pdd_adapter import PDDCapturedMessage, PDDPrivacyFilter, PDDPrivacyFilteredMessage

from .pdd_login import PDDCDPPageTarget


SYNTHETIC_PDD_CONTRACT_VERSION = "synthetic-pdd-contract.v1"
SYNTHETIC_PDD_URL = "http://127.0.0.1:8431/"


class SyntheticPDDModel(BaseModel):
    # Browser contracts arrive as ordinary JSON (ISO timestamps and arrays).
    # Pydantic still enforces every field/literal while decoding those JSON shapes.
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class SyntheticPDDStore(SyntheticPDDModel):
    platform: Literal["PDD"] = "PDD"
    store_id: str = Field(alias="storeId", pattern=r"^SIM-STORE-[A-Z0-9-]+$")
    store_name: str = Field(alias="storeName", min_length=1, max_length=128)


class SyntheticPDDConversation(SyntheticPDDModel):
    conversation_id: str = Field(alias="conversationId", pattern=r"^SIM-CONV-[A-Z0-9-]+$")
    customer_reference: str = Field(alias="customerReference", pattern=r"^sim-customer-[a-z0-9-]+$")
    customer_label: str = Field(alias="customerLabel", min_length=1, max_length=128)


class SyntheticPDDProduct(SyntheticPDDModel):
    product_id: str = Field(alias="productId", pattern=r"^SIM-PRODUCT-[A-Z0-9-]+$")
    product_name: str = Field(alias="productName", min_length=1, max_length=512)
    attributes: dict[str, str] = Field(default_factory=dict)


class SyntheticPDDSKU(SyntheticPDDModel):
    sku_id: str = Field(alias="skuId", pattern=r"^SIM-SKU-[A-Z0-9-]+$")
    sku_name: str = Field(alias="skuName", min_length=1, max_length=512)
    attributes: dict[str, str] = Field(default_factory=dict)


class SyntheticPDDOrder(SyntheticPDDModel):
    order_id: str = Field(alias="orderId", pattern=r"^SIM-ORDER-[A-Z0-9-]+$")
    order_status: str = Field(alias="orderStatus", min_length=1, max_length=128)
    logistics_status: str = Field(alias="logisticsStatus", min_length=1, max_length=128)
    aftersales_status: str = Field(alias="aftersalesStatus", min_length=1, max_length=128)
    payment_data_included: Literal[False] = Field(False, alias="paymentDataIncluded")
    address_data_included: Literal[False] = Field(False, alias="addressDataIncluded")


class SyntheticPDDMessage(SyntheticPDDModel):
    external_message_id: str = Field(alias="externalMessageId", pattern=r"^SIM-MSG-[A-Z0-9-]+$")
    sender: Literal["customer", "operator"]
    content: str = Field(min_length=1, max_length=8_000, repr=False)
    timestamp: AwareDatetime
    sequence: int = Field(ge=1)


class SyntheticPDDContract(SyntheticPDDModel):
    schema_version: Literal["synthetic-pdd-contract.v1"] = Field(alias="schemaVersion")
    environment: Literal["SIMULATOR"] = "SIMULATOR"
    synthetic_only: Literal[True] = Field(alias="syntheticOnly")
    real_platform_connected: Literal[False] = Field(alias="realPlatformConnected")
    external_send_enabled: Literal[False] = Field(alias="externalSendEnabled")
    page_state: Literal["CUSTOMER_SERVICE_READY"] = Field(alias="pageState")
    generated_at: AwareDatetime = Field(alias="generatedAt")
    store: SyntheticPDDStore
    conversation: SyntheticPDDConversation
    product: SyntheticPDDProduct
    sku: SyntheticPDDSKU
    order: SyntheticPDDOrder
    messages: tuple[SyntheticPDDMessage, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def messages_are_ordered_and_unique(self) -> "SyntheticPDDContract":
        identities = [item.external_message_id for item in self.messages]
        if len(identities) != len(set(identities)):
            raise ValueError("synthetic PDD messages must have unique ids")
        if list(self.messages) != sorted(
            self.messages, key=lambda item: (item.sequence, item.timestamp, item.external_message_id)
        ):
            raise ValueError("synthetic PDD messages must be ordered")
        return self


class SyntheticPDDWorkspaceSnapshot(SyntheticPDDModel):
    contract_version: Literal["synthetic-pdd-contract.v1"] = SYNTHETIC_PDD_CONTRACT_VERSION
    browser_id: str
    profile_reference: str
    page_url: Literal["http://127.0.0.1:8431/"] = SYNTHETIC_PDD_URL
    page_state: Literal["CUSTOMER_SERVICE_READY"] = "CUSTOMER_SERVICE_READY"
    store_id: str
    store_name: str
    conversation_id: str
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    customer_label: str
    product: ProductContext
    transaction: TransactionContext
    visible_history: tuple[ConversationHistoryEntry, ...]
    captured_at: AwareDatetime
    synthetic_only: Literal[True] = True
    real_platform_connected: Literal[False] = False
    external_send_enabled: Literal[False] = False

    def public_view(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "browser_id": self.browser_id,
            "profile_reference": self.profile_reference,
            "page_url": self.page_url,
            "page_state": self.page_state,
            "store_id": self.store_id,
            "store_name": self.store_name,
            "conversation_id": self.conversation_id,
            "customer_reference": self.customer_reference,
            "product": self.product.model_dump(mode="json"),
            "transaction": self.transaction.model_dump(mode="json"),
            "visible_message_count": len(self.visible_history),
            "captured_at": self.captured_at.isoformat(),
            "synthetic_only": True,
            "real_platform_connected": False,
            "external_send_enabled": False,
        }


class SyntheticPDDTargetResolver:
    """Resolves only the Agent-owned loopback simulator target."""

    def __init__(self, timeout_seconds: float = 1.0) -> None:
        self._timeout = timeout_seconds
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def resolve(self, profile_path: Path) -> PDDCDPPageTarget:
        try:
            port = int((profile_path / "DevToolsActivePort").read_text(encoding="utf-8").splitlines()[0])
        except (OSError, IndexError, ValueError) as exc:
            raise RuntimeError("synthetic Edge debugging port is unavailable") from exc
        request = urllib.request.Request(f"http://127.0.0.1:{port}/json/list", method="GET")
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                values = json.loads(response.read(1_048_577))
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise RuntimeError("synthetic Edge target list is unavailable") from exc
        matches: list[PDDCDPPageTarget] = []
        for value in values if isinstance(values, list) else []:
            if not isinstance(value, dict) or value.get("type") != "page":
                continue
            page_url = value.get("url")
            websocket_url = value.get("webSocketDebuggerUrl")
            target_id = value.get("id")
            if not all(isinstance(item, str) for item in (page_url, websocket_url, target_id)):
                continue
            if page_url != SYNTHETIC_PDD_URL:
                continue
            parsed_ws = urlsplit(websocket_url)
            if (
                parsed_ws.scheme != "ws"
                or parsed_ws.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed_ws.port != port
                or not parsed_ws.path.startswith("/devtools/page/")
            ):
                raise RuntimeError("synthetic Edge CDP endpoint escaped loopback")
            matches.append(PDDCDPPageTarget(target_id, websocket_url, page_url, "http://127.0.0.1:8431", "/"))
        if len(matches) != 1:
            raise RuntimeError("expected exactly one synthetic PDD page")
        return matches[0]


class SyntheticPDDCDPClient:
    """Narrow simulator-only CDP port. It cannot target a non-loopback page."""

    def __init__(self, timeout_seconds: float = 3.0) -> None:
        self._timeout = timeout_seconds
        self._sequence = 0
        self._lock = threading.RLock()

    def _evaluate(self, target: PDDCDPPageTarget, expression: str) -> object:
        if target.page_url != SYNTHETIC_PDD_URL or target.page_origin != "http://127.0.0.1:8431":
            raise RuntimeError("synthetic CDP action rejected a non-simulator page")
        with self._lock:
            self._sequence += 1
            command_id = self._sequence
        command = json.dumps({
            "id": command_id,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True, "awaitPromise": True, "silent": True},
        }, separators=(",", ":"))
        connection = None
        try:
            connection = websocket.create_connection(
                target.websocket_url, timeout=self._timeout, suppress_origin=True, http_proxy_host=None
            )
            connection.send(command)
            while True:
                raw = connection.recv()
                if not isinstance(raw, str) or len(raw.encode("utf-8")) > 1_048_576:
                    raise RuntimeError("synthetic CDP returned an invalid response")
                response = json.loads(raw)
                if not isinstance(response, dict) or response.get("id") != command_id:
                    continue
                if "error" in response:
                    raise RuntimeError("synthetic CDP rejected the operation")
                result = response.get("result")
                remote = result.get("result") if isinstance(result, dict) else None
                if isinstance(remote, dict) and remote.get("subtype") == "error":
                    raise RuntimeError("synthetic page operation failed")
                return remote.get("value") if isinstance(remote, dict) else None
        except (OSError, ValueError, websocket.WebSocketException) as exc:
            raise RuntimeError("synthetic CDP channel failed") from exc
        finally:
            if connection is not None:
                connection.close()

    def capture_contract(self, target: PDDCDPPageTarget) -> SyntheticPDDContract:
        deadline = time.monotonic() + max(1.0, self._timeout)
        while True:
            value = self._evaluate(
                target,
                "window.__PDD_SIMULATOR__ && window.__PDD_SIMULATOR__.contract()",
            )
            if value is not None:
                return SyntheticPDDContract.model_validate(value)
            if time.monotonic() >= deadline:
                raise RuntimeError("synthetic PDD contract was not ready before timeout")
            time.sleep(0.1)

    def push_customer_message(self, target: PDDCDPPageTarget, content: str, conversation_id: str) -> str:
        expression = (
            "window.__PDD_SIMULATOR__.pushCustomerMessage("
            + json.dumps(content, ensure_ascii=False)
            + ","
            + json.dumps(conversation_id)
            + ").message.id"
        )
        value = self._evaluate(target, expression)
        if not isinstance(value, str) or not value.startswith("SIM-MSG-"):
            raise RuntimeError("synthetic buyer message was not accepted")
        return value

    def submit_reply(
        self,
        target: PDDCDPPageTarget,
        *,
        content: str,
        expected_store_id: str,
        expected_conversation_id: str,
        expected_customer_reference: str,
    ) -> str:
        before = self.capture_contract(target)
        if (
            before.store.store_id != expected_store_id
            or before.conversation.conversation_id != expected_conversation_id
            or _customer_reference(before.store.store_id, before.conversation.conversation_id) != expected_customer_reference
        ):
            raise ExecutionBoundaryDenied("synthetic send target changed before input")
        payload = json.dumps(content, ensure_ascii=False)
        expected_conversation = json.dumps(expected_conversation_id)
        prepare = f"""
(() => {{
 const c=window.__PDD_SIMULATOR__.contract();
 if(c.environment!=='SIMULATOR'||!c.syntheticOnly||c.realPlatformConnected||c.externalSendEnabled) throw new Error('unsafe simulator');
 if(c.conversation.conversationId!=={expected_conversation}) throw new Error('conversation changed');
 const input=document.querySelector('#replyTextarea'); const button=document.querySelector('.reply-footer .send-btn');
 if(!input||!button||input.value) throw new Error('input unavailable');
 input.value={payload}; input.dispatchEvent(new Event('input',{{bubbles:true}})); button.click();
 return !document.querySelector('#confirmLayer').hidden;
}})()
""".strip()
        if self._evaluate(target, prepare) is not True:
            raise ExecutionBoundaryDenied("synthetic confirmation did not open")
        confirm = f"""
(() => {{
 if(document.querySelector('#confirmConversation').textContent!=={expected_conversation}) throw new Error('conversation changed');
 const before=window.__PDD_SIMULATOR__.contract().messages.filter(m=>m.sender==='operator').map(m=>m.externalMessageId);
 document.querySelector('#confirmSend').click();
 const after=window.__PDD_SIMULATOR__.contract().messages.filter(m=>m.sender==='operator');
 const added=after.find(m=>!before.includes(m.externalMessageId)&&m.content==={payload});
 return added ? added.externalMessageId : null;
}})()
""".strip()
        try:
            external_id = self._evaluate(target, confirm)
        except RuntimeError as exc:
            raise AdapterOutcomeUnknown("synthetic confirmation outcome could not be proved") from exc
        if not isinstance(external_id, str):
            raise AdapterOutcomeUnknown("synthetic confirmation produced no provable message")
        return external_id


def _customer_reference(store_id: str, conversation_id: str) -> str:
    material = json.dumps([store_id, conversation_id], ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


class SyntheticPDDAdapter:
    def __init__(
        self,
        *,
        browser_id: str,
        profile_path: str | Path,
        profile_reference: str,
        resolver: SyntheticPDDTargetResolver,
        client: SyntheticPDDCDPClient,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.browser_id = browser_id
        self.profile_path = Path(profile_path).resolve()
        self.profile_reference = profile_reference
        self._resolver = resolver
        self.client = client
        self._clock = clock
        self._privacy = PDDPrivacyFilter()
        self._latest: SyntheticPDDWorkspaceSnapshot | None = None

    @property
    def latest_snapshot(self) -> SyntheticPDDWorkspaceSnapshot | None:
        return self._latest

    def target(self) -> PDDCDPPageTarget:
        return self._resolver.resolve(self.profile_path)

    def capture(self) -> SyntheticPDDWorkspaceSnapshot:
        contract = self.client.capture_contract(self.target())
        now = self._clock().astimezone(UTC)
        customer_reference = _customer_reference(contract.store.store_id, contract.conversation.conversation_id)
        history: list[ConversationHistoryEntry] = []
        for message in contract.messages:
            filtered = self._privacy.apply(PDDCapturedMessage(
                store_id=contract.store.store_id,
                conversation_id=contract.conversation.conversation_id,
                external_message_id=message.external_message_id,
                sender=message.sender,
                content=message.content,
                timestamp=message.timestamp,
                captured_at=now,
            ))
            history.append(ConversationHistoryEntry(
                store_id=contract.store.store_id,
                conversation_id=contract.conversation.conversation_id,
                external_message_id=message.external_message_id,
                sender=message.sender,
                content=filtered.content,
                timestamp=message.timestamp,
                content_digest=filtered.redacted_content_digest,
            ))
        snapshot = SyntheticPDDWorkspaceSnapshot(
            browser_id=self.browser_id,
            profile_reference=self.profile_reference,
            store_id=contract.store.store_id,
            store_name=contract.store.store_name,
            conversation_id=contract.conversation.conversation_id,
            customer_reference=customer_reference,
            customer_label=contract.conversation.customer_label,
            product=ProductContext(
                product_reference=contract.product.product_id,
                product_name=contract.product.product_name,
                sku_reference=contract.sku.sku_id,
                sku_name=contract.sku.sku_name,
                attributes={**contract.product.attributes, **{f"sku_{k}": v for k, v in contract.sku.attributes.items()}},
            ),
            transaction=TransactionContext(
                order_reference=contract.order.order_id,
                order_status=contract.order.order_status,
                logistics_status=contract.order.logistics_status,
                aftersales_status=contract.order.aftersales_status,
            ),
            visible_history=tuple(history),
            captured_at=now,
        )
        self._latest = snapshot
        return snapshot

    def to_inbound(self, snapshot: SyntheticPDDWorkspaceSnapshot, message: ConversationHistoryEntry) -> PDDPrivacyFilteredMessage:
        if message.sender != "customer":
            raise ValueError("only a synthetic customer message can enter the AI pipeline")
        return PDDPrivacyFilteredMessage(
            store_id=snapshot.store_id,
            conversation_id=snapshot.conversation_id,
            external_message_id=message.external_message_id,
            content=message.content,
            timestamp=message.timestamp,
            captured_at=snapshot.captured_at,
            redacted_content_digest=message.content_digest,
        )


class SyntheticPDDContextProvider:
    def __init__(self, adapter: SyntheticPDDAdapter, buffer: SQLiteConversationBuffer) -> None:
        self._adapter = adapter
        self._buffer = buffer

    def _current(self, store_id: str, conversation_id: str) -> SyntheticPDDWorkspaceSnapshot:
        snapshot = self._adapter.latest_snapshot or self._adapter.capture()
        if snapshot.store_id != store_id or snapshot.conversation_id != conversation_id:
            raise ExecutionBoundaryDenied("synthetic context changed before AI generation")
        return snapshot

    def capture_page_context(self, *, store_id: str, conversation_id: str) -> PageContext:
        snapshot = self._current(store_id, conversation_id)
        return PageContext(store_id=store_id, store_name=snapshot.store_name, conversation_id=conversation_id, state=ContextPageState.CUSTOMER_SERVICE, product=snapshot.product, captured_at=snapshot.captured_at)

    def capture_transaction_context(self, *, store_id: str, conversation_id: str) -> TransactionContext:
        return self._current(store_id, conversation_id).transaction

    def load_history(self, *, store_id: str, conversation_id: str, limit: int) -> tuple[BufferedCustomerMessage, ...]:
        return self._buffer.load_history(store_id=store_id, conversation_id=conversation_id, limit=limit)

    def load_visible_history(self, *, store_id: str, conversation_id: str, limit: int) -> tuple[ConversationHistoryEntry, ...]:
        return self._current(store_id, conversation_id).visible_history[-limit:]

    def scopes_for(self, *, store_id: str, conversation_id: str) -> tuple[str, ...]:
        self._current(store_id, conversation_id)
        return ("conversation", "products", "orders")


class SimulatorConfirmationPolicy:
    """The only automatic confirmation policy; immutable production flags remain safe."""

    @staticmethod
    def confirmation(package, snapshot: SyntheticPDDWorkspaceSnapshot) -> HumanSendConfirmation:
        if not (
            snapshot.synthetic_only
            and not snapshot.real_platform_connected
            and not snapshot.external_send_enabled
            and snapshot.store_id.startswith("SIM-STORE-")
            and snapshot.conversation_id.startswith("SIM-CONV-")
        ):
            raise ExecutionBoundaryDenied("simulator confirmation is not allowed outside SIMULATOR")
        return HumanSendConfirmation(
            decision_id=package.decision_id,
            operator_id="simulator-auto-confirmation",
            expected_store_id=package.store_id,
            expected_conversation_id=package.conversation_id,
            expected_customer_reference=package.customer_reference,
            current_store_id=snapshot.store_id,
            current_conversation_id=snapshot.conversation_id,
            current_customer_reference=snapshot.customer_reference,
            confirmation_phrase=f"CONFIRM SEND {package.decision_id}",
            confirmed_at=datetime.now(UTC),
        )


class SyntheticPDDExecutionAdapter:
    def __init__(
        self,
        *,
        authorization_service: LedgerExecutionAuthorizationService,
        adapter: SyntheticPDDAdapter,
        expected_store_id: str,
        expected_conversation_id: str,
        expected_customer_reference: str,
        expected_content: str,
    ) -> None:
        self._authorization = authorization_service
        self._adapter = adapter
        self._store_id = expected_store_id
        self._conversation_id = expected_conversation_id
        self._customer_reference = expected_customer_reference
        self._content = expected_content
        self._lock = threading.RLock()
        self._results: dict[str, tuple[str, ExecutionResult | AdapterOutcomeUnknown]] = {}

    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        del command
        return self._failed("SYNTHETIC_EXECUTION_LEASE_REQUIRED")

    def execute_claimed(self, command: ExecutionCommand, context: ClaimedExecutionContext) -> ExecutionResult:
        fingerprint = hashlib.sha256(json.dumps(command.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self._lock:
            replay = self._results.get(command.idempotency_key)
            if replay is not None:
                if replay[0] != fingerprint:
                    raise AdapterIdempotencyConflict("synthetic send key changed payload")
                if isinstance(replay[1], AdapterOutcomeUnknown):
                    raise replay[1]
                return replay[1]
            if command.execution_id != context.execution_id or command.decision_id != context.decision_id or command.proposed_content != self._content:
                return self._failed("SYNTHETIC_EXECUTION_CONTEXT_MISMATCH")
            try:
                authorized = self._authorization.issue(execution_id=context.execution_id, worker_id=context.worker_id, execution_lease_token=context.lease_token)
                self._authorization.verify(authorized)
                if authorized.authorization.approval_id != context.approval_id or authorized.message.content != self._content:
                    return self._failed("SYNTHETIC_AUTHORIZATION_MISMATCH")
                external_id = self._adapter.client.submit_reply(
                    self._adapter.target(), content=self._content,
                    expected_store_id=self._store_id,
                    expected_conversation_id=self._conversation_id,
                    expected_customer_reference=self._customer_reference,
                )
            except AdapterOutcomeUnknown as exc:
                self._results[command.idempotency_key] = (fingerprint, exc)
                raise
            except (ExecutionBoundaryDenied, RuntimeError, ValueError) as exc:
                result = self._failed("SYNTHETIC_SEND_FAIL_CLOSED", reason=type(exc).__name__)
                self._results[command.idempotency_key] = (fingerprint, result)
                return result
            result = ExecutionResult(
                outcome=ReceiptOutcome.SUCCESS,
                external_reference=external_id,
                details={
                    "mode": "SYNTHETIC_PDD",
                    "contract_version": SYNTHETIC_PDD_CONTRACT_VERSION,
                    "simulation": True,
                    "simulator_auto_confirmation": True,
                    "simulator_message_appended": True,
                    "manual_approval_required": True,
                    "auto_reply_enabled": False,
                    "real_send_enabled": False,
                    "real_channel_called": False,
                    "customer_message_sent": False,
                    "external_side_effect": False,
                    "automatic_retry_allowed": False,
                    "store_id": self._store_id,
                    "conversation_id": self._conversation_id,
                    "refund_performed": False,
                    "order_modified": False,
                },
            )
            self._results[command.idempotency_key] = (fingerprint, result)
            return result

    @staticmethod
    def _failed(error_code: str, *, reason: str | None = None) -> ExecutionResult:
        return ExecutionResult(
            outcome=ReceiptOutcome.FAILED,
            error_code=error_code,
            details={
                "mode": "SYNTHETIC_PDD",
                "simulation": True,
                "reason": reason,
                "simulator_message_appended": False,
                "manual_approval_required": True,
                "auto_reply_enabled": False,
                "real_send_enabled": False,
                "real_channel_called": False,
                "customer_message_sent": False,
                "external_side_effect": False,
                "automatic_retry_allowed": False,
            },
        )


def simulator_workspace_feed(snapshot: SyntheticPDDWorkspaceSnapshot, package=None, execution=None) -> dict[str, object]:
    reply = None
    if package is not None:
        customer_messages = [item for item in snapshot.visible_history if item.sender == "customer"]
        reply = {
            "conversationId": package.conversation_id,
            "messageId": (
                customer_messages[-1].external_message_id
                if customer_messages
                else package.turn_id
            ),
            "answer": package.reply_content,
            "requestId": package.request_id,
            "decisionId": package.decision_id,
            "action": "CONTROLLED_ANSWER" if package.action == "SUGGEST_REPLY" else "REFUSE",
            "riskLevel": package.risk_level.value,
            "citations": [{"file": item.title, "summary": item.reference} for item in package.citations],
            "warnings": ["SIMULATOR_ONLY", "REAL_SEND_DISABLED"],
            "requiredFields": [],
            "state": "COMPLETED" if execution and execution.outcome == "SUCCESS" else package.state,
        }
    return {
        "schemaVersion": "channel-agent-workspace-feed.v1",
        "updatedAt": datetime.now(UTC).isoformat(),
        "safety": {
            # Frozen Desktop feed safety fields describe real-channel effects.
            # Synthetic execution evidence is kept in the separate simulation block.
            "readOnly": True,
            "simulatorOnly": True,
            "manualApprovalRequired": True,
            "simulatorAutoConfirmation": True,
            "autoReply": False,
            "realSend": False,
            "realPlatformConnected": False,
            "browserWriteOperations": 0,
            "executionCount": 0,
            "receiptCount": 0,
            "sendCount": 0,
        },
        "simulation": {
            "environment": "SIMULATOR",
            "contractVersion": SYNTHETIC_PDD_CONTRACT_VERSION,
            "executionCount": 1 if execution else 0,
            "receiptCount": 1 if execution and execution.receipt_id else 0,
            "syntheticSendCount": 1 if execution and execution.outcome == "SUCCESS" else 0,
            "customerMessageSent": False,
            "externalSideEffect": False,
        },
        "storeContext": {"storeId": snapshot.store_id, "storeName": snapshot.store_name},
        "productContext": {
            "productReference": snapshot.product.product_reference,
            "productName": snapshot.product.product_name,
            "skuReference": snapshot.product.sku_reference,
            "skuName": snapshot.product.sku_name,
            "applicableAge": snapshot.product.attributes.get("applicable_age", ""),
        },
        "transactionContext": snapshot.transaction.model_dump(mode="json"),
        "conversations": [{
            "conversationId": snapshot.conversation_id,
            "customerLabel": snapshot.customer_label,
            "unreadCount": 0,
            "source": "SYNTHETIC_PDD_ADAPTER",
            "messages": [{
                "messageId": item.external_message_id,
                "conversationId": snapshot.conversation_id,
                "customerLabel": snapshot.customer_label if item.sender == "customer" else "仿真客服",
                "content": item.content,
                "receivedAt": item.timestamp.isoformat(),
                "source": "SYNTHETIC_PDD_ADAPTER",
                "senderRole": "CUSTOMER" if item.sender == "customer" else "AGENT",
            } for item in snapshot.visible_history],
        }],
        "reply": reply,
    }


__all__ = [
    "SYNTHETIC_PDD_CONTRACT_VERSION", "SYNTHETIC_PDD_URL",
    "SyntheticPDDAdapter", "SyntheticPDDCDPClient", "SyntheticPDDContextProvider",
    "SyntheticPDDContract", "SyntheticPDDExecutionAdapter", "SyntheticPDDTargetResolver",
    "SyntheticPDDWorkspaceSnapshot", "SimulatorConfirmationPolicy", "simulator_workspace_feed",
]
