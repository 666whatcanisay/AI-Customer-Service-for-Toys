from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

import channel_agent.binding as binding_module
from channel_agent.assistant_bridge import ApprovedReplyResponse
from channel_agent.controlled_reply_pilot import (
    ControlledReplyPilotError,
    ControlledReplyPilotOrchestrator,
)
from channel_agent.controlled_send_grant import (
    ControlledAutoPolicyGrantV1,
    ControlledPilotSendWindowStore,
    ControlledSendGrantV1,
)
from channel_engine.customer_assistant import (
    AIReplyPackage,
    BufferedCustomerMessage,
    ContextPageState,
    CustomerContext,
    KnowledgeCitation,
    PageContext,
    ProductContext,
    SQLiteConversationBuffer,
    TransactionContext,
)
from channel_engine.gateway import GatewayRiskLevel

NOW = datetime(2026, 8, 14, 9, 0, tzinfo=UTC)
STORE = "store-pilot"
CONVERSATION = "conversation-pilot"
PRODUCT = "product-pilot"
SKU = "sku-pilot"
QUESTION = "这款积木适合几岁？"
REPLY = "这款积木建议五岁以上使用，三岁以下儿童不适用。"


class _Harness:
    def __init__(self, tmp_path) -> None:
        self.now = NOW
        self.buffer = SQLiteConversationBuffer(
            tmp_path / "conversation-buffer.sqlite3",
            quiet_window=timedelta(seconds=1),
            processing_lease=timedelta(minutes=1),
            clock=lambda: self.now,
        )
        self.windows = ControlledPilotSendWindowStore(
            tmp_path / "controlled-pilot-window.sqlite3"
        )
        self.feed_path = tmp_path / "assistant-feed.json"
        self.posts: list[tuple[object, str]] = []
        self.orchestrator = ControlledReplyPilotOrchestrator(
            feed_path=self.feed_path,
            buffer=self.buffer,
            pilot_window_store=self.windows,
            state_root=tmp_path / "pilot-state",
            post_approved_reply=self._post,
            clock=lambda: self.now,
        )

    def _post(self, request, intent: str) -> ApprovedReplyResponse:
        self.posts.append((request, intent))
        stored = self.buffer.load_reply(request.decision_id)
        assert stored is not None
        self.buffer.complete(stored[1].turn_id)
        authorization_kind = (
            "AUTO_POLICY"
            if isinstance(request.controlled_send_grant, ControlledAutoPolicyGrantV1)
            else "MANUAL_CONFIRM"
        )
        return ApprovedReplyResponse(
            decision_id=request.decision_id,
            approval_id=f"approval:{request.decision_id}",
            execution_id=f"execution:{request.decision_id}",
            receipt_id=f"receipt:{request.decision_id}",
            outcome="SUCCESS",
            customer_message_sent=True,
            manual_intervention_required=False,
            authorization_kind=authorization_kind,
            pilot_window_id=request.controlled_send_grant.pilot_window_id,
        )

    def add_reply(
        self,
        *,
        message_id: str,
        decision_id: str,
        policy_mode: str,
        question: str = QUESTION,
        reply_text: str = REPLY,
        risk_level: GatewayRiskLevel = GatewayRiskLevel.LOW,
        ai_cs_action: str = "DIRECT_ANSWER",
    ) -> AIReplyPackage:
        self.now += timedelta(seconds=2)
        message = BufferedCustomerMessage.from_redacted(
            store_id=STORE,
            conversation_id=CONVERSATION,
            external_message_id=message_id,
            content=question,
            timestamp=self.now,
            received_at=self.now,
        )
        self.buffer.append(message)
        self.now += timedelta(seconds=2)
        turn = self.buffer.claim_ready(now=self.now)
        assert turn is not None
        context_digest = hashlib.sha256(decision_id.encode("utf-8")).hexdigest()
        context = CustomerContext(
            context_id=f"customer-context:{context_digest}",
            turn_id=turn.turn_id,
            store_id=STORE,
            conversation_id=CONVERSATION,
            customer_reference=turn.customer_reference,
            page=PageContext(
                store_id=STORE,
                conversation_id=CONVERSATION,
                state=ContextPageState.PRODUCT,
                product=ProductContext(
                    product_reference=PRODUCT,
                    product_name="离线验收商品",
                    sku_reference=SKU,
                    sku_name="标准款",
                ),
                captured_at=self.now,
            ),
            transaction=TransactionContext(),
            conversation_history=turn.messages,
            current_turn_message_ids=(message_id,),
            current_question=question,
            knowledge_scopes=("products",),
            assembled_at=self.now,
        )
        package = AIReplyPackage(
            turn_id=turn.turn_id,
            context_id=context.context_id,
            request_id=f"request:{decision_id}",
            decision_id=decision_id,
            store_id=STORE,
            conversation_id=CONVERSATION,
            customer_reference=turn.customer_reference,
            customer_question=question,
            reply_content=reply_text,
            citations=(
                KnowledgeCitation(
                    reference="product-knowledge:pilot",
                    title="商品知识",
                    excerpt="适用年龄与安全说明",
                    product_id=PRODUCT,
                    sku_id=SKU,
                    source_kind="PRODUCT_KNOWLEDGE",
                ),
            ),
            risk_level=risk_level,
            ai_cs_action=ai_cs_action,
            gateway_version="gateway-test-v1",
            generated_at=self.now,
        )
        self.buffer.save_reply(turn.turn_id, context, package)
        self.write_feed(package, message_id=message_id, policy_mode=policy_mode)
        return package

    def write_feed(
        self,
        package: AIReplyPackage,
        *,
        message_id: str,
        policy_mode: str,
        answer: str | None = None,
    ) -> None:
        self.feed_path.write_text(
            json.dumps(
                {
                    "safety": {"realSend": False, "autoReply": False},
                    "reply": {
                        "decisionId": package.decision_id,
                        "messageId": message_id,
                        "conversationId": package.conversation_id,
                        "answer": package.reply_content if answer is None else answer,
                        "state": "WAITING_APPROVAL",
                        "qualityStatus": "PASS",
                        "policyMode": policy_mode,
                        "action": package.ai_cs_action,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def send_stage_b(self) -> None:
        self.add_reply(
            message_id="message-stage-b",
            decision_id="decision-stage-b",
            policy_mode="MANUAL_CONFIRM",
        )
        preview, _, _ = self.orchestrator.preview_manual(
            policy_revision=1,
            whitelist_revision="allowlist-1",
        )
        response = self.orchestrator.send_manual(
            confirmation_token=preview.confirmation_token,
            operator_reference="operator-pilot",
            policy_revision=1,
            whitelist_revision="allowlist-1",
        )
        assert response.outcome == "SUCCESS"


def test_manual_preview_uses_existing_endpoint_and_persists_hash_only_baseline(
    tmp_path,
) -> None:
    harness = _Harness(tmp_path)
    harness.send_stage_b()

    assert len(harness.posts) == 1
    request, intent = harness.posts[0]
    assert intent == "HUMAN_CONFIRMED_SEND"
    assert isinstance(request.controlled_send_grant, ControlledSendGrantV1)
    assert harness.windows.active(now=harness.now) is None
    baseline = json.loads(harness.orchestrator.baseline_path.read_text(encoding="utf-8"))
    assert baseline["stage_b_decision_id"] == "decision-stage-b"
    assert baseline["approved_reply_sha256"] == hashlib.sha256(
        REPLY.encode("utf-8")
    ).hexdigest()
    assert REPLY not in harness.orchestrator.baseline_path.read_text(encoding="utf-8")


def test_manual_preview_allows_human_confirmed_medium_controlled_answer(
    tmp_path,
) -> None:
    harness = _Harness(tmp_path)
    harness.add_reply(
        message_id="message-medium",
        decision_id="decision-medium",
        policy_mode="MANUAL_CONFIRM",
        risk_level=GatewayRiskLevel.MEDIUM,
        ai_cs_action="CONTROLLED_ANSWER",
    )

    preview, candidate, reply = harness.orchestrator.preview_manual(
        policy_revision=1,
        whitelist_revision="allowlist-1",
    )

    assert preview.mode == "MANUAL_CONFIRM"
    assert candidate.risk_level == "MEDIUM"
    assert candidate.action == "CONTROLLED_ANSWER"
    assert reply == REPLY


def test_pilot_state_write_retries_transient_windows_sharing_conflict(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _Harness(tmp_path)
    original_replace = binding_module._atomic_replace
    attempts = 0

    def transient_replace(source, target) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("synthetic Windows sharing violation")
        original_replace(source, target)

    monkeypatch.setattr(binding_module, "_atomic_replace", transient_replace)
    harness.send_stage_b()

    assert attempts >= 3
    baseline = json.loads(harness.orchestrator.baseline_path.read_text(encoding="utf-8"))
    assert baseline["stage_b_decision_id"] == "decision-stage-b"


def test_manual_send_blocks_when_reply_changes_after_human_preview(tmp_path) -> None:
    harness = _Harness(tmp_path)
    package = harness.add_reply(
        message_id="message-stage-b",
        decision_id="decision-stage-b",
        policy_mode="MANUAL_CONFIRM",
    )
    preview, _, _ = harness.orchestrator.preview_manual(
        policy_revision=1,
        whitelist_revision="allowlist-1",
    )
    harness.write_feed(
        package,
        message_id="message-stage-b",
        policy_mode="MANUAL_CONFIRM",
        answer=REPLY + "。",
    )

    with pytest.raises(ControlledReplyPilotError) as captured:
        harness.orchestrator.send_manual(
            confirmation_token=preview.confirmation_token,
            operator_reference="operator-pilot",
            policy_revision=1,
            whitelist_revision="allowlist-1",
        )
    assert captured.value.error_code == "PILOT_REPLY_PACKAGE_MISMATCH"
    assert harness.posts == []
    assert harness.windows.active(now=harness.now) is None


def test_auto_waits_past_stale_manual_feed_then_sends_exact_new_decision(tmp_path) -> None:
    harness = _Harness(tmp_path)
    harness.send_stage_b()
    preview, _, _ = harness.orchestrator.preview_auto(
        policy_revision=2,
        whitelist_revision="allowlist-2",
    )
    sleeps = 0

    def advance(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        harness.now += timedelta(milliseconds=100)
        if sleeps == 1:
            harness.add_reply(
                message_id="message-stage-c",
                decision_id="decision-stage-c",
                policy_mode="AUTO_LOW_RISK",
            )

    response = harness.orchestrator.run_auto_once(
        confirmation_token=preview.confirmation_token,
        operator_reference="operator-pilot",
        policy_revision=2,
        whitelist_revision="allowlist-2",
        timeout_seconds=30,
        poll_interval_seconds=0.1,
        sleep=advance,
    )

    assert response.outcome == "SUCCESS"
    assert sleeps == 1
    assert len(harness.posts) == 2
    request, intent = harness.posts[-1]
    assert intent == "AUTO_POLICY_PILOT_SEND"
    assert isinstance(request.controlled_send_grant, ControlledAutoPolicyGrantV1)
    assert request.controlled_send_grant.policy_revision == 2
    assert request.controlled_send_grant.whitelist_revision == "allowlist-2"
    assert harness.windows.active(now=harness.now) is None


@pytest.mark.parametrize("changed_reply", [REPLY + "。", REPLY + " ", "建议五岁以上使用。"])
def test_auto_blocks_any_reply_hash_change_and_closes_window(
    tmp_path, changed_reply: str
) -> None:
    harness = _Harness(tmp_path)
    harness.send_stage_b()
    preview, _, _ = harness.orchestrator.preview_auto(
        policy_revision=2,
        whitelist_revision="allowlist-2",
    )
    harness.add_reply(
        message_id="message-stage-c",
        decision_id="decision-stage-c",
        policy_mode="AUTO_LOW_RISK",
        reply_text=changed_reply,
    )

    with pytest.raises(ControlledReplyPilotError) as captured:
        harness.orchestrator.run_auto_once(
            confirmation_token=preview.confirmation_token,
            operator_reference="operator-pilot",
            policy_revision=2,
            whitelist_revision="allowlist-2",
            timeout_seconds=5,
            poll_interval_seconds=0.1,
            sleep=lambda _seconds: None,
        )
    assert captured.value.error_code == "REPLY_HASH_MISMATCH"
    assert len(harness.posts) == 1
    assert harness.windows.active(now=harness.now) is None


def test_auto_preview_policy_drift_blocks_before_opening_window(tmp_path) -> None:
    harness = _Harness(tmp_path)
    harness.send_stage_b()
    preview, _, _ = harness.orchestrator.preview_auto(
        policy_revision=2,
        whitelist_revision="allowlist-2",
    )

    with pytest.raises(ControlledReplyPilotError) as captured:
        harness.orchestrator.run_auto_once(
            confirmation_token=preview.confirmation_token,
            operator_reference="operator-pilot",
            policy_revision=3,
            whitelist_revision="allowlist-2",
            timeout_seconds=1,
            sleep=lambda _seconds: None,
        )
    assert captured.value.error_code == "AUTO_PREVIEW_CHANGED"
    assert len(harness.posts) == 1
    assert harness.windows.active(now=harness.now) is None


def test_auto_timeout_ignores_stale_stage_b_decision_and_disables_pilot(tmp_path) -> None:
    harness = _Harness(tmp_path)
    harness.send_stage_b()
    preview, _, _ = harness.orchestrator.preview_auto(
        policy_revision=2,
        whitelist_revision="allowlist-2",
    )

    def advance(_seconds: float) -> None:
        harness.now += timedelta(seconds=1)

    with pytest.raises(ControlledReplyPilotError) as captured:
        harness.orchestrator.run_auto_once(
            confirmation_token=preview.confirmation_token,
            operator_reference="operator-pilot",
            policy_revision=2,
            whitelist_revision="allowlist-2",
            timeout_seconds=2,
            poll_interval_seconds=1,
            sleep=advance,
        )
    assert captured.value.error_code == "AUTO_PILOT_TIMEOUT"
    assert len(harness.posts) == 1
    assert harness.windows.active(now=harness.now) is None
