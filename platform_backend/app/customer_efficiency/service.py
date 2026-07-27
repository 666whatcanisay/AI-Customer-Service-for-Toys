"""Aggregate-only summary construction shared by A and C Admin projections."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.customer_efficiency.models import CustomerEfficiencyEvent, utc_now
from app.customer_efficiency.schemas import CustomerEfficiencyEventType, CustomerEfficiencySummary


SUMMARY_VERSION = "customer-efficiency.v1"


def default_window(generated_at: datetime) -> tuple[datetime, datetime]:
    start = generated_at.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, generated_at


def build_summary(
    session: Session,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> CustomerEfficiencySummary:
    generated_at = utc_now()
    default_start, default_end = default_window(generated_at)
    start = window_start or default_start
    end = window_end or default_end
    counts = {event_type.value: 0 for event_type in CustomerEfficiencyEventType}
    for event_type, count in session.execute(
        select(CustomerEfficiencyEvent.event_type, func.count(CustomerEfficiencyEvent.id))
        .where(
            CustomerEfficiencyEvent.occurred_at >= start,
            CustomerEfficiencyEvent.occurred_at < end,
        )
        .group_by(CustomerEfficiencyEvent.event_type)
    ):
        if event_type in counts:
            counts[event_type] = int(count)
    ai_request_count = counts[CustomerEfficiencyEventType.AI_REQUEST]
    direct_adoption_count = counts[CustomerEfficiencyEventType.DIRECT_ADOPTION]
    edited_adoption_count = counts[CustomerEfficiencyEventType.EDITED_ADOPTION]
    return CustomerEfficiencySummary(
        summary_version=SUMMARY_VERSION,
        generated_at=generated_at,
        window_start=start,
        window_end=end,
        ai_request_count=ai_request_count,
        direct_adoption_count=direct_adoption_count,
        edited_adoption_count=edited_adoption_count,
        not_adopted_count=counts[CustomerEfficiencyEventType.NOT_ADOPTED],
        adoption_rate=(direct_adoption_count + edited_adoption_count) / ai_request_count
        if ai_request_count
        else 0.0,
    )
