from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from channel_agent.control_v2 import ServiceRequestSigner, ServiceRequestVerifier
from channel_agent.desktop import DesktopAssistantServer
from channel_agent.providers import RecordedReplayProvider, SyntheticPDDProvider
from channel_engine.agent.control_v2 import create_channel_agent_service_v2_router
from channel_engine.agent.node_api import ChannelAgentNodeRegistry
from channel_engine.customer_assistant import ReplyPolicyMode
from channel_engine.gateway import (
    DecisionRequest,
    DecisionResponse,
    GatewayRiskLevel,
)
from channel_engine.models import DecisionAction
from channel_engine.offline_runtime import OfflineCompleteRuntime
from channel_engine.provider import NormalizedChannelObservation
from channel_engine.recorded_replay_acceptance import (
    ProductScopeIsolationStatus,
    RecordedReplayDecision,
    evaluate_recorded_replay,
    load_recorded_replay_acceptance,
)

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
RECORDED_NOW = datetime(2026, 8, 14, 16, 0, tzinfo=UTC)
RECORDED_FIXTURE = (
    Path(__file__).parents[2]
    / "simulators"
    / "recorded-replay"
    / "fixtures"
    / "pdd-recorded-replay-20260814.v1.json"
)


class OfflineAICSGateway:
    version = "offline-ai-cs.v1"

    def __init__(self) -> None:
        self.requests: list[DecisionRequest] = []

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        self.requests.append(request)
        scope = request.context["ai_cs_scope"]
        product = request.context["product"]
        return DecisionResponse(
            contract_version="1.0",
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            correlation_id=request.correlation_id,
            decision_id=f"decision-{request.message_id[-32:]}",
            action=DecisionAction.SUGGEST_REPLY,
            proposed_content="这款合成商品有现货知识记录，请在确认当前款式后回复买家。",
            requires_approval=True,
            risk_level=GatewayRiskLevel.LOW,
            gateway_version=self.version,
            metadata={
                "ai_cs_action": "DIRECT_ANSWER",
                "warnings": [],
                "required_fields": [],
                "citations": [
                    {
                        "reference": "synthetic-faq-001",
                        "title": "合成商品 FAQ",
                        "excerpt": "当前商品有现货知识记录。",
                        "product_id": scope["product_id"],
                        "sku_id": scope["sku_id"],
                        "source_kind": "RAG_KNOWLEDGE",
                    }
                ],
                "verified_product_name": product.get("product_name"),
            },
            decided_at=NOW,
        )


class ReferenceBlindRecordedReplayGateway:
    """Deterministic AI boundary that never receives evaluation references."""

    version = "recorded-replay-reference-blind.v1"

    def __init__(self) -> None:
        self.requests: list[DecisionRequest] = []

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        self.requests.append(request)
        scope = request.context["ai_cs_scope"]
        product = request.context["product"]
        return DecisionResponse(
            contract_version="1.0",
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            correlation_id=request.correlation_id,
            decision_id=f"decision-{request.message_id[-32:]}",
            action=DecisionAction.SUGGEST_REPLY,
            proposed_content="当前商品资料不足，请人工核对具体参数后再回复买家。",
            requires_approval=True,
            risk_level=GatewayRiskLevel.LOW,
            gateway_version=self.version,
            metadata={
                "ai_cs_action": "DIRECT_ANSWER",
                "warnings": ["RECORDED_REPLAY_BASELINE"],
                "required_fields": [],
                "citations": [
                    {
                        "reference": "recorded-replay-scope-only",
                        "title": "录制样本商品作用域",
                        "excerpt": "仅验证消息链与商品隔离，不提供历史人工答案。",
                        "product_id": scope["product_id"],
                        "sku_id": scope["sku_id"],
                        "source_kind": "SCOPE_EVIDENCE",
                    }
                ],
                "verified_product_name": product.get("product_name"),
            },
            decided_at=RECORDED_NOW,
        )


def _signed_service_request(
    client: TestClient,
    signer: ServiceRequestSigner,
    method: str,
    path: str,
    *,
    nonce: str,
    payload: dict[str, object] | None = None,
    intent: str | None = None,
):
    body = (
        b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    )
    headers = signer.headers(
        method,
        path,
        body,
        timestamp=int(NOW.timestamp()),
        nonce=nonce,
    )
    if intent is not None:
        headers["X-Operator-Intent"] = intent
    return client.request(method, path, content=body or None, headers=headers)


