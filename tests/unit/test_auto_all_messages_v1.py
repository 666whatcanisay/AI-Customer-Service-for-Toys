from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from channel_agent.assistant_bridge import ApprovedReplyService, knowledge_scope_sha256
from channel_agent.controlled_auto_runtime import (
    ControlledAutoRuntimeStateStore,
    evaluate_send_safety,
)
from channel_agent.controlled_send_grant import ControlledAutoPolicyGrantV1
from channel_engine.customer_assistant import (
    AICustomerReplyService,
    ContextPageState,
    CustomerContext,
    PageContext,
    ProductContext,
    StoreApprovedAutoFirstResponseGateway,
    TransactionContext,
)
from channel_engine.gateway import (
    CONTRACT_VERSION,
    DecisionRequest,
    DecisionResponse,
    GatewayRiskLevel,
)
from channel_engine.models import DecisionAction

NOW = datetime(2026, 8, 15, 5, 0, tzinfo=UTC)
AI_CS_STORE = "c-store-6639df2982014226"
PLATFORM_STORE = "328616090"
WORKSPACE_STORE = "pdd-store:" + "a" * 64
BUYER = "sha256:" + "b" * 64


class RaisingGateway:
    def decide(self, request: DecisionRequest) -> DecisionResponse:
        del request
        raise TimeoutError("AI-CS unavailable")


class ContextCapturingRaisingGateway:
    def __init__(self) -> None:
        self.requests: list[DecisionRequest] = []

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        self.requests.append(request)
        raise TimeoutError("AI-CS unavailable")


class ControlledAnswerGateway:
    def decide(self, request: DecisionRequest) -> DecisionResponse:
        return DecisionResponse(
            contract_version=CONTRACT_VERSION,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            correlation_id=request.correlation_id,
            decision_id="decision-controlled-answer",
            action=DecisionAction.SUGGEST_REPLY,
            proposed_content="亲，这款约500颗，具体以实际清点为准哦。",
            requires_approval=True,
            risk_level=GatewayRiskLevel.MEDIUM,
            gateway_version="ai-cs-test.v1",
            metadata={
                "ai_cs_action": "CONTROLLED_ANSWER",
                "quality_gate_status": "PASS",
                "reply_evidence_bundle": {"bundle_sha256": "e" * 64},
            },
            decided_at=NOW,
        )


def _request(question: str, *, product_id: str | None = "982904528556") -> DecisionRequest:
    return DecisionRequest(
        contract_version=CONTRACT_VERSION,
        request_id="request-1",
        idempotency_key="idempotency-1",
        correlation_id="correlation-1",
        conversation_id="conversation-1",
        message_id="message-1",
        customer_message=question,
        context={
            "product": {
                "product_reference": product_id,
                "product_name": "粉白布加迪威龙积木" if product_id else None,
            }
        },
        requested_at=NOW,
    )


def test_unavailable_ai_produces_one_governed_price_fallback() -> None:
    gateway = StoreApprovedAutoFirstResponseGateway(
        RaisingGateway(), clock=lambda: NOW
    )

    response = gateway.decide(_request("这个多少钱？"))

    assert response.action is DecisionAction.SUGGEST_REPLY
    assert response.risk_level is GatewayRiskLevel.MEDIUM
    assert response.metadata["ai_cs_action"] == "CONTROLLED_ANSWER"
    assert response.metadata["fixed_reply_rule_id"] == "PRICE_STOCK_LIVE_PAGE"
    assert response.metadata["auto_authorization_basis"] == (
        "STORE_APPROVED_FIXED_REPLY"
    )
    assert len(response.metadata["reply_evidence_bundle"]["bundle_sha256"]) == 64
    assert "以当前商品页面显示为准" in (response.proposed_content or "")


def test_unknown_product_produces_clarifying_first_response() -> None:
    response = StoreApprovedAutoFirstResponseGateway(
        RaisingGateway(), clock=lambda: NOW
    ).decide(_request("这个呢？", product_id=None))

    assert response.metadata["ai_cs_action"] == "ASK_CLARIFY"
    assert response.metadata["required_fields"] == ["product"]
    assert "商品卡" in (response.proposed_content or "")


def test_eligible_medium_answer_is_preserved_as_store_approved_knowledge() -> None:
    response = StoreApprovedAutoFirstResponseGateway(
        ControlledAnswerGateway(), clock=lambda: NOW
    ).decide(_request("有多少颗？"))

    assert response.decision_id == "decision-controlled-answer"
    assert response.risk_level is GatewayRiskLevel.MEDIUM
    assert response.metadata["auto_authorization_basis"] == (
        "STORE_APPROVED_KNOWLEDGE"
    )


def _grant(*, basis: str, product_id: str | None) -> ControlledAutoPolicyGrantV1:
    return ControlledAutoPolicyGrantV1.issue(
        pilot_window_id="controlled-pilot-window:" + "c" * 64,
        store_id=WORKSPACE_STORE,
        ai_cs_store_id=AI_CS_STORE,
        platform_store_id=PLATFORM_STORE,
        test_buyer_hash=BUYER,
        conversation_id="conversation-1",
        customer_message_id="message-1",
        decision_id="decision-1",
        question="这个多少钱？",
        reply_content="亲，价格以当前商品页面显示为准哦。",
        approved_reply_sha256=None,
        product_id=product_id,
        sku_id=None,
        policy_revision=5,
        whitelist_revision="single-store-auto-all-v1",
        knowledge_scope_sha256="d" * 64,
        reply_evidence_bundle_sha256="e" * 64,
        authorization_basis=basis,
        policy_mode="AUTO_ALL_MESSAGES_V1",
        deployment_scope="PRODUCTION_AUTO",
        issued_at=NOW,
    )


