"""C-line read-only administration APIs.

All projections originate from the isolated test-catalog and existing local
import tables.  They never expose raw workbook payloads, attachment bytes, or
local absolute paths.
"""

from datetime import datetime, timezone
import json
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.admin.schemas import (
    AdminImportBatchItem,
    AdminImportBatchListResponse,
    AdminOverviewResponse,
    ConflictItem,
    ConflictListResponse,
    FaqItem,
    FaqListResponse,
    OverviewCounts,
    PilotExperienceCaseCounts,
    PilotOperationDashboardResponse,
    PilotTodayCounts,
    ProductDetailResponse,
    ProductItem,
    ProductListResponse,
    SafetyRuleItem,
    SafetyRuleListResponse,
    SkuItem,
    SkuListResponse,
    SourceItem,
    SourceListResponse,
    StoreItem,
    StoreListResponse,
    SuggestionStatusCounts,
    FrequentQuestionItem,
)
from app.database import get_db
from app.errors import AppError
from app.experience_cases.models import CustomerExperienceCase
from app.experience_cases.schemas import EvaluationStatus, ExperienceCaseReviewStatus
from app.ingestion.models import ImportBatch
from app.suggestions.models import CustomerSuggestion
from app.test_catalog.models import (
    TestConflictRecord,
    TestFaq,
    TestKnowledgePackage,
    TestProduct,
    TestSafetyRule,
    TestSku,
    TestSourceEvidence,
    TestStore,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _loads(value: str) -> dict | list:
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, (dict, list)) else {}


def _string_list(value: str) -> list[str]:
    loaded = _loads(value)
    return [str(item) for item in loaded] if isinstance(loaded, list) else []


def _safe_relative_path(value: str | None) -> str | None:
    """Return an archive-relative locator only; suppress filesystem paths."""
    if not value:
        return None
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ":" in normalized or ".." in path.parts:
        return None
    return normalized


def _total(session: Session, statement: object) -> int:
    return int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)  # type: ignore[attr-defined]


def _product_item(item: TestProduct) -> ProductItem:
    return ProductItem(
        product_id=item.product_id,
        store_code=item.store_code,
        platform=item.platform,
        product_name_official=item.product_name_official,
        product_name_display=item.product_name_display,
        sales_status=item.sales_status,
        age_min=item.age_min,
        age_max=item.age_max,
        safety_summary=item.safety_summary,
        review_status=item.review_status,
        publishable=item.publishable,
        source_ids=_string_list(item.source_ids_json),
    )


def _sku_item(item: TestSku) -> SkuItem:
    return SkuItem(
        sku_id=item.sku_id,
        product_id=item.product_id,
        sku_code=item.sku_code,
        sku_name_official=item.sku_name_official,
        sku_name_display=item.sku_name_display,
        relation_type=item.relation_type,
        canonical_sku_id=item.canonical_sku_id,
        reference_sku_id=item.reference_sku_id,
        component_sku_refs=_string_list(item.component_sku_refs_json),
        publishable=item.publishable,
        source_ids=_string_list(item.source_ids_json),
    )


