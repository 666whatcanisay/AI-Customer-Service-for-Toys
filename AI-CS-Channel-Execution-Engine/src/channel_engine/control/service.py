from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from channel_engine.models.entities import new_id, utc_now
from channel_engine.storage import SqlAlchemyUnitOfWork

from .models import (
    ConfigSnapshot,
    ControlPlaneAuditAction,
    ControlPlaneAuditEvent,
    ControlPlaneAuditState,
    ControlPlaneStatus,
    KillSwitchState,
    KillSwitchStatus,
)
from .repository import ControlPlaneRepository, ControlPlaneStateRecord


class ControlPlaneService:
    """Transactional command/query service for production control metadata."""

    def __init__(
        self,
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def status(self) -> ControlPlaneStatus:
        now = self._clock()
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = ControlPlaneRepository(uow.session)
            state = repo.get_or_create_state(now)
            active_config = repo.get_active_config(state)
            audit_count = repo.operational_metrics().audit_events_total
            return ControlPlaneStatus(
                kill_switch=self._kill_switch_status(state),
                active_config=active_config,
                audit_event_count=audit_count,
                captured_at=now,
            )

    def kill_switch_status(self) -> KillSwitchStatus:
        with self._uow_factory() as uow:
            assert uow.session is not None
            state = ControlPlaneRepository(uow.session).get_or_create_state(
                self._clock()
            )
            return self._kill_switch_status(state)

    def enable_kill_switch(
        self,
        *,
        operator: str,
        reason: str,
    ) -> KillSwitchStatus:
        return self._set_kill_switch(
            target=KillSwitchState.ENABLED,
            operator=operator,
            reason=reason,
            action=ControlPlaneAuditAction.KILL_SWITCH_ENABLED,
        )

    def disable_kill_switch(
        self,
        *,
        operator: str,
        reason: str,
    ) -> KillSwitchStatus:
        return self._set_kill_switch(
            target=KillSwitchState.DISABLED,
            operator=operator,
            reason=reason,
            action=ControlPlaneAuditAction.KILL_SWITCH_DISABLED,
        )

    def save_config_snapshot(
        self,
        *,
        adapter_config_version: str,
        policy_version: str,
        gateway_version: str,
        operator: str,
        reason: str,
    ) -> ConfigSnapshot:
        now = self._clock()
        snapshot = ConfigSnapshot(
            snapshot_id=new_id("control-config"),
            adapter_config_version=adapter_config_version,
            policy_version=policy_version,
            gateway_version=gateway_version,
            created_at=now,
            created_by=operator,
            reason=reason,
        )
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = ControlPlaneRepository(uow.session)
            state = repo.get_or_create_state(now)
            before = self._audit_state(repo, state)
            repo.append_config_snapshot(snapshot)
            repo.append_audit_event(
                ControlPlaneAuditEvent(
                    audit_event_id=new_id("control-audit"),
                    operator=operator,
                    action=ControlPlaneAuditAction.CONFIG_SNAPSHOT_CREATED,
                    timestamp=now,
                    reason=reason,
                    subject_id=snapshot.snapshot_id,
                    before=before,
                    after=before,
                )
            )
        return snapshot

    def activate_config_snapshot(
        self,
        snapshot_id: str,
        *,
        operator: str,
        reason: str,
    ) -> ConfigSnapshot:
        return self._activate_config_snapshot(
            snapshot_id,
            operator=operator,
            reason=reason,
            action=ControlPlaneAuditAction.CONFIG_SNAPSHOT_ACTIVATED,
        )

    def rollback_config_snapshot(
        self,
        snapshot_id: str,
        *,
        operator: str,
        reason: str,
    ) -> ConfigSnapshot:
        return self._activate_config_snapshot(
            snapshot_id,
            operator=operator,
            reason=reason,
            action=ControlPlaneAuditAction.CONFIG_SNAPSHOT_ROLLED_BACK,
        )

    def get_config_snapshot(self, snapshot_id: str) -> ConfigSnapshot:
        with self._uow_factory() as uow:
            assert uow.session is not None
            return ControlPlaneRepository(uow.session).get_config_snapshot(snapshot_id)

    def list_config_snapshots(self, limit: int = 100) -> list[ConfigSnapshot]:
        with self._uow_factory() as uow:
            assert uow.session is not None
            return ControlPlaneRepository(uow.session).list_config_snapshots(limit)

    def list_audit_events(self, limit: int = 100) -> list[ControlPlaneAuditEvent]:
        with self._uow_factory() as uow:
            assert uow.session is not None
            return ControlPlaneRepository(uow.session).list_audit_events(limit)

    def _set_kill_switch(
        self,
        *,
        target: KillSwitchState,
        operator: str,
        reason: str,
        action: ControlPlaneAuditAction,
    ) -> KillSwitchStatus:
        now = self._clock()
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = ControlPlaneRepository(uow.session)
            state = repo.get_or_create_state(now)
            before = self._audit_state(repo, state)
            updated = repo.update_kill_switch(
                state,
                target=target,
                updated_at=now,
                updated_by=operator,
                reason=reason,
            )
            after = self._audit_state(repo, updated)
            event = ControlPlaneAuditEvent(
                audit_event_id=new_id("control-audit"),
                operator=operator,
                action=action,
                timestamp=now,
                reason=reason,
                subject_id="channel-engine-control-plane",
                before=before,
                after=after,
            )
            repo.append_audit_event(event)
            return self._kill_switch_status(updated)

    def _activate_config_snapshot(
        self,
        snapshot_id: str,
        *,
        operator: str,
        reason: str,
        action: ControlPlaneAuditAction,
    ) -> ConfigSnapshot:
        now = self._clock()
        with self._uow_factory() as uow:
            assert uow.session is not None
            repo = ControlPlaneRepository(uow.session)
            state = repo.get_or_create_state(now)
            snapshot = repo.get_config_snapshot(snapshot_id)
            before = self._audit_state(repo, state)
            updated = repo.set_active_config(
                state,
                snapshot_id=snapshot_id,
                updated_at=now,
                updated_by=operator,
                reason=reason,
            )
            after = self._audit_state(repo, updated)
            repo.append_audit_event(
                ControlPlaneAuditEvent(
                    audit_event_id=new_id("control-audit"),
                    operator=operator,
                    action=action,
                    timestamp=now,
                    reason=reason,
                    subject_id=snapshot_id,
                    before=before,
                    after=after,
                )
            )
            return snapshot

    @staticmethod
    def _kill_switch_status(state: ControlPlaneStateRecord) -> KillSwitchStatus:
        return KillSwitchStatus(
            state=state.kill_switch_state,
            revision=state.revision,
            updated_at=state.kill_switch_updated_at,
            updated_by=state.kill_switch_updated_by,
            reason=state.kill_switch_reason,
        )

    @staticmethod
    def _audit_state(
        repo: ControlPlaneRepository,
        state: ControlPlaneStateRecord,
    ) -> ControlPlaneAuditState:
        active = repo.get_active_config(state)
        return ControlPlaneAuditState(
            kill_switch=state.kill_switch_state,
            state_revision=state.revision,
            active_config_snapshot_id=state.active_config_snapshot_id,
            adapter_config_version=(
                active.adapter_config_version if active is not None else None
            ),
            policy_version=active.policy_version if active is not None else None,
            gateway_version=active.gateway_version if active is not None else None,
        )


__all__ = ["ControlPlaneService"]
