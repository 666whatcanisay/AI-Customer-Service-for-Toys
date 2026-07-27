"""C-only read model for the daily AI operations center.

The projection intentionally returns counts, state and timestamps only.  It
never reads raw customer-service text into the response and has no lifecycle
side effects.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.schemas import (
    AdminOperationsTodayResponse,
    OperationsKnowledgeStatus,
    OperationsWorkQueue,
    TodayOperationsMetrics,
)
from app.ai_feedback.models import AIResponseFeedback, AIResponseFeedbackAnalysis
from app.customer_efficiency.service import build_summary
from app.database import get_db
from app.experience_cases.models import CustomerExperienceCase
from app.ingestion.models import ImportBatch
from app.test_catalog.models import (
    TestConflictRecord,
    TestFaq,
    TestKnowledgePackage,
    TestProduct,
    TestSafetyRule,
    TestSku,
    TestStore,
)


router = APIRouter(prefix="/api/v1/admin/operations", tags=["admin-operations"])


def _utc_today_window(generated_at: datetime) -> tuple[datetime, datetime]:
    """Use the same UTC calendar-day convention as customer-efficiency.v1."""
    end = generated_at.astimezone(timezone.utc)
    start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, end


def _count(session: Session, statement: object) -> int:
    return int(session.scalar(statement) or 0)  # type: ignore[arg-type]


@router.get("/today", response_model=AdminOperationsTodayResponse)
def get_admin_operations_today(session: Session = Depends(get_db)) -> AdminOperationsTodayResponse:
    """Return a content-free, one-request snapshot for the C Admin landing page."""
    generated_at = datetime.now(timezone.utc)
    window_start, window_end = _utc_today_window(generated_at)
    efficiency = build_summary(session, window_start=window_start, window_end=window_end)

    newest_test_package = session.scalar(
        select(TestKnowledgePackage.imported_at).order_by(TestKnowledgePackage.imported_at.desc()).limit(1)
    )
    newest_import_batch = session.scalar(
        select(ImportBatch.created_at).order_by(ImportBatch.created_at.desc()).limit(1)
    )
    import_dates = [item for item in (newest_test_package, newest_import_batch) if item is not None]

    return AdminOperationsTodayResponse(
        today=TodayOperationsMetrics(
            generated_at=generated_at,
            window_start=window_start,
            window_end=window_end,
            ai_request_count=efficiency.ai_request_count,
            direct_adoption_count=efficiency.direct_adoption_count,
            edited_adoption_count=efficiency.edited_adoption_count,
            not_adopted_count=efficiency.not_adopted_count,
            adoption_rate=efficiency.adoption_rate,
            experience_case_submission_count=_count(
                session,
                select(func.count(CustomerExperienceCase.id)).where(
                    CustomerExperienceCase.created_at >= window_start,
                    CustomerExperienceCase.created_at < window_end,
                ),
            ),
            ai_feedback_submission_count=_count(
                session,
                select(func.count(AIResponseFeedback.id)).where(
                    AIResponseFeedback.created_at >= window_start,
                    AIResponseFeedback.created_at < window_end,
                ),
            ),
            completed_ai_analysis_count=_count(
                session,
                select(func.count(AIResponseFeedbackAnalysis.id)).where(
                    AIResponseFeedbackAnalysis.recorded_at >= window_start,
                    AIResponseFeedbackAnalysis.recorded_at < window_end,
                ),
            ),
        ),
        work_queue=OperationsWorkQueue(
            pending_experience_review_count=_count(
                session,
                select(func.count(CustomerExperienceCase.id)).where(
                    CustomerExperienceCase.review_status.in_(("NEW", "REVIEWING"))
                ),
            ),
            pending_ai_analysis_count=_count(
                session,
                select(func.count(AIResponseFeedback.id)).where(
                    AIResponseFeedback.analysis_status.in_(("NEW", "ANALYZING"))
                ),
            ),
            open_knowledge_conflict_count=_count(
                session,
                select(func.count(TestConflictRecord.issue_id)).where(TestConflictRecord.status != "RESOLVED"),
            ),
        ),
        knowledge=OperationsKnowledgeStatus(
            store_count=_count(session, select(func.count(TestStore.id))),
            product_count=_count(session, select(func.count(TestProduct.product_id))),
            sku_count=_count(session, select(func.count(TestSku.sku_id))),
            faq_count=_count(session, select(func.count(TestFaq.faq_id))),
            safety_rule_count=_count(session, select(func.count(TestSafetyRule.rule_id))),
            recent_imported_at=max(import_dates) if import_dates else None,
        ),
        test_data_mode=True,
        production_usable=False,
    )
