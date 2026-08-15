from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from channel_agent.assistant_bridge import (
    ApprovedReplyBridgeError,
    ApprovedReplyService,
    knowledge_scope_sha256,
)
from channel_agent.controlled_auto_runtime import (
    ControlledAutoDecisionLedger,
    ControlledAutoRuntimeStateStore,
    ControlledAutoRuntimeStateV1,
    evaluate_send_safety,
)
from channel_agent.controlled_send_grant import (
    ControlledAutoPolicyGrantV1,
    ControlledPilotSendWindowStore,
    ControlledPilotSendWindowV1,
    ControlledSendGrantError,
)

NOW = datetime(2026, 8, 15, 2, 0, tzinfo=UTC)
AI_CS_STORE = "c-store-6639df2982014226"
PLATFORM_STORE = "328616090"
WORKSPACE_STORE = "pdd-store:" + "a" * 64
BUYER = "sha256:" + "b" * 64
EVIDENCE = "e" * 64
QUESTION = "这款积木有多少颗粒？"
REPLY = "这款积木共有500颗粒。"


def _window() -> ControlledPilotSendWindowV1:
    return ControlledPilotSendWindowV1.issue(
        mode="AUTO_POLICY",
        store_id=WORKSPACE_STORE,
        ai_cs_store_id=AI_CS_STORE,
        platform_store_id=PLATFORM_STORE,
        test_buyer_hash=BUYER,
        conversation_id="conversation-1",
        question=QUESTION,
        approved_reply=REPLY,
        product_id="product-1",
        sku_id=None,
        policy_revision=4,
        whitelist_revision="single-store-v1",
        knowledge_scope_sha256="c" * 64,
        reply_evidence_bundle_sha256=EVIDENCE,
        authorization_basis="QUALITY_GATED_LOW_RISK",
        deployment_scope="PRODUCTION_AUTO",
        issued_at=NOW,
    )


def _grant(window: ControlledPilotSendWindowV1) -> ControlledAutoPolicyGrantV1:
    return ControlledAutoPolicyGrantV1.issue(
        pilot_window_id=window.window_id,
        store_id=WORKSPACE_STORE,
        ai_cs_store_id=AI_CS_STORE,
        platform_store_id=PLATFORM_STORE,
        test_buyer_hash=BUYER,
        conversation_id="conversation-1",
        customer_message_id="message-1",
        decision_id="decision-1",
        question=QUESTION,
        reply_content=REPLY,
        approved_reply_sha256=None,
        product_id="product-1",
        sku_id=None,
        policy_revision=4,
        whitelist_revision="single-store-v1",
        knowledge_scope_sha256="c" * 64,
        reply_evidence_bundle_sha256=EVIDENCE,
        authorization_basis="QUALITY_GATED_LOW_RISK",
        deployment_scope="PRODUCTION_AUTO",
        nonce="d" * 64,
        issued_at=NOW,
    )


def _package(*, action: str = "DIRECT_ANSWER", evidence: str | None = EVIDENCE):
    return SimpleNamespace(
        reply_content=REPLY,
        customer_question=QUESTION,
        gateway_version="gateway-v1",
        citations=(),
        evidence_bundle_sha256=evidence,
        quality_gate_status="PASS",
        required_fields=(),
        action="SUGGEST_REPLY",
        ai_cs_action=action,
        risk_level=SimpleNamespace(value="LOW"),
        state="WAITING_APPROVAL",
    )


def test_quality_gated_grant_binds_double_store_evidence_nonce_and_one_reply() -> None:
    window = _window()
    grant = _grant(window)

    assert grant.test_only is False
    assert grant.authorization_basis == "QUALITY_GATED_LOW_RISK"
    assert grant.ai_cs_store_id == AI_CS_STORE
    assert grant.platform_store_id == PLATFORM_STORE
    assert grant.reply_evidence_bundle_sha256 == EVIDENCE
    grant.assert_target(
        store_id=WORKSPACE_STORE,
        test_buyer_hash=BUYER,
        conversation_id="conversation-1",
        customer_message_id="message-1",
        decision_id="decision-1",
        reply_content=REPLY,
        now=NOW + timedelta(seconds=1),
    )
    with pytest.raises(ControlledSendGrantError):
        grant.assert_target(
            store_id=WORKSPACE_STORE,
            test_buyer_hash=BUYER,
            conversation_id="conversation-1",
            customer_message_id="message-1",
            decision_id="decision-1",
            reply_content=REPLY + "。",
            now=NOW + timedelta(seconds=1),
        )