def observation(
    *,
    message_id: str,
    conversation_id: str = "conversation-001",
    store_id: str = "store-001",
    product_id: str = "product-001",
):
    return NormalizedChannelObservation.synthetic(
        provider_id="synthetic-pdd-blackbox",
        store_id=store_id,
        store_name="离线验收店铺",
        conversation_id=conversation_id,
        external_message_id=message_id,
        source_sequence=int(message_id.rsplit("-", 1)[-1]),
        content="这款商品现在有货吗？",
        timestamp=NOW - timedelta(seconds=1),
        product={
            "product_id": product_id,
            "product_name": "合成验收商品",
            "sku_id": "sku-001",
            "sku_name": "标准款",
            "attributes": {"color": "violet"},
        },
        order={
            "order_reference": "synthetic-order-001",
            "order_status": "PAID",
            "logistics_status": "NOT_SHIPPED",
            "payment_data_included": False,
            "address_data_included": False,
        },
    )


def test_black_box_manual_confirm_reaches_execution_prepared_without_real_send(
    tmp_path: Path,
) -> None:
    runtime = OfflineCompleteRuntime(
        tmp_path / "manual", OfflineAICSGateway(), clock=lambda: NOW
    )
    value = observation(message_id="synthetic-message-1")
    try:
        assert runtime.ingest_provider(SyntheticPDDProvider((value,))) == 1
        result = runtime.drain()
        assert result.observations_ingested == 1
        assert result.replies_generated == 1

        snapshot = runtime.conversations()[0]
        assert snapshot.status == "WAITING_APPROVAL"
        assert snapshot.policy_mode == "MANUAL_CONFIRM"
        assert snapshot.quality_status == "PASS"
        assert snapshot.product_context["product_reference"] == "product-001"
        assert snapshot.product_context["sku_reference"] == "sku-001"
        assert snapshot.citations[0]["excerpt"] == "当前商品有现货知识记录。"
        assert snapshot.safety.real_send is False
        assert snapshot.safety.execution_count == 0
        assert snapshot.safety.receipt_count == 0

        prepared = runtime.prepare_manually(
            snapshot.decision_id,
            authorized_by="operator:offline-acceptance",
            store_id=snapshot.store_id,
            conversation_id=snapshot.conversation_id,
            customer_reference=snapshot.customer_reference,
        )
        refreshed = runtime.conversations()[0]
        assert prepared.state == "READY"
        assert prepared.authorization_kind == "HUMAN"
        assert refreshed.status == "EXECUTION_PREPARED"
        assert refreshed.safety.execution_prepared is True
        assert refreshed.safety.execution_count == 0
        assert refreshed.safety.send_count == 0

        stages = {item.stage.value: item for item in runtime.trace(value.trace_id)}
        assert {
            "PROVIDER_READ",
            "EDGE_SPOOL",
            "HOST_PERSIST",
            "BUFFERING",
            "CUSTOMER_CONTEXT",
            "AI_GENERATING",
            "QUALITY_GATE",
            "WAITING_CONFIRMATION",
            "EXECUTION_PREPARED",
        } <= stages.keys()
        assert stages["EXECUTION_PREPARED"].reason_code == "REAL_SEND_BLOCKED"
        assert runtime.offline_control.real_success_count() == 0
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "checkpoint",
    [
        "AFTER_BUFFER_REPLY_COMMIT",
        "AFTER_CONTROL_DECISION_COMMIT",
        "AFTER_ASSISTANT_SNAPSHOT_COMMIT",
    ],
)
def test_projection_reconciler_repairs_each_cross_database_crash_window(
    tmp_path: Path,
    checkpoint: str,
) -> None:
    root = tmp_path / checkpoint.casefold()
    gateway = OfflineAICSGateway()
    triggered = False

    def fail_once(value: str) -> None:
        nonlocal triggered
        if not triggered and value == checkpoint:
            triggered = True
            raise RuntimeError(f"injected crash at {value}")

    first = OfflineCompleteRuntime(
        root,
        gateway,
        clock=lambda: NOW,
        fault_injector=fail_once,
    )
    value = observation(message_id="synthetic-message-1")
    try:
        first.ingest_provider(SyntheticPDDProvider((value,)))
        with pytest.raises(RuntimeError, match="injected crash"):
            first.drain()
    finally:
        first.close()

    recovered = OfflineCompleteRuntime(root, gateway, clock=lambda: NOW)
    try:
        snapshot = recovered.conversations()[0]
        assert snapshot.status == "WAITING_APPROVAL"
        assert snapshot.safety.real_send is False
        assert recovered.offline_control.reply_outcome(snapshot.decision_id) is not None
        revision = snapshot.revision

        second = recovered.reconcile_projections()
        assert second.unchanged == 1
        assert second.snapshots_rebuilt == 0
        assert recovered.conversations()[0].revision == revision
        assert recovered.offline_control.real_success_count() == 0
    finally:
        recovered.close()


