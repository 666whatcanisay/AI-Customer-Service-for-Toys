from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


REGISTRY_SCHEMA_VERSION = 1
REAL_FIXTURE_PREFIX = "real-pdd-sanitized:"
REGISTRY_ENV = "CHANNEL_AGENT_REPLAY_APPROVAL_REGISTRY"
REGISTRY_KEY_ENV = "CHANNEL_AGENT_REPLAY_APPROVAL_KEY"


class PDDReplayApprovalError(RuntimeError):
    """A real-derived Replay was not immutably reviewed and anchored."""


class PDDReplayApprovalManifestV1(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", populate_by_name=True, serialize_by_alias=True
    )

    schema_name: Literal["pdd-replay-approval.v1"] = Field(
        default="pdd-replay-approval.v1", alias="schema"
    )
    approval_id: str = Field(pattern=r"^replay-approval:[a-f0-9]{64}$")
    fixture_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    privacy_processed: Literal[True] = True
    scan_policy_version: Literal["pdd-replay-residual-scan.v1"] = (
        "pdd-replay-residual-scan.v1"
    )
    automated_scan_result: Literal["PASS"] = "PASS"
    reviewer_reference: str = Field(min_length=3, max_length=160)
    reviewed_at: AwareDatetime
    manual_review_completed: Literal[True] = True
    replay_export_allowed: Literal[True] = True
    approval_reason: str = Field(min_length=3, max_length=512)


def approval_sidecar_path(fixture_path: str | Path) -> Path:
    fixture = Path(fixture_path).resolve(strict=False)
    return fixture.with_suffix(fixture.suffix + ".approval.json")


