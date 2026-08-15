from __future__ import annotations

import hashlib
import json
import secrets
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.customer_assistant import SQLiteConversationBuffer

from .assistant_bridge import (
    ApprovedReplyRequest,
    ApprovedReplyResponse,
    knowledge_scope_sha256,
)
from .binding import atomic_write_bytes
from .controlled_send_grant import (
    ControlledAutoPolicyGrantV1,
    ControlledPilotSendWindowStore,
    ControlledPilotSendWindowV1,
    ControlledSendGrantError,
    ControlledSendGrantV1,
    normalized_question_sha256,
)


class ControlledReplyPilotError(RuntimeError):
    """Fail-closed error raised before the unique real-send endpoint is called."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class _PilotModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ReplyPilotCandidateV1(_PilotModel):
    schema_version: Literal["controlled-reply-pilot-candidate.v1"] = (
        "controlled-reply-pilot-candidate.v1"
    )
    store_id: str = Field(min_length=1, max_length=160)
    ai_cs_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    platform_store_id: str | None = Field(default=None, min_length=1, max_length=160)
    test_buyer_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_message_id: str = Field(min_length=1, max_length=255)
    decision_id: str = Field(min_length=1, max_length=255)
    normalized_question_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_reply_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    product_id: str | None = Field(default=None, max_length=255)
    sku_id: str | None = Field(default=None, max_length=255)
    policy_mode: Literal["MANUAL_CONFIRM", "AUTO_LOW_RISK"]
    policy_revision: int = Field(ge=1)
    whitelist_revision: str = Field(min_length=1, max_length=160)
    knowledge_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reply_evidence_bundle_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    quality_status: Literal["PASS"] = "PASS"
    risk_level: Literal["LOW"] = "LOW"
    action: Literal["DIRECT_ANSWER"] = "DIRECT_ANSWER"

    def digest(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


class ReplyPilotPreviewV1(_PilotModel):
    schema_version: Literal["controlled-reply-pilot-preview.v1"] = (
        "controlled-reply-pilot-preview.v1"
    )
    mode: Literal["MANUAL_CONFIRM", "AUTO_POLICY"]
    candidate_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation_token: str = Field(pattern=r"^[A-Z0-9]{6}-[A-Z0-9]{6}$")
    issued_at: AwareDatetime
    expires_at: AwareDatetime


class AutoPilotBaselineV1(_PilotModel):
    schema_version: Literal["controlled-auto-pilot-baseline.v1"] = (
        "controlled-auto-pilot-baseline.v1"
    )
    stage_b_decision_id: str = Field(min_length=1, max_length=255)
    stage_b_receipt_id: str = Field(min_length=1, max_length=255)
    store_id: str = Field(min_length=1, max_length=160)
    test_buyer_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    conversation_id: str = Field(min_length=1, max_length=255)
    normalized_question_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_reply_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    product_id: str | None = Field(default=None, max_length=255)
    sku_id: str | None = Field(default=None, max_length=255)
    policy_revision: int = Field(ge=1)
    whitelist_revision: str = Field(min_length=1, max_length=160)
    knowledge_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    recorded_at: AwareDatetime

    def digest(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


class _CurrentCandidate:
    def __init__(self, *, candidate: ReplyPilotCandidateV1, reply_text: str, question: str) -> None:
        self.candidate = candidate
        self.reply_text = reply_text
        self.question = question


PostApprovedReply = Callable[[ApprovedReplyRequest, str], ApprovedReplyResponse]


class ControlledReplyPilotOrchestrator:
    """Human-armed Stage B/C orchestration over the sole approved-reply endpoint."""

    def __init__(
        self,
        *,
        feed_path: str | Path,
        buffer: SQLiteConversationBuffer,
        pilot_window_store: ControlledPilotSendWindowStore,
        state_root: str | Path,
        post_approved_reply: PostApprovedReply,
        store_identity_provider: Callable[[], tuple[str, str]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.feed_path = Path(feed_path)
        self.buffer = buffer
        self.pilot_windows = pilot_window_store
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._post = post_approved_reply
        self._store_identity_provider = store_identity_provider
        self._clock = clock

    @property
    def manual_preview_path(self) -> Path:
        return self.state_root / "manual-preview.json"

    @property
    def auto_preview_path(self) -> Path:
        return self.state_root / "auto-preview.json"

    @property
    def baseline_path(self) -> Path:
        return self.state_root / "stage-b-baseline.json"

    def preview_manual(
        self,
        *,
        policy_revision: int,
        whitelist_revision: str,
    ) -> tuple[ReplyPilotPreviewV1, ReplyPilotCandidateV1, str]:
        current = self._current_candidate(
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
            expected_policy_mode="MANUAL_CONFIRM",
        )
        preview = self._issue_preview("MANUAL_CONFIRM", current.candidate.digest())
        self._write_json(self.manual_preview_path, preview)
        return preview, current.candidate, current.reply_text

    def send_manual(
        self,
        *,
        confirmation_token: str,
        operator_reference: str,
        policy_revision: int,
        whitelist_revision: str,
    ) -> ApprovedReplyResponse:
        preview = self._load_preview(self.manual_preview_path, mode="MANUAL_CONFIRM")
        self._assert_token(preview, confirmation_token)
        current = self._current_candidate(
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
            expected_policy_mode="MANUAL_CONFIRM",
        )
        if current.candidate.digest() != preview.candidate_digest:
            raise ControlledReplyPilotError(
                "the Stage B reply changed after preview",
                error_code="MANUAL_PREVIEW_CHANGED",
            )
        now = self._now()
        window = ControlledPilotSendWindowV1.issue(
            mode="MANUAL_CONFIRM",
            store_id=current.candidate.store_id,
            ai_cs_store_id=current.candidate.ai_cs_store_id,
            platform_store_id=current.candidate.platform_store_id,
            test_buyer_hash=current.candidate.test_buyer_hash,
            conversation_id=current.candidate.conversation_id,
            question=current.question,
            approved_reply=current.reply_text,
            product_id=current.candidate.product_id,
            sku_id=current.candidate.sku_id,
            policy_revision=current.candidate.policy_revision,
            whitelist_revision=current.candidate.whitelist_revision,
            knowledge_scope_sha256=current.candidate.knowledge_scope_sha256,
            reply_evidence_bundle_sha256=(
                current.candidate.reply_evidence_bundle_sha256
            ),
            issued_at=now,
        )
        self.pilot_windows.arm(window, now=now)
        grant = ControlledSendGrantV1.issue(
            store_id=current.candidate.store_id,
            ai_cs_store_id=current.candidate.ai_cs_store_id,
            platform_store_id=current.candidate.platform_store_id,
            test_buyer_hash=current.candidate.test_buyer_hash,
            conversation_id=current.candidate.conversation_id,
            customer_message_id=current.candidate.customer_message_id,
            decision_id=current.candidate.decision_id,
            reply_content=current.reply_text,
            operator_reference=operator_reference,
            issued_at=now,
            pilot_window_id=window.window_id,
        )
        request = self._request(
            current=current,
            operator_reference=operator_reference,
            grant=grant,
            now=now,
        )
        try:
            response = self._post(request, "HUMAN_CONFIRMED_SEND")
        except Exception:
            self._close_safely(window.window_id, "ORCHESTRATOR_POST_FAILED")
            raise
        if response.outcome != "SUCCESS" or response.customer_message_sent is not True:
            self._close_safely(window.window_id, f"ORCHESTRATOR_{response.outcome}")
            raise ControlledReplyPilotError(
                "Stage B did not produce a confirmed real receipt",
                error_code="MANUAL_SEND_NOT_CONFIRMED",
            )
        baseline = AutoPilotBaselineV1(
            stage_b_decision_id=current.candidate.decision_id,
            stage_b_receipt_id=response.receipt_id,
            store_id=current.candidate.store_id,
            test_buyer_hash=current.candidate.test_buyer_hash,
            conversation_id=current.candidate.conversation_id,
            normalized_question_sha256=current.candidate.normalized_question_sha256,
            approved_reply_sha256=current.candidate.approved_reply_sha256,
            product_id=current.candidate.product_id,
            sku_id=current.candidate.sku_id,
            policy_revision=current.candidate.policy_revision,
            whitelist_revision=current.candidate.whitelist_revision,
            knowledge_scope_sha256=current.candidate.knowledge_scope_sha256,
            recorded_at=self._now(),
        )
        self._write_json(self.baseline_path, baseline)
        self._close_safely(window.window_id, "ORCHESTRATOR_SUCCESS_CONFIRMED")
        self.manual_preview_path.unlink(missing_ok=True)
        return response

    def preview_auto(
        self,
        *,
        policy_revision: int,
        whitelist_revision: str,
    ) -> tuple[ReplyPilotPreviewV1, AutoPilotBaselineV1, str]:
        baseline, approved_reply = self._load_verified_baseline()
        preview = self._issue_preview(
            "AUTO_POLICY",
            self._auto_authorization_digest(
                baseline,
                policy_revision=policy_revision,
                whitelist_revision=whitelist_revision,
            ),
        )
        self._write_json(self.auto_preview_path, preview)
        return preview, baseline, approved_reply

    def run_auto_once(
        self,
        *,
        confirmation_token: str,
        operator_reference: str,
        policy_revision: int,
        whitelist_revision: str,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> ApprovedReplyResponse:
        preview = self._load_preview(self.auto_preview_path, mode="AUTO_POLICY")
        self._assert_token(preview, confirmation_token)
        baseline, approved_reply = self._load_verified_baseline()
        if self._auto_authorization_digest(
            baseline,
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
        ) != preview.candidate_digest:
            raise ControlledReplyPilotError(
                "the Stage B baseline or AUTO policy changed after preview",
                error_code="AUTO_PREVIEW_CHANGED",
            )
        now = self._now()
        window = ControlledPilotSendWindowV1.issue(
            mode="AUTO_POLICY",
            store_id=baseline.store_id,
            test_buyer_hash=baseline.test_buyer_hash,
            conversation_id=baseline.conversation_id,
            question=self._stage_b_question(baseline),
            approved_reply=approved_reply,
            product_id=baseline.product_id,
            sku_id=baseline.sku_id,
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
            knowledge_scope_sha256=baseline.knowledge_scope_sha256,
            issued_at=now,
        )
        self.pilot_windows.arm(window, now=now)
        deadline = min(
            now + timedelta(seconds=max(0.0, timeout_seconds)),
            window.expires_at,
            preview.expires_at,
        )
        try:
            while self._now() < deadline:
                feed_identity = self._feed_reply_identity()
                if (
                    feed_identity is None
                    or feed_identity[0] == baseline.stage_b_decision_id
                    or feed_identity[1] != baseline.conversation_id
                ):
                    sleep(poll_interval_seconds)
                    continue
                current = self._candidate_if_available(
                    policy_revision=policy_revision,
                    whitelist_revision=whitelist_revision,
                    expected_policy_mode="AUTO_LOW_RISK",
                )
                if current is None:
                    sleep(poll_interval_seconds)
                    continue
                candidate = current.candidate
                if candidate.conversation_id != baseline.conversation_id:
                    sleep(poll_interval_seconds)
                    continue
                if candidate.decision_id == baseline.stage_b_decision_id:
                    sleep(poll_interval_seconds)
                    continue
                self._assert_auto_exact(candidate, baseline)
                auto_grant = ControlledAutoPolicyGrantV1.issue(
                    pilot_window_id=window.window_id,
                    store_id=candidate.store_id,
                    test_buyer_hash=candidate.test_buyer_hash,
                    conversation_id=candidate.conversation_id,
                    customer_message_id=candidate.customer_message_id,
                    decision_id=candidate.decision_id,
                    question=current.question,
                    reply_content=current.reply_text,
                    approved_reply_sha256=baseline.approved_reply_sha256,
                    product_id=candidate.product_id,
                    sku_id=candidate.sku_id,
                    policy_revision=candidate.policy_revision,
                    whitelist_revision=candidate.whitelist_revision,
                    knowledge_scope_sha256=candidate.knowledge_scope_sha256,
                    issued_at=self._now(),
                )
                request = self._request(
                    current=current,
                    operator_reference=operator_reference,
                    grant=auto_grant,
                    now=self._now(),
                )
                response = self._post(request, "AUTO_POLICY_PILOT_SEND")
                if response.outcome != "SUCCESS" or response.customer_message_sent is not True:
                    raise ControlledReplyPilotError(
                        "AUTO Pilot did not produce a confirmed real receipt",
                        error_code="AUTO_SEND_NOT_CONFIRMED",
                    )
                self._close_safely(window.window_id, "ORCHESTRATOR_SUCCESS_CONFIRMED")
                self.auto_preview_path.unlink(missing_ok=True)
                return response
            raise ControlledReplyPilotError(
                "no eligible new AUTO_LOW_RISK decision arrived before expiry",
                error_code="AUTO_PILOT_TIMEOUT",
            )
        except Exception:
            self._close_safely(window.window_id, "AUTO_PILOT_TERMINATED")
            raise

    def send_general_auto_current(
        self,
        *,
        operator_reference: str,
        policy_revision: int,
        whitelist_revision: str,
        deployment_scope: Literal["PILOT", "PRODUCTION_AUTO"],
        expected_decision_id: str | None = None,
    ) -> ApprovedReplyResponse:
        """Authorize the current quality-gated reply once; never a Store wildcard."""

        current = self._current_candidate(
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
            expected_policy_mode="AUTO_LOW_RISK",
        )
        candidate = current.candidate
        if (
            expected_decision_id is not None
            and candidate.decision_id != expected_decision_id
        ):
            raise ControlledReplyPilotError(
                "the current AUTO Decision changed before authorization",
                error_code="GENERAL_AUTO_DECISION_CHANGED",
            )
        if (
            candidate.ai_cs_store_id is None
            or candidate.platform_store_id is None
            or candidate.reply_evidence_bundle_sha256 is None
        ):
            raise ControlledReplyPilotError(
                "general AUTO requires double Store identity and Evidence",
                error_code="GENERAL_AUTO_SCOPE_INCOMPLETE",
            )
        now = self._now()
        window = ControlledPilotSendWindowV1.issue(
            mode="AUTO_POLICY",
            store_id=candidate.store_id,
            ai_cs_store_id=candidate.ai_cs_store_id,
            platform_store_id=candidate.platform_store_id,
            test_buyer_hash=candidate.test_buyer_hash,
            conversation_id=candidate.conversation_id,
            question=current.question,
            approved_reply=current.reply_text,
            product_id=candidate.product_id,
            sku_id=candidate.sku_id,
            policy_revision=candidate.policy_revision,
            whitelist_revision=candidate.whitelist_revision,
            knowledge_scope_sha256=candidate.knowledge_scope_sha256,
            reply_evidence_bundle_sha256=(
                candidate.reply_evidence_bundle_sha256
            ),
            authorization_basis="QUALITY_GATED_LOW_RISK",
            deployment_scope=deployment_scope,
            issued_at=now,
        )
        self.pilot_windows.arm(window, now=now)
        grant = ControlledAutoPolicyGrantV1.issue(
            pilot_window_id=window.window_id,
            store_id=candidate.store_id,
            ai_cs_store_id=candidate.ai_cs_store_id,
            platform_store_id=candidate.platform_store_id,
            test_buyer_hash=candidate.test_buyer_hash,
            conversation_id=candidate.conversation_id,
            customer_message_id=candidate.customer_message_id,
            decision_id=candidate.decision_id,
            question=current.question,
            reply_content=current.reply_text,
            approved_reply_sha256=None,
            product_id=candidate.product_id,
            sku_id=candidate.sku_id,
            policy_revision=candidate.policy_revision,
            whitelist_revision=candidate.whitelist_revision,
            knowledge_scope_sha256=candidate.knowledge_scope_sha256,
            reply_evidence_bundle_sha256=(
                candidate.reply_evidence_bundle_sha256
            ),
            authorization_basis="QUALITY_GATED_LOW_RISK",
            deployment_scope=deployment_scope,
            issued_at=now,
        )
        request = self._request(
            current=current,
            operator_reference=operator_reference,
            grant=grant,
            now=now,
        )
        try:
            response = self._post(request, "AUTO_POLICY_PILOT_SEND")
        except Exception:
            self._close_safely(window.window_id, "GENERAL_AUTO_POST_FAILED")
            raise
        if response.outcome != "SUCCESS" or response.customer_message_sent is not True:
            self._close_safely(window.window_id, f"GENERAL_AUTO_{response.outcome}")
            return response
        self._close_safely(window.window_id, "GENERAL_AUTO_SUCCESS_CONFIRMED")
        return response

    def current_general_auto_candidate(
        self,
        *,
        policy_revision: int,
        whitelist_revision: str,
    ) -> ReplyPilotCandidateV1 | None:
        current = self._candidate_if_available(
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
            expected_policy_mode="AUTO_LOW_RISK",
        )
        return current.candidate if current is not None else None

    def revoke(self) -> None:
        active = self.pilot_windows.active(now=self._now())
        if active is not None:
            self.pilot_windows.close(active.window_id, reason="USER_REVOKED", now=self._now())
        self.manual_preview_path.unlink(missing_ok=True)
        self.auto_preview_path.unlink(missing_ok=True)

    def _current_candidate(
        self,
        *,
        policy_revision: int,
        whitelist_revision: str,
        expected_policy_mode: Literal["MANUAL_CONFIRM", "AUTO_LOW_RISK"],
    ) -> _CurrentCandidate:
        current = self._candidate_if_available(
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
            expected_policy_mode=expected_policy_mode,
        )
        if current is None:
            raise ControlledReplyPilotError(
                "the current AI reply is unavailable",
                error_code="PILOT_REPLY_NOT_AVAILABLE",
            )
        return current

    def _candidate_if_available(
        self,
        *,
        policy_revision: int,
        whitelist_revision: str,
        expected_policy_mode: Literal["MANUAL_CONFIRM", "AUTO_LOW_RISK"],
    ) -> _CurrentCandidate | None:
        try:
            feed = json.loads(self.feed_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(feed, dict):
            return None
        safety = feed.get("safety")
        reply = feed.get("reply")
        if (
            not isinstance(safety, dict)
            or not isinstance(reply, dict)
        ):
            return None
        safety_pair = (safety.get("realSend"), safety.get("autoReply"))
        allowed_safety_pairs = (
            {(False, False)}
            if expected_policy_mode == "MANUAL_CONFIRM"
            else {(False, False), (True, True)}
        )
        if safety_pair not in allowed_safety_pairs:
            raise ControlledReplyPilotError(
                "feed send state is inconsistent with the current policy mode",
                error_code="PILOT_FEED_SEND_STATE_INVALID",
            )
        decision_id = self._required_string(reply, "decisionId")
        stored = self.buffer.load_reply(decision_id)
        if stored is None:
            return None
        context, package = stored
        reply_text = package.reply_content or ""
        customer_message_id = self._required_string(reply, "messageId")
        if (
            package.decision_id != decision_id
            or package.conversation_id != self._required_string(reply, "conversationId")
            or package.reply_content != reply.get("answer")
            or package.state != "WAITING_APPROVAL"
            or reply.get("state") != "WAITING_APPROVAL"
        ):
            raise ControlledReplyPilotError(
                "feed and durable AI package disagree",
                error_code="PILOT_REPLY_PACKAGE_MISMATCH",
            )
        quality = str(
            reply.get("qualityStatus") or package.quality_gate_status
        ).upper()
        policy_mode = str(reply.get("policyMode") or "").upper()
        if not policy_mode:
            policy_mode = expected_policy_mode
        if (
            quality != "PASS"
            or policy_mode != expected_policy_mode
            or package.action != "SUGGEST_REPLY"
            or package.ai_cs_action != "DIRECT_ANSWER"
            or package.risk_level.value != "LOW"
            or bool(package.required_fields)
            or not reply_text
        ):
            raise ControlledReplyPilotError(
                "the AI package is not an eligible low-risk direct answer",
                error_code="PILOT_QUALITY_GATE_BLOCKED",
            )
        ai_cs_store_id: str | None = None
        platform_store_id: str | None = None
        if self._store_identity_provider is not None:
            try:
                ai_cs_store_id, platform_store_id = self._store_identity_provider()
            except Exception as exc:
                raise ControlledReplyPilotError(
                    "current double Store identity is unavailable",
                    error_code="PILOT_DOUBLE_STORE_IDENTITY_UNAVAILABLE",
                ) from exc
        candidate = ReplyPilotCandidateV1(
            store_id=package.store_id,
            ai_cs_store_id=ai_cs_store_id,
            platform_store_id=platform_store_id,
            test_buyer_hash=package.customer_reference,
            conversation_id=package.conversation_id,
            customer_message_id=customer_message_id,
            decision_id=package.decision_id,
            normalized_question_sha256=normalized_question_sha256(
                package.customer_question
            ),
            approved_reply_sha256=hashlib.sha256(
                reply_text.encode("utf-8")
            ).hexdigest(),
            product_id=context.page.product.product_reference,
            sku_id=context.page.product.sku_reference,
            policy_mode=expected_policy_mode,
            policy_revision=policy_revision,
            whitelist_revision=whitelist_revision,
            knowledge_scope_sha256=knowledge_scope_sha256(package),
            reply_evidence_bundle_sha256=package.evidence_bundle_sha256,
        )
        return _CurrentCandidate(
            candidate=candidate,
            reply_text=reply_text,
            question=package.customer_question,
        )

    def _feed_reply_identity(self) -> tuple[str, str] | None:
        """Return only routing identity without treating a stale MANUAL reply as AUTO."""

        try:
            feed = json.loads(self.feed_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(feed, dict) or not isinstance(feed.get("reply"), dict):
            return None
        reply = feed["reply"]
        decision_id = reply.get("decisionId")
        conversation_id = reply.get("conversationId")
        if (
            not isinstance(decision_id, str)
            or not decision_id.strip()
            or not isinstance(conversation_id, str)
            or not conversation_id.strip()
        ):
            return None
        return decision_id.strip(), conversation_id.strip()

    def _load_verified_baseline(self) -> tuple[AutoPilotBaselineV1, str]:
        try:
            baseline = AutoPilotBaselineV1.model_validate_json(
                self.baseline_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError) as exc:
            raise ControlledReplyPilotError(
                "a successful Stage B baseline is unavailable",
                error_code="STAGE_B_BASELINE_UNAVAILABLE",
            ) from exc
        stored = self.buffer.load_reply(baseline.stage_b_decision_id)
        if stored is None:
            raise ControlledReplyPilotError(
                "the Stage B durable package is unavailable",
                error_code="STAGE_B_PACKAGE_UNAVAILABLE",
            )
        context, package = stored
        reply = package.reply_content or ""
        actual = (
            package.store_id,
            package.customer_reference,
            package.conversation_id,
            normalized_question_sha256(package.customer_question),
            hashlib.sha256(reply.encode("utf-8")).hexdigest(),
            context.page.product.product_reference,
            context.page.product.sku_reference,
            knowledge_scope_sha256(package),
        )
        expected = (
            baseline.store_id,
            baseline.test_buyer_hash,
            baseline.conversation_id,
            baseline.normalized_question_sha256,
            baseline.approved_reply_sha256,
            baseline.product_id,
            baseline.sku_id,
            baseline.knowledge_scope_sha256,
        )
        if actual != expected:
            raise ControlledReplyPilotError(
                "the Stage B durable package no longer matches its baseline",
                error_code="STAGE_B_BASELINE_TAMPERED",
            )
        return baseline, reply

    def _stage_b_question(self, baseline: AutoPilotBaselineV1) -> str:
        stored = self.buffer.load_reply(baseline.stage_b_decision_id)
        if stored is None:
            raise ControlledReplyPilotError(
                "the Stage B question is unavailable",
                error_code="STAGE_B_PACKAGE_UNAVAILABLE",
            )
        return stored[1].customer_question

    @staticmethod
    def _assert_auto_exact(
        candidate: ReplyPilotCandidateV1,
        baseline: AutoPilotBaselineV1,
    ) -> None:
        actual = (
            candidate.store_id,
            candidate.test_buyer_hash,
            candidate.conversation_id,
            candidate.normalized_question_sha256,
            candidate.approved_reply_sha256,
            candidate.product_id,
            candidate.sku_id,
            candidate.knowledge_scope_sha256,
        )
        expected = (
            baseline.store_id,
            baseline.test_buyer_hash,
            baseline.conversation_id,
            baseline.normalized_question_sha256,
            baseline.approved_reply_sha256,
            baseline.product_id,
            baseline.sku_id,
            baseline.knowledge_scope_sha256,
        )
        if actual != expected:
            error_code = (
                "REPLY_HASH_MISMATCH"
                if candidate.approved_reply_sha256 != baseline.approved_reply_sha256
                else "AUTO_PILOT_SCOPE_MISMATCH"
            )
            raise ControlledReplyPilotError(
                "the new AUTO decision does not exactly match the Stage B baseline",
                error_code=error_code,
            )

    @staticmethod
    def _auto_authorization_digest(
        baseline: AutoPilotBaselineV1,
        *,
        policy_revision: int,
        whitelist_revision: str,
    ) -> str:
        canonical = json.dumps(
            {
                "baseline_digest": baseline.digest(),
                "policy_mode": "AUTO_LOW_RISK",
                "policy_revision": policy_revision,
                "whitelist_revision": whitelist_revision,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _request(
        self,
        *,
        current: _CurrentCandidate,
        operator_reference: str,
        grant: ControlledSendGrantV1 | ControlledAutoPolicyGrantV1,
        now: datetime,
    ) -> ApprovedReplyRequest:
        decision_id = current.candidate.decision_id
        return ApprovedReplyRequest(
            decision_id=decision_id,
            conversation_id=current.candidate.conversation_id,
            customer_message_id=current.candidate.customer_message_id,
            reply_text=current.reply_text,
            operator_reference=operator_reference,
            confirmation_phrase=f"CONFIRM SEND {decision_id}",
            idempotency_key=f"pdd-controlled-send:{decision_id}",
            confirmed_at=now,
            controlled_send_grant=grant,
        )

    def _issue_preview(
        self,
        mode: Literal["MANUAL_CONFIRM", "AUTO_POLICY"],
        candidate_digest: str,
    ) -> ReplyPilotPreviewV1:
        now = self._now()
        raw = secrets.token_hex(6).upper()
        return ReplyPilotPreviewV1(
            mode=mode,
            candidate_digest=candidate_digest,
            confirmation_token=f"{raw[:6]}-{raw[6:]}",
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
        )

    def _load_preview(
        self,
        path: Path,
        *,
        mode: Literal["MANUAL_CONFIRM", "AUTO_POLICY"],
    ) -> ReplyPilotPreviewV1:
        try:
            preview = ReplyPilotPreviewV1.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError) as exc:
            raise ControlledReplyPilotError(
                "the explicit user preview is unavailable",
                error_code="PILOT_PREVIEW_UNAVAILABLE",
            ) from exc
        if preview.mode != mode or self._now() >= preview.expires_at:
            path.unlink(missing_ok=True)
            raise ControlledReplyPilotError(
                "the explicit user preview expired or has the wrong mode",
                error_code="PILOT_PREVIEW_EXPIRED",
            )
        return preview

    @staticmethod
    def _assert_token(preview: ReplyPilotPreviewV1, supplied: str) -> None:
        if not secrets.compare_digest(preview.confirmation_token, supplied.strip().upper()):
            raise ControlledReplyPilotError(
                "the explicit user confirmation token is invalid",
                error_code="PILOT_CONFIRMATION_TOKEN_INVALID",
            )

    def _close_safely(self, window_id: str, reason: str) -> None:
        try:
            self.pilot_windows.close(window_id, reason=reason, now=self._now())
        except ControlledSendGrantError:
            return

    @staticmethod
    def _required_string(value: dict[str, object], key: str) -> str:
        raw = value.get(key)
        if not isinstance(raw, str) or not raw.strip():
            raise ControlledReplyPilotError(
                f"the feed field {key} is unavailable",
                error_code="PILOT_FEED_FIELD_MISSING",
            )
        return raw.strip()

    def _now(self) -> datetime:
        return self._clock().astimezone(UTC)

    @staticmethod
    def _write_json(path: Path, value: BaseModel) -> None:
        atomic_write_bytes(path, value.model_dump_json(indent=2).encode("utf-8"))


def post_approved_reply_http(
    *,
    bridge_url: str,
    allowed_origin: str,
    timeout_seconds: float = 20.0,
) -> PostApprovedReply:
    endpoint = bridge_url.rstrip("/") + "/v1/approved-replies"

    def post(request: ApprovedReplyRequest, intent: str) -> ApprovedReplyResponse:
        raw = request.model_dump_json().encode("utf-8")
        http_request = urllib.request.Request(
            endpoint,
            data=raw,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Origin": allowed_origin,
                "X-Channel-Agent-Intent": intent,
            },
        )
        try:
            with urllib.request.urlopen(http_request, timeout=timeout_seconds) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                code = str(payload.get("error_code") or "APPROVED_REPLY_HTTP_REJECTED")
            except (ValueError, UnicodeError, AttributeError):
                code = "APPROVED_REPLY_HTTP_REJECTED"
            raise ControlledReplyPilotError(
                "the existing approved-reply endpoint rejected the request",
                error_code=code,
            ) from exc
        except OSError as exc:
            raise ControlledReplyPilotError(
                "the existing approved-reply endpoint is unavailable",
                error_code="APPROVED_REPLY_ENDPOINT_UNAVAILABLE",
            ) from exc
        try:
            return ApprovedReplyResponse.model_validate_json(body)
        except ValueError as exc:
            raise ControlledReplyPilotError(
                "the approved-reply endpoint returned an invalid response",
                error_code="APPROVED_REPLY_RESPONSE_INVALID",
            ) from exc

    return post


__all__ = [
    "AutoPilotBaselineV1",
    "ControlledReplyPilotError",
    "ControlledReplyPilotOrchestrator",
    "ReplyPilotCandidateV1",
    "ReplyPilotPreviewV1",
    "post_approved_reply_http",
]