@router.get("/overview", response_model=AdminOverviewResponse)
def get_overview(session: Session = Depends(get_db)) -> AdminOverviewResponse:
    suggestion_counts = {status: 0 for status in ("SUBMITTED", "REVIEWING", "PLANNED", "DONE", "REJECTED")}
    for status, count in session.execute(
        select(CustomerSuggestion.status, func.count(CustomerSuggestion.id)).group_by(CustomerSuggestion.status)
    ):
        if status in suggestion_counts:
            suggestion_counts[status] = count

    newest_test_package = session.scalar(
        select(TestKnowledgePackage.imported_at).order_by(TestKnowledgePackage.imported_at.desc()).limit(1)
    )
    newest_import_batch = session.scalar(
        select(ImportBatch.created_at).order_by(ImportBatch.created_at.desc()).limit(1)
    )
    dates = [value for value in (newest_test_package, newest_import_batch) if value is not None]
    return AdminOverviewResponse(
        counts=OverviewCounts(
            stores=session.scalar(select(func.count(TestStore.id))) or 0,
            products=session.scalar(select(func.count(TestProduct.product_id))) or 0,
            skus=session.scalar(select(func.count(TestSku.sku_id))) or 0,
            faqs=session.scalar(select(func.count(TestFaq.faq_id))) or 0,
            safety_rules=session.scalar(select(func.count(TestSafetyRule.rule_id))) or 0,
            sources=session.scalar(select(func.count(TestSourceEvidence.source_id))) or 0,
            conflicts=session.scalar(select(func.count(TestConflictRecord.issue_id))) or 0,
            import_batches=(session.scalar(select(func.count(ImportBatch.id))) or 0)
            + (session.scalar(select(func.count(TestKnowledgePackage.package_id))) or 0),
            suggestions=SuggestionStatusCounts(
                submitted=suggestion_counts["SUBMITTED"],
                reviewing=suggestion_counts["REVIEWING"],
                planned=suggestion_counts["PLANNED"],
                done=suggestion_counts["DONE"],
                rejected=suggestion_counts["REJECTED"],
            ),
        ),
        recent_imported_at=max(dates) if dates else None,
        test_data_mode=True,
        production_usable=False,
    )


@router.get("/pilot-operation-dashboard", response_model=PilotOperationDashboardResponse)
def get_pilot_operation_dashboard(
    session: Session = Depends(get_db),
) -> PilotOperationDashboardResponse:
    """Return a deliberately simple, case-observed pilot dashboard.

    The project has no AI request telemetry table.  The displayed AI-call
    value is therefore limited to today's submitted cases containing their
    required AI answer, not a production call-volume assertion.
    """
    generated_at = datetime.now(timezone.utc)
    today_start = generated_at.replace(hour=0, minute=0, second=0, microsecond=0)
    today_statement = select(CustomerExperienceCase).where(CustomerExperienceCase.created_at >= today_start)
    case_submission_count = session.scalar(select(func.count()).select_from(today_statement.subquery())) or 0
    ai_call_count = session.scalar(
        select(func.count()).select_from(
            today_statement.where(CustomerExperienceCase.ai_answer != "").subquery()
        )
    ) or 0

    pending_review_count = session.scalar(
        select(func.count()).select_from(CustomerExperienceCase).where(
            CustomerExperienceCase.review_status.in_(
                (ExperienceCaseReviewStatus.NEW, ExperienceCaseReviewStatus.REVIEWING)
            )
        )
    ) or 0
    approved_case_count = session.scalar(
        select(func.count()).select_from(CustomerExperienceCase).where(
            CustomerExperienceCase.review_status == ExperienceCaseReviewStatus.APPROVED
        )
    ) or 0
    evaluated_case_count = session.scalar(
        select(func.count()).select_from(CustomerExperienceCase).where(
            CustomerExperienceCase.evaluation_status == EvaluationStatus.EVALUATED
        )
    ) or 0

    status_counts = {
        status: 0
        for status in (
            ExperienceCaseReviewStatus.NEW,
            ExperienceCaseReviewStatus.REVIEWING,
            ExperienceCaseReviewStatus.APPROVED,
        )
    }
    for status, count in session.execute(
        select(CustomerExperienceCase.review_status, func.count(CustomerExperienceCase.id)).group_by(
            CustomerExperienceCase.review_status
        )
    ):
        if status in status_counts:
            status_counts[status] = count

    frequent_questions = session.execute(
        select(CustomerExperienceCase.question, func.count(CustomerExperienceCase.id).label("case_count"))
        .group_by(CustomerExperienceCase.question)
        .order_by(func.count(CustomerExperienceCase.id).desc(), CustomerExperienceCase.question.asc())
        .limit(10)
    ).all()

    return PilotOperationDashboardResponse(
        generated_at=generated_at,
        data_mode="TEST_OR_PILOT",
        official_operation_report=False,
        ai_call_measurement="CASE_AI_ANSWER_PROXY",
        today=PilotTodayCounts(
            ai_call_count=ai_call_count,
            case_submission_count=case_submission_count,
            pending_review_count=pending_review_count,
            approved_case_count=approved_case_count,
            evaluated_case_count=evaluated_case_count,
        ),
        experience_cases=PilotExperienceCaseCounts(
            new=status_counts[ExperienceCaseReviewStatus.NEW],
            reviewing=status_counts[ExperienceCaseReviewStatus.REVIEWING],
            approved=status_counts[ExperienceCaseReviewStatus.APPROVED],
            evaluated=evaluated_case_count,
        ),
        frequent_questions=[
            FrequentQuestionItem(question=question, case_count=count)
            for question, count in frequent_questions
        ],
    )