def initialize_approval_registry(
    registry_path: str | Path,
    key_path: str | Path,
) -> None:
    registry = Path(registry_path).resolve(strict=False)
    key = Path(key_path).resolve(strict=False)
    if registry.exists() or key.exists():
        raise PDDReplayApprovalError("approval registry initialization refuses overwrite")
    registry.parent.mkdir(parents=True, exist_ok=True)
    key.parent.mkdir(parents=True, exist_ok=True)
    _publish_immutable(key, (secrets.token_hex(32) + "\n").encode("ascii"))
    try:
        with sqlite3.connect(registry) as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA user_version=1;
                CREATE TABLE approval_registry_metadata(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    schema_version INTEGER NOT NULL,
                    registry_instance_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE replay_approval_anchors(
                    approval_id TEXT PRIMARY KEY,
                    fixture_sha256 TEXT NOT NULL UNIQUE,
                    sidecar_sha256 TEXT NOT NULL UNIQUE,
                    sidecar_path_digest TEXT NOT NULL,
                    approved_at TEXT NOT NULL,
                    signature TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT INTO approval_registry_metadata VALUES(1,?,?,?)",
                (REGISTRY_SCHEMA_VERSION, secrets.token_hex(16), datetime.now(UTC).isoformat()),
            )
    except Exception:
        registry.unlink(missing_ok=True)
        key.unlink(missing_ok=True)
        raise


def approve_replay_fixture(
    fixture_path: str | Path,
    registry_path: str | Path,
    key_path: str | Path,
    *,
    reviewer_reference: str,
    approval_reason: str,
    reviewed_at: datetime | None = None,
) -> PDDReplayApprovalManifestV1:
    fixture = Path(fixture_path).resolve(strict=True)
    payload = _read_fixture_payload(fixture)
    fixture_id = payload.get("fixture_id")
    if not isinstance(fixture_id, str) or not fixture_id.startswith(REAL_FIXTURE_PREFIX):
        raise PDDReplayApprovalError("only real-derived sanitized Replay needs this approval")
    if payload.get("sanitized") is not True:
        raise PDDReplayApprovalError("Replay fixture did not complete privacy processing")
    _scan_fixture(payload)
    fixture_sha = _sha256_file(fixture)
    reviewed = (reviewed_at or datetime.now(UTC)).astimezone(UTC)
    approval_id = "replay-approval:" + hashlib.sha256(
        f"{fixture_sha}|{reviewer_reference}|{reviewed.isoformat()}".encode("utf-8")
    ).hexdigest()
    manifest = PDDReplayApprovalManifestV1(
        approval_id=approval_id,
        fixture_sha256=fixture_sha,
        privacy_processed=True,
        automated_scan_result="PASS",
        reviewer_reference=reviewer_reference.strip(),
        reviewed_at=reviewed,
        manual_review_completed=True,
        replay_export_allowed=True,
        approval_reason=approval_reason.strip(),
    )
    sidecar = approval_sidecar_path(fixture)
    if sidecar.exists():
        existing = _load_sidecar(sidecar)
        if (
            existing.fixture_sha256 != fixture_sha
            or existing.reviewer_reference != manifest.reviewer_reference
            or existing.approval_reason != manifest.approval_reason
        ):
            raise PDDReplayApprovalError("immutable Replay approval Sidecar already exists")
        manifest = existing
    else:
        _publish_immutable(
            sidecar,
            (manifest.model_dump_json(indent=2) + "\n").encode("utf-8"),
        )
    _anchor_sidecar(
        fixture,
        sidecar,
        manifest,
        Path(registry_path).resolve(strict=True),
        Path(key_path).resolve(strict=True),
    )
    validate_replay_approval(fixture, registry_path, key_path)
    return manifest


def validate_replay_approval(
    fixture_path: str | Path,
    registry_path: str | Path,
    key_path: str | Path,
) -> PDDReplayApprovalManifestV1:
    fixture = Path(fixture_path).resolve(strict=True)
    sidecar = approval_sidecar_path(fixture)
    if not sidecar.is_file():
        raise PDDReplayApprovalError("real-derived Replay requires manual review Sidecar")
    manifest = _load_sidecar(sidecar)
    fixture_sha = _sha256_file(fixture)
    sidecar_sha = _sha256_file(sidecar)
    if not hmac.compare_digest(fixture_sha, manifest.fixture_sha256):
        raise PDDReplayApprovalError("Replay fixture changed after manual approval")
    registry = Path(registry_path).resolve(strict=True)
    key = _load_key(Path(key_path).resolve(strict=True))
    with sqlite3.connect(f"file:{registry.as_posix()}?mode=ro", uri=True) as connection:
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) != REGISTRY_SCHEMA_VERSION:
            raise PDDReplayApprovalError("Replay approval registry schema is unsupported")
        rows = connection.execute(
            """
            SELECT fixture_sha256,sidecar_sha256,sidecar_path_digest,approved_at,signature
            FROM replay_approval_anchors WHERE approval_id=?
            """,
            (manifest.approval_id,),
        ).fetchall()
    if len(rows) != 1:
        raise PDDReplayApprovalError("Replay approval anchor is missing or ambiguous")
    row = rows[0]
    path_digest = _path_digest(sidecar)
    if not (
        hmac.compare_digest(str(row[0]), fixture_sha)
        and hmac.compare_digest(str(row[1]), sidecar_sha)
        and hmac.compare_digest(str(row[2]), path_digest)
    ):
        raise PDDReplayApprovalError("Replay approval registry anchor does not match")
    material = _anchor_material(
        manifest.approval_id,
        fixture_sha,
        sidecar_sha,
        path_digest,
        str(row[3]),
    )
    expected = hmac.new(key, material, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(str(row[4]), expected):
        raise PDDReplayApprovalError("Replay approval registry signature is invalid")
    return manifest


def validate_real_fixture_from_environment(fixture_path: str | Path) -> None:
    registry = os.getenv(REGISTRY_ENV, "").strip()
    key = os.getenv(REGISTRY_KEY_ENV, "").strip()
    if not registry or not key:
        raise PDDReplayApprovalError(
            "real-derived Replay approval registry and key are required"
        )
    validate_replay_approval(fixture_path, registry, key)


def publish_immutable_fixture(path: str | Path, payload: bytes) -> None:
    _publish_immutable(Path(path).resolve(strict=False), payload)


def _anchor_sidecar(
    fixture: Path,
    sidecar: Path,
    manifest: PDDReplayApprovalManifestV1,
    registry: Path,
    key_path: Path,
) -> None:
    fixture_sha = _sha256_file(fixture)
    sidecar_sha = _sha256_file(sidecar)
    path_digest = _path_digest(sidecar)
    approved_at = manifest.reviewed_at.astimezone(UTC).isoformat()
    key = _load_key(key_path)
    signature = hmac.new(
        key,
        _anchor_material(
            manifest.approval_id,
            fixture_sha,
            sidecar_sha,
            path_digest,
            approved_at,
        ),
        hashlib.sha256,
    ).hexdigest()
    with sqlite3.connect(registry) as connection:
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) != REGISTRY_SCHEMA_VERSION:
            raise PDDReplayApprovalError("Replay approval registry schema is unsupported")
        existing = connection.execute(
            "SELECT fixture_sha256,sidecar_sha256,sidecar_path_digest,approved_at,signature "
            "FROM replay_approval_anchors WHERE approval_id=?",
            (manifest.approval_id,),
        ).fetchone()
        expected = (fixture_sha, sidecar_sha, path_digest, approved_at, signature)
        if existing is not None:
            if tuple(str(item) for item in existing) != expected:
                raise PDDReplayApprovalError("immutable Replay approval anchor conflicts")
            return
        connection.execute(
            "INSERT INTO replay_approval_anchors VALUES(?,?,?,?,?,?)",
            (manifest.approval_id, *expected),
        )