def test_quality_gated_grant_rejects_missing_evidence_or_double_store() -> None:
    window = _window()
    with pytest.raises(ValidationError, match="double Store identity"):
        ControlledAutoPolicyGrantV1.issue(
            pilot_window_id=window.window_id,
            store_id=WORKSPACE_STORE,
            test_buyer_hash=BUYER,
            conversation_id="conversation-1",
            customer_message_id="message-1",
            decision_id="decision-1",
            question=QUESTION,
            reply_content=REPLY,
            approved_reply_sha256=None,
            product_id="product-1",
            sku_id=None,
            policy_revision=4,
            whitelist_revision="single-store-v1",
            knowledge_scope_sha256="c" * 64,
            authorization_basis="QUALITY_GATED_LOW_RISK",
            deployment_scope="PRODUCTION_AUTO",
            issued_at=NOW,
        )

    with pytest.raises(ValidationError, match="product"):
        ControlledAutoPolicyGrantV1.issue(
            pilot_window_id=window.window_id,
            store_id=WORKSPACE_STORE,
            ai_cs_store_id=AI_CS_STORE,
            platform_store_id=PLATFORM_STORE,
            test_buyer_hash=BUYER,
            conversation_id="conversation-1",
            customer_message_id="message-1",
            decision_id="decision-1",
            question=QUESTION,
            reply_content=REPLY,
            approved_reply_sha256=None,
            product_id=None,
            sku_id=None,
            policy_revision=4,
            whitelist_revision="single-store-v1",
            knowledge_scope_sha256="c" * 64,
            reply_evidence_bundle_sha256=EVIDENCE,
            authorization_basis="QUALITY_GATED_LOW_RISK",
            deployment_scope="PRODUCTION_AUTO",
            issued_at=NOW,
        )


def test_dynamic_window_rejects_evidence_or_store_drift(tmp_path) -> None:
    store = ControlledPilotSendWindowStore(tmp_path / "windows.sqlite3")
    window = _window()
    grant = _grant(window)
    store.arm(window, now=NOW)
    assert store.assert_authorized(
        grant,
        question=QUESTION,
        product_id="product-1",
        sku_id=None,
        knowledge_scope_sha256="c" * 64,
        reply_evidence_bundle_sha256=EVIDENCE,
        now=NOW + timedelta(seconds=1),
    ) == window
    with pytest.raises(ControlledSendGrantError):
        store.assert_authorized(
            grant.model_copy(update={"platform_store_id": "wrong"}),
            question=QUESTION,
            product_id="product-1",
            sku_id=None,
            knowledge_scope_sha256="c" * 64,
            reply_evidence_bundle_sha256=EVIDENCE,
            now=NOW + timedelta(seconds=1),
        )


def test_bridge_dynamic_quality_gate_requires_current_evidence_and_direct_low() -> None:
    service = object.__new__(ApprovedReplyService)
    package = _package()
    grant = _grant(_window()).model_copy(
        update={"knowledge_scope_sha256": knowledge_scope_sha256(package)}
    )
    service._assert_auto_policy_package(
        feed_reply={
            "qualityStatus": "PASS",
            "policyMode": "AUTO_LOW_RISK",
            "action": "DIRECT_ANSWER",
        },
        package=package,
        grant=grant,
    )
    with pytest.raises(ApprovedReplyBridgeError) as captured:
        service._assert_auto_policy_package(
            feed_reply={
                "qualityStatus": "PASS",
                "policyMode": "AUTO_LOW_RISK",
                "action": "DIRECT_ANSWER",
            },
            package=_package(action="REQUIRE_LOOKUP"),
            grant=grant,
        )
    assert captured.value.error_code == "AUTO_POLICY_QUALITY_GATE_BLOCKED"


def test_bridge_requires_feed_send_state_to_match_grant_deployment() -> None:
    production_grant = _grant(_window())
    ApprovedReplyService._assert_feed_send_state(
        feed={"safety": {"realSend": True, "autoReply": True}},
        grant=production_grant,
    )
    with pytest.raises(ApprovedReplyBridgeError) as captured:
        ApprovedReplyService._assert_feed_send_state(
            feed={"safety": {"realSend": False, "autoReply": False}},
            grant=production_grant,
        )
    assert captured.value.error_code == "PDD_SEND_FEED_RUNTIME_MODE_MISMATCH"

    pilot_grant = production_grant.model_copy(update={"deployment_scope": "PILOT"})
    ApprovedReplyService._assert_feed_send_state(
        feed={"safety": {"realSend": False, "autoReply": False}},
        grant=pilot_grant,
    )


