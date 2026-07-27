"""Response projections for the C-internal trial governance screen."""

from datetime import datetime

from pydantic import BaseModel


class TrialGovernanceStatus(BaseModel):
    actor_id: str
    role: str
    capabilities: list[str]
    access_boundary_mode: str = "FIXED_TRIAL_CONTEXT"
    formal_authentication_enabled: bool = False
    formal_authorization_enabled: bool = False
    audit_foundation_enabled: bool = True
    automatic_redaction_enabled: bool = False
    retention_policy_configured: bool = False
    current_redaction_marker: str = "v1-reminder-only"
    test_data_mode: bool = True
    production_usable: bool = False


class TrialAuditEventItem(BaseModel):
    id: str
    occurred_at: datetime
    actor_id: str
    actor_role: str
    action: str
    resource_type: str
    resource_id: str
    outcome: str
    reason_code: str
    metadata: dict[str, int | str | bool]


class TrialAuditEventListResponse(BaseModel):
    items: list[TrialAuditEventItem]
    total: int
    page: int
    size: int
