"""Strict API schemas for store platform identity bindings."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StorePlatformBindingStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


def normalize_platform(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip()).lower()
    aliases = {"pdd": "pinduoduo", "拼多多": "pinduoduo"}
    normalized = aliases.get(normalized, normalized)
    if not normalized or len(normalized) > 32:
        raise ValueError("platform must contain between 1 and 32 normalized characters")
    if not all(character.isalnum() or character in "_-" for character in normalized):
        raise ValueError("platform may contain only letters, numbers, underscore, or hyphen")
    return normalized


def normalize_platform_store_id(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip())
    if not normalized or len(normalized) > 96:
        raise ValueError("platform_store_id must contain between 1 and 96 characters")
    if any(character.isspace() for character in normalized):
        raise ValueError("platform_store_id must not contain whitespace")
    return normalized


class StorePlatformBindingCreateRequest(StrictModel):
    platform: str = Field(min_length=1, max_length=32)
    platform_store_id: str = Field(min_length=1, max_length=96)
    change_reason: str = Field(min_length=8, max_length=512)
    confirmation_phrase: Literal["确认绑定平台店铺"]

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        return normalize_platform(value)

    @field_validator("platform_store_id")
    @classmethod
    def validate_platform_store_id(cls, value: str) -> str:
        return normalize_platform_store_id(value)

    @field_validator("change_reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class StorePlatformBindingRevokeRequest(StrictModel):
    change_reason: str = Field(min_length=8, max_length=512)
    confirmation_phrase: Literal["确认撤销平台店铺绑定"]

    @field_validator("change_reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class StorePlatformBindingProjection(StrictModel):
    binding_id: str
    store_id: int
    store_code: str
    store_name: str
    platform: str
    platform_store_id: str
    status: StorePlatformBindingStatus
    verified_at: datetime
    verified_by: str
    created_at: datetime
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    change_reason: str


class StorePlatformBindingListResponse(StrictModel):
    items: list[StorePlatformBindingProjection]
    total: int
