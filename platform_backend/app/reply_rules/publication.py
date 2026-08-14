from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError
from app.knowledge_publishing.ai_client import (
    AiKnowledgePublicationClient,
    AiKnowledgePublicationUnavailable,
)
from app.reply_rules.models import (
    ReplyRule,
    ReplyRuleEvent,
    ReplyRuleSnapshotPublication,
    ReplyRuleSnapshotPublicationIdempotency,
    ReplyRuleSnapshotPublicationReceipt,
    utc_now,
)
from app.reply_rules.schemas import (
    ReplyRuleEventType,
    ReplyRulePublicationReceiptWire,
    ReplyRuleSnapshotPublicationResponse,
    ReplyRuleSnapshotPublishCommand,
    ReplyRuleSnapshotReceiptListResponse,
    ReplyRuleSnapshotReceiptProjection,
    ReplyRuleStatus,
    ReplyRuleSourceMaterialEvidence,
)
from app.reply_rules.service import ReplyRuleService


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _json_datetime(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


class ReplyRulePublicationService:
    def __init__(
        self,
        session: Session,
        actor_user_id: str,
        ai_client: AiKnowledgePublicationClient | None = None,
        lease_seconds: int | None = None,
    ) -> None:
        self.session = session
        self.actor_user_id = actor_user_id
        self.ai_client = ai_client or AiKnowledgePublicationClient()
        self.lease_seconds = (
            lease_seconds or get_settings().knowledge_publication_lease_seconds
        )

    def publish(
        self,
        command: ReplyRuleSnapshotPublishCommand,
        idempotency_key: str | None,
        *,
        withdrawal_target: tuple[str, int] | None = None,
    ) -> tuple[ReplyRuleSnapshotPublicationResponse, bool]:
        key = self._require_key(idempotency_key)
        request_fingerprint = _canonical_sha256(
            {
                "command": command.model_dump(mode="json"),
                "withdrawal_target": withdrawal_target,
                "actor_user_id": self.actor_user_id,
            }
        )
        replay = self.session.get(ReplyRuleSnapshotPublicationIdempotency, key)
        if replay is not None:
            if replay.request_fingerprint != request_fingerprint:
                raise AppError(
                    "REPLY_RULE_PUBLICATION_IDEMPOTENCY_CONFLICT",
                    "Idempotency-Key已用于另一项规则发布操作。",
                    status_code=409,
                )
            return ReplyRuleSnapshotPublicationResponse.model_validate_json(
                replay.response_json
            ), True

        target = self._withdrawal_target(command, withdrawal_target)
        now = utc_now()
        selected, excluded, source_evidence = self._effective_rules(
            command, target, now
        )
        scope_key = self._scope_key(command.tenant_id, command.platform)
        current = self.session.get(ReplyRuleSnapshotPublication, scope_key)
        if not selected and current is None:
            raise AppError(
                "REPLY_RULE_PUBLICATION_EMPTY",
                "当前范围没有可发布的已审核固定回复规则。",
                status_code=409,
            )

        rules = [
            self._wire_rule(row, source_evidence[row.id]) for row in selected
        ]
        rules_fingerprint = _canonical_sha256(rules)
        same_rules = bool(current and current.rules_fingerprint == rules_fingerprint)
        expected_changed = not same_rules
        snapshot_revision = (
            current.snapshot_revision
            if same_rules
            else (current.snapshot_revision if current else 0) + 1
        )
        snapshot_fingerprint = _canonical_sha256(
            {
                "tenant_id": command.tenant_id,
                "platform": command.platform,
                "snapshot_revision": snapshot_revision,
                "rules": rules,
            }
        )
        publication_id = "RRP-" + hashlib.sha256(
            f"{scope_key}\0{key}".encode("utf-8")
        ).hexdigest()[:32]
        payload = {
            "schema_version": "reply-rule-publication.v1",
            "publication_id": publication_id,
            "idempotency_key": key,
            "tenant_id": command.tenant_id,
            "platform": command.platform,
            "snapshot_revision": snapshot_revision,
            "rules": rules,
            "snapshot_fingerprint": snapshot_fingerprint,
            "produced_by": self.actor_user_id,
            "produced_at": _json_datetime(now),
        }

        generation_token = self._claim(scope_key, command, current, now)
        try:
            result = self.ai_client.publish_reply_rules(payload)
            published_at = self._validate_receipt(
                result,
                publication_id=publication_id,
                command=command,
                snapshot_revision=snapshot_revision,
                snapshot_fingerprint=snapshot_fingerprint,
                rule_count=len(rules),
                expected_changed=expected_changed,
            )
        except (AiKnowledgePublicationUnavailable, KeyError, TypeError, ValueError) as exc:
            self._record_failure(scope_key, generation_token)
            raise AppError(
                "REPLY_RULE_PUBLICATION_FAILED",
                "固定回复规则同步失败，A继续使用上一有效快照。",
                status_code=502,
            ) from exc

        current = self.session.get(ReplyRuleSnapshotPublication, scope_key)
        if current is None or current.generation_token != generation_token:
            raise AppError(
                "REPLY_RULE_PUBLICATION_LEASE_LOST",
                "固定回复规则发布租约已失效。",
                status_code=409,
            )
        changed = expected_changed
        receipt = ReplyRuleSnapshotPublicationReceipt(
            publication_receipt_id=publication_id,
            publication_id=publication_id,
            scope_key=scope_key,
            tenant_id=command.tenant_id,
            platform=command.platform,
            snapshot_revision=snapshot_revision,
            snapshot_fingerprint=snapshot_fingerprint,
            rules_fingerprint=rules_fingerprint,
            accepted_rule_count=len(rules),
            changed=changed,
            operator=self.actor_user_id,
            published_at=published_at,
        )
        if self.session.get(
            ReplyRuleSnapshotPublicationReceipt, publication_id
        ) is None:
            self.session.add(receipt)

        if changed:
            self._apply_rule_states(
                selected=selected,
                excluded=excluded,
                target=target,
                reason=command.confirmation_note,
            )
        current.status = "PUBLISHED"
        current.snapshot_revision = snapshot_revision
        current.snapshot_fingerprint = snapshot_fingerprint
        current.rules_fingerprint = rules_fingerprint
        current.rule_count = len(rules)
        current.publication_receipt_id = publication_id
        current.generation_token = None
        current.generation_started_at = None
        current.last_error_code = None
        current.published_at = published_at
        current.updated_at = utc_now()
        response = ReplyRuleSnapshotPublicationResponse(
            changed=changed,
            tenant_id=command.tenant_id,
            platform=command.platform,
            snapshot_revision=snapshot_revision,
            snapshot_fingerprint=snapshot_fingerprint,
            rules_fingerprint=rules_fingerprint,
            accepted_rule_count=len(rules),
            publication_receipt=self._receipt(receipt),
        )
        self.session.add(
            ReplyRuleSnapshotPublicationIdempotency(
                idempotency_key=key,
                request_fingerprint=request_fingerprint,
                response_json=response.model_dump_json(),
            )
        )
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            self._record_failure(scope_key, generation_token)
            raise AppError(
                "REPLY_RULE_PUBLICATION_IDEMPOTENCY_CONFLICT",
                "固定回复规则发布回执发生并发冲突。",
                status_code=409,
            ) from None
        except SQLAlchemyError:
            self.session.rollback()
            self._record_failure(scope_key, generation_token)
            raise AppError(
                "REPLY_RULE_PUBLICATION_LOCAL_COMMIT_FAILED",
                "固定回复规则发布回执未能本地落账；A回执可用于安全重试。",
                status_code=503,
            ) from None
        return response, False

    def withdraw(
        self,
        rule_id: str,
        rule_version: int,
        reason: str,
        idempotency_key: str | None,
    ) -> tuple[ReplyRuleSnapshotPublicationResponse, bool]:
        row = self.session.scalar(
            select(ReplyRule).where(
                ReplyRule.rule_id == rule_id,
                ReplyRule.rule_version == rule_version,
            )
        )
        if row is None:
            raise AppError(
                "REPLY_RULE_NOT_FOUND", "未找到固定回复规则版本。", status_code=404
            )
        return self.publish(
            ReplyRuleSnapshotPublishCommand(
                tenant_id=row.tenant_id,
                platform=row.platform,
                confirmation_note=reason,
            ),
            idempotency_key,
            withdrawal_target=(rule_id, rule_version),
        )

    def list_receipts(
        self, tenant_id: str, platform: str
    ) -> ReplyRuleSnapshotReceiptListResponse:
        rows = self.session.scalars(
            select(ReplyRuleSnapshotPublicationReceipt)
            .where(
                ReplyRuleSnapshotPublicationReceipt.tenant_id == tenant_id,
                ReplyRuleSnapshotPublicationReceipt.platform == platform,
            )
            .order_by(
                ReplyRuleSnapshotPublicationReceipt.published_at.desc(),
                ReplyRuleSnapshotPublicationReceipt.publication_id.desc(),
            )
        ).all()
        return ReplyRuleSnapshotReceiptListResponse(
            items=[self._receipt(row) for row in rows], total=len(rows)
        )

    def _withdrawal_target(
        self,
        command: ReplyRuleSnapshotPublishCommand,
        withdrawal_target: tuple[str, int] | None,
    ) -> ReplyRule | None:
        if withdrawal_target is None:
            return None
        target = self.session.scalar(
            select(ReplyRule).where(
                ReplyRule.rule_id == withdrawal_target[0],
                ReplyRule.rule_version == withdrawal_target[1],
            )
        )
        if (
            target is None
            or target.tenant_id != command.tenant_id
            or target.platform != command.platform
        ):
            raise AppError(
                "REPLY_RULE_NOT_FOUND", "未找到固定回复规则版本。", status_code=404
            )
        if target.status != ReplyRuleStatus.PUBLISHED.value:
            raise AppError(
                "REPLY_RULE_STATE_INVALID",
                "只有已发布的固定回复规则可以撤回。",
                status_code=409,
            )
        return target

    def _effective_rules(
        self,
        command: ReplyRuleSnapshotPublishCommand,
        target: ReplyRule | None,
        now: datetime,
    ) -> tuple[
        list[ReplyRule],
        list[tuple[ReplyRule, ReplyRuleStatus]],
        dict[str, tuple[ReplyRuleSourceMaterialEvidence, ...]],
    ]:
        rows = list(
            self.session.scalars(
                select(ReplyRule)
                .where(
                    ReplyRule.tenant_id == command.tenant_id,
                    ReplyRule.platform == command.platform,
                    ReplyRule.status.in_(
                        [
                            ReplyRuleStatus.APPROVED.value,
                            ReplyRuleStatus.PUBLISHED.value,
                        ]
                    ),
                )
                .order_by(ReplyRule.rule_id, ReplyRule.rule_version.desc())
            )
        )
        selected: dict[str, ReplyRule] = {}
        excluded: list[tuple[ReplyRule, ReplyRuleStatus]] = []
        source_evidence: dict[
            str, tuple[ReplyRuleSourceMaterialEvidence, ...]
        ] = {}
        validator = ReplyRuleService(self.session, self.actor_user_id)
        for row in rows:
            if target is not None and row.id == target.id:
                excluded.append((row, ReplyRuleStatus.WITHDRAWN))
                continue
            effective_from = _as_utc(row.effective_from)
            effective_to = _as_utc(row.effective_to) if row.effective_to else None
            if effective_to is not None and effective_to <= now:
                excluded.append((row, ReplyRuleStatus.EXPIRED))
                continue
            if effective_from > now or row.rule_id in selected:
                continue
            try:
                source_evidence[row.id] = validator.validate_publishable(
                    row, require_bound_evidence=True
                )
            except AppError:
                excluded.append((row, ReplyRuleStatus.WITHDRAWN))
                continue
            selected[row.rule_id] = row
        selected_rows = [selected[key] for key in sorted(selected)]
        return (
            selected_rows,
            excluded,
            {row.id: source_evidence[row.id] for row in selected_rows},
        )

    def _claim(
        self,
        scope_key: str,
        command: ReplyRuleSnapshotPublishCommand,
        current: ReplyRuleSnapshotPublication | None,
        now: datetime,
    ) -> str:
        generation_token = str(uuid4())
        if current is None:
            self.session.add(
                ReplyRuleSnapshotPublication(
                    scope_key=scope_key,
                    tenant_id=command.tenant_id,
                    platform=command.platform,
                    status="GENERATING",
                    snapshot_revision=0,
                    rule_count=0,
                    generation_token=generation_token,
                    generation_started_at=now,
                    updated_at=now,
                )
            )
            try:
                self.session.commit()
            except IntegrityError:
                self.session.rollback()
                raise AppError(
                    "REPLY_RULE_PUBLICATION_IN_PROGRESS",
                    "该范围已有固定回复规则发布正在进行。",
                    status_code=409,
                ) from None
            return generation_token

        lease_cutoff = now - timedelta(seconds=self.lease_seconds)
        claimed = self.session.execute(
            update(ReplyRuleSnapshotPublication)
            .where(
                ReplyRuleSnapshotPublication.scope_key == scope_key,
                or_(
                    ReplyRuleSnapshotPublication.status != "GENERATING",
                    ReplyRuleSnapshotPublication.generation_started_at.is_(None),
                    ReplyRuleSnapshotPublication.generation_started_at <= lease_cutoff,
                ),
            )
            .values(
                status="GENERATING",
                generation_token=generation_token,
                generation_started_at=now,
                last_error_code=None,
                updated_at=now,
            )
        ).rowcount
        if claimed != 1:
            self.session.rollback()
            raise AppError(
                "REPLY_RULE_PUBLICATION_IN_PROGRESS",
                "该范围已有固定回复规则发布正在进行。",
                status_code=409,
            )
        self.session.commit()
        return generation_token

    def _record_failure(self, scope_key: str, generation_token: str) -> None:
        current = self.session.get(ReplyRuleSnapshotPublication, scope_key)
        if current is not None and current.generation_token == generation_token:
            current.status = "SYNC_FAILED"
            current.last_error_code = "REPLY_RULE_PUBLICATION_FAILED"
            current.generation_token = None
            current.generation_started_at = None
            current.updated_at = utc_now()
            self.session.commit()

    def _apply_rule_states(
        self,
        *,
        selected: list[ReplyRule],
        excluded: list[tuple[ReplyRule, ReplyRuleStatus]],
        target: ReplyRule | None,
        reason: str,
    ) -> None:
        selected_ids = {row.id for row in selected}
        selected_rule_ids = {row.rule_id for row in selected}
        for row in selected:
            if row.status == ReplyRuleStatus.APPROVED.value:
                self._transition(
                    row, ReplyRuleStatus.PUBLISHED, ReplyRuleEventType.PUBLISHED, reason
                )
        for row, next_status in excluded:
            if row.id in selected_ids or row.status == next_status.value:
                continue
            self._transition(
                row,
                next_status,
                (
                    ReplyRuleEventType.EXPIRED
                    if next_status is ReplyRuleStatus.EXPIRED
                    else ReplyRuleEventType.WITHDRAWN
                ),
                reason if target is not None and row.id == target.id else "发布快照排除已失效规则",
            )
        superseded = self.session.scalars(
            select(ReplyRule).where(
                ReplyRule.rule_id.in_(selected_rule_ids),
                ReplyRule.status == ReplyRuleStatus.PUBLISHED.value,
                ReplyRule.id.not_in(selected_ids),
            )
        ).all()
        for row in superseded:
            self._transition(
                row,
                ReplyRuleStatus.WITHDRAWN,
                ReplyRuleEventType.WITHDRAWN,
                "已由同规则的新版本替代",
            )

    def _transition(
        self,
        row: ReplyRule,
        next_status: ReplyRuleStatus,
        event_type: ReplyRuleEventType,
        reason: str,
    ) -> None:
        previous = row.status
        row.status = next_status.value
        row.updated_at = utc_now()
        self.session.add(
            ReplyRuleEvent(
                rule_record_id=row.id,
                rule_id=row.rule_id,
                rule_version=row.rule_version,
                event_type=event_type.value,
                previous_status=previous,
                next_status=next_status.value,
                actor_user_id=self.actor_user_id,
                reason=reason,
                content_fingerprint=row.content_fingerprint,
            )
        )

    @staticmethod
    def _wire_rule(
        row: ReplyRule,
        source_evidence: tuple[ReplyRuleSourceMaterialEvidence, ...],
    ) -> dict[str, object]:
        if row.reviewed_by is None or row.reviewed_at is None or row.review_note is None:
            raise AppError(
                "REPLY_RULE_REVIEW_EVIDENCE_MISSING",
                "固定回复规则缺少审核证据。",
                status_code=409,
            )
        return {
            "schema_version": "reply-rule.v1",
            "rule_id": row.rule_id,
            "rule_version": row.rule_version,
            "scope": {
                "scope_kind": row.scope_kind,
                "tenant_id": row.tenant_id,
                "platform": row.platform,
                "store_code": row.store_code,
                "product_id": row.product_id,
                "sku_id": row.sku_id,
            },
            "canonical_question": row.canonical_question,
            "aliases": json.loads(row.aliases_json),
            "fixed_reply": row.fixed_reply,
            "variable_names": json.loads(row.variable_names_json),
            "action": row.action,
            "risk_level": row.risk_level,
            "required_context_fields": json.loads(row.required_context_fields_json),
            "prohibited_claims": json.loads(row.prohibited_claims_json),
            "allow_auto_candidate": row.allow_auto_candidate,
            "source_materials": [
                item.model_dump(mode="json") for item in source_evidence
            ],
            "effective_from": _json_datetime(row.effective_from),
            "effective_to": (
                _json_datetime(row.effective_to) if row.effective_to else None
            ),
            "status": ReplyRuleStatus.PUBLISHED.value,
            "review": {
                "reviewed_by": row.reviewed_by,
                "reviewed_at": _json_datetime(row.reviewed_at),
                "review_note": row.review_note,
            },
            "content_fingerprint": row.content_fingerprint,
        }

    @staticmethod
    def _validate_receipt(
        result: dict[str, object],
        *,
        publication_id: str,
        command: ReplyRuleSnapshotPublishCommand,
        snapshot_revision: int,
        snapshot_fingerprint: str,
        rule_count: int,
        expected_changed: bool,
    ) -> datetime:
        receipt = ReplyRulePublicationReceiptWire.model_validate_json(
            json.dumps(result, ensure_ascii=False, allow_nan=False)
        )
        if (
            receipt.publication_id != publication_id
            or receipt.tenant_id != command.tenant_id
            or receipt.platform != command.platform
            or receipt.snapshot_revision != snapshot_revision
            or receipt.snapshot_fingerprint != snapshot_fingerprint
            or receipt.accepted_rule_count != rule_count
            or receipt.changed is not expected_changed
        ):
            raise ValueError("A固定回复规则发布回执校验失败")
        return receipt.published_at.astimezone(timezone.utc)

    @staticmethod
    def _scope_key(tenant_id: str, platform: str) -> str:
        return hashlib.sha256(f"{tenant_id}\0{platform}".encode("utf-8")).hexdigest()

    @staticmethod
    def _require_key(value: str | None) -> str:
        key = (value or "").strip()
        if not key or len(key) > 255 or "\r" in key or "\n" in key:
            raise AppError(
                "REPLY_RULE_PUBLICATION_IDEMPOTENCY_REQUIRED",
                "必须提供有效的Idempotency-Key。",
                status_code=422,
            )
        return key

    @staticmethod
    def _receipt(
        row: ReplyRuleSnapshotPublicationReceipt,
    ) -> ReplyRuleSnapshotReceiptProjection:
        return ReplyRuleSnapshotReceiptProjection(
            publication_id=row.publication_id,
            tenant_id=row.tenant_id,
            platform=row.platform,
            snapshot_revision=row.snapshot_revision,
            snapshot_fingerprint=row.snapshot_fingerprint,
            changed=row.changed,
            accepted_rule_count=row.accepted_rule_count,
            published_at=row.published_at,
            operator=row.operator,
        )
