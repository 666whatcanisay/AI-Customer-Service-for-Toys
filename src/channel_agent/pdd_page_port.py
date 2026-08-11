from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class PDDPageReadPortError(RuntimeError):
    """Fail-closed page-read boundary shared by Live and Replay inputs."""


@runtime_checkable
class PDDPageReadPort(Protocol):
    """Narrow page read port; intentionally has no navigate/click/input API."""

    source_kind: Literal["LIVE_PDD", "OFFLINE_REPLAY"]
    pdd_network_requests: int

    def read(
        self,
        operation: Literal["SCAN", "CAPTURE"],
        expression: str,
    ) -> object: ...


class PDDReadReplayFixture(BaseModel):
    """Sanitized DOM-extraction fixture, not a prebuilt CustomerContext."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["pdd-readonly-page-fixture.v1"]
    fixture_id: str = Field(min_length=1, max_length=160)
    source: Literal["SYNTHETIC_SANITIZED"]
    sanitized: Literal[True]
    captured_at: AwareDatetime
    page_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    selector_contract_version: Literal["pdd-replay.v1"] = "pdd-replay.v1"
    role_map: dict[str, Literal["CUSTOMER", "OPERATOR", "BOT", "SYSTEM"]]
    scan: dict[str, Any]
    capture: dict[str, Any]
    pdd_network_requests: Literal[0] = 0

    @model_validator(mode="after")
    def validate_raw_page_results(self) -> "PDDReadReplayFixture":
        if self.scan.get("fingerprint") != self.page_fingerprint:
            raise ValueError("replay scan fingerprint is inconsistent")
        if self.capture.get("fingerprint") != self.page_fingerprint:
            raise ValueError("replay capture fingerprint is inconsistent")
        if not isinstance(self.scan.get("conversations"), list):
            raise ValueError("replay scan must contain raw conversation rows")
        if not isinstance(self.capture.get("messages"), list):
            raise ValueError("replay capture must contain raw message rows")
        _reject_sensitive_fixture_keys(self.model_dump(mode="json"))
        return self


def load_pdd_replay_fixture(path: str | Path) -> PDDReadReplayFixture:
    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise PDDPageReadPortError("PDD replay fixture cannot be read") from exc
    if len(payload) > 1024 * 1024:
        raise PDDPageReadPortError("PDD replay fixture exceeds one MiB")
    try:
        return PDDReadReplayFixture.model_validate_json(payload)
    except Exception as exc:
        raise PDDPageReadPortError("PDD replay fixture is invalid") from exc


class ReplayPDDPageReadPort:
    """Deterministic zero-network implementation of ``PDDPageReadPort``."""

    source_kind: Literal["OFFLINE_REPLAY"] = "OFFLINE_REPLAY"
    pdd_network_requests = 0
    page_write_operations = 0
    execution_calls = 0
    transport_calls = 0

    def __init__(self, fixture: PDDReadReplayFixture) -> None:
        self.fixture = fixture
        self.read_calls = 0

    def read(
        self,
        operation: Literal["SCAN", "CAPTURE"],
        expression: str,
    ) -> object:
        if not expression or len(expression.encode("utf-8")) > 262_144:
            raise PDDPageReadPortError("PDD replay read expression is invalid")
        self.read_calls += 1
        value = self.fixture.scan if operation == "SCAN" else self.fixture.capture
        # Copy through JSON so tests and callers cannot mutate the frozen fixture.
        return json.loads(json.dumps(value, ensure_ascii=False))


def _reject_sensitive_fixture_keys(value: object, path: str = "fixture") -> None:
    forbidden = ("authorization", "cookie", "credential", "password", "secret", "token")
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key).casefold()
            if any(part in key for part in forbidden):
                raise ValueError(f"sensitive field is forbidden at {path}")
            _reject_sensitive_fixture_keys(child, f"{path}.{raw_key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_fixture_keys(child, f"{path}[{index}]")


__all__ = [
    "PDDPageReadPort",
    "PDDPageReadPortError",
    "PDDReadReplayFixture",
    "ReplayPDDPageReadPort",
    "load_pdd_replay_fixture",
]
