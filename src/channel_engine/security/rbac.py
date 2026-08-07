from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.models.entities import utc_now


RBAC_CONTRACT_VERSION = "1.0"


class RBACModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    rbac_version: Literal["1.0"] = RBAC_CONTRACT_VERSION


class OperatorRole(StrEnum):
    OPERATOR = "OPERATOR"
    SUPERVISOR = "SUPERVISOR"
    ADMIN = "ADMIN"


class OperatorPermission(StrEnum):
    APPROVAL_READ = "APPROVAL_READ"
    APPROVAL_DECIDE = "APPROVAL_DECIDE"
    EXECUTION_READ = "EXECUTION_READ"
    EXECUTION_TRIGGER = "EXECUTION_TRIGGER"
    SELECTOR_VERIFY = "SELECTOR_VERIFY"
    SAFETY_ADMIN = "SAFETY_ADMIN"
    AGENT_IDENTITY_READ = "AGENT_IDENTITY_READ"
    AGENT_IDENTITY_MANAGE = "AGENT_IDENTITY_MANAGE"


class OperatorPrincipal(RBACModel):
    """Authenticated identity produced by an external identity provider."""

    principal_id: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$",
    )
    roles: frozenset[OperatorRole] = Field(min_length=1)
    authenticated: Literal[True] = True
    identity_provider: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$",
    )
    authenticated_at: AwareDatetime = Field(default_factory=utc_now)


class OperatorAccessDenied(PermissionError):
    def __init__(self, permission: OperatorPermission) -> None:
        super().__init__(f"operator permission denied: {permission.value}")
        self.permission = permission
        self.error_code = "OPERATOR_PERMISSION_DENIED"


class RBACAuthorizer:
    _permissions = {
        OperatorRole.OPERATOR: frozenset(
            {
                OperatorPermission.APPROVAL_READ,
                OperatorPermission.APPROVAL_DECIDE,
                OperatorPermission.EXECUTION_READ,
            }
        ),
        OperatorRole.SUPERVISOR: frozenset(
            {
                OperatorPermission.APPROVAL_READ,
                OperatorPermission.APPROVAL_DECIDE,
                OperatorPermission.EXECUTION_READ,
                OperatorPermission.EXECUTION_TRIGGER,
                OperatorPermission.SELECTOR_VERIFY,
            }
        ),
        OperatorRole.ADMIN: frozenset(OperatorPermission),
    }

    def permissions_for(
        self, principal: OperatorPrincipal
    ) -> frozenset[OperatorPermission]:
        result: set[OperatorPermission] = set()
        for role in principal.roles:
            result.update(self._permissions[role])
        return frozenset(result)

    def require(
        self,
        principal: OperatorPrincipal,
        permission: OperatorPermission,
    ) -> None:
        if not isinstance(principal, OperatorPrincipal):
            raise OperatorAccessDenied(permission)
        if permission not in self.permissions_for(principal):
            raise OperatorAccessDenied(permission)


@runtime_checkable
class OperatorIdentityProvider(Protocol):
    """Authenticate an opaque session reference outside request payload fields."""

    def authenticate(self, session_reference: str) -> OperatorPrincipal: ...


class DenyAllOperatorIdentityProvider:
    """Safe default until a deployment injects its identity provider."""

    def authenticate(self, session_reference: str) -> OperatorPrincipal:
        del session_reference
        raise OperatorAccessDenied(OperatorPermission.APPROVAL_READ)


__all__ = [
    "DenyAllOperatorIdentityProvider",
    "OperatorAccessDenied",
    "OperatorIdentityProvider",
    "OperatorPermission",
    "OperatorPrincipal",
    "OperatorRole",
    "RBACAuthorizer",
    "RBAC_CONTRACT_VERSION",
]