def test_runtime_backup_quiesces_reconciles_and_creates_one_epoch(
    tmp_path: Path,
) -> None:
    runtime = OfflineCompleteRuntime(
        tmp_path / "backup-runtime", OfflineAICSGateway(), clock=lambda: NOW
    )
    try:
        runtime.ingest_provider(
            SyntheticPDDProvider((observation(message_id="synthetic-message-1"),))
        )
        runtime.drain()
        manifest = runtime.create_backup(tmp_path / "backup-set")

        payload = json.loads((manifest.destination / "manifest.json").read_text())
        assert payload["backup_epoch"] == manifest.backup_epoch
        assert payload["whole_file_sha_usage"] == "BACKUP_EVIDENCE_ONLY"
        assert payload["projection_reconciliation"]["unchanged"] == 1
        assert set(payload["high_water_marks"]) == {
            "HOST_CONTROL",
            "CONVERSATION_BUFFER",
            "OFFLINE_CONTROL",
        }
        assert all(item["sha256"] for item in payload["artifacts"])
        for item in payload["artifacts"]:
            assert (manifest.destination / item["backup_name"]).is_file()
    finally:
        runtime.close()


def test_black_box_auto_low_risk_switch_and_new_message_invalidation(
    tmp_path: Path,
) -> None:
    runtime = OfflineCompleteRuntime(
        tmp_path / "auto", OfflineAICSGateway(), clock=lambda: NOW
    )
    first = observation(message_id="synthetic-message-1")
    try:
        policy = runtime.set_policy("store-001", ReplyPolicyMode.AUTO_LOW_RISK)
        assert policy.mode == "AUTO_LOW_RISK"
        runtime.ingest_provider(SyntheticPDDProvider((first,)))
        runtime.drain()

        snapshot = runtime.conversations()[0]
        prepared = runtime.offline_control.preparation(snapshot.decision_id)
        assert snapshot.status == "EXECUTION_PREPARED"
        assert prepared is not None
        assert prepared.authorization_kind == "AUTO_POLICY"
        assert snapshot.safety.auto_reply is True
        assert snapshot.safety.execution_count == 0

        second = observation(message_id="synthetic-message-2")
        runtime.ingest_provider(SyntheticPDDProvider((second,)))
        runtime.drain()
        assert (
            runtime.offline_control.preparation(snapshot.decision_id).state
            == "INVALIDATED"
        )

        manual = runtime.set_policy("store-001", ReplyPolicyMode.MANUAL_CONFIRM)
        assert manual.mode == "MANUAL_CONFIRM"
        assert manual.revision > policy.revision
    finally:
        runtime.close()


def test_auto_low_risk_fails_closed_when_citation_scope_is_not_current_product(
    tmp_path: Path,
) -> None:
    class WrongProductGateway(OfflineAICSGateway):
        def decide(self, request: DecisionRequest) -> DecisionResponse:
            response = super().decide(request)
            metadata = dict(response.metadata)
            citation = dict(metadata["citations"][0])
            citation["product_id"] = "different-product"
            metadata["citations"] = [citation]
            return response.model_copy(update={"metadata": metadata})

    runtime = OfflineCompleteRuntime(
        tmp_path / "wrong-product", WrongProductGateway(), clock=lambda: NOW
    )
    try:
        runtime.set_policy("store-001", ReplyPolicyMode.AUTO_LOW_RISK)
        runtime.ingest_provider(
            SyntheticPDDProvider((observation(message_id="synthetic-message-1"),))
        )
        runtime.drain()
        snapshot = runtime.conversations()[0]
        outcome = runtime.offline_control.reply_outcome(snapshot.decision_id)
        assert outcome is not None
        assert outcome.quality.status == "BLOCKED"
        assert "CITATION_PRODUCT_CONTEXT_MISMATCH" in outcome.quality.reason_codes
        assert outcome.preparation is None
        assert snapshot.status == "MANUAL_INTERVENTION"
        assert snapshot.safety.real_send is False
    finally:
        runtime.close()


