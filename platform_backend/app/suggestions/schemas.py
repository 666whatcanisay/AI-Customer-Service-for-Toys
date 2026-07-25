"""API schemas and lifecycle rules for customer suggestions."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field


class SuggestionStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    REVIEWING = "REVIEWING"
    PLANNED = "PLANNED"
    DONE = "DONE"
    REJECTED = "REJECTED"


ALLOWED_STATUS_TRANSITIONS: dict[SuggestionStatus, set[SuggestionStatus]] = {
    SuggestionStatus.SUBMITTED: {
        SuggestionStatus.REVIEWING,
        SuggestionStatus.PLANNED,
        SuggestionStatus.REJECTED,
    },
    SuggestionStatus.REVIEWING: {
        SuggestionStatus.PLANNED,
        SuggestionStatus.DONE,
        SuggestionStatus.REJECTED,
    },
    SuggestionStatus.PLANNED: {SuggestionStatus.DONE, SuggestionStatus.REJECTED},
    SuggestionStatus.DONE: set(),
    SuggestionStatus.REJECTED: set(),
}


class SuggestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reporter_id: str = Field(min_length=1, max_length=64)
    reporter_name: str | None = Field(default=None, max_length=128)
    store_code: str | None = Field(default=None, max_length=96)
    module_key: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=4000)
    frequency: str | None = Field(default=None, max_length=32)
    urgency: str | None = Field(default=None, max_length=32)


class SuggestionResponse(BaseModel):
    id: str
    reporter_id: str
    reporter_name: str | None
    store_code: str | None
    module_key: str | None
    category: str | None
    title: str
    description: str
    frequency: str | None
    urgency: str | None
    status: SuggestionStatus
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def suggestion_id(self) -> str:
        """Compatibility alias for the C-owned customer-workbench API."""
        return self.id


class AdminSuggestionResponse(SuggestionResponse):
    internal_note: str | None


class SuggestionListResponse(BaseModel):
    items: list[SuggestionResponse]
    page: int
    size: int
    total: int


class AdminSuggestionListResponse(BaseModel):
    items: list[AdminSuggestionResponse]
    page: int
    size: int
    total: int


class AdminSuggestionUpdate(BaseModel):
    """The administration endpoint is intentionally limited to lifecycle metadata."""

    model_config = ConfigDict(extra="forbid")

    status: SuggestionStatus | None = None
    internal_note: str | None = Field(default=None, max_length=2000)
