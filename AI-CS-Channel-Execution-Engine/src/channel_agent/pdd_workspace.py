from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol, runtime_checkable
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.customer_assistant import (
    BufferedCustomerMessage,
    ContextPageState,
    ConversationHistoryEntry,
    PageContext,
    ProductContext,
    SQLiteConversationBuffer,
    TransactionContext,
)
from channel_engine.pdd_adapter import (
    PDDCapturedMessage,
    PDDPrivacyFilter,
    PDDPrivacyFilteredMessage,
)

from .pdd_login import EdgePDDTargetResolver, PDDCDPPageTarget


PDD_WORKSPACE_OBSERVER_VERSION = "1.0"
PDD_WORKSPACE_URL = "https://mms.pinduoduo.com/chat-merchant/index.html#/"
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_MESSAGE_TIMESTAMP = re.compile(r"(?:^|_)(\d{13})(?:$|_)")
_PDD_PRODUCT_ID = re.compile(r"^\d{6,32}$")


class PDDWorkspaceError(RuntimeError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class PDDWorkspaceSafetyError(PDDWorkspaceError):
    pass


class PDDWorkspaceSelectorState(StrEnum):
    DISCOVERY = "DISCOVERY"
    VERIFIED = "VERIFIED"


class PDDWorkspaceModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class PDDWorkspaceSelectorContract(PDDWorkspaceModel):
    version: Literal["pdd-merchant-chat-observe.v1"] = "pdd-merchant-chat-observe.v1"
    state: PDDWorkspaceSelectorState = PDDWorkspaceSelectorState.DISCOVERY
    message_container: Literal["#msgListContainer"] = "#msgListContainer"
    message_item: Literal["li.onemsg"] = "li.onemsg"
    customer_marker: Literal[".buyer-item"] = ".buyer-item"
    operator_marker: Literal[".cs-item"] = ".cs-item"
    content: Literal[".msg-content-box"] = ".msg-content-box"
    conversation_marker: Literal["[currentuid]"] = "[currentuid]"
    product_card: Literal[".commonCard .good-content"] = ".commonCard .good-content"
    order_card: Literal["#right-panel .order-item"] = "#right-panel .order-item"
    reply_input_forbidden_marker: Literal["#replyTextarea"] = "#replyTextarea"
    read_only: Literal[True] = True
    write_capabilities: tuple[()] = ()


class PDDWorkspaceSnapshot(PDDWorkspaceModel):
    observer_version: Literal["1.0"] = PDD_WORKSPACE_OBSERVER_VERSION
    browser_id: str = Field(min_length=1, max_length=128)
    profile_reference: str = Field(min_length=1, max_length=512)
    page_url: Literal["https://mms.pinduoduo.com/chat-merchant/index.html#/"]
    page_state: Literal["CUSTOMER_SERVICE_RUNNING"] = "CUSTOMER_SERVICE_RUNNING"
    selector_version: Literal["pdd-merchant-chat-observe.v1"]
    selector_state: PDDWorkspaceSelectorState
    store_id: str = Field(pattern=r"^pdd-store:[a-f0-9]{64}$")
    store_name: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(pattern=r"^pdd-conversation:[a-f0-9]{64}$")
    customer_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    product: ProductContext
    transaction: TransactionContext
    visible_history: tuple[ConversationHistoryEntry, ...] = Field(max_length=100)
    captured_at: AwareDatetime
    read_only: Literal[True] = True
    browser_write_operations: Literal[0] = 0
    send_operations: Literal[0] = 0
    auto_reply_enabled: Literal[False] = False

    def public_view(self) -> dict[str, object]:
        return {
            "observer_version": self.observer_version,
            "browser_id": self.browser_id,
            "profile_reference": self.profile_reference,
            "page_url": self.page_url,
            "page_state": self.page_state,
            "selector_version": self.selector_version,
            "selector_state": self.selector_state.value,
            "store_id": self.store_id,
            "store_name": self.store_name,
            "conversation_id": self.conversation_id,
            "customer_reference": self.customer_reference,
            "visible_message_count": len(self.visible_history),
            "captured_at": self.captured_at.isoformat(),
            "read_only": True,
            "browser_write_operations": 0,
            "send_operations": 0,
            "auto_reply_enabled": False,
        }


@runtime_checkable
class PDDWorkspaceEvaluator(Protocol):
    def capture(self, target: PDDCDPPageTarget) -> Mapping[str, object]: ...


class FixedReadOnlyPDDWorkspaceEvaluator:
    """Fixed DOM projection. It exposes no navigation, input, click, or send API."""

    _ORDER_STATUSES = (
        "待付款",
        "待发货",
        "已发货",
        "运输中",
        "已签收",
        "交易成功",
        "交易关闭",
        "退款中",
        "退款成功",
        "售后处理中",
    )

    def __init__(self, evaluator, contract: PDDWorkspaceSelectorContract | None = None):
        self._evaluator = evaluator
        self.contract = contract or PDDWorkspaceSelectorContract()
        self.browser_write_operations = 0

    def capture(self, target: PDDCDPPageTarget) -> Mapping[str, object]:
        selectors = self.contract.model_dump(mode="json")
        statuses = json.dumps(self._ORDER_STATUSES, ensure_ascii=False)
        selector_json = json.dumps(selectors, ensure_ascii=False)
        expression = f"""
(() => {{
  const s = {selector_json};
  const statusWords = {statuses};
  const root = document.querySelector(s.message_container);
  const scope = document.querySelector(s.conversation_marker);
  const oneLine = (value, limit) => String(value || '').replace(/\\s+/g, ' ').trim().slice(0, limit);
  const stableHash = (value) => {{
    let first = 0xdeadbeef ^ value.length;
    let second = 0x41c6ce57 ^ value.length;
    for (let index = 0; index < value.length; index += 1) {{
      const code = value.charCodeAt(index);
      first = Math.imul(first ^ code, 2654435761);
      second = Math.imul(second ^ code, 1597334677);
    }}
    first = Math.imul(first ^ (first >>> 16), 2246822507) ^ Math.imul(second ^ (second >>> 13), 3266489909);
    second = Math.imul(second ^ (second >>> 16), 2246822507) ^ Math.imul(first ^ (first >>> 13), 3266489909);
    return (second >>> 0).toString(16).padStart(8, '0') + (first >>> 0).toString(16).padStart(8, '0');
  }};
  const messages = [];
  const fallbackOccurrences = new Map();
  if (root) {{
    const nodes = Array.from(root.querySelectorAll(s.message_item)).slice(-100);
    for (let index = 0; index < nodes.length; index += 1) {{
      const node = nodes[index];
      const customer = Boolean(node.querySelector(s.customer_marker));
      const operator = Boolean(node.querySelector(s.operator_marker));
      if (!customer && !operator) continue;
      const box = node.querySelector(s.content);
      const text = oneLine(box ? box.innerText : '', 8000);
      if (!text) continue;
      const vm = node.__vue__ || {{}};
      const vmMessage = vm.msg || (vm.$props || {{}}).msg || (vm.$data || {{}}).msg || {{}};
      const sourceCandidates = [
        node.id,
        node.getAttribute('data-message-id'),
        node.getAttribute('data-msg-id'),
        node.getAttribute('data-id'),
        node.getAttribute('msgid'),
        vmMessage.message_id,
        vmMessage.msg_id,
        vmMessage.msgId,
        vmMessage.id,
        vmMessage.trace_id,
        vmMessage.sequence
      ];
      let sourceId = '';
      for (const candidate of sourceCandidates) {{
        sourceId = oneLine(candidate, 256);
        if (sourceId) break;
      }}
      if (!sourceId) {{
        const timeNode = node.querySelector('.msg-time,.message-time,.time');
        const fallbackMaterial = `${{customer ? 'customer' : 'operator'}}\\u0000${{oneLine(timeNode ? timeNode.innerText : '', 128)}}\\u0000${{text}}`;
        const occurrence = fallbackOccurrences.get(fallbackMaterial) || 0;
        fallbackOccurrences.set(fallbackMaterial, occurrence + 1);
        sourceId = `fallback-${{stableHash(fallbackMaterial)}}-${{occurrence}}`;
      }}
      messages.push({{
        source_id: sourceId,
        role: customer ? 'customer' : 'operator',
        content: text
      }});
    }}
  }}
  const productCards = Array.from(document.querySelectorAll(s.product_card));
  const product = productCards.length ? productCards[productCards.length - 1] : null;
  const commonCard = product ? product.closest('.commonCard') : null;
  const goodsInfo = commonCard && commonCard.__vue__ && commonCard.__vue__.$props
    ? (((commonCard.__vue__.$props.msg || {{}}).info || {{}}).goods_info || {{}})
    : {{}};
  const productIdCandidate = oneLine(goodsInfo.goods_id, 96);
  const productId = /^\\d{{6,32}}$/.test(productIdCandidate) ? productIdCandidate : '';
  const productName = oneLine(
    goodsInfo.goods_name || (product ? ((product.querySelector('p') || product).innerText) : ''),
    512
  );
  const order = document.querySelector(s.order_card);
  const orderText = order ? String(order.innerText || '') : '';
  const orderStatus = statusWords.find((word) => orderText.includes(word)) || '';
  const skuLine = orderText.split(/\\r?\\n/).map((line) => oneLine(line, 512))
    .find((line) => /^(规格|SKU|商品规格)[:：]/i.test(line)) || '';
  return {{
    ready_state: String(document.readyState || ''),
    url: String(location.href || ''),
    title: oneLine(document.title, 128),
    current_uid: scope ? oneLine(scope.getAttribute('currentuid'), 128) : '',
    message_container_present: Boolean(root),
    reply_input_present: Boolean(document.querySelector(s.reply_input_forbidden_marker)),
    product_id: productId,
    product_name: productName,
    order_status: oneLine(orderStatus, 128),
    sku_name: oneLine(skuLine.replace(/^(规格|SKU|商品规格)[:：]\\s*/i, ''), 512),
    messages
  }};
}})()
""".strip()
        value = self._evaluator.evaluate(target, expression)
        if not isinstance(value, dict):
            raise PDDWorkspaceError(
                "PDD workspace returned an invalid observation",
                error_code="PDD_WORKSPACE_CAPTURE_INVALID",
            )
        return value


class ExistingPDDWorkspaceObserver:
    """Attach to the existing Agent-owned Edge session without owning its lifecycle."""

    read_only = True
    browser_write_operations = 0
    send_operations = 0

    def __init__(
        self,
        *,
        browser_id: str,
        profile_path: str | Path,
        profile_reference: str,
        resolver: EdgePDDTargetResolver,
        evaluator: PDDWorkspaceEvaluator,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        privacy_filter: PDDPrivacyFilter | None = None,
        human_verified_product_attributes: Mapping[str, str] | None = None,
    ) -> None:
        self.browser_id = browser_id
        self.profile_path = Path(profile_path).resolve()
        self.profile_reference = profile_reference
        self._resolver = resolver
        self._evaluator = evaluator
        self._clock = clock
        self._privacy = privacy_filter or PDDPrivacyFilter()
        self._human_verified_product_attributes = dict(
            human_verified_product_attributes or {}
        )
        self._latest: PDDWorkspaceSnapshot | None = None
        self._lock = RLock()

    @property
    def latest_snapshot(self) -> PDDWorkspaceSnapshot | None:
        with self._lock:
            return self._latest

    def capture(self) -> PDDWorkspaceSnapshot:
        with self._lock:
            target = self._resolver.resolve(self.profile_path)
            if target.page_url != PDD_WORKSPACE_URL:
                raise PDDWorkspaceSafetyError(
                    "PDD workspace URL changed",
                    error_code="PDD_WORKSPACE_URL_MISMATCH",
                )
            raw = self._evaluator.capture(target)
            snapshot = self._map(raw)
            self._latest = snapshot
            return snapshot

    def to_inbound(
        self, snapshot: PDDWorkspaceSnapshot, message: ConversationHistoryEntry
    ) -> PDDPrivacyFilteredMessage:
        if message.sender != "customer":
            raise PDDWorkspaceSafetyError(
                "only customer messages may enter the AI pipeline",
                error_code="PDD_WORKSPACE_NON_CUSTOMER_MESSAGE",
            )
        return PDDPrivacyFilteredMessage(
            store_id=snapshot.store_id,
            conversation_id=snapshot.conversation_id,
            external_message_id=message.external_message_id,
            content=message.content,
            timestamp=message.timestamp,
            captured_at=snapshot.captured_at,
            redacted_content_digest=message.content_digest,
        )

    def _map(self, raw: Mapping[str, object]) -> PDDWorkspaceSnapshot:
        now = self._clock().astimezone(UTC)
        if raw.get("ready_state") != "complete" or raw.get("message_container_present") is not True:
            raise PDDWorkspaceSafetyError(
                "PDD customer service workspace is not ready",
                error_code="PDD_WORKSPACE_NOT_READY",
            )
        url = str(raw.get("url") or "")
        parsed = urlsplit(url)
        if (
            f"{parsed.scheme}://{parsed.netloc}" != "https://mms.pinduoduo.com"
            or parsed.path != "/chat-merchant/index.html"
            or parsed.fragment not in {"", "/"}
            or parsed.query
            or parsed.username
            or parsed.password
        ):
            raise PDDWorkspaceSafetyError(
                "PDD customer service page escaped the allowlist",
                error_code="PDD_WORKSPACE_PAGE_NOT_ALLOWLISTED",
            )
        account_label = self._safe_label(raw.get("title"), "PDD商家账号")
        raw_conversation = str(raw.get("current_uid") or "").strip()
        if not raw_conversation:
            raise PDDWorkspaceSafetyError(
                "no PDD conversation is selected",
                error_code="PDD_WORKSPACE_CONVERSATION_NOT_SELECTED",
            )
        store_id = "pdd-store:" + self._digest(f"PDD\0{account_label}")
        conversation_id = "pdd-conversation:" + self._digest(
            f"{store_id}\0{raw_conversation}"
        )
        customer_reference = "sha256:" + self._digest(
            json.dumps([store_id, conversation_id], separators=(",", ":"))
        )
        history: list[ConversationHistoryEntry] = []
        raw_messages = raw.get("messages")
        if not isinstance(raw_messages, list):
            raise PDDWorkspaceError(
                "PDD message projection is invalid",
                error_code="PDD_WORKSPACE_MESSAGES_INVALID",
            )
        for index, item in enumerate(raw_messages):
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role not in {"customer", "operator"}:
                continue
            source_id = str(item.get("source_id") or f"visible-{index}").strip()
            raw_content = str(item.get("content") or "").strip()
            if not raw_content:
                continue
            timestamp = self._message_timestamp(source_id, now)
            external_id = "pdd-message:" + self._digest(
                f"{store_id}\0{conversation_id}\0{source_id}"
            )
            filtered = self._privacy.apply(
                PDDCapturedMessage(
                    store_id=store_id,
                    conversation_id=conversation_id,
                    external_message_id=external_id,
                    sender=role,
                    content=raw_content,
                    timestamp=timestamp,
                    captured_at=now,
                )
            )
            history.append(
                ConversationHistoryEntry(
                    store_id=store_id,
                    conversation_id=conversation_id,
                    external_message_id=external_id,
                    sender=role,
                    content=filtered.content,
                    timestamp=timestamp,
                    content_digest=filtered.redacted_content_digest,
                )
            )
        product_name = self._filtered_business_text(
            raw.get("product_name"), store_id, conversation_id, now
        )
        raw_product_id = self._safe_label(raw.get("product_id"), "")
        product_id = (
            raw_product_id if _PDD_PRODUCT_ID.fullmatch(raw_product_id) else None
        )
        sku_name = self._filtered_business_text(
            raw.get("sku_name"), store_id, conversation_id, now
        )
        order_status = self._safe_label(raw.get("order_status"), "") or None
        return PDDWorkspaceSnapshot(
            browser_id=self.browser_id,
            profile_reference=self.profile_reference,
            page_url=PDD_WORKSPACE_URL,
            selector_version="pdd-merchant-chat-observe.v1",
            selector_state=self._evaluator.contract.state,  # type: ignore[attr-defined]
            store_id=store_id,
            store_name=account_label,
            conversation_id=conversation_id,
            customer_reference=customer_reference,
            product=ProductContext(
                product_reference=(
                    product_id
                    or (
                        "pdd-product:" + self._digest(product_name)
                        if product_name
                        else None
                    )
                ),
                product_name=product_name,
                sku_reference=(
                    "pdd-sku:" + self._digest(f"{product_name}\0{sku_name}")
                    if sku_name
                    else None
                ),
                sku_name=sku_name,
                attributes=self._human_verified_product_attributes,
            ),
            transaction=TransactionContext(order_status=order_status),
            visible_history=tuple(history[-100:]),
            captured_at=now,
        )

    def _filtered_business_text(
        self,
        value: object,
        store_id: str,
        conversation_id: str,
        now: datetime,
    ) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        filtered = self._privacy.apply(
            PDDCapturedMessage(
                store_id=store_id,
                conversation_id=conversation_id,
                external_message_id="context:" + self._digest(text),
                sender="context",
                content=text,
                timestamp=now,
                captured_at=now,
            )
        )
        return filtered.content[:512]

    @staticmethod
    def _message_timestamp(source_id: str, fallback: datetime) -> datetime:
        match = _MESSAGE_TIMESTAMP.search(source_id)
        if match is None:
            return fallback
        try:
            return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return fallback

    @staticmethod
    def _safe_label(value: object, fallback: str) -> str:
        normalized = " ".join(str(value or "").split())[:128]
        if not normalized or _PHONE.search(normalized) or _EMAIL.search(normalized):
            return fallback
        return normalized

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SQLitePDDWorkspaceCheckpoint:
    """Durable cursor: customer content commits before message acknowledgement."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def baseline(self, snapshot: PDDWorkspaceSnapshot) -> int:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            scope = connection.execute(
                "SELECT store_id, conversation_id FROM pdd_workspace_scope WHERE id=1"
            ).fetchone()
            if scope is not None:
                self._assert_scope(scope, snapshot)
                self._validate_known(connection, snapshot)
                connection.commit()
                return 0
            connection.execute(
                "INSERT INTO pdd_workspace_scope(id, store_id, conversation_id, baseline_at) VALUES(1,?,?,?)",
                (snapshot.store_id, snapshot.conversation_id, snapshot.captured_at.isoformat()),
            )
            self._insert_messages(connection, snapshot.visible_history)
            connection.commit()
            return len(snapshot.visible_history)

    def pending_customer_messages(
        self, snapshot: PDDWorkspaceSnapshot
    ) -> tuple[ConversationHistoryEntry, ...]:
        with self._lock, self._connect() as connection:
            scope = connection.execute(
                "SELECT store_id, conversation_id FROM pdd_workspace_scope WHERE id=1"
            ).fetchone()
            if scope is None:
                raise PDDWorkspaceSafetyError(
                    "PDD observer baseline has not been created",
                    error_code="PDD_WORKSPACE_BASELINE_REQUIRED",
                )
            self._assert_scope(scope, snapshot)
            self._validate_known(connection, snapshot)
            known = {
                row[0]
                for row in connection.execute(
                    "SELECT external_message_id FROM pdd_workspace_messages"
                ).fetchall()
            }
            operator_only = tuple(
                item
                for item in snapshot.visible_history
                if item.external_message_id not in known and item.sender == "operator"
            )
            self._insert_messages(connection, operator_only)
            return tuple(
                item
                for item in snapshot.visible_history
                if item.external_message_id not in known and item.sender == "customer"
            )

    def acknowledge(
        self,
        snapshot: PDDWorkspaceSnapshot,
        messages: tuple[ConversationHistoryEntry, ...],
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            scope = connection.execute(
                "SELECT store_id, conversation_id FROM pdd_workspace_scope WHERE id=1"
            ).fetchone()
            if scope is None:
                connection.rollback()
                raise PDDWorkspaceSafetyError(
                    "PDD observer baseline disappeared",
                    error_code="PDD_WORKSPACE_BASELINE_REQUIRED",
                )
            self._assert_scope(scope, snapshot)
            self._insert_messages(connection, messages)
            connection.commit()

    def status(self) -> dict[str, object]:
        with self._connect() as connection:
            scope = connection.execute(
                "SELECT store_id, conversation_id, baseline_at FROM pdd_workspace_scope WHERE id=1"
            ).fetchone()
            count = connection.execute(
                "SELECT COUNT(*) FROM pdd_workspace_messages"
            ).fetchone()[0]
        return {
            "baseline_ready": scope is not None,
            "store_id": scope[0] if scope else None,
            "conversation_id": scope[1] if scope else None,
            "baseline_at": scope[2] if scope else None,
            "acknowledged_message_count": int(count),
            "contains_customer_content": False,
        }

    @staticmethod
    def _assert_scope(scope: tuple[str, str], snapshot: PDDWorkspaceSnapshot) -> None:
        if tuple(scope) != (snapshot.store_id, snapshot.conversation_id):
            raise PDDWorkspaceSafetyError(
                "selected PDD conversation changed after baseline",
                error_code="PDD_WORKSPACE_CONVERSATION_CHANGED",
            )

    @staticmethod
    def _validate_known(
        connection: sqlite3.Connection, snapshot: PDDWorkspaceSnapshot
    ) -> None:
        known = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT external_message_id, content_digest FROM pdd_workspace_messages"
            ).fetchall()
        }
        for message in snapshot.visible_history:
            digest = known.get(message.external_message_id)
            if digest is not None and digest != message.content_digest:
                raise PDDWorkspaceSafetyError(
                    "PDD message identity changed content",
                    error_code="PDD_WORKSPACE_MESSAGE_ID_CONFLICT",
                )

    @staticmethod
    def _insert_messages(
        connection: sqlite3.Connection,
        messages: tuple[ConversationHistoryEntry, ...],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO pdd_workspace_messages(
                external_message_id, content_digest, sender, message_timestamp
            ) VALUES(?,?,?,?)
            ON CONFLICT(external_message_id) DO NOTHING
            """,
            [
                (
                    item.external_message_id,
                    item.content_digest,
                    item.sender,
                    item.timestamp.isoformat(),
                )
                for item in messages
            ],
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pdd_workspace_scope (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    store_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    baseline_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pdd_workspace_messages (
                    external_message_id TEXT PRIMARY KEY,
                    content_digest TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    message_timestamp TEXT NOT NULL
                );
                """
            )


class LivePDDContextProvider:
    """Context ports backed by the latest privacy-filtered live snapshot."""

    def __init__(
        self,
        observer: ExistingPDDWorkspaceObserver,
        buffer: SQLiteConversationBuffer,
        *,
        catalog_tenant_id: str = "CHANNEL-AGENT-PILOT",
        catalog_store_code: str | None = None,
    ) -> None:
        self._observer = observer
        self._buffer = buffer
        self._catalog_tenant_id = catalog_tenant_id
        self._catalog_store_code = catalog_store_code

    def _current(self, store_id: str, conversation_id: str) -> PDDWorkspaceSnapshot:
        snapshot = self._observer.latest_snapshot or self._observer.capture()
        if snapshot.store_id != store_id or snapshot.conversation_id != conversation_id:
            raise PDDWorkspaceSafetyError(
                "live context no longer matches the buffered conversation",
                error_code="PDD_WORKSPACE_CONTEXT_CHANGED",
            )
        return snapshot

    def capture_page_context(self, *, store_id: str, conversation_id: str) -> PageContext:
        snapshot = self._current(store_id, conversation_id)
        return PageContext(
            store_id=store_id,
            catalog_tenant_id=self._catalog_tenant_id,
            catalog_store_code=self._catalog_store_code,
            store_name=snapshot.store_name,
            conversation_id=conversation_id,
            state=ContextPageState.CUSTOMER_SERVICE,
            product=snapshot.product,
            captured_at=snapshot.captured_at,
        )

    def capture_transaction_context(
        self, *, store_id: str, conversation_id: str
    ) -> TransactionContext:
        return self._current(store_id, conversation_id).transaction

    def load_history(
        self, *, store_id: str, conversation_id: str, limit: int
    ) -> tuple[BufferedCustomerMessage, ...]:
        return self._buffer.load_history(
            store_id=store_id, conversation_id=conversation_id, limit=limit
        )

    def load_visible_history(
        self, *, store_id: str, conversation_id: str, limit: int
    ) -> tuple[ConversationHistoryEntry, ...]:
        return self._current(store_id, conversation_id).visible_history[-limit:]

    def scopes_for(self, *, store_id: str, conversation_id: str) -> tuple[str, ...]:
        snapshot = self._current(store_id, conversation_id)
        scopes = ["conversation"]
        if snapshot.product.product_name:
            scopes.append("products")
        if snapshot.transaction.order_status:
            scopes.append("orders")
        return tuple(scopes)


__all__ = [
    "ExistingPDDWorkspaceObserver",
    "FixedReadOnlyPDDWorkspaceEvaluator",
    "LivePDDContextProvider",
    "PDDWorkspaceError",
    "PDDWorkspaceSafetyError",
    "PDDWorkspaceSelectorContract",
    "PDDWorkspaceSelectorState",
    "PDDWorkspaceSnapshot",
    "PDD_WORKSPACE_OBSERVER_VERSION",
    "PDD_WORKSPACE_URL",
    "SQLitePDDWorkspaceCheckpoint",
]