def test_black_box_manual_multiturn_projects_only_authorized_reply_history(
    tmp_path: Path,
) -> None:
    gateway = OfflineAICSGateway()
    runtime = OfflineCompleteRuntime(
        tmp_path / "multiturn-human", gateway, clock=lambda: NOW
    )
    first = observation(message_id="synthetic-message-1")
    second = observation(message_id="synthetic-message-2")
    try:
        runtime.ingest_provider(SyntheticPDDProvider((first,)))
        runtime.drain()
        initial = runtime.conversations()[0]
        assert gateway.requests[0].context["visible_conversation_history"] == []
        runtime.prepare_manually(
            initial.decision_id,
            authorized_by="operator:multiturn",
            store_id=initial.store_id,
            conversation_id=initial.conversation_id,
            customer_reference=initial.customer_reference,
        )

        runtime.ingest_provider(SyntheticPDDProvider((second,)))
        runtime.drain()

        history = gateway.requests[1].context["visible_conversation_history"]
        assert [item["sender"] for item in history] == ["customer", "operator"]
        assert history[0]["message_id"] == first.external_message_id
        assert history[1]["message_id"].startswith("authorized-reply:")
        audit = runtime.offline_control.history_audit(second.trace_id)
        assert audit is not None
        assert [item["source"] for item in audit["entries"]] == [
            "SYNTHETIC",
            "HUMAN",
        ]
        assert audit["external_message_id"] == second.external_message_id
        assert audit["source_sequence"] == 2
        assert audit["excluded_current_turn_message_ids"] == [
            second.external_message_id
        ]
    finally:
        runtime.close()


def test_black_box_unconfirmed_draft_never_enters_next_turn_history(
    tmp_path: Path,
) -> None:
    gateway = OfflineAICSGateway()
    runtime = OfflineCompleteRuntime(
        tmp_path / "multiturn-unconfirmed", gateway, clock=lambda: NOW
    )
    first = observation(message_id="synthetic-message-1")
    second = observation(message_id="synthetic-message-2")
    try:
        runtime.ingest_provider(SyntheticPDDProvider((first,)))
        runtime.drain()
        runtime.ingest_provider(SyntheticPDDProvider((second,)))
        runtime.drain()

        history = gateway.requests[1].context["visible_conversation_history"]
        assert [item["sender"] for item in history] == ["customer"]
        assert all(
            not item["message_id"].startswith("authorized-reply:") for item in history
        )
    finally:
        runtime.close()


def test_black_box_auto_policy_reply_is_preserved_as_operator_history(
    tmp_path: Path,
) -> None:
    gateway = OfflineAICSGateway()
    runtime = OfflineCompleteRuntime(
        tmp_path / "multiturn-auto", gateway, clock=lambda: NOW
    )
    first = observation(message_id="synthetic-message-1")
    second = observation(message_id="synthetic-message-2")
    try:
        runtime.set_policy("store-001", ReplyPolicyMode.AUTO_LOW_RISK)
        runtime.ingest_provider(SyntheticPDDProvider((first,)))
        runtime.drain()
        runtime.ingest_provider(SyntheticPDDProvider((second,)))
        runtime.drain()

        history = gateway.requests[1].context["visible_conversation_history"]
        assert [item["sender"] for item in history] == ["customer", "operator"]
        audit = runtime.offline_control.history_audit(second.trace_id)
        assert audit is not None
        assert [item["source"] for item in audit["entries"]] == [
            "SYNTHETIC",
            "AUTO_POLICY",
        ]
    finally:
        runtime.close()


