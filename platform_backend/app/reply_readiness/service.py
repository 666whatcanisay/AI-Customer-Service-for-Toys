from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.knowledge_materials.models import KnowledgeMaterial
from app.knowledge_publishing.models import ProductKnowledgePublication
from app.reply_readiness.baseline import BASELINE_QUESTIONS, BASELINE_VERSION
from app.reply_readiness.models import ReplyReadinessQuestionSetExtension, ReplyReadinessRun, utc_now
from app.reply_readiness.schemas import (
    ExpectedAction,
    ExtensionScopeKind,
    PddQuestionSetProjection,
    PddReplyReadinessInputV1,
    PddReplyReadinessQuestionV1,
    PddReplyReadinessResultV1,
    QuestionSetExtensionCreate,
    QuestionSetExtensionList,
    QuestionSetExtensionProjection,
    ReplyReadinessExecutionMode,
    ReplyReadinessKnowledgeSnapshotV1,
    ReplyReadinessPublicationStateV1,
    ReplyReadinessRunComparison,
    ReplyReadinessRunCreate,
    ReplyReadinessRunList,
    ReplyReadinessRunProjection,
    ReplyReadinessScopeV1,
    ReplyReadinessVerifiedProductV1,
    RiskLevel,
    canonical_sha256,
)
from app.reply_rules.models import ReplyRuleSnapshotPublication
from app.test_catalog.models import TestProduct, TestSku


_RISK = {RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3}
_ACTION = {
    ExpectedAction.DIRECT_ANSWER: 1,
    ExpectedAction.CONTROLLED_ANSWER: 2,
    ExpectedAction.ASK_CLARIFY: 3,
    ExpectedAction.REQUIRE_LOOKUP: 4,
    ExpectedAction.TRANSFER_HUMAN: 5,
    ExpectedAction.REFUSE: 6,
}
_ROUTER_BUILD_FINGERPRINT = canonical_sha256({"component": "ReplyRouter", "contract": "reply-router.v1"})
_READINESS_TEMPLATES = {"PRODUCT_KNOWLEDGE", "SKU_DIFFERENCE", "FAQ", "SAFETY_RULE"}
_REVIEWED_MATERIAL_STATUSES = {"APPROVED_FOR_ANALYSIS", "ANALYZING", "ANALYZED"}
_DRAFT_OVERLAY_STATUSES = {"RECOGNIZED", "REVIEWING"}


