from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect

from channel_engine.control.models import (
    CONTROL_PLANE_VERSION,
    ConfigSnapshot,
    ControlPlaneAuditAction,
    ControlPlaneAuditEvent,
    ControlPlaneAuditState,
    KillSwitchState,
)
from channel_engine.control.service import ControlPlaneService


class ControlClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 4, 14, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: int = 1) -> None:
        self.current += timedelta(seconds=seconds)


def test_control_plane_models_are_versioned_and_structurally_redacted() -> None:
    now = datetime(2026, 8, 4, 14, 0, tzinfo=timezone.utc)
    before = ControlPlaneAuditState(
        kill_switch=KillSwitchState.DISABLED,
        state_revision=0,
    )
    event = ControlPlaneAuditEvent(
        audit_event_id="control-audit-contract",
        operator="operator.control",
        action=ControlPlaneAuditAction.KILL_SWITCH_ENABLED,
        timestamp=now,
        reason="INCIDENT_CONTAINMENT",
        before=before,
        after=before.model_copy(
            update={
                "kill_switch": KillSwitchState.ENABLED,
                "state_revision": 1,
            }
        ),
    )

    assert event.control_plane_version == CONTROL_PLANE_VERSION == "1.0"
    assert set(event.before.model_dump()) == {
        "control_plane_version",
        "kill_switch",
        "state_revision",
        "active_config_snapshot_id",
        "adapter_config_version",
        "policy_version",
        "gateway_version",
    }
    serialized = event.model_dump_json().lower()
    for prohibited in (
        '"secret"',
        '"token"',
        '"password"',
        '"cookie"',
        '"customer_message"',
        '"message_content"',
    ):
        assert prohibited not in serialized

    with pytest.raises(ValidationError, match="prohibited marker"):
        event.model_copy(update={"reason": "TOKEN_EXPOSURE"}, deep=True)
        ControlPlaneAuditEvent(
            audit_event_id="control-audit-sensitive",
            operator="operator.control",
            action=ControlPlaneAuditAction.KILL_SWITCH_ENABLED,
            timestamp=now,
            reason="TOKEN_EXPOSURE",
            before=before,
            after=before,
        )
    with pytest.raises(ValidationError):
        ControlPlaneAuditEvent.model_validate(
            {
                **event.model_dump(mode="json"),
                "customer_message": "must never be accepted",
            }
        )


def test_config_snapshot_switch_and_rollback_are_immutable_and_audited(
    foundation,
) -> None:
    clock = ControlClock()
    control = ControlPlaneService(foundation["uow_factory"], clock=clock)

    first = control.save_config_snapshot(
        adapter_config_version="pdd-adapter.v1",
        policy_version="send-policy.v1",
        gateway_version="gateway.v1",
        operator="config.operator",
        reason="INITIAL_CONTROL_CONFIG",
    )
    clock.advance()
    control.activate_config_snapshot(
        first.snapshot_id,
        operator="config.operator",
        reason="ACTIVATE_INITIAL_CONFIG",
    )
    clock.advance()
    second = control.save_config_snapshot(
        adapter_config_version="pdd-adapter.v2",
        policy_version="send-policy.v2",
        gateway_version="gateway.v1",
        operator="config.operator",
        reason="PREPARE_CONFIG_VERSION_TWO",
    )
    clock.advance()
    control.activate_config_snapshot(
        second.snapshot_id,
        operator="config.operator",
        reason="ACTIVATE_CONFIG_VERSION_TWO",
    )
    assert control.status().active_config == second

    clock.advance()
    rolled_back = control.rollback_config_snapshot(
        first.snapshot_id,
        operator="rollback.operator",
        reason="ROLLBACK_TO_KNOWN_GOOD_CONFIG",
    )

    assert rolled_back == first
    assert control.status().active_config == first
    assert control.get_config_snapshot(second.snapshot_id) == second
    assert control.list_config_snapshots() == [first, second]
    events = control.list_audit_events()
    assert [event.action for event in events] == [
        ControlPlaneAuditAction.CONFIG_SNAPSHOT_CREATED,
        ControlPlaneAuditAction.CONFIG_SNAPSHOT_ACTIVATED,
        ControlPlaneAuditAction.CONFIG_SNAPSHOT_CREATED,
        ControlPlaneAuditAction.CONFIG_SNAPSHOT_ACTIVATED,
        ControlPlaneAuditAction.CONFIG_SNAPSHOT_ROLLED_BACK,
    ]
    rollback_event = events[-1]
    assert rollback_event.before.active_config_snapshot_id == second.snapshot_id
    assert rollback_event.after.active_config_snapshot_id == first.snapshot_id
    assert rollback_event.before.policy_version == "send-policy.v2"
    assert rollback_event.after.policy_version == "send-policy.v1"

    with pytest.raises(ValidationError, match="prohibited marker"):
        control.save_config_snapshot(
            adapter_config_version="pdd-adapter.v3",
            policy_version="send-policy.v3",
            gateway_version="gateway-secret.v3",
            operator="config.operator",
            reason="PREPARE_CONFIG_VERSION_THREE",
        )
    assert control.list_config_snapshots() == [first, second]

    with pytest.raises(ValidationError):
        first.adapter_config_version = "pdd-adapter.modified"  # type: ignore[misc]


def test_control_plane_schema_is_additive(foundation) -> None:
    tables = set(inspect(foundation["engine"]).get_table_names())
    assert {
        "control_plane_state",
        "control_plane_config_snapshots",
        "control_plane_audit_events",
    } <= tables


def test_config_snapshot_contract_rejects_secret_shaped_metadata() -> None:
    with pytest.raises(ValidationError, match="prohibited marker"):
        ConfigSnapshot(
            snapshot_id="config-sensitive",
            adapter_config_version="adapter.v1",
            policy_version="token-policy.v1",
            gateway_version="gateway.v1",
            created_at=datetime(2026, 8, 4, 14, 0, tzinfo=timezone.utc),
            created_by="config.operator",
            reason="CONFIG_CREATED",
        )
