from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .models import EnvironmentProfileV1, StagingAction


class StagingSafetyDenied(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class StagingSafetyDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    allowed: bool
    reason_code: str
    action: StagingAction
    account_allowed: bool
    conversation_allowed: bool
    action_allowed: bool


class StagingSafetyGuard:
    def __init__(self, profile: EnvironmentProfileV1) -> None:
        if profile.profile.value != "staging" or profile.allowlist is None:
            raise ValueError("staging safety guard requires a staging profile")
        self.profile = profile

    def evaluate(
        self,
        *,
        account_ref: str,
        conversation_id: str,
        action: StagingAction,
    ) -> StagingSafetyDecision:
        allowlist = self.profile.allowlist
        assert allowlist is not None
        account_allowed = account_ref in allowlist.account_refs
        conversation_allowed = conversation_id in allowlist.conversation_ids
        action_allowed = (
            action in allowlist.allowed_actions
            and action not in allowlist.blocked_actions
        )
        if action in allowlist.blocked_actions:
            reason = "STAGING_ACTION_BLOCKED"
        elif not action_allowed:
            reason = "STAGING_ACTION_NOT_ALLOWLISTED"
        elif not account_allowed:
            reason = "STAGING_ACCOUNT_NOT_ALLOWLISTED"
        elif not conversation_allowed:
            reason = "STAGING_CONVERSATION_NOT_ALLOWLISTED"
        else:
            reason = "STAGING_SCOPE_ALLOWED"
        return StagingSafetyDecision(
            allowed=account_allowed and conversation_allowed and action_allowed,
            reason_code=reason,
            action=action,
            account_allowed=account_allowed,
            conversation_allowed=conversation_allowed,
            action_allowed=action_allowed,
        )

    def assert_allowed(
        self,
        *,
        account_ref: str,
        conversation_id: str,
        action: StagingAction,
    ) -> StagingSafetyDecision:
        decision = self.evaluate(
            account_ref=account_ref,
            conversation_id=conversation_id,
            action=action,
        )
        if not decision.allowed:
            raise StagingSafetyDenied(decision.reason_code)
        return decision


__all__ = ["StagingSafetyDecision", "StagingSafetyDenied", "StagingSafetyGuard"]
