from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.knowledge_materials.models import KnowledgeMaterial
from app.knowledge_materials.schemas import KnowledgeMaterialStatus
from app.reply_rules.models import ReplyRule, ReplyRuleEvent, utc_now
from app.reply_rules.schemas import (
    ReplyRuleContent,
    ReplyRuleCreate,
    ReplyRuleDraftUpdate,
    ReplyRuleEventListResponse,
    ReplyRuleEventProjection,
    ReplyRuleEventType,
    ReplyRuleListResponse,
    ReplyRuleProjection,
    ReplyRuleReviewDecision,
    ReplyRuleRiskLevel,
    ReplyRuleScopeKind,
    ReplyRuleSourceMaterialEvidence,
    ReplyRuleSourceScope,
    ReplyRuleStatus,
)
from app.test_catalog.models import TestProduct, TestSku, TestStore


_APPROVED_SOURCE_STATES = {
    KnowledgeMaterialStatus.APPROVED_FOR_ANALYSIS.value,
    KnowledgeMaterialStatus.ANALYZING.value,
    KnowledgeMaterialStatus.ANALYZED.value,
}
_SOURCE_EVIDENCE_ADAPTER = TypeAdapter(tuple[ReplyRuleSourceMaterialEvidence, ...])
_SHA256_CONTENT_HASH = re.compile(r"^sha256:([a-f0-9]{64})$")


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


