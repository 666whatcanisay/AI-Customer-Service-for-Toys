from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

import pytest

from channel_agent.pdd_page_port import (
    PDDPageReadPortError,
    build_sanitized_pdd_replay_fixture,
    load_pdd_replay_fixture,
)
from channel_agent.pdd_replay_approval import (
    PDDReplayApprovalError,
    approval_sidecar_path,
    approve_replay_fixture,
    initialize_approval_registry,
    validate_replay_approval,
)


def _fixture(tmp_path):
    fingerprint = "sha256:" + "a" * 64
    value = build_sanitized_pdd_replay_fixture(
        scan={
            "fingerprint": fingerprint,
            "conversations": [
                {
                    "conversation_id": "real-conversation",
                    "customer_reference": "customer",
                    "unread_count": 1,
                    "last_activity": "2026-08-12T08:00:00Z",
                    "latest_sequence": 1,
                }
            ],
        },
        capture={
            "fingerprint": fingerprint,
            "active_conversation_id": "real-conversation",
            "customer_reference": "customer",
            "store_name": "test store",
            "product": {
                "product_id": "product-1",
                "product_name": "toy",
                "sku_id": "sku-1",
                "sku_name": "blue",
                "attributes_text": "ABS",
            },
            "messages": [
                {
                    "message_id": "message-1",
                    "role": "buyer",
                    "content": "Is this ABS?",
                    "timestamp": "2026-08-12T08:00:00Z",
                    "sequence": 1,
                }
            ],
        },
        role_map={"buyer": "CUSTOMER"},
        target_conversation_id="real-conversation",
        allowed_message_ids=("message-1",),
        captured_at=datetime(2026, 8, 12, 8, 0, tzinfo=UTC),
    )
    path = tmp_path / "real-replay.json"
    path.write_text(value.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_real_replay_requires_anchored_manual_approval(tmp_path, monkeypatch) -> None:
    fixture = _fixture(tmp_path)
    registry = tmp_path / "approval.sqlite3"
    key = tmp_path / "approval.key"
    with pytest.raises(PDDPageReadPortError, match="not approved"):
        load_pdd_replay_fixture(fixture)

    initialize_approval_registry(registry, key)
    approve_replay_fixture(
        fixture,
        registry,
        key,
        reviewer_reference="operator:test",
        approval_reason="bounded sanitized Pilot sample",
    )
    monkeypatch.setenv("CHANNEL_AGENT_REPLAY_APPROVAL_REGISTRY", str(registry))
    monkeypatch.setenv("CHANNEL_AGENT_REPLAY_APPROVAL_KEY", str(key))
    assert load_pdd_replay_fixture(fixture).fixture_id.startswith("real-pdd-sanitized:")


def test_sidecar_modification_is_detected_by_registry_anchor(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    registry = tmp_path / "approval.sqlite3"
    key = tmp_path / "approval.key"
    initialize_approval_registry(registry, key)
    approve_replay_fixture(
        fixture,
        registry,
        key,
        reviewer_reference="operator:test",
        approval_reason="bounded sanitized Pilot sample",
    )
    sidecar = approval_sidecar_path(fixture)
    value = json.loads(sidecar.read_text(encoding="utf-8"))
    value["approval_reason"] = "modified after review"
    sidecar.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PDDReplayApprovalError, match="anchor does not match"):
        validate_replay_approval(fixture, registry, key)


def test_registry_modification_breaks_hmac_anchor(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    registry = tmp_path / "approval.sqlite3"
    key = tmp_path / "approval.key"
    initialize_approval_registry(registry, key)
    manifest = approve_replay_fixture(
        fixture,
        registry,
        key,
        reviewer_reference="operator:test",
        approval_reason="bounded sanitized Pilot sample",
    )
    with sqlite3.connect(registry) as connection:
        connection.execute(
            "UPDATE replay_approval_anchors SET approved_at=? WHERE approval_id=?",
            ("2026-08-12T09:00:00+00:00", manifest.approval_id),
        )
    with pytest.raises(PDDReplayApprovalError, match="signature is invalid"):
        validate_replay_approval(fixture, registry, key)


def test_privacy_residual_blocks_approval(tmp_path) -> None:
    fixture = _fixture(tmp_path)
    value = json.loads(fixture.read_text(encoding="utf-8"))
    value["capture"]["messages"][0]["content"] = "call 13800138000"
    fixture.write_text(json.dumps(value), encoding="utf-8")
    registry = tmp_path / "approval.sqlite3"
    key = tmp_path / "approval.key"
    initialize_approval_registry(registry, key)
    with pytest.raises(PDDReplayApprovalError, match="residual privacy scan failed"):
        approve_replay_fixture(
            fixture,
            registry,
            key,
            reviewer_reference="operator:test",
            approval_reason="must not pass",
        )