class ReplyReadinessService:
    def __init__(self, session: Session, actor_user_id: str) -> None:
        self.session = session
        self.actor_user_id = actor_user_id

    def scope(self, store_code: str, product_id: str, sku_id: str | None) -> ReplyReadinessScopeV1:
        product = self.session.get(TestProduct, product_id)
        if product is None or product.store_code != store_code:
            raise AppError("REPLY_READINESS_SCOPE_INVALID", "商品不属于当前店铺。", status_code=422)
        if sku_id:
            sku = self.session.get(TestSku, sku_id)
            if sku is None or sku.product_id != product_id:
                raise AppError("REPLY_READINESS_SCOPE_INVALID", "SKU不属于当前商品。", status_code=422)
        return ReplyReadinessScopeV1(
            tenant_id=product.tenant_id,
            platform=product.platform,
            store_code=store_code,
            product_id=product_id,
            sku_id=sku_id,
        )

    @staticmethod
    def _question_dicts(raw: str) -> list[dict[str, object]]:
        value = json.loads(raw)
        if not isinstance(value, list):
            raise ValueError("questions must be a list")
        return [dict(item) for item in value if isinstance(item, dict)]

    def effective_question_set(self, scope: ReplyReadinessScopeV1) -> PddQuestionSetProjection:
        questions = {
            item["question_id"]: PddReplyReadinessQuestionV1.model_validate(item)
            for item in BASELINE_QUESTIONS
        }
        extensions = list(
            self.session.scalars(
                select(ReplyReadinessQuestionSetExtension).where(
                    ReplyReadinessQuestionSetExtension.status == "ACTIVE",
                    ReplyReadinessQuestionSetExtension.store_code == scope.store_code,
                ).order_by(ReplyReadinessQuestionSetExtension.scope_kind, ReplyReadinessQuestionSetExtension.created_at)
            ).all()
        )
        for extension in extensions:
            if extension.scope_kind == ExtensionScopeKind.PRODUCT.value and extension.product_id != scope.product_id:
                continue
            for raw in self._question_dicts(extension.questions_json):
                candidate = PddReplyReadinessQuestionV1.model_validate(raw)
                current = questions.get(candidate.question_id)
                if current is None:
                    questions[candidate.question_id] = candidate
                    continue
                questions[candidate.question_id] = current.model_copy(update={
                    "aliases": list(dict.fromkeys([*current.aliases, *candidate.aliases])),
                    "policy_risk_floor": candidate.policy_risk_floor,
                    "expected_action": candidate.expected_action,
                    "required_fact_keys": candidate.required_fact_keys,
                    "requires_realtime_lookup": candidate.requires_realtime_lookup,
                    "prohibited_claims": candidate.prohibited_claims,
                })
        ordered = sorted(questions.values(), key=lambda item: item.question_id)
        fingerprint = canonical_sha256({
            "baseline_version": BASELINE_VERSION,
            "questions": [item.model_dump(mode="json") for item in ordered],
        })
        return PddQuestionSetProjection(
            baseline_version=BASELINE_VERSION,
            fingerprint=fingerprint,
            questions=ordered,
        )

    def create_extension(self, payload: QuestionSetExtensionCreate) -> QuestionSetExtensionProjection:
        self.scope(payload.store_code, payload.product_id or self._first_product(payload.store_code), None)
        baseline = {
            item["question_id"]: PddReplyReadinessQuestionV1.model_validate(item)
            for item in BASELINE_QUESTIONS
        }
        for candidate in payload.questions:
            current = baseline.get(candidate.question_id)
            if current is None:
                continue
            if candidate.canonical_question != current.canonical_question:
                raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "扩展不能改写全局标准问题。", status_code=422)
            if _RISK[candidate.policy_risk_floor] < _RISK[current.policy_risk_floor]:
                raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "扩展不能降低全局风险。", status_code=422)
            if _ACTION[candidate.expected_action] < _ACTION[current.expected_action]:
                raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "扩展不能放宽回答动作。", status_code=422)
            if not set(current.required_fact_keys).issubset(candidate.required_fact_keys):
                raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "扩展不能移除必需事实。", status_code=422)
            if not set(current.prohibited_claims).issubset(candidate.prohibited_claims):
                raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "扩展不能移除禁止声明。", status_code=422)
            if current.requires_realtime_lookup and not candidate.requires_realtime_lookup:
                raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "扩展不能取消实时查询。", status_code=422)
        extension_id = payload.extension_id or f"RQX-{uuid4().hex[:16].upper()}"
        previous = self.session.scalar(
            select(ReplyReadinessQuestionSetExtension)
            .where(ReplyReadinessQuestionSetExtension.extension_id == extension_id)
            .order_by(ReplyReadinessQuestionSetExtension.version.desc())
            .limit(1)
        )
        if previous is not None:
            previous_questions = {
                item.question_id: item
                for item in (
                    PddReplyReadinessQuestionV1.model_validate(raw)
                    for raw in self._question_dicts(previous.questions_json)
                )
            }
            candidate_ids = {item.question_id for item in payload.questions}
            if not set(previous_questions).issubset(candidate_ids):
                raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "extension revision cannot remove questions", status_code=422)
            for candidate in payload.questions:
                current = previous_questions.get(candidate.question_id)
                if current is None:
                    continue
                if candidate.canonical_question != current.canonical_question:
                    raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "extension revision cannot rewrite canonical question", status_code=422)
                if not set(current.aliases).issubset(candidate.aliases):
                    raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "extension revision cannot remove aliases", status_code=422)
                if current.mandatory and not candidate.mandatory:
                    raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "extension revision cannot remove a mandatory question", status_code=422)
                if _RISK[candidate.policy_risk_floor] < _RISK[current.policy_risk_floor]:
                    raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "extension revision cannot lower risk", status_code=422)
                if _ACTION[candidate.expected_action] < _ACTION[current.expected_action]:
                    raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "extension revision cannot relax action", status_code=422)
                if not set(current.required_fact_keys).issubset(candidate.required_fact_keys):
                    raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "extension revision cannot remove required facts", status_code=422)
                if not set(current.prohibited_claims).issubset(candidate.prohibited_claims):
                    raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "extension revision cannot remove prohibited claims", status_code=422)
                if current.requires_realtime_lookup and not candidate.requires_realtime_lookup:
                    raise AppError("REPLY_READINESS_EXTENSION_RELAXED", "extension revision cannot disable realtime lookup", status_code=422)
            if previous.scope_kind != payload.scope_kind.value or previous.store_code != payload.store_code or previous.product_id != payload.product_id:
                raise AppError("REPLY_READINESS_EXTENSION_SCOPE_CHANGED", "扩展修订不能改变业务范围。", status_code=409)
            previous.status = "RETIRED"
        content = [item.model_dump(mode="json") for item in payload.questions]
        row = ReplyReadinessQuestionSetExtension(
            extension_id=extension_id,
            version=(previous.version + 1 if previous else 1),
            status="ACTIVE",
            scope_kind=payload.scope_kind.value,
            store_code=payload.store_code,
            product_id=payload.product_id,
            questions_json=json.dumps(content, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
            content_fingerprint=canonical_sha256(content),
            change_reason=payload.change_reason,
            created_by=self.actor_user_id,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._extension_projection(row)

    def _first_product(self, store_code: str) -> str:
        product_id = self.session.scalar(select(TestProduct.product_id).where(TestProduct.store_code == store_code).limit(1))
        if not product_id:
            raise AppError("REPLY_READINESS_SCOPE_INVALID", "店铺下没有可用商品。", status_code=422)
        return product_id

    def list_extensions(self, store_code: str, product_id: str | None = None) -> QuestionSetExtensionList:
        statement = select(ReplyReadinessQuestionSetExtension).where(ReplyReadinessQuestionSetExtension.store_code == store_code)
        rows = list(self.session.scalars(statement.order_by(ReplyReadinessQuestionSetExtension.created_at.desc())).all())
        items = [self._extension_projection(row) for row in rows if row.product_id is None or product_id is None or row.product_id == product_id]
        return QuestionSetExtensionList(items=items, total=len(items))

    @staticmethod
    def _extension_projection(row: ReplyReadinessQuestionSetExtension) -> QuestionSetExtensionProjection:
        return QuestionSetExtensionProjection(
            extension_id=row.extension_id,
            version=row.version,
            status=row.status,
            scope_kind=row.scope_kind,
            store_code=row.store_code,
            product_id=row.product_id,
            questions=[PddReplyReadinessQuestionV1.model_validate(item) for item in ReplyReadinessService._question_dicts(row.questions_json)],
            change_reason=row.change_reason,
            content_fingerprint=row.content_fingerprint,
            created_by=row.created_by,
            created_at=row.created_at,
        )

    @staticmethod
    def _material_template(material: KnowledgeMaterial) -> str | None:
        value = (material.recognition_summary or {}).get("template_type")
        return str(value) if value else None

    @classmethod
    def _knowledge_snapshot(cls, material: KnowledgeMaterial) -> ReplyReadinessKnowledgeSnapshotV1:
        return ReplyReadinessKnowledgeSnapshotV1(
            material_id=material.material_id,
            revision=material.revision,
            content_hash=material.content_hash,
            material_status=material.material_status,
            template_type=cls._material_template(material),
            store_code=material.store_code,
            product_id=material.product_id,
            sku_id=material.sku_id,
            analysis_text=material.analysis_text,
        )

    def _knowledge_sources(
        self,
        scope: ReplyReadinessScopeV1,
        overlay: KnowledgeMaterial | None,
    ) -> list[ReplyReadinessKnowledgeSnapshotV1]:
        rows = list(self.session.scalars(
            select(KnowledgeMaterial).where(
                KnowledgeMaterial.store_code == scope.store_code,
                KnowledgeMaterial.product_id == scope.product_id,
            ).order_by(KnowledgeMaterial.material_id, KnowledgeMaterial.revision.desc())
        ).all())
        selected: dict[str, KnowledgeMaterial] = {}
        for material in rows:
            if material.sku_id not in {None, scope.sku_id}:
                continue
            if self._material_template(material) not in _READINESS_TEMPLATES:
                continue
            if material.material_status not in _REVIEWED_MATERIAL_STATUSES:
                continue
            selected.setdefault(material.material_id, material)
        if overlay is not None:
            selected[overlay.material_id] = overlay
        ordered = sorted(
            selected.values(),
            key=lambda item: (
                0 if item.sku_id is None else 1,
                self._material_template(item) or "",
                item.material_id,
                item.revision,
            ),
        )
        return [self._knowledge_snapshot(item) for item in ordered]

    def debug_input(
        self,
        *,
        scope: ReplyReadinessScopeV1,
        customer_message: str,
    ) -> PddReplyReadinessInputV1:
        product = self.session.get(TestProduct, scope.product_id)
        if product is None or product.store_code != scope.store_code:
            raise AppError(
                "REPLY_DEBUG_SCOPE_INVALID",
                "Selected Product does not belong to the Store.",
                status_code=422,
            )
        sku = self.session.get(TestSku, scope.sku_id) if scope.sku_id else None
        if scope.sku_id and (sku is None or sku.product_id != product.product_id):
            raise AppError(
                "REPLY_DEBUG_SCOPE_INVALID",
                "Selected SKU does not belong to the Product.",
                status_code=422,
            )
        publication = self.session.get(ProductKnowledgePublication, product.product_id)
        publication_state = ReplyReadinessPublicationStateV1(
            status=publication.status if publication is not None else "NOT_GENERATED",
            current_fingerprint=(publication.current_fingerprint if publication else None),
            indexed_fingerprint=(publication.indexed_fingerprint if publication else None),
            active_collection=(publication.active_collection if publication else None),
        )
        snapshot = self.session.scalar(
            select(ReplyRuleSnapshotPublication).where(
                ReplyRuleSnapshotPublication.tenant_id == scope.tenant_id,
                ReplyRuleSnapshotPublication.platform == scope.platform,
                ReplyRuleSnapshotPublication.status == "PUBLISHED",
                ReplyRuleSnapshotPublication.snapshot_revision >= 1,
                ReplyRuleSnapshotPublication.snapshot_fingerprint.is_not(None),
            )
        )
        question_id = f"DEBUG-{canonical_sha256(customer_message)[:24].upper()}"
        question = PddReplyReadinessQuestionV1(
            schema_version="pdd-reply-readiness-question.v1",
            question_id=question_id,
            category="DEBUG",
            canonical_question=customer_message,
            aliases=[],
            policy_risk_floor=RiskLevel.LOW,
            expected_action=ExpectedAction.DIRECT_ANSWER,
            required_fact_keys=[],
            requires_realtime_lookup=False,
            prohibited_claims=[],
            mandatory=True,
        )
        question_set_base = {
            "baseline_version": "pdd-published-router-debug.v1",
            "questions": [question.model_dump(mode="json")],
        }
        return PddReplyReadinessInputV1(
            schema_version="pdd-reply-readiness-input.v1",
            run_id=f"DBG-{uuid4().hex[:20].upper()}",
            test_data_mode=True,
            production_usable=False,
            allow_auto_send=False,
            execution_mode=ReplyReadinessExecutionMode.PUBLISHED_ROUTER_DEBUG,
            scope=scope,
            question_set=PddQuestionSetProjection(
                schema_version="pdd-reply-readiness-question-set.v1",
                **question_set_base,
                fingerprint=canonical_sha256(question_set_base),
            ),
            reply_rule_snapshot_revision=(snapshot.snapshot_revision if snapshot else None),
            reply_rule_snapshot_fingerprint=(snapshot.snapshot_fingerprint if snapshot else None),
            router_build_fingerprint=_ROUTER_BUILD_FINGERPRINT,
            publication_state=publication_state,
            verified_product=self._verified_product(product, sku),
        )

    @staticmethod
    def _verified_product(
        product: TestProduct, sku: TestSku | None
    ) -> ReplyReadinessVerifiedProductV1:
        def values(raw: str) -> dict[str, object]:
            try:
                result = json.loads(raw or "{}")
            except (TypeError, ValueError):
                return {}
            return result if isinstance(result, dict) else {}

        product_values = values(product.raw_data_json)
        sku_values = values(sku.raw_data_json) if sku is not None else {}
        attributes: dict[str, str] = {}
        candidates = {
            "particle_count": (
                sku_values.get("particle_count")
                if sku is not None
                else product_values.get("particle_count")
            ),
            "finished_size": (
                sku_values.get("assembled_size")
                if sku is not None
                else product_values.get("assembled_size")
            ),
            "material": sku_values.get("material") or product_values.get("material"),
            "ship_origin": product_values.get("ship_origin"),
        }
        for key, raw_value in candidates.items():
            value = str(raw_value).strip() if raw_value is not None else ""
            if value and len(value) <= 512:
                attributes[key] = value
        return ReplyReadinessVerifiedProductV1(
            product_reference=product.product_id,
            product_name=product.product_name_display or product.product_name_official,
            sku_reference=sku.sku_id if sku else None,
            sku_name=(sku.sku_name_display or sku.sku_name_official) if sku else None,
            attributes=attributes,
        )

    def prepare_run(self, payload: ReplyReadinessRunCreate, idempotency_key: str) -> tuple[ReplyReadinessRun, bool]:
        scope = self.scope(payload.store_code, payload.product_id, payload.sku_id)
        request_fingerprint = canonical_sha256(payload.model_dump(mode="json"))
        replay = self.session.scalar(select(ReplyReadinessRun).where(
            ReplyReadinessRun.requested_by == self.actor_user_id,
            ReplyReadinessRun.idempotency_key == idempotency_key,
        ))
        if replay is not None:
            if replay.request_fingerprint != request_fingerprint:
                raise AppError("REPLY_READINESS_IDEMPOTENCY_CONFLICT", "幂等键已对应另一请求。", status_code=409)
            return replay, True
        overlay = None
        if payload.material_id and payload.material_revision:
            material = self.session.scalar(select(KnowledgeMaterial).where(
                KnowledgeMaterial.material_id == payload.material_id,
                KnowledgeMaterial.revision == payload.material_revision,
            ))
            if material is None:
                raise AppError("REPLY_READINESS_MATERIAL_NOT_FOUND", "未找到指定资料修订。", status_code=404)
            if material.store_code != scope.store_code or material.product_id != scope.product_id or material.sku_id not in {None, scope.sku_id}:
                raise AppError("REPLY_READINESS_MATERIAL_SCOPE_MISMATCH", "资料修订不属于当前商品范围。", status_code=422)
            if self._material_template(material) not in _READINESS_TEMPLATES:
                raise AppError("REPLY_READINESS_MATERIAL_UNSUPPORTED", "该资料模板不能用于回答风险评测。", status_code=422)
            if material.material_status not in _DRAFT_OVERLAY_STATUSES:
                raise AppError("REPLY_READINESS_MATERIAL_NOT_READY", "该资料状态不能用于草稿评测。", status_code=422)
            overlay = material
        knowledge_sources = self._knowledge_sources(scope, overlay)
        question_set = self.effective_question_set(scope)
        rule_snapshot = self.session.scalar(
            select(ReplyRuleSnapshotPublication).where(
                ReplyRuleSnapshotPublication.tenant_id == scope.tenant_id,
                ReplyRuleSnapshotPublication.platform == scope.platform,
                ReplyRuleSnapshotPublication.status == "PUBLISHED",
                ReplyRuleSnapshotPublication.snapshot_revision >= 1,
                ReplyRuleSnapshotPublication.snapshot_fingerprint.is_not(None),
            )
        )
        if rule_snapshot is None or not rule_snapshot.snapshot_fingerprint:
            raise AppError(
                "REPLY_READINESS_RULE_SNAPSHOT_UNAVAILABLE",
                "A published ReplyRule snapshot is required for a reproducible evaluation.",
                status_code=409,
            )
        run_id = f"RRN-{uuid4().hex[:20].upper()}"
        input_payload = PddReplyReadinessInputV1(
            run_id=run_id,
            scope=scope,
            question_set=question_set,
            knowledge_sources=knowledge_sources,
            reply_rule_snapshot_revision=rule_snapshot.snapshot_revision,
            reply_rule_snapshot_fingerprint=rule_snapshot.snapshot_fingerprint,
            router_build_fingerprint=_ROUTER_BUILD_FINGERPRINT,
            sandbox_vector_identity=f"in-memory-replay:{run_id}",
        )
        row = ReplyReadinessRun(
            run_id=run_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            status="PENDING",
            tenant_id=scope.tenant_id,
            platform=scope.platform,
            store_code=scope.store_code,
            product_id=scope.product_id,
            sku_id=scope.sku_id,
            question_set_fingerprint=question_set.fingerprint,
            question_count=len(question_set.questions),
            material_id=overlay.material_id if overlay else None,
            material_revision=overlay.revision if overlay else None,
            material_content_hash=overlay.content_hash if overlay else None,
            reply_rule_snapshot_revision=rule_snapshot.snapshot_revision,
            reply_rule_snapshot_fingerprint=rule_snapshot.snapshot_fingerprint,
            router_build_fingerprint=_ROUTER_BUILD_FINGERPRINT,
            sandbox_vector_identity=input_payload.sandbox_vector_identity,
            test_data_mode=True,
            production_usable=False,
            allow_auto_send=False,
            input_json=input_payload.model_dump_json(),
            requested_by=self.actor_user_id,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row, False

    def input_for(self, row: ReplyReadinessRun) -> PddReplyReadinessInputV1:
        return PddReplyReadinessInputV1.model_validate_json(row.input_json)

    def mark_running(self, row: ReplyReadinessRun) -> None:
        if row.status == "PENDING":
            row.status = "RUNNING"
            self.session.commit()

    def record_result(self, row: ReplyReadinessRun, raw: dict[str, object]) -> ReplyReadinessRunProjection:
        result = PddReplyReadinessResultV1.model_validate(raw)
        if result.run_id != row.run_id or result.question_set_fingerprint != row.question_set_fingerprint:
            raise AppError("REPLY_READINESS_RESULT_SCOPE_MISMATCH", "评测结果与运行快照不一致。", status_code=422)
        if len(result.items) != row.question_count or len({item.question_id for item in result.items}) != row.question_count:
            raise AppError("REPLY_READINESS_RESULT_INCOMPLETE", "评测结果未完整覆盖问题集。", status_code=422)
        expected_question_ids = {
            item.question_id for item in self.input_for(row).question_set.questions
        }
        if {item.question_id for item in result.items} != expected_question_ids:
            raise AppError(
                "REPLY_READINESS_RESULT_INCOMPLETE",
                "Result question identities do not match the frozen input.",
                status_code=422,
            )
        if row.status == "FAILED":
            raise AppError(
                "REPLY_READINESS_RESULT_AFTER_FAILURE",
                "A failed run cannot be overwritten by a late result.",
                status_code=409,
            )
        if row.result_sha256 and row.result_sha256 != result.result_sha256:
            raise AppError("REPLY_READINESS_RESULT_CONFLICT", "该运行已有不同结果。", status_code=409)
        row.status = "COMPLETED"
        row.result_json = result.model_dump_json()
        row.result_sha256 = result.result_sha256
        row.failure_code = None
        row.completed_at = utc_now()
        self.session.commit()
        self.session.refresh(row)
        return self.projection(row)

    def mark_failed(self, row: ReplyReadinessRun, code: str) -> None:
        row.status = "FAILED"
        row.failure_code = code[:96]
        row.completed_at = utc_now()
        self.session.commit()

    def get(self, run_id: str) -> ReplyReadinessRunProjection:
        row = self.session.get(ReplyReadinessRun, run_id)
        if row is None:
            raise AppError("REPLY_READINESS_RUN_NOT_FOUND", "未找到评测运行。", status_code=404)
        return self.projection(row)

    def list_runs(
        self,
        store_code: str,
        product_id: str,
        *,
        scope_kind: str | None = None,
        sku_id: str | None = None,
    ) -> ReplyReadinessRunList:
        statement = select(ReplyReadinessRun).where(
            ReplyReadinessRun.store_code == store_code,
            ReplyReadinessRun.product_id == product_id,
        )
        if scope_kind == "PRODUCT":
            statement = statement.where(ReplyReadinessRun.sku_id.is_(None))
        elif scope_kind == "SKU":
            statement = statement.where(ReplyReadinessRun.sku_id == sku_id)
        rows = list(self.session.scalars(
            statement.order_by(ReplyReadinessRun.requested_at.desc())
        ).all())
        return ReplyReadinessRunList(items=[self.projection(row) for row in rows], total=len(rows))

    def compare(self, baseline_run_id: str, candidate_run_id: str) -> ReplyReadinessRunComparison:
        baseline = self.get(baseline_run_id)
        candidate = self.get(candidate_run_id)
        if baseline.store_code != candidate.store_code or baseline.product_id != candidate.product_id or baseline.sku_id != candidate.sku_id:
            raise AppError("REPLY_READINESS_COMPARISON_SCOPE_MISMATCH", "只能比较同一商品范围的运行。", status_code=422)
        if baseline.result is None or candidate.result is None:
            raise AppError("REPLY_READINESS_COMPARISON_NOT_READY", "只有已完成运行可以比较。", status_code=409)
        before = {item.question_id: item for item in baseline.result.items}
        changed: list[dict[str, object]] = []
        for item in candidate.result.items:
            previous = before.get(item.question_id)
            if previous is None or previous.model_dump(mode="json") != item.model_dump(mode="json"):
                changed.append({
                    "question_id": item.question_id,
                    "before_risk": previous.effective_risk.value if previous else None,
                    "after_risk": item.effective_risk.value,
                    "answer_changed": previous is None or previous.answer_sha256 != item.answer_sha256,
                    "missing_fact_keys_before": previous.missing_fact_keys if previous else [],
                    "missing_fact_keys_after": item.missing_fact_keys,
                    "blocker_codes_before": previous.blocker_codes if previous else [],
                    "blocker_codes_after": item.blocker_codes,
                    "evidence_changed": previous is None or (
                        previous.evidence_bundle_sha256 != item.evidence_bundle_sha256
                        or previous.citation_ids != item.citation_ids
                    ),
                })
        return ReplyReadinessRunComparison(
            baseline_run_id=baseline_run_id,
            candidate_run_id=candidate_run_id,
            changed_items=changed,
        )

    @staticmethod
    def projection(row: ReplyReadinessRun) -> ReplyReadinessRunProjection:
        result = PddReplyReadinessResultV1.model_validate_json(row.result_json) if row.result_json else None
        frozen_input = PddReplyReadinessInputV1.model_validate_json(row.input_json)
        source_count = len(frozen_input.knowledge_sources) or (1 if frozen_input.knowledge_snapshot else 0)
        return ReplyReadinessRunProjection(
            run_id=row.run_id,
            status=row.status,
            tenant_id=row.tenant_id,
            platform=row.platform,
            store_code=row.store_code,
            product_id=row.product_id,
            sku_id=row.sku_id,
            question_set_fingerprint=row.question_set_fingerprint,
            question_count=row.question_count,
            material_id=row.material_id,
            material_revision=row.material_revision,
            material_content_hash=row.material_content_hash,
            knowledge_source_count=source_count,
            reply_rule_snapshot_revision=row.reply_rule_snapshot_revision,
            reply_rule_snapshot_fingerprint=row.reply_rule_snapshot_fingerprint,
            result=result,
            failure_code=row.failure_code,
            requested_by=row.requested_by,
            requested_at=row.requested_at,
            completed_at=row.completed_at,
        )
