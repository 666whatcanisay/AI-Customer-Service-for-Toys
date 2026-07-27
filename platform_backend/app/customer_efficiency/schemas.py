"""`customer-efficiency.v1` C Provider request and aggregate response schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CustomerEfficiencyEventType(StrEnum):
    AI_REQUEST = "AI_REQUEST"
    DIRECT_ADOPTION = "DIRECT_ADOPTION"
    EDITED_ADOPTION = "EDITED_ADOPTION"
    NOT_ADOPTED = "NOT_ADOPTED"


class CustomerEfficiencyEventCreate(BaseModel):
    """Content-free B-to-C event. Server controls ID and idempotency receipt."""

    model_config = ConfigDict(extra="forbid")

    event_type: CustomerEfficiencyEventType
    occurred_at: datetime | None = None

    @field_validator("occurred_at")
    @classmethod
    def require_timezone_when_supplied(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("occurred_at must include a timezone offset")
        return value


class CustomerEfficiencyEventCreated(BaseModel):
    event_id: str
    event_type: CustomerEfficiencyEventType
    occurred_at: datetime
    created_at: datetime


class CustomerEfficiencySummary(BaseModel):
    summary_version: str = "customer-efficiency.v1"
    generated_at: datetime
    window_start: datetime
    window_end: datetime
    ai_request_count: int = Field(ge=0)
    direct_adoption_count: int = Field(ge=0)
    edited_adoption_count: int = Field(ge=0)
    not_adopted_count: int = Field(ge=0)
    adoption_rate: float = Field(ge=0, le=1)
