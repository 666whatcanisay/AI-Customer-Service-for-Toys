from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.reply_router.contracts import (
    ReplyRulePublicationReceiptV1,
    ReplyRulePublicationV1,
    canonical_json_bytes,
    canonical_sha256,
)


MAX_RULE_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_RULE_SNAPSHOT_STORE_BYTES = 32 * 1024 * 1024
MAX_PUBLICATION_RECEIPTS = 10_000
Sha256Hex = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ReplyRuleSnapshotConflict(ValueError):
    pass


class ReplyRuleSnapshotUnavailable(RuntimeError):
    pass


class _StoredPublicationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    request_sha256: Sha256Hex
    receipt: ReplyRulePublicationReceiptV1


class _StoredRuleSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["reply-rule-snapshot-store.v1"]
    tenant_id: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=40)
    current: ReplyRulePublicationV1
    receipts: dict[str, _StoredPublicationReceipt] = Field(
        default_factory=dict, max_length=MAX_PUBLICATION_RECEIPTS
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReplyRuleSnapshotStore:
    """Atomically retain the last valid C-published rule snapshot per scope."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._lock = threading.RLock()

    def publish(
        self, publication: ReplyRulePublicationV1
    ) -> ReplyRulePublicationReceiptV1:
        request_bytes = canonical_json_bytes(publication)
        if len(request_bytes) > MAX_RULE_SNAPSHOT_BYTES:
            raise ReplyRuleSnapshotConflict("REPLY_RULE_SNAPSHOT_TOO_LARGE")
        # produced_at is transport metadata and can legitimately change when C
        # retries an otherwise identical publication. Bind idempotency to the
        # publication identity and governed content instead of wall-clock time.
        request_sha256 = canonical_sha256(
            {
                "publication_id": publication.publication_id,
                "tenant_id": publication.tenant_id,
                "platform": publication.platform,
                "snapshot_revision": publication.snapshot_revision,
                "rules": [rule.model_dump(mode="json") for rule in publication.rules],
                "snapshot_fingerprint": publication.snapshot_fingerprint,
                "produced_by": publication.produced_by,
            }
        )
        path = self._scope_path(publication.tenant_id, publication.platform)

        with self._lock:
            existing = self._read(path)
            if existing is not None:
                replay = existing.receipts.get(publication.idempotency_key)
                if replay is not None:
                    if replay.request_sha256 != request_sha256:
                        raise ReplyRuleSnapshotConflict(
                            "REPLY_RULE_PUBLICATION_IDEMPOTENCY_CONFLICT"
                        )
                    return replay.receipt
                if any(
                    stored.receipt.publication_id == publication.publication_id
                    for stored in existing.receipts.values()
                ):
                    raise ReplyRuleSnapshotConflict(
                        "REPLY_RULE_PUBLICATION_ID_CONFLICT"
                    )
                current = existing.current
                if publication.snapshot_revision < current.snapshot_revision:
                    raise ReplyRuleSnapshotConflict(
                        "REPLY_RULE_SNAPSHOT_REVISION_STALE"
                    )
                if publication.snapshot_revision == current.snapshot_revision:
                    if (
                        publication.snapshot_fingerprint
                        != current.snapshot_fingerprint
                        or canonical_sha256(
                            [rule.model_dump(mode="json") for rule in publication.rules]
                        )
                        != canonical_sha256(
                            [rule.model_dump(mode="json") for rule in current.rules]
                        )
                    ):
                        raise ReplyRuleSnapshotConflict(
                            "REPLY_RULE_SNAPSHOT_REVISION_CONFLICT"
                        )
                    changed = False
                elif publication.snapshot_revision != current.snapshot_revision + 1:
                    raise ReplyRuleSnapshotConflict(
                        "REPLY_RULE_SNAPSHOT_REVISION_GAP"
                    )
                else:
                    changed = True
                receipts = dict(existing.receipts)
            else:
                if publication.snapshot_revision != 1:
                    raise ReplyRuleSnapshotConflict(
                        "REPLY_RULE_SNAPSHOT_INITIAL_REVISION_INVALID"
                    )
                changed = True
                receipts = {}

            if len(receipts) >= MAX_PUBLICATION_RECEIPTS:
                raise ReplyRuleSnapshotUnavailable(
                    "REPLY_RULE_PUBLICATION_RECEIPT_CAPACITY_EXCEEDED"
                )
            receipt = ReplyRulePublicationReceiptV1(
                schema_version="reply-rule-publication-receipt.v1",
                publication_id=publication.publication_id,
                tenant_id=publication.tenant_id,
                platform=publication.platform,
                snapshot_revision=publication.snapshot_revision,
                snapshot_fingerprint=publication.snapshot_fingerprint,
                status="PUBLISHED",
                changed=changed,
                accepted_rule_count=len(publication.rules),
                published_at=_now(),
            )
            receipts[publication.idempotency_key] = _StoredPublicationReceipt(
                request_sha256=request_sha256,
                receipt=receipt,
            )
            state = _StoredRuleSnapshot(
                schema_version="reply-rule-snapshot-store.v1",
                tenant_id=publication.tenant_id,
                platform=publication.platform,
                current=publication,
                receipts=receipts,
            )
            self._atomic_write(path, canonical_json_bytes(state))
            return receipt

    def current(
        self, tenant_id: str, platform: str
    ) -> ReplyRulePublicationV1 | None:
        with self._lock:
            stored = self._read(self._scope_path(tenant_id, platform))
            return stored.current if stored is not None else None

    def _scope_path(self, tenant_id: str, platform: str) -> Path:
        scope_hash = hashlib.sha256(
            f"{tenant_id}\0{platform}".encode("utf-8")
        ).hexdigest()
        return self.root / "scopes" / f"{scope_hash}.json"

    @staticmethod
    def _read(path: Path) -> _StoredRuleSnapshot | None:
        if not path.exists():
            return None
        try:
            if path.stat().st_size > MAX_RULE_SNAPSHOT_STORE_BYTES:
                raise ReplyRuleSnapshotUnavailable(
                    "REPLY_RULE_SNAPSHOT_FILE_TOO_LARGE"
                )
            return _StoredRuleSnapshot.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except ReplyRuleSnapshotUnavailable:
            raise
        except (OSError, UnicodeError, ValueError) as exc:
            raise ReplyRuleSnapshotUnavailable(
                "REPLY_RULE_SNAPSHOT_CORRUPT"
            ) from exc

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        temporary: Path | None = None
        try:
            if len(content) > MAX_RULE_SNAPSHOT_STORE_BYTES:
                raise ReplyRuleSnapshotUnavailable(
                    "REPLY_RULE_SNAPSHOT_STORE_CAPACITY_EXCEEDED"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                temporary.chmod(0o600)
            except OSError:
                pass
            os.replace(temporary, path)
        except ReplyRuleSnapshotUnavailable:
            raise
        except OSError as exc:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            raise ReplyRuleSnapshotUnavailable(
                "REPLY_RULE_SNAPSHOT_WRITE_FAILED"
            ) from exc
