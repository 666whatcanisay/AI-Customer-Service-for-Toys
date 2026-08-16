from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from channel_agent.pdd_login import PDDCDPPageTarget
from channel_agent.pdd_workspace import (
    ExistingPDDWorkspaceObserver,
    FixedReadOnlyPDDWorkspaceEvaluator,
    LivePDDContextProvider,
    PDDWorkspaceSelectorContract,
)
from channel_engine.customer_assistant import (
    CustomerContext,
    SQLiteConversationBuffer,
)

NOW = datetime(2026, 8, 15, tzinfo=UTC)
WORKSPACE_URL = "https://mms.pinduoduo.com/chat-merchant/index.html#/"


class _ExpressionEvaluator:
    def __init__(self) -> None:
        self.expression = ""

    def evaluate(self, _target, expression: str) -> object:
        self.expression = expression
        return {
            "ready_state": "complete",
            "url": WORKSPACE_URL,
            "title": "测试店铺",
            "current_uid": "buyer-1",
            "message_container_present": True,
            "reply_input_present": True,
            "product_id": "982904528556",
            "product_name": "兼容乐高粉白布加迪威龙积木",
            "order_status": "",
            "sku_name": "",
            "messages": [],
        }


class _Resolver:
    def resolve(self, _profile_path: Path) -> PDDCDPPageTarget:
        return PDDCDPPageTarget(
            target_id="target-1",
            websocket_url="ws://127.0.0.1:1/devtools/page/target-1",
            page_url=WORKSPACE_URL,
            page_origin="https://mms.pinduoduo.com",
            page_path="/chat-merchant/index.html",
        )


def _observer(raw_evaluator: _ExpressionEvaluator) -> ExistingPDDWorkspaceObserver:
    evaluator = FixedReadOnlyPDDWorkspaceEvaluator(
        raw_evaluator,
        PDDWorkspaceSelectorContract(),
    )
    return ExistingPDDWorkspaceObserver(
        browser_id="browser-1",
        profile_path=Path("profile"),
        profile_reference="profile-reference",
        resolver=_Resolver(),
        evaluator=evaluator,
        clock=lambda: NOW,
    )


def test_real_product_card_projects_latest_platform_goods_id() -> None:
    raw_evaluator = _ExpressionEvaluator()

    snapshot = _observer(raw_evaluator).capture()

    assert snapshot.product.product_reference == "982904528556"
    assert snapshot.product.product_name == "兼容乐高粉白布加迪威龙积木"
    assert "querySelectorAll(s.product_card)" in raw_evaluator.expression
    assert "goods_info" in raw_evaluator.expression
    assert "data-message-id" in raw_evaluator.expression
    assert "vmMessage.message_id" in raw_evaluator.expression
    assert "stableHash(fallbackMaterial)" in raw_evaluator.expression
    assert "visible-${index}" not in raw_evaluator.expression


def test_invalid_product_id_falls_back_to_non_authoritative_name_digest() -> None:
    raw_evaluator = _ExpressionEvaluator()

    original = raw_evaluator.evaluate

    def evaluate(target, expression: str) -> object:
        value = original(target, expression)
        assert isinstance(value, dict)
        value["product_id"] = "not-a-pdd-product"
        return value

    raw_evaluator.evaluate = evaluate  # type: ignore[method-assign]

    snapshot = _observer(raw_evaluator).capture()

    assert snapshot.product.product_reference is not None
    assert snapshot.product.product_reference.startswith("pdd-product:")


def test_live_context_keeps_page_identity_and_projects_verified_catalog_scope(
    tmp_path: Path,
) -> None:
    raw_evaluator = _ExpressionEvaluator()
    observer = _observer(raw_evaluator)
    snapshot = observer.capture()
    provider = LivePDDContextProvider(
        observer,
        SQLiteConversationBuffer(tmp_path / "buffer.sqlite3", clock=lambda: NOW),
        catalog_tenant_id="c-tenant-6639df2982014226be2f5164ba642a72",
        catalog_store_code="c-store-6639df2982014226",
    )

    page = provider.capture_page_context(
        store_id=snapshot.store_id,
        conversation_id=snapshot.conversation_id,
    )
    context = CustomerContext(
        context_id="customer-context:" + "a" * 64,
        turn_id="assistant-turn:" + "b" * 64,
        store_id=snapshot.store_id,
        conversation_id=snapshot.conversation_id,
        customer_reference=snapshot.customer_reference,
        page=page,
        transaction=snapshot.transaction,
        conversation_history=(),
        current_question="多少颗粒？",
        assembled_at=NOW,
    )

    scope = context.gateway_context()["ai_cs_scope"]
    assert isinstance(scope, dict)
    assert scope == {
        "tenant_id": "c-tenant-6639df2982014226be2f5164ba642a72",
        "platform": "pinduoduo",
        "store_code": "c-store-6639df2982014226",
        "product_id": "982904528556",
        "sku_id": None,
    }