def _scan_fixture(payload: dict[str, object]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    patterns = {
        "PHONE": r"(?<!\d)1[3-9]\d{9}(?!\d)",
        "ID_CARD": r"(?<!\d)\d{17}[0-9Xx](?!\w)",
        "PAYMENT": r"(?<!\d)\d{12,19}(?!\d)",
        "EMAIL": r"(?<![\w.])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.])",
    }
    residual = [name for name, pattern in patterns.items() if re.search(pattern, serialized)]
    if residual:
        raise PDDReplayApprovalError(
            "Replay residual privacy scan failed: " + ",".join(residual)
        )


def _read_fixture_payload(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > 1024 * 1024:
        raise PDDReplayApprovalError("Replay fixture exceeds one MiB")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise PDDReplayApprovalError("Replay fixture must be an object")
    return value


def _load_sidecar(path: Path) -> PDDReplayApprovalManifestV1:
    try:
        return PDDReplayApprovalManifestV1.model_validate_json(path.read_bytes())
    except Exception as exc:
        raise PDDReplayApprovalError("Replay approval Sidecar is invalid") from exc


def _load_key(path: Path) -> bytes:
    try:
        value = bytes.fromhex(path.read_text(encoding="ascii").strip())
    except Exception as exc:
        raise PDDReplayApprovalError("Replay approval registry key is invalid") from exc
    if len(value) != 32:
        raise PDDReplayApprovalError("Replay approval registry key must be 256 bits")
    return value


def _publish_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise PDDReplayApprovalError(f"immutable file already exists: {path}")
    temporary = path.with_name(path.name + f".{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise PDDReplayApprovalError(f"immutable file already exists: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_digest(path: Path) -> str:
    return hashlib.sha256(str(path.resolve(strict=False)).casefold().encode("utf-8")).hexdigest()


def _anchor_material(
    approval_id: str,
    fixture_sha: str,
    sidecar_sha: str,
    path_digest: str,
    approved_at: str,
) -> bytes:
    return json.dumps(
        {
            "approval_id": approval_id,
            "fixture_sha256": fixture_sha,
            "sidecar_sha256": sidecar_sha,
            "sidecar_path_digest": path_digest,
            "approved_at": approved_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


__all__ = [
    "PDDReplayApprovalError",
    "PDDReplayApprovalManifestV1",
    "approval_sidecar_path",
    "approve_replay_fixture",
    "initialize_approval_registry",
    "publish_immutable_fixture",
    "validate_real_fixture_from_environment",
    "validate_replay_approval",
]