def test_signed_workspace_service_controls_policy_and_manual_preparation(
    tmp_path: Path,
) -> None:
    runtime = OfflineCompleteRuntime(
        tmp_path / "signed-service", OfflineAICSGateway(), clock=lambda: NOW
    )
    secret = b"offline-service-control-secret-32-bytes-minimum"
    signer = ServiceRequestSigner("ai-cs", "service-key-1", secret)
    verifier = ServiceRequestVerifier(
        lambda service, key: (
            secret if (service, key) == ("ai-cs", "service-key-1") else b""
        ),
        clock=lambda: NOW.timestamp(),
    )
    value = observation(message_id="synthetic-message-1")
    try:
        runtime.ingest_provider(SyntheticPDDProvider((value,)))
        runtime.drain()
        snapshot = runtime.conversations()[0]

        app = FastAPI()
        app.include_router(
            create_channel_agent_service_v2_router(
                cast(ChannelAgentNodeRegistry, object()),
                verifier,
                runtime.control_store,
                offline_control=runtime.offline_control,
            )
        )
        client = TestClient(app, base_url="https://testserver")

        policy_path = "/channel-agent/v2/service/reply-policies/store-001"
        policy = _signed_service_request(
            client, signer, "GET", policy_path, nonce="1" * 32
        )
        assert policy.status_code == 200
        assert policy.json()["mode"] == "MANUAL_CONFIRM"

        changed = _signed_service_request(
            client,
            signer,
            "PUT",
            policy_path,
            nonce="2" * 32,
            payload={
                "mode": "AUTO_LOW_RISK",
                "expected_revision": 1,
                "actor_reference": "11111111-1111-4111-8111-111111111111",
            },
            intent="AUTHORIZED_REPLY_POLICY_CHANGE",
        )
        assert changed.status_code == 200
        assert changed.json()["mode"] == "AUTO_LOW_RISK"
        assert "11111111" not in changed.json()["updated_by"]

        preparation_path = (
            "/channel-agent/v2/service/decisions/"
            f"{snapshot.decision_id}/execution-preparations"
        )
        prepared = _signed_service_request(
            client,
            signer,
            "POST",
            preparation_path,
            nonce="3" * 32,
            payload={
                "store_id": snapshot.store_id,
                "conversation_id": snapshot.conversation_id,
                "customer_reference": snapshot.customer_reference,
                "actor_reference": "11111111-1111-4111-8111-111111111111",
            },
            intent="HUMAN_CONFIRMED_EXECUTION_PREPARATION",
        )
        assert prepared.status_code == 201, prepared.text
        assert prepared.json()["authorization_kind"] == "HUMAN"
        assert prepared.json()["real_send_enabled"] is False
        assert runtime.conversations()[0].status == "EXECUTION_PREPARED"
        events = runtime.control_store.poll_assistant_events(
            "offline-agent", "offline-device", after_sequence_id=0, limit=100
        )
        assert any(item.event_type == "EXECUTION_PREPARED" for item in events)
    finally:
        runtime.close()


def test_recorded_pdd_replay_persists_16_formal_messages_without_answer_leak(
    tmp_path: Path,
) -> None:
    fixture = load_recorded_replay_acceptance(RECORDED_FIXTURE)
    gateway = ReferenceBlindRecordedReplayGateway()
    runtime = OfflineCompleteRuntime(
        tmp_path / "recorded-pdd-20260814",
        gateway,
        clock=lambda: RECORDED_NOW,
    )
    try:
        assert runtime.ingest_provider(RecordedReplayProvider(RECORDED_FIXTURE)) == 16
        drained = runtime.drain(limit=100)
        assert drained.observations_ingested == 16
        assert drained.replies_generated == 16

        snapshots = runtime.conversations()
        assert len(snapshots) == 16
        assert len(gateway.requests) == 16
        assert {item.customer_message for item in gateway.requests} == {
            item.content for item in fixture.observations
        }
        assert all(
            item.context["visible_conversation_history"] == []
            for item in gateway.requests
        )
        assert all(
            item.context["ai_cs_scope"]["platform"] == "pinduoduo"
            for item in gateway.requests
        )

        ai_visible_payload = json.dumps(
            [item.model_dump(mode="json") for item in gateway.requests],
            ensure_ascii=False,
            sort_keys=True,
        )
        assert all(
            reference.operator_answer not in ai_visible_payload
            for reference in fixture.evaluation_references
        )

        decisions = tuple(
            RecordedReplayDecision(
                external_message_id=snapshot.customer_message_id or "",
                reply_content=snapshot.reply_content,
                action=snapshot.ai_cs_action,
                risk_level=snapshot.risk_level,
                quality_status=snapshot.quality_status,
                store_id=snapshot.store_id,
                product_ref=(snapshot.product_context or {}).get("product_reference"),
                sku_ref=(snapshot.product_context or {}).get("sku_reference"),
            )
            for snapshot in snapshots
        )
        baseline = evaluate_recorded_replay(fixture, decisions)
        assert baseline.total_cases == 16
        assert baseline.accepted_cases < 13
        assert baseline.accuracy_gate_passed is False
        assert (
            baseline.product_scope_isolation
            is ProductScopeIsolationStatus.PASS
        )
        assert baseline.simulated_auto_send_ready is False

        assert {
            (item.store_id, (item.product_context or {}).get("product_reference"))
            for item in snapshots
        } == {
            (fixture.observations[0].store_id, product_id)
            for product_id in (
                "970504176629",
                "972030445746",
                "982904528556",
                "984350540183",
            )
        }
        assert all(item.status == "WAITING_APPROVAL" for item in snapshots)
        assert all(item.safety.receipt_count == 0 for item in snapshots)
        assert all(item.safety.send_count == 0 for item in snapshots)

        selected = snapshots[0]
        prepared = runtime.prepare_manually(
            selected.decision_id,
            authorized_by="operator:offline-recorded-acceptance",
            store_id=selected.store_id,
            conversation_id=selected.conversation_id,
            customer_reference=selected.customer_reference,
        )
        assert prepared.state == "READY"
        assert runtime.conversations()[0].safety.real_send is False
        assert runtime.offline_control.real_success_count() == 0
    finally:
        runtime.close()


