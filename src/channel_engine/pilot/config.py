from __future__ import annotations

from pathlib import Path

from .models import PDD_PILOT_TARGET_STORE_NAME, PilotStoreConfig


_MAX_PILOT_CONFIG_BYTES = 1_048_576


class PilotConfigError(ValueError):
    pass


def default_pilot_store_config() -> PilotStoreConfig:
    return PilotStoreConfig(
        store_id="pdd-store-id-must-be-verified",
        store_name=PDD_PILOT_TARGET_STORE_NAME,
        credential_reference="secret-ref://pdd/pilot/wanqu-lego/manual-session",
        send_limit=1,
        approval_required=True,
        auto_reply=False,
    )


def load_pilot_store_config(path: str | Path) -> PilotStoreConfig:
    source = Path(path).expanduser().resolve()
    if source.suffix.casefold() != ".json":
        raise PilotConfigError("Pilot config must be one typed JSON document")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise PilotConfigError("Pilot config cannot be read") from exc
    if len(raw) > _MAX_PILOT_CONFIG_BYTES:
        raise PilotConfigError("Pilot config exceeds one MiB")
    try:
        return PilotStoreConfig.model_validate_json(raw)
    except Exception as exc:
        raise PilotConfigError("Pilot config validation failed") from exc


__all__ = [
    "PilotConfigError",
    "default_pilot_store_config",
    "load_pilot_store_config",
]
