"""Stable, minimal identity selection payloads."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CustomerUserRole(StrEnum):
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE"
    OPERATIONS = "OPERATIONS"
    ADMIN = "ADMIN"


class CustomerUserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class CustomerUserWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    role: CustomerUserRole
    store_codes: list[str] = Field(min_length=1, max_length=20)
    default_store_code: str = Field(min_length=1, max_length=96)

    @field_validator("display_name", "default_store_code")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("store_codes")
    @classmethod
    def _unique_store_codes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("store code must not be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("store codes must be unique")
        return normalized

    @model_validator(mode="after")
    def _default_is_bound(self) -> "CustomerUserWrite":
        if self.default_store_code not in self.store_codes:
            raise ValueError("default_store_code must be included in store_codes")
        return self


class CustomerUserStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: CustomerUserStatus


class CustomerUserStoreBindingResponse(BaseModel):
    store_code: str
    is_default: bool


class CustomerUserResponse(BaseModel):
    user_id: str
    display_name: str
    role: CustomerUserRole
    status: CustomerUserStatus
    default_store_code: str
    store_bindings: list[CustomerUserStoreBindingResponse]
    created_at: datetime
    updated_at: datetime


class CustomerUserListResponse(BaseModel):
    items: list[CustomerUserResponse]
    total: int
