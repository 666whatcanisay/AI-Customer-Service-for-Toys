from __future__ import annotations

from datetime import datetime

from .models import (
    ChannelInstance,
    ChannelInstanceStatus,
    ChannelSession,
    ChannelSessionStatus,
)


class InvalidSessionTransition(ValueError):
    pass


_INSTANCE_TRANSITIONS = {
    ChannelInstanceStatus.CREATED: {
        ChannelInstanceStatus.STARTING,
        ChannelInstanceStatus.STOPPED,
        ChannelInstanceStatus.FAILED,
    },
    ChannelInstanceStatus.STARTING: {
        ChannelInstanceStatus.CONNECTED,
        ChannelInstanceStatus.AUTH_REQUIRED,
        ChannelInstanceStatus.DEGRADED,
        ChannelInstanceStatus.FAILED,
        ChannelInstanceStatus.STOPPED,
    },
    ChannelInstanceStatus.CONNECTED: {
        ChannelInstanceStatus.STARTING,
        ChannelInstanceStatus.DEGRADED,
        ChannelInstanceStatus.AUTH_REQUIRED,
        ChannelInstanceStatus.STOPPED,
        ChannelInstanceStatus.FAILED,
    },
    ChannelInstanceStatus.AUTH_REQUIRED: {
        ChannelInstanceStatus.STARTING,
        ChannelInstanceStatus.STOPPED,
        ChannelInstanceStatus.FAILED,
    },
    ChannelInstanceStatus.DEGRADED: {
        ChannelInstanceStatus.STARTING,
        ChannelInstanceStatus.CONNECTED,
        ChannelInstanceStatus.AUTH_REQUIRED,
        ChannelInstanceStatus.STOPPED,
        ChannelInstanceStatus.FAILED,
    },
    ChannelInstanceStatus.STOPPED: {
        ChannelInstanceStatus.STARTING,
        ChannelInstanceStatus.FAILED,
    },
    ChannelInstanceStatus.FAILED: {
        ChannelInstanceStatus.STARTING,
        ChannelInstanceStatus.STOPPED,
    },
}


_SESSION_TRANSITIONS = {
    ChannelSessionStatus.CREATED: {
        ChannelSessionStatus.AUTH_REQUIRED,
        ChannelSessionStatus.CONNECTED,
        ChannelSessionStatus.FAILED,
    },
    ChannelSessionStatus.AUTH_REQUIRED: {
        ChannelSessionStatus.CONNECTED,
        ChannelSessionStatus.EXPIRED,
        ChannelSessionStatus.FAILED,
    },
    ChannelSessionStatus.CONNECTED: {
        ChannelSessionStatus.EXPIRED,
        ChannelSessionStatus.FAILED,
    },
    ChannelSessionStatus.EXPIRED: set(),
    ChannelSessionStatus.FAILED: set(),
}


def transition_instance(
    instance: ChannelInstance,
    target: ChannelInstanceStatus,
    now: datetime,
    *,
    failure_code: str | None = None,
    active_session_id: str | None = None,
) -> ChannelInstance:
    if target not in _INSTANCE_TRANSITIONS[instance.status]:
        raise InvalidSessionTransition(
            f"invalid channel instance transition: {instance.status} -> {target}"
        )
    return instance.model_copy(
        update={
            "status": target,
            "failure_code": failure_code,
            "active_session_id": (
                instance.active_session_id
                if active_session_id is None
                else active_session_id
            ),
            "updated_at": now,
        }
    )


def transition_session(
    session: ChannelSession,
    target: ChannelSessionStatus,
    now: datetime,
    *,
    credential_lease_ref: str | None = None,
    heartbeat_time: datetime | None = None,
    expires_at: datetime | None = None,
    failure_code: str | None = None,
) -> ChannelSession:
    if target not in _SESSION_TRANSITIONS[session.status]:
        raise InvalidSessionTransition(
            f"invalid channel session transition: {session.status} -> {target}"
        )
    return session.model_copy(
        update={
            "status": target,
            "credential_lease_ref": credential_lease_ref,
            "heartbeat_time": heartbeat_time,
            "expires_at": expires_at,
            "failure_code": failure_code,
            "updated_at": now,
        }
    )


__all__ = [
    "InvalidSessionTransition",
    "transition_instance",
    "transition_session",
]