class ReplyRuleService:
    def __init__(self, session: Session, actor_user_id: str) -> None:
        self.session = session
        self.actor_user_id = actor_user_id

    def create(self, payload: ReplyRuleCreate) -> ReplyRuleProjection:
        self._validate_catalog_scope(payload)
        rule_id = payload.rule_id or f"RR-{uuid4().hex[:20].upper()}"
        if self.session.scalar(
            select(ReplyRule.id).where(ReplyRule.rule_id == rule_id)
        ) is not None:
            raise AppError(
                "REPLY_RULE_ID_CONFLICT",
                "该固定回复规则编号已经存在。",
                status_code=409,
            )
        content = payload.model_dump(
            exclude={"rule_id", "change_reason"}, mode="python"
        )
        row = self._new_row(rule_id=rule_id, rule_version=1, content=content)
        self.session.add(row)
        self.session.flush()
        self._record_event(
            row,
            ReplyRuleEventType.CREATED,
            previous_status=None,
            reason=payload.change_reason,
        )
        self._commit_or_conflict()
        return self._projection(row)

    def update_draft(
        self, rule_id: str, rule_version: int, payload: ReplyRuleDraftUpdate
    ) -> ReplyRuleProjection:
        row = self._rule_or_404(rule_id, rule_version)
        self._require_status(row, ReplyRuleStatus.DRAFT)
        self._validate_catalog_scope(payload)
        content = payload.model_dump(exclude={"change_reason"}, mode="python")
        self._apply_content(row, content)
        row.content_fingerprint = self._content_fingerprint(
            rule_id, rule_version, content
        )
        row.updated_at = utc_now()
        self._record_event(
            row,
            ReplyRuleEventType.DRAFT_UPDATED,
            previous_status=ReplyRuleStatus.DRAFT,
            reason=payload.change_reason,
        )
        self.session.commit()
        return self._projection(row)

    def submit_review(
        self, rule_id: str, rule_version: int, reason: str
    ) -> ReplyRuleProjection:
        row = self._rule_or_404(rule_id, rule_version)
        self._require_status(row, ReplyRuleStatus.DRAFT)
        previous = ReplyRuleStatus.DRAFT
        row.status = ReplyRuleStatus.IN_REVIEW.value
        row.updated_at = utc_now()
        self._record_event(
            row,
            ReplyRuleEventType.REVIEW_SUBMITTED,
            previous_status=previous,
            reason=reason,
        )
        self.session.commit()
        return self._projection(row)

    def review(
        self,
        rule_id: str,
        rule_version: int,
        decision: ReplyRuleReviewDecision,
        reason: str,
    ) -> ReplyRuleProjection:
        row = self._rule_or_404(rule_id, rule_version)
        self._require_status(row, ReplyRuleStatus.IN_REVIEW)
        if decision is ReplyRuleReviewDecision.APPROVE:
            source_evidence = self.validate_publishable(row)
            row.source_material_evidence_json = json.dumps(
                [item.model_dump(mode="json") for item in source_evidence],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            next_status = ReplyRuleStatus.APPROVED
            event_type = ReplyRuleEventType.APPROVED
        else:
            row.source_material_evidence_json = "[]"
            next_status = ReplyRuleStatus.REJECTED
            event_type = ReplyRuleEventType.REJECTED
        row.status = next_status.value
        row.reviewed_by = self.actor_user_id
        row.reviewed_at = utc_now()
        row.review_note = reason
        row.updated_at = row.reviewed_at
        self._record_event(
            row,
            event_type,
            previous_status=ReplyRuleStatus.IN_REVIEW,
            reason=reason,
        )
        self.session.commit()
        return self._projection(row)

    def create_revision(self, rule_id: str, reason: str) -> ReplyRuleProjection:
        source = self._latest_rule_or_404(rule_id)
        if ReplyRuleStatus(source.status) not in {
            ReplyRuleStatus.APPROVED,
            ReplyRuleStatus.REJECTED,
            ReplyRuleStatus.PUBLISHED,
            ReplyRuleStatus.WITHDRAWN,
            ReplyRuleStatus.EXPIRED,
        }:
            raise AppError(
                "REPLY_RULE_STATE_INVALID",
                "当前版本完成审核后才能创建下一修订版本。",
                status_code=409,
            )
        content = self._content_from_row(source)
        row = self._new_row(
            rule_id=rule_id,
            rule_version=source.rule_version + 1,
            content=content,
        )
        self.session.add(row)
        self.session.flush()
        self._record_event(
            row,
            ReplyRuleEventType.REVISION_CREATED,
            previous_status=ReplyRuleStatus(source.status),
            reason=reason,
        )
        self._commit_or_conflict()
        return self._projection(row)

    def get(self, rule_id: str, rule_version: int) -> ReplyRuleProjection:
        return self._projection(self._rule_or_404(rule_id, rule_version))

    def list(
        self,
        *,
        status: ReplyRuleStatus | None,
        store_code: str | None,
        product_id: str | None,
        page: int,
        size: int,
    ) -> ReplyRuleListResponse:
        statement = select(ReplyRule)
        if status is not None:
            statement = statement.where(ReplyRule.status == status.value)
        if store_code:
            statement = statement.where(ReplyRule.store_code == store_code)
        if product_id:
            statement = statement.where(ReplyRule.product_id == product_id)
        total = self.session.scalar(
            select(func.count()).select_from(statement.subquery())
        ) or 0
        rows = self.session.scalars(
            statement.order_by(
                ReplyRule.updated_at.desc(),
                ReplyRule.rule_id,
                ReplyRule.rule_version.desc(),
            )
            .offset((page - 1) * size)
            .limit(size)
        ).all()
        return ReplyRuleListResponse(
            items=[self._projection(row) for row in rows],
            total=total,
            page=page,
            size=size,
        )

    def events(self, rule_id: str) -> ReplyRuleEventListResponse:
        if self.session.scalar(
            select(ReplyRule.id).where(ReplyRule.rule_id == rule_id).limit(1)
        ) is None:
            raise AppError(
                "REPLY_RULE_NOT_FOUND", "未找到固定回复规则。", status_code=404
            )
        rows = self.session.scalars(
            select(ReplyRuleEvent)
            .where(ReplyRuleEvent.rule_id == rule_id)
            .order_by(
                ReplyRuleEvent.occurred_at,
                ReplyRuleEvent.rule_version,
                ReplyRuleEvent.event_id,
            )
        ).all()
        return ReplyRuleEventListResponse(
            items=[self._event_projection(row) for row in rows], total=len(rows)
        )

    def _validate_catalog_scope(self, content: ReplyRuleContent) -> None:
        if content.scope_kind is ReplyRuleScopeKind.TENANT:
            if self.session.scalar(
                select(TestStore.id).where(
                    TestStore.tenant_id == content.tenant_id,
                    TestStore.platform == content.platform,
                )
            ) is None:
                raise AppError(
                    "REPLY_RULE_SCOPE_INVALID",
                    "规则租户或平台不在当前C目录中。",
                    status_code=422,
                )
            return
        store = self.session.scalar(
            select(TestStore).where(TestStore.store_code == content.store_code)
        )
        if (
            store is None
            or store.tenant_id != content.tenant_id
            or store.platform != content.platform
        ):
            raise AppError(
                "REPLY_RULE_SCOPE_INVALID",
                "规则店铺与租户或平台不匹配。",
                status_code=422,
            )
        if content.scope_kind is ReplyRuleScopeKind.STORE:
            return
        product = self.session.get(TestProduct, content.product_id)
        if (
            product is None
            or product.tenant_id != content.tenant_id
            or product.platform != content.platform
            or product.store_code != content.store_code
        ):
            raise AppError(
                "REPLY_RULE_SCOPE_INVALID",
                "规则商品不属于指定店铺范围。",
                status_code=422,
            )
        if content.scope_kind is ReplyRuleScopeKind.PRODUCT:
            return
        sku = self.session.get(TestSku, content.sku_id)
        if sku is None or sku.product_id != content.product_id:
            raise AppError(
                "REPLY_RULE_SCOPE_INVALID",
                "规则SKU不属于指定商品范围。",
                status_code=422,
            )

    def validate_publishable(
        self,
        row: ReplyRule,
        *,
        require_bound_evidence: bool = False,
    ) -> tuple[ReplyRuleSourceMaterialEvidence, ...]:
        now = utc_now()
        if row.effective_to is not None and _as_utc(row.effective_to) <= now:
            raise AppError(
                "REPLY_RULE_EXPIRED",
                "已超过有效期的固定回复规则不能审核通过。",
                status_code=409,
            )
        if not row.source_confirmed:
            raise AppError(
                "REPLY_RULE_SOURCE_UNCONFIRMED",
                "固定回复事实来源尚未人工确认。",
                status_code=409,
            )
        if (
            row.risk_level == ReplyRuleRiskLevel.HIGH.value
            and not row.high_risk_source_confirmed
        ):
            raise AppError(
                "REPLY_RULE_HIGH_RISK_UNCONFIRMED",
                "高风险规则缺少独立来源确认。",
                status_code=409,
            )
        source_ids = json.loads(row.source_material_ids_json)
        current_evidence: list[ReplyRuleSourceMaterialEvidence] = []
        for material_id in source_ids:
            material = self.session.scalar(
                select(KnowledgeMaterial)
                .where(KnowledgeMaterial.material_id == material_id)
                .order_by(KnowledgeMaterial.revision.desc())
                .limit(1)
            )
            if material is None or material.material_status not in _APPROVED_SOURCE_STATES:
                raise AppError(
                    "REPLY_RULE_SOURCE_NOT_APPROVED",
                    "固定回复规则只能引用已人工审核通过的资料版本。",
                    status_code=409,
                )
            if material.reviewed_by is None or material.reviewed_at is None:
                raise AppError(
                    "REPLY_RULE_SOURCE_REVIEW_EVIDENCE_MISSING",
                    "固定回复来源缺少人工审核身份或时间。",
                    status_code=409,
                )
            content_hash_match = _SHA256_CONTENT_HASH.fullmatch(
                material.content_hash
            )
            if content_hash_match is None:
                raise AppError(
                    "REPLY_RULE_SOURCE_FINGERPRINT_INVALID",
                    "固定回复来源内容指纹无效。",
                    status_code=409,
                )
            product = self.session.get(TestProduct, material.product_id)
            if (
                product is None
                or product.tenant_id != row.tenant_id
                or product.platform != row.platform
                or product.store_code != material.store_code
            ):
                raise AppError(
                    "REPLY_RULE_SOURCE_SCOPE_MISMATCH",
                    "固定回复来源越过了规则业务范围。",
                    status_code=409,
                )
            if material.sku_id is None:
                source_scope = ReplyRuleSourceScope(
                    scope_kind=ReplyRuleScopeKind.PRODUCT,
                    tenant_id=product.tenant_id,
                    platform=product.platform,
                    store_code=product.store_code,
                    product_id=product.product_id,
                )
            else:
                sku = self.session.get(TestSku, material.sku_id)
                if sku is None or sku.product_id != material.product_id:
                    raise AppError(
                        "REPLY_RULE_SOURCE_SCOPE_MISMATCH",
                        "固定回复来源SKU不属于来源商品。",
                        status_code=409,
                    )
                source_scope = ReplyRuleSourceScope(
                    scope_kind=ReplyRuleScopeKind.SKU,
                    tenant_id=product.tenant_id,
                    platform=product.platform,
                    store_code=product.store_code,
                    product_id=product.product_id,
                    sku_id=material.sku_id,
                )
            if not self._source_scope_supports_rule(source_scope, row):
                raise AppError(
                    "REPLY_RULE_SOURCE_SCOPE_TOO_NARROW",
                    "固定回复来源范围窄于规则范围，不能将局部事实推广使用。",
                    status_code=409,
                )
            current_evidence.append(
                ReplyRuleSourceMaterialEvidence(
                    material_id=material.material_id,
                    revision=material.revision,
                    content_sha256=content_hash_match.group(1),
                    governance_status="REVIEWED_VALID",
                    scope=source_scope,
                    reviewed_by=material.reviewed_by,
                    reviewed_at=_as_utc(material.reviewed_at),
                )
            )

        evidence = tuple(current_evidence)
        if require_bound_evidence:
            bound = self.bound_source_evidence(row)
            if not bound:
                raise AppError(
                    "REPLY_RULE_SOURCE_EVIDENCE_MISSING",
                    "固定回复规则没有绑定审核时的来源版本证据。",
                    status_code=409,
                )
            if _canonical_sha256(
                [item.model_dump(mode="json") for item in bound]
            ) != _canonical_sha256(
                [item.model_dump(mode="json") for item in evidence]
            ):
                raise AppError(
                    "REPLY_RULE_SOURCE_EVIDENCE_STALE",
                    "固定回复来源版本已经变化，必须新建规则版本并重新审核。",
                    status_code=409,
                )
        return evidence

    @staticmethod
    def _source_scope_supports_rule(
        source: ReplyRuleSourceScope,
        row: ReplyRule,
    ) -> bool:
        if source.tenant_id != row.tenant_id or source.platform != row.platform:
            return False
        if source.scope_kind is ReplyRuleScopeKind.TENANT:
            return True
        if row.scope_kind == ReplyRuleScopeKind.TENANT.value:
            return False
        if source.store_code != row.store_code:
            return False
        if source.scope_kind is ReplyRuleScopeKind.STORE:
            return True
        if row.scope_kind == ReplyRuleScopeKind.STORE.value:
            return False
        if source.product_id != row.product_id:
            return False
        if source.scope_kind is ReplyRuleScopeKind.PRODUCT:
            return True
        return (
            row.scope_kind == ReplyRuleScopeKind.SKU.value
            and source.scope_kind is ReplyRuleScopeKind.SKU
            and source.sku_id == row.sku_id
        )

    @staticmethod
    def bound_source_evidence(
        row: ReplyRule,
    ) -> tuple[ReplyRuleSourceMaterialEvidence, ...]:
        try:
            return _SOURCE_EVIDENCE_ADAPTER.validate_json(
                row.source_material_evidence_json
            )
        except (ValidationError, ValueError) as exc:
            raise AppError(
                "REPLY_RULE_SOURCE_EVIDENCE_INVALID",
                "固定回复规则的来源证据结构无效。",
                status_code=409,
            ) from exc

    def _new_row(
        self, *, rule_id: str, rule_version: int, content: dict[str, object]
    ) -> ReplyRule:
        row = ReplyRule(
            rule_id=rule_id,
            rule_version=rule_version,
            status=ReplyRuleStatus.DRAFT.value,
            created_by=self.actor_user_id,
            source_material_evidence_json="[]",
        )
        self._apply_content(row, content)
        row.content_fingerprint = self._content_fingerprint(
            rule_id, rule_version, content
        )
        return row

    @staticmethod
    def _apply_content(row: ReplyRule, content: dict[str, object]) -> None:
        for field in (
            "tenant_id",
            "platform",
            "scope_kind",
            "store_code",
            "product_id",
            "sku_id",
            "canonical_question",
            "fixed_reply",
            "action",
            "risk_level",
            "allow_auto_candidate",
            "source_confirmed",
            "high_risk_source_confirmed",
            "effective_from",
            "effective_to",
        ):
            value = content[field]
            setattr(row, field, value.value if hasattr(value, "value") else value)
        for field in (
            "aliases",
            "variable_names",
            "required_context_fields",
            "prohibited_claims",
            "source_material_ids",
        ):
            setattr(
                row,
                f"{field}_json",
                json.dumps(content[field], ensure_ascii=False, separators=(",", ":")),
            )

    @staticmethod
    def _content_fingerprint(
        rule_id: str, rule_version: int, content: dict[str, object]
    ) -> str:
        serialized = ReplyRuleContent.model_validate(content).model_dump(mode="json")
        source_only = {
            key: serialized.pop(key)
            for key in (
                "source_material_ids",
                "source_confirmed",
                "high_risk_source_confirmed",
            )
        }
        del source_only
        scope = {
            "scope_kind": serialized.pop("scope_kind"),
            "tenant_id": serialized.pop("tenant_id"),
            "platform": serialized.pop("platform"),
            "store_code": serialized.pop("store_code"),
            "product_id": serialized.pop("product_id"),
            "sku_id": serialized.pop("sku_id"),
        }
        return _canonical_sha256(
            {
                "schema_version": "reply-rule.v1",
                "rule_id": rule_id,
                "rule_version": rule_version,
                "scope": scope,
                **serialized,
            }
        )

    @staticmethod
    def _content_from_row(row: ReplyRule) -> dict[str, object]:
        return {
            "tenant_id": row.tenant_id,
            "platform": row.platform,
            "scope_kind": row.scope_kind,
            "store_code": row.store_code,
            "product_id": row.product_id,
            "sku_id": row.sku_id,
            "canonical_question": row.canonical_question,
            "aliases": json.loads(row.aliases_json),
            "fixed_reply": row.fixed_reply,
            "variable_names": json.loads(row.variable_names_json),
            "action": row.action,
            "risk_level": row.risk_level,
            "required_context_fields": json.loads(row.required_context_fields_json),
            "prohibited_claims": json.loads(row.prohibited_claims_json),
            "allow_auto_candidate": row.allow_auto_candidate,
            "source_material_ids": json.loads(row.source_material_ids_json),
            "source_confirmed": row.source_confirmed,
            "high_risk_source_confirmed": row.high_risk_source_confirmed,
            "effective_from": _as_utc(row.effective_from),
            "effective_to": (
                _as_utc(row.effective_to) if row.effective_to is not None else None
            ),
        }

    def _record_event(
        self,
        row: ReplyRule,
        event_type: ReplyRuleEventType,
        *,
        previous_status: ReplyRuleStatus | None,
        reason: str,
    ) -> None:
        self.session.add(
            ReplyRuleEvent(
                rule_record_id=row.id,
                rule_id=row.rule_id,
                rule_version=row.rule_version,
                event_type=event_type.value,
                previous_status=(previous_status.value if previous_status else None),
                next_status=row.status,
                actor_user_id=self.actor_user_id,
                reason=reason,
                content_fingerprint=row.content_fingerprint,
            )
        )

    def _rule_or_404(self, rule_id: str, rule_version: int) -> ReplyRule:
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
        return row

    def _latest_rule_or_404(self, rule_id: str) -> ReplyRule:
        row = self.session.scalar(
            select(ReplyRule)
            .where(ReplyRule.rule_id == rule_id)
            .order_by(ReplyRule.rule_version.desc())
            .limit(1)
        )
        if row is None:
            raise AppError(
                "REPLY_RULE_NOT_FOUND", "未找到固定回复规则。", status_code=404
            )
        return row

    @staticmethod
    def _require_status(row: ReplyRule, expected: ReplyRuleStatus) -> None:
        if row.status != expected.value:
            raise AppError(
                "REPLY_RULE_STATE_INVALID",
                f"该操作只允许规则处于{expected.value}状态。",
                status_code=409,
            )

    def _commit_or_conflict(self) -> None:
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise AppError(
                "REPLY_RULE_VERSION_CONFLICT",
                "固定回复规则版本发生并发冲突。",
                status_code=409,
            ) from None

    @classmethod
    def _projection(cls, row: ReplyRule) -> ReplyRuleProjection:
        return ReplyRuleProjection(
            rule_id=row.rule_id,
            rule_version=row.rule_version,
            status=ReplyRuleStatus(row.status),
            **cls._content_from_row(row),
            content_fingerprint=row.content_fingerprint,
            created_by=row.created_by,
            reviewed_by=row.reviewed_by,
            reviewed_at=row.reviewed_at,
            review_note=row.review_note,
            source_material_evidence=list(cls.bound_source_evidence(row)),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _event_projection(row: ReplyRuleEvent) -> ReplyRuleEventProjection:
        return ReplyRuleEventProjection(
            event_id=row.event_id,
            rule_id=row.rule_id,
            rule_version=row.rule_version,
            event_type=ReplyRuleEventType(row.event_type),
            previous_status=(
                ReplyRuleStatus(row.previous_status) if row.previous_status else None
            ),
            next_status=ReplyRuleStatus(row.next_status),
            actor_user_id=row.actor_user_id,
            reason=row.reason,
            content_fingerprint=row.content_fingerprint,
            occurred_at=row.occurred_at,
        )
