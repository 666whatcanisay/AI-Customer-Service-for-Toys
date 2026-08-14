from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reply_router.contracts import (
    ReplyRulePublicationV1,
    canonical_sha256,
)
from app.reply_router.publication_store import (
    ReplyRuleSnapshotStore,
    ReplyRuleSnapshotUnavailable,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    ROOT
    / "contracts"
    / "candidates"
    / "reply-router-v1"
    / "fixtures"
    / "reply-rule-publication.valid.json"
)


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _publication(payload: dict | None = None) -> ReplyRulePublicationV1:
    return ReplyRulePublicationV1.model_validate_json(
        json.dumps(payload or _payload(), ensure_ascii=False)
    )


def _next_empty(publication: ReplyRulePublicationV1) -> ReplyRulePublicationV1:
    payload = publication.model_dump(mode="json")
    payload.update(
        {
            "publication_id": "reply-rule-publication-synthetic-002",
            "idempotency_key": "reply-rule-publication-synthetic-002",
            "snapshot_revision": 2,
            "rules": [],
            "snapshot_fingerprint": canonical_sha256(
                {
                    "tenant_id": publication.tenant_id,
                    "platform": publication.platform,
                    "snapshot_revision": 2,
                    "rules": [],
                }
            ),
        }
    )
    return _publication(payload)


def test_snapshot_store_is_atomic_versioned_and_idempotent(tmp_path: Path) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "reply-rules")
    first = _publication()
    receipt = store.publish(first)
    assert receipt.changed is True
    assert receipt.accepted_rule_count == 1
    assert store.current(first.tenant_id, first.platform) == first

    replay = store.publish(first)
    assert replay == receipt

    same_payload = first.model_dump(mode="json")
    same_payload["publication_id"] = "reply-rule-publication-synthetic-same"
    same_payload["idempotency_key"] = "reply-rule-publication-synthetic-same"
    same = store.publish(_publication(same_payload))
    assert same.changed is False

    second = _next_empty(first)
    second_receipt = store.publish(second)
    assert second_receipt.changed is True
    assert second_receipt.accepted_rule_count == 0
    assert store.current(first.tenant_id, first.platform) == second


def test_idempotent_retry_ignores_only_transport_timestamp(tmp_path: Path) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "reply-rules")
    first = _publication()
    receipt = store.publish(first)

    retry_payload = first.model_dump(mode="json")
    retry_payload["produced_at"] = "2026-08-14T12:34:56Z"
    assert store.publish(_publication(retry_payload)) == receipt

    conflict_payload = dict(retry_payload)
    conflict_payload["produced_by"] = "different-publisher"
    with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
        store.publish(_publication(conflict_payload))


def test_failed_atomic_write_keeps_previous_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ReplyRuleSnapshotStore(tmp_path / "reply-rules")
    first = _publication()
    store.publish(first)

    def fail_write(path: Path, content: bytes) -> None:
        del path, content
        raise ReplyRuleSnapshotUnavailable("SYNTHETIC_WRITE_FAILURE")

    monkeypatch.setattr(store, "_atomic_write", fail_write)
    with pytest.raises(ReplyRuleSnapshotUnavailable, match="SYNTHETIC_WRITE_FAILURE"):
        store.publish(_next_empty(first))
    assert store.current(first.tenant_id, first.platform) == first


def test_publication_endpoint_requires_internal_identity_and_persists(api_client) -> None:
    client, vector_path = api_client
    payload = _payload()
    response = client.post("/api/admin/ai/reply-rule-publications", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "PUBLISHED"
    assert response.json()["accepted_rule_count"] == 1
    assert list((vector_path / "reply_rule_snapshots" / "scopes").glob("*.json"))

    anonymous = client.post(
        "/api/admin/ai/reply-rule-publications",
        json=payload,
        headers={"X-AI-CS-Service-Token": ""},
    )
    assert anonymous.status_code == 401
    assert anonymous.json()["detail"] == "INTERNAL_SERVICE_AUTHENTICATION_FAILED"


def test_publication_endpoint_rejects_revision_conflict(api_client) -> None:
    client, _ = api_client
    first = _publication()
    assert client.post(
        "/api/admin/ai/reply-rule-publications",
        json=first.model_dump(mode="json"),
    ).status_code == 200

    conflict = first.model_dump(mode="json")
    conflict.update(
        {
            "publication_id": "reply-rule-publication-conflict",
            "idempotency_key": "reply-rule-publication-conflict",
            "rules": [],
            "snapshot_fingerprint": canonical_sha256(
                {
                    "tenant_id": first.tenant_id,
                    "platform": first.platform,
                    "snapshot_revision": 1,
                    "rules": [],
                }
            ),
        }
    )
    response = client.post("/api/admin/ai/reply-rule-publications", json=conflict)
    assert response.status_code == 409
    assert response.json()["detail"] == "REPLY_RULE_SNAPSHOT_REVISION_CONFLICT"