@router.get("/stores", response_model=StoreListResponse)
def list_stores(
    keyword: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> StoreListResponse:
    statement = select(TestStore)
    if keyword:
        statement = statement.where(
            or_(TestStore.store_code.ilike(f"%{keyword}%"), TestStore.store_name.ilike(f"%{keyword}%"))
        )
    total = _total(session, statement)
    stores = session.scalars(
        statement.order_by(TestStore.store_code).offset((page - 1) * size).limit(size)
    ).all()
    items = [
        StoreItem(
            store_code=item.store_code,
            store_name=item.store_name,
            platform=item.platform,
            test_data_mode=item.test_data_mode,
            product_count=session.scalar(
                select(func.count(TestProduct.product_id)).where(TestProduct.store_code == item.store_code)
            )
            or 0,
        )
        for item in stores
    ]
    return StoreListResponse(items=items, page=page, size=size, total=total)


@router.get("/products", response_model=ProductListResponse)
def list_products(
    store_code: str | None = Query(default=None, max_length=96),
    status: str | None = Query(default=None, max_length=40),
    keyword: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> ProductListResponse:
    statement = select(TestProduct)
    if store_code:
        statement = statement.where(TestProduct.store_code == store_code)
    if status:
        statement = statement.where(TestProduct.sales_status == status)
    if keyword:
        statement = statement.where(
            or_(
                TestProduct.product_id.ilike(f"%{keyword}%"),
                TestProduct.product_name_official.ilike(f"%{keyword}%"),
                TestProduct.product_name_display.ilike(f"%{keyword}%"),
            )
        )
    total = _total(session, statement)
    items = session.scalars(
        statement.order_by(TestProduct.product_id).offset((page - 1) * size).limit(size)
    ).all()
    return ProductListResponse(items=[_product_item(item) for item in items], page=page, size=size, total=total)


@router.get("/products/{product_id}", response_model=ProductDetailResponse)
def get_product(product_id: str, session: Session = Depends(get_db)) -> ProductDetailResponse:
    item = session.get(TestProduct, product_id)
    if item is None:
        raise AppError("ADMIN_PRODUCT_NOT_FOUND", "Product was not found", status_code=404)
    data = _product_item(item).model_dump()
    data["sku_count"] = session.scalar(
        select(func.count(TestSku.sku_id)).where(TestSku.product_id == product_id)
    ) or 0
    return ProductDetailResponse(**data)


@router.get("/products/{product_id}/skus", response_model=SkuListResponse)
def list_product_skus(
    product_id: str,
    relation_type: str | None = Query(default=None, max_length=32),
    keyword: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> SkuListResponse:
    if session.get(TestProduct, product_id) is None:
        raise AppError("ADMIN_PRODUCT_NOT_FOUND", "Product was not found", status_code=404)
    statement = select(TestSku).where(TestSku.product_id == product_id)
    if relation_type:
        statement = statement.where(TestSku.relation_type == relation_type)
    if keyword:
        statement = statement.where(
            or_(TestSku.sku_code.ilike(f"%{keyword}%"), TestSku.sku_name_display.ilike(f"%{keyword}%"))
        )
    total = _total(session, statement)
    items = session.scalars(
        statement.order_by(TestSku.sku_id).offset((page - 1) * size).limit(size)
    ).all()
    return SkuListResponse(items=[_sku_item(item) for item in items], page=page, size=size, total=total)


@router.get("/faqs", response_model=FaqListResponse)
def list_faqs(
    store_code: str | None = Query(default=None, max_length=96),
    product_id: str | None = Query(default=None, max_length=96),
    risk_level: str | None = Query(default=None, max_length=16),
    keyword: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> FaqListResponse:
    statement = select(TestFaq)
    if store_code:
        statement = statement.where(TestFaq.store_code == store_code)
    if product_id:
        statement = statement.where(TestFaq.product_id == product_id)
    if risk_level:
        statement = statement.where(TestFaq.risk_level == risk_level)
    if keyword:
        statement = statement.where(TestFaq.canonical_question.ilike(f"%{keyword}%"))
    total = _total(session, statement)
    rows = session.scalars(statement.order_by(TestFaq.faq_id).offset((page - 1) * size).limit(size)).all()
    return FaqListResponse(
        items=[
            FaqItem(
                faq_id=item.faq_id,
                store_code=item.store_code,
                product_id=item.product_id,
                sku_id=item.sku_id,
                question=item.canonical_question,
                recommended_reply=item.recommended_reply,
                answer_action=item.answer_action,
                risk_level=item.risk_level,
                source_ids=_string_list(item.source_ids_json),
            )
            for item in rows
        ],
        page=page,
        size=size,
        total=total,
    )


@router.get("/safety-rules", response_model=SafetyRuleListResponse)
def list_safety_rules(
    store_code: str | None = Query(default=None, max_length=96),
    risk_level: str | None = Query(default=None, max_length=16),
    keyword: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> SafetyRuleListResponse:
    statement = select(TestSafetyRule)
    if store_code:
        statement = statement.where(TestSafetyRule.store_code == store_code)
    if risk_level:
        statement = statement.where(TestSafetyRule.risk_level == risk_level)
    if keyword:
        statement = statement.where(TestSafetyRule.scenario.ilike(f"%{keyword}%"))
    total = _total(session, statement)
    rows = session.scalars(
        statement.order_by(TestSafetyRule.rule_id).offset((page - 1) * size).limit(size)
    ).all()
    items: list[SafetyRuleItem] = []
    for item in rows:
        raw = _loads(item.raw_data_json)
        raw = raw if isinstance(raw, dict) else {}
        items.append(
            SafetyRuleItem(
                rule_id=item.rule_id,
                store_code=item.store_code,
                scenario=item.scenario,
                risk_level=item.risk_level,
                action=str(raw["allowed_action"]) if raw.get("allowed_action") is not None else None,
                forbidden_claim=(
                    str(raw["forbidden_claim"]) if raw.get("forbidden_claim") is not None else None
                ),
                source_ids=_string_list(item.source_ids_json),
            )
        )
    return SafetyRuleListResponse(items=items, page=page, size=size, total=total)


@router.get("/sources", response_model=SourceListResponse)
def list_sources(
    store_code: str | None = Query(default=None, max_length=96),
    product_id: str | None = Query(default=None, max_length=96),
    sku_id: str | None = Query(default=None, max_length=128),
    source_type: str | None = Query(default=None, max_length=64),
    keyword: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> SourceListResponse:
    statement = select(TestSourceEvidence).join(
        TestKnowledgePackage, TestKnowledgePackage.package_id == TestSourceEvidence.package_id
    )
    if store_code:
        statement = statement.where(TestKnowledgePackage.store_code == store_code)
    if product_id:
        statement = statement.where(TestSourceEvidence.product_id == product_id)
    if sku_id:
        statement = statement.where(TestSourceEvidence.sku_id == sku_id)
    if source_type:
        statement = statement.where(TestSourceEvidence.source_type == source_type)
    if keyword:
        statement = statement.where(
            or_(
                TestSourceEvidence.source_id.ilike(f"%{keyword}%"),
                TestSourceEvidence.file_name.ilike(f"%{keyword}%"),
            )
        )
    total = _total(session, statement)
    rows = session.scalars(
        statement.order_by(TestSourceEvidence.source_id).offset((page - 1) * size).limit(size)
    ).all()
    return SourceListResponse(
        items=[
            SourceItem(
                source_id=item.source_id,
                source_type=item.source_type,
                file_name=item.file_name,
                file_sha256=item.file_sha256,
                relative_path=_safe_relative_path(item.relative_path),
                product_id=item.product_id,
                sku_id=item.sku_id,
            )
            for item in rows
        ],
        page=page,
        size=size,
        total=total,
    )


@router.get("/conflicts", response_model=ConflictListResponse)
def list_conflicts(
    status: str | None = Query(default=None, max_length=64),
    product_id: str | None = Query(default=None, max_length=96),
    keyword: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> ConflictListResponse:
    statement = select(TestConflictRecord)
    if status:
        statement = statement.where(TestConflictRecord.status == status)
    if product_id:
        statement = statement.where(TestConflictRecord.entity_id == product_id)
    if keyword:
        statement = statement.where(
            or_(
                TestConflictRecord.issue_id.ilike(f"%{keyword}%"),
                TestConflictRecord.field_name.ilike(f"%{keyword}%"),
            )
        )
    total = _total(session, statement)
    rows = session.scalars(
        statement.order_by(TestConflictRecord.issue_id).offset((page - 1) * size).limit(size)
    ).all()
    items: list[ConflictItem] = []
    for item in rows:
        raw = _loads(item.raw_data_json)
        raw = raw if isinstance(raw, dict) else {}
        items.append(
            ConflictItem(
                issue_id=item.issue_id,
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                field_name=item.field_name,
                value_a=str(raw["value_a"]) if raw.get("value_a") is not None else None,
                value_b=str(raw["value_b"]) if raw.get("value_b") is not None else None,
                source_ids=[str(value) for value in raw.get("source_ids", [])]
                if isinstance(raw.get("source_ids"), list)
                else [],
                status=item.status,
                decision=item.decision,
            )
        )
    return ConflictListResponse(items=items, page=page, size=size, total=total)


@router.get("/import-batches", response_model=AdminImportBatchListResponse)
def list_import_batches(
    status: str | None = Query(default=None, max_length=64),
    keyword: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db),
) -> AdminImportBatchListResponse:
    rows: list[AdminImportBatchItem] = []
    for item in session.scalars(select(ImportBatch)).all():
        rows.append(
            AdminImportBatchItem(
                id=item.id,
                import_type=item.import_type,
                original_filename=item.original_filename,
                status=item.status,
                created_at=item.created_at,
                completed_at=item.completed_at,
                test_data_mode=False,
            )
        )
    for item in session.scalars(select(TestKnowledgePackage)).all():
        rows.append(
            AdminImportBatchItem(
                id=item.package_id,
                import_type="TEST_DATA_PACKAGE",
                original_filename=item.original_filename,
                status=item.import_status,
                created_at=item.imported_at,
                completed_at=item.imported_at,
                test_data_mode=item.test_data_mode,
            )
        )
    if status:
        rows = [item for item in rows if item.status == status]
    if keyword:
        needle = keyword.casefold()
        rows = [
            item
            for item in rows
            if needle in item.id.casefold() or needle in item.original_filename.casefold()
        ]
    rows.sort(key=lambda item: item.created_at, reverse=True)
    total = len(rows)
    return AdminImportBatchListResponse(
        items=rows[(page - 1) * size : page * size], page=page, size=size, total=total
    )
