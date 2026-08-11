"""Strict IAM V1 request and response schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


IAM_SCHEMA_VERSION = "ai-cs.iam.v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoleName(StrEnum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


Username = Annotated[str, StringConstraints(min_length=1, max_length=64)]


def canonical_username(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value.strip())
    if not normalized:
        raise ValueError("username must not be blank")
    if len(normalized) > 64:
        raise ValueError("username must contain at most 64 normalized characters")
    if not all(
        character in "._-" or unicodedata.category(character)[0] in {"L", "N"}
        for character in normalized
    ):
        raise ValueError("username may contain only Unicode letters, numbers, dot, underscore, or hyphen")
    return normalized


class StoreBindingInput(StrictModel):
    store_id: int = Field(ge=1)
    is_default: bool = False


class StorePlatformIdentityProjection(StrictModel):
    platform: str
    platform_store_id: str
    status: str
    verified_at: datetime
    verified_by: str


class StoreBindingProjection(StrictModel):
    id: int
    store_id: int
    store_code: str
    store_name: str
    platform: str
    is_default: bool
    platform_bindings: list[StorePlatformIdentityProjection] = Field(default_factory=list)


class StoreOptionProjection(StrictModel):
    store_id: int
    store_code: str
    store_name: str
    platform: str
    platform_bindings: list[StorePlatformIdentityProjection] = Field(default_factory=list)


class UserProjection(StrictModel):
    id: str
    username: str
    display_name: str
    status: UserStatus
    roles: list[RoleName]
    permissions: list[str]
    stores: list[StoreBindingProjection]
    must_change_password: bool
    all_store_access: bool
    created_at: datetime
    updated_at: datetime


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(StrictModel):
    schema_version: str = IAM_SCHEMA_VERSION
    token_type: str = "Bearer"
    access_token: str
    expires_at: datetime
    user: UserProjection


class CurrentUserResponse(StrictModel):
    schema_version: str = IAM_SCHEMA_VERSION
    user: UserProjection


class UserCreateRequest(StrictModel):
    username: Username
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    roles: list[RoleName] = Field(min_length=1)
    store_bindings: list[StoreBindingInput] = Field(default_factory=list)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return canonical_username(value)

    @field_validator("display_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("identity text must not be blank")
        return stripped

    @model_validator(mode="after")
    def reject_duplicates(self) -> "UserCreateRequest":
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("roles must be unique")
        ids = [item.store_id for item in self.store_bindings]
        if len(set(ids)) != len(ids):
            raise ValueError("store bindings must be unique")
        return self


class UserUpdateRequest(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    status: UserStatus | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_change(self) -> "UserUpdateRequest":
        if self.display_name is None and self.status is None and self.password is None:
            raise ValueError("at least one user field must be provided")
        if self.display_name is not None:
            self.display_name = self.display_name.strip()
            if not self.display_name:
                raise ValueError("display_name must not be blank")
        return self


class RoleAssignmentRequest(StrictModel):
    roles: list[RoleName] = Field(min_length=1)

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, values: list[RoleName]) -> list[RoleName]:
        if len(set(values)) != len(values):
            raise ValueError("roles must be unique")
        return values


class ChangePasswordRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class SelfStoreBindingRequest(StrictModel):
    store_ids: list[int] = Field(min_length=1)
    default_store_id: int | None = Field(default=None, ge=1)

    @field_validator("store_ids")
    @classmethod
    def unique_store_ids(cls, values: list[int]) -> list[int]:
        if any(value < 1 for value in values) or len(set(values)) != len(values):
            raise ValueError("store_ids must contain unique positive identifiers")
        return values

    @model_validator(mode="after")
    def default_must_be_selected(self) -> "SelfStoreBindingRequest":
        if self.default_store_id is not None and self.default_store_id not in self.store_ids:
            raise ValueError("default_store_id must be included in store_ids")
        return self


class DefaultStoreRequest(StrictModel):
    store_id: int = Field(ge=1)


class StoreOptionListResponse(StrictModel):
    schema_version: str = IAM_SCHEMA_VERSION
    items: list[StoreOptionProjection]


class StoreBindingAssignmentRequest(StrictModel):
    store_bindings: list[StoreBindingInput]

    @field_validator("store_bindings")
    @classmethod
    def unique_stores(cls, values: list[StoreBindingInput]) -> list[StoreBindingInput]:
        ids = [item.store_id for item in values]
        if len(set(ids)) != len(ids):
            raise ValueError("store bindings must be unique")
        return values


class UserListResponse(StrictModel):
    schema_version: str = IAM_SCHEMA_VERSION
    items: list[UserProjection]
    total: int


class RoleListResponse(StrictModel):
    schema_version: str = IAM_SCHEMA_VERSION
    items: list[RoleName]
