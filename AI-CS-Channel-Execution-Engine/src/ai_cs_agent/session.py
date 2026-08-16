from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .models import SessionStatus, utc_now_text


@dataclass(slots=True)
class ChannelSession:
    schema_version: str = "1.0"
    session_id: str | None = None
    status: SessionStatus = SessionStatus.CREATED
    credential_reference: str | None = None
    last_heartbeat: str | None = None
    recovery_reason: str | None = None
    updated_at: str = field(default_factory=utc_now_text)

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["status"] = self.status.value
        return value


class SessionManager:
    """Fail-closed local session state; it never claims login without observation."""

    def initialize(self, credential_reference: str) -> ChannelSession:
        return ChannelSession(
            status=SessionStatus.AUTH_REQUIRED,
            credential_reference=credential_reference,
            last_heartbeat=utc_now_text(),
        )

    def recover(self, previous: dict[str, object], credential_reference: str) -> ChannelSession:
        raw_status = str(previous.get("status", "CREATED"))
        if raw_status in {
            SessionStatus.CONNECTED.value,
            SessionStatus.DEGRADED.value,
            SessionStatus.EXPIRED.value,
            SessionStatus.RECOVERING.value,
        }:
            return ChannelSession(
                session_id=previous.get("session_id") if isinstance(previous.get("session_id"), str) else None,
                status=SessionStatus.AUTH_REQUIRED,
                credential_reference=credential_reference,
                last_heartbeat=utc_now_text(),
                recovery_reason="LOGIN_REVALIDATION_REQUIRED",
            )
        return self.initialize(credential_reference)