def test_fixed_reply_grant_does_not_require_product_but_knowledge_does() -> None:
    fixed = _grant(basis="STORE_APPROVED_FIXED_REPLY", product_id=None)
    assert fixed.test_only is False
    assert fixed.max_attempts == fixed.max_successes == 1

    with pytest.raises(ValidationError, match="requires product"):
        _grant(basis="STORE_APPROVED_KNOWLEDGE", product_id=None)


def test_bridge_accepts_governed_medium_answer_under_auto_all() -> None:
    package = SimpleNamespace(
        reply_content="亲，这款约500颗，具体以实际清点为准哦。",
        customer_question="这款有多少颗？",
        gateway_version="ai-cs-test.v1",
        citations=(),
        evidence_bundle_sha256="e" * 64,
        quality_gate_status="PASS",
        required_fields=(),
        action="SUGGEST_REPLY",
        ai_cs_action="CONTROLLED_ANSWER",
        risk_level=SimpleNamespace(value="MEDIUM"),
        state="WAITING_APPROVAL",
        auto_authorization_basis="STORE_APPROVED_KNOWLEDGE",
    )
    grant = ControlledAutoPolicyGrantV1.issue(
        pilot_window_id="controlled-pilot-window:" + "c" * 64,
        store_id=WORKSPACE_STORE,
        ai_cs_store_id=AI_CS_STORE,
        platform_store_id=PLATFORM_STORE,
        test_buyer_hash=BUYER,
        conversation_id="conversation-1",
        customer_message_id="message-1",
        decision_id="decision-1",
        question=package.customer_question,
        reply_content=package.reply_content,
        approved_reply_sha256=None,
        product_id="982904528556",
        sku_id=None,
        policy_revision=5,
        whitelist_revision="single-store-auto-all-v1",
        knowledge_scope_sha256=knowledge_scope_sha256(package),
        reply_evidence_bundle_sha256="e" * 64,
        authorization_basis="STORE_APPROVED_KNOWLEDGE",
        policy_mode="AUTO_ALL_MESSAGES_V1",
        deployment_scope="PRODUCTION_AUTO",
        issued_at=NOW,
    )

    ApprovedReplyService._assert_auto_policy_package(
        object.__new__(ApprovedReplyService),
        feed_reply={
            "qualityStatus": "PASS",
            "policyMode": "AUTO_ALL_MESSAGES_V1",
            "action": "CONTROLLED_ANSWER",
        },
        package=package,
        grant=grant,
    )


def test_auto_all_runtime_governance_is_mode_consistent(tmp_path) -> None:
    store = ControlledAutoRuntimeStateStore(tmp_path / "auto-runtime.sqlite3")
    state = store.activate_production_auto(
        ai_cs_store_id=AI_CS_STORE,
        platform_store_id=PLATFORM_STORE,
        policy_revision=5,
        whitelist_revision="single-store-auto-all-v1",
        operator="operator-1",
        reason="explicit all-message activation",
        policy_mode="AUTO_ALL_MESSAGES_V1",
    )

    result = evaluate_send_safety(
        state,
        observed_ai_cs_store_id=AI_CS_STORE,
        observed_platform_store_id=PLATFORM_STORE,
    )

    assert state.production_real_send_enabled is True
    assert state.controlled_store_auto_enabled is True
    assert state.policy_mode == "AUTO_ALL_MESSAGES_V1"
    assert result.status == "PASS"


def test_fallback_is_persisted_as_the_core_decision(foundation) -> None:
    context = CustomerContext(
        context_id="customer-context:" + "1" * 64,
        turn_id="assistant-turn:" + "2" * 64,
        store_id="store-1",
        conversation_id="conversation-1",
        customer_reference=BUYER,
        page=PageContext(
            store_id="store-1",
            conversation_id="conversation-1",
            state=ContextPageState.PRODUCT,
            product=ProductContext(
                product_reference="982904528556",
                product_name="粉白布加迪威龙积木",
            ),
            captured_at=NOW,
        ),
        transaction=TransactionContext(),
        conversation_history=(),
        current_question="这个多少钱？",
        knowledge_scopes=("products",),
        assembled_at=NOW,
    )
    gateway = ContextCapturingRaisingGateway()
    service = AICustomerReplyService(
        foundation["uow_factory"],
        gateway,
        clock=lambda: NOW,
        auto_first_response_enabled=True,
    )

    package = service.generate(context)

    assert package.action == "SUGGEST_REPLY"
    assert gateway.requests[0].context["auto_first_response_policy"] == (
        "AUTO_ALL_MESSAGES_V1"
    )
    assert package.state == "WAITING_APPROVAL"
    assert package.auto_authorization_basis == "STORE_APPROVED_FIXED_REPLY"
    with foundation["uow_factory"]() as uow:
        decision = uow.require_repository().get_decision(package.decision_id)
    assert decision is not None
    assert decision.proposed_content == package.reply_content

    recovered = AICustomerReplyService(
        foundation["uow_factory"],
        RaisingGateway(),
        clock=lambda: NOW,
        auto_first_response_enabled=True,
    ).generate(context)
    assert recovered.decision_id == package.decision_id
    assert recovered.reply_content == package.reply_content
    assert recovered.quality_gate_status == "PASS"
    assert recovered.auto_authorization_basis == "STORE_APPROVED_FALLBACK"
    assert "DECISION_METADATA_RECOVERED" in recovered.warnings