def test_runtime_mode_governance_and_kill_switch_are_mode_aware(tmp_path) -> None:
    store = ControlledAutoRuntimeStateStore(tmp_path / "runtime.sqlite3")
    pilot = store.set_pilot(
        operator="tester",
        reason="pilot",
        controlled_pilot_send_enabled=True,
        kill_switch_enabled=False,
    )
    assert evaluate_send_safety(pilot).status == "PASS"

    production = store.activate_production_auto(
        ai_cs_store_id=AI_CS_STORE,
        platform_store_id=PLATFORM_STORE,
        policy_revision=4,
        whitelist_revision="single-store-v1",
        operator="tester",
        reason="explicit production activation",
    )
    assert evaluate_send_safety(
        production,
        observed_ai_cs_store_id=AI_CS_STORE,
        observed_platform_store_id=PLATFORM_STORE,
    ).status == "PASS"
    assert evaluate_send_safety(
        production,
        observed_ai_cs_store_id=AI_CS_STORE,
        observed_platform_store_id="wrong",
    ).status == "BLOCKED"
    assert evaluate_send_safety(
        production,
        observed_ai_cs_store_id=AI_CS_STORE,
        observed_platform_store_id=PLATFORM_STORE,
        concrete_send_requested=True,
        concrete_send_has_valid_grant=False,
    ).status == "BLOCKED"

    stopped = store.enable_kill_switch(operator="tester", reason="test stop")
    assert stopped.runtime_mode == "PILOT"
    assert stopped.kill_switch_enabled is True
    assert stopped.production_real_send_enabled is False
    assert stopped.controlled_store_auto_enabled is False


def test_human_pause_retains_verified_scope_for_explicit_resume(tmp_path) -> None:
    store = ControlledAutoRuntimeStateStore(tmp_path / "runtime.sqlite3")
    active = store.activate_production_auto(
        ai_cs_store_id=AI_CS_STORE,
        platform_store_id=PLATFORM_STORE,
        policy_revision=5,
        whitelist_revision="single-store-auto-all-v1",
        operator="tester",
        reason="explicit production activation",
        policy_mode="AUTO_ALL_MESSAGES_V1",
    )

    paused = store.pause_production_auto(
        operator="tester", reason="desktop pause"
    )

    assert active.runtime_mode == "PRODUCTION_AUTO"
    assert paused.runtime_mode == "PILOT"
    assert paused.production_real_send_enabled is False
    assert paused.controlled_store_auto_enabled is False
    assert paused.kill_switch_enabled is True
    assert paused.ai_cs_store_id == AI_CS_STORE
    assert paused.platform_store_id == PLATFORM_STORE
    assert paused.policy_mode == "AUTO_ALL_MESSAGES_V1"


def test_governance_blocks_inconsistent_constructed_modes() -> None:
    pilot_with_production = ControlledAutoRuntimeStateV1.model_construct(
        revision=1,
        runtime_mode="PILOT",
        production_real_send_enabled=True,
        controlled_pilot_send_enabled=False,
        controlled_store_auto_enabled=False,
        ai_cs_store_id=None,
        platform_store_id=None,
        policy_mode="MANUAL_CONFIRM",
        policy_revision=1,
        whitelist_revision="v1",
        kill_switch_enabled=False,
        per_message_grant_enforced=True,
        unique_sender_path_enabled=True,
        unknown_automatic_retry_enabled=False,
        changed_by="test",
        changed_at=NOW,
        reason="test",
    )
    assert evaluate_send_safety(pilot_with_production).status == "BLOCKED"

    production_with_kill = ControlledAutoRuntimeStateV1.model_construct(
        **{
            **pilot_with_production.model_dump(),
            "runtime_mode": "PRODUCTION_AUTO",
            "production_real_send_enabled": True,
            "controlled_store_auto_enabled": True,
            "ai_cs_store_id": AI_CS_STORE,
            "platform_store_id": PLATFORM_STORE,
            "policy_mode": "AUTO_LOW_RISK",
            "kill_switch_enabled": True,
        }
    )
    result = evaluate_send_safety(
        production_with_kill,
        observed_ai_cs_store_id=AI_CS_STORE,
        observed_platform_store_id=PLATFORM_STORE,
    )
    assert result.status == "BLOCKED"
    assert "PRODUCTION_KILL_SWITCH_ENABLED" in result.reason_codes


def test_decision_ledger_never_reclaims_after_success_or_failure(tmp_path) -> None:
    ledger = ControlledAutoDecisionLedger(tmp_path / "decisions.sqlite3")
    assert ledger.claim_once("decision-1", now=NOW) is True
    ledger.finish(
        "decision-1", outcome="SUCCESS", receipt_id="receipt-1", now=NOW
    )
    assert ledger.claim_once("decision-1", now=NOW + timedelta(seconds=1)) is False

    assert ledger.claim_once("decision-2", now=NOW) is True
    ledger.finish("decision-2", outcome="UNKNOWN", receipt_id=None, now=NOW)
    assert ledger.claim_once("decision-2", now=NOW + timedelta(seconds=1)) is False


def test_double_store_name_is_irrelevant_but_ids_must_match() -> None:
    service = object.__new__(ApprovedReplyService)
    service._require_double_store_identity = True
    service._store_identity_provider = lambda: (AI_CS_STORE, PLATFORM_STORE)
    service._auto_runtime = None
    grant = _grant(_window())
    service._assert_double_store_identity(grant)
    service._store_identity_provider = lambda: (AI_CS_STORE, "wrong")
    with pytest.raises(ApprovedReplyBridgeError) as captured:
        service._assert_double_store_identity(grant)
    assert captured.value.error_code == "PDD_SEND_DOUBLE_STORE_IDENTITY_MISMATCH"
