"""Strict request and acknowledgement schemas for customer-efficiency.v1."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = "customer-efficiency.v1"


class CustomerEfficiencyEventType(StrEnum):
    AI_REQUEST = "AI_REQUEST"
    AI_DIRECT_ADOPT = "AI_DIRECT_ADOPT"
    AI_EDIT_ADOPT = "AI_EDIT_ADOPT"
    AI_REJECT = "AI_REJECT"
    EXPERIENCE_CASE_SAVE = "EXPERIENCE_CASE_SAVE"
    AI_FEEDBACK_SUBMIT = "AI_FEEDBACK_SUBMIT"


TERMINAL_EVENT_TYPES = {
    CustomerEfficiencyEventType.AI_DIRECT_ADOPT,
    CustomerEfficiencyEventType.AI_EDIT_ADOPT,
    CustomerEfficiencyEventType.AI_REJECT,
}


class CustomerEfficiencyEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=SCHEMA_VERSION, min_length=1, max_length=64)
    event_type: CustomerEfficiencyEventType
    operator_id: str = Field(min_length=1, max_length=128)
    store_code: str = Field(min_length=1, max_length=96)
    product_id: str | None = Field(default=None, max_length=128)
    sku_id: str | None = Field(default=None, max_length=128)
    conversation_id: str | None = Field(default=None, max_length=128)
    interaction_id: str | None = Field(default=None, max_length=128)
    feedback_id: str | None = Field(default=None, max_length=64)

    @field_validator("schema_version", "operator_id", "store_code")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("product_id", "sku_id", "conversation_id", "interaction_id", "feedback_id")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_event_shape(self) -> "CustomerEfficiencyEventCreate":
        if self.event_type in TERMINAL_EVENT_TYPES | {CustomerEfficiencyEventType.AI_REQUEST}:
            if self.interaction_id is None:
                raise ValueError("interaction_id is required for AI request and terminal events")
        if self.event_type == CustomerEfficiencyEventType.AI_FEEDBACK_SUBMIT and self.feedback_id is None:
            raise ValueError("feedback_id is required for AI_FEEDBACK_SUBMIT")
        return self


class CustomerEfficiencyEventAccepted(BaseModel):
    event_id: str
    event_type: CustomerEfficiencyEventType
    created_at: datetime
    accepted: bool = True