def test_provider_implementations_are_substitutable_at_the_external_boundary(
    tmp_path: Path,
) -> None:
    value = observation(message_id="synthetic-message-1")
    fixture = tmp_path / "recorded-replay.json"
    fixture.write_text(
        json.dumps(
            {"observations": [value.model_dump(mode="json")]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    synthetic = SyntheticPDDProvider((value,)).poll()[0]
    replay = RecordedReplayProvider(fixture).poll()[0]

    ignored = {"provider_id", "provider_kind"}
    assert {
        key: item
        for key, item in synthetic.model_dump(mode="json").items()
        if key not in ignored
    } == {
        key: item
        for key, item in replay.model_dump(mode="json").items()
        if key not in ignored
    }

    assert "channel_agent.providers" not in (
        Path(__file__).parents[2] / "src" / "channel_engine" / "offline_runtime.py"
    ).read_text(encoding="utf-8")


def test_black_box_two_stores_and_four_conversations_never_cross_scope(
    tmp_path: Path,
) -> None:
    runtime = OfflineCompleteRuntime(
        tmp_path / "isolation", OfflineAICSGateway(), clock=lambda: NOW
    )
    values = tuple(
        observation(
            message_id=f"synthetic-message-{index}",
            store_id=f"store-{1 if index <= 2 else 2:03d}",
            conversation_id=f"conversation-{index:03d}",
            product_id=f"product-{index:03d}",
        )
        for index in range(1, 5)
    )
    try:
        assert runtime.ingest_provider(SyntheticPDDProvider(values)) == 4
        result = runtime.drain()
        assert result.observations_ingested == 4
        assert result.replies_generated == 4
        snapshots = runtime.conversations()
        assert len(snapshots) == 4
        assert len({(item.store_id, item.conversation_id) for item in snapshots}) == 4
        assert all(item.status == "WAITING_APPROVAL" for item in snapshots)
        assert all(item.safety.execution_count == 0 for item in snapshots)

        feed = DesktopAssistantServer._snapshots_feed(
            tuple(item.model_dump(mode="json") for item in snapshots)
        )
        conversations = feed["conversations"]
        assert len(conversations) == 4
        assert {item["conversationId"] for item in conversations} == {
            f"conversation-{index:03d}" for index in range(1, 5)
        }
        assert len(feed["replies"]) == 4
        assert {
            item["productContext"]["productReference"] for item in conversations
        } == {f"product-{index:03d}" for index in range(1, 5)}
        assert all(len(item["messages"]) == 1 for item in conversations)
        assert all(
            item["reply"]["conversationId"] == item["conversationId"]
            for item in conversations
        )
        assert feed["safety"] == {
            "readOnly": True,
            "autoReply": False,
            "realSend": False,
            "browserWriteOperations": 0,
            "executionCount": 0,
            "receiptCount": 0,
            "sendCount": 0,
            "executionPrepared": False,
        }
    finally:
        runtime.close()
