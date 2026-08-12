from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from channel_engine.storage.runtime_database_identity import (
    RuntimeDatabaseIdentityError,
    bind_runtime_database,
    initialize_runtime_database,
    validate_runtime_database,
)


def test_runtime_database_identity_uses_internal_and_sidecar_facts(
    tmp_path: Path,
) -> None:
    database = (tmp_path / "host.sqlite3").resolve()
    binding = (tmp_path / "host.binding.json").resolve()
    created = initialize_runtime_database(
        database,
        binding,
        environment_id="RC5_OFFLINE_TEST",
        source_commit="test-source",
    )

    validated = validate_runtime_database(
        database,
        binding,
        expected_environment_id="RC5_OFFLINE_TEST",
    )
    assert validated.database_instance_id == created.database_instance_id
    assert validated.restore_generation == 0


def test_normal_business_write_does_not_invalidate_database_identity(
    tmp_path: Path,
) -> None:
    database = (tmp_path / "host.sqlite3").resolve()
    binding = (tmp_path / "host.binding.json").resolve()
    initialize_runtime_database(
        database,
        binding,
        environment_id="RC5_OFFLINE_TEST",
        source_commit="test-source",
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO runtime_heartbeats(
                heartbeat_id,runtime_id,reliability_version,cycle_id,component,
                health,available,reason_code,latency_ms,checked_at
            ) VALUES(?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            """,
            (
                "heartbeat:test",
                "runtime:test",
                "1.0",
                "cycle:test",
                "HOST",
                "HEALTHY",
                1,
                "NORMAL_WRITE",
                0.0,
            ),
        )
        connection.commit()

    validate_runtime_database(
        database,
        binding,
        expected_environment_id="RC5_OFFLINE_TEST",
    )


def test_sidecar_copy_or_environment_mismatch_fails_closed(tmp_path: Path) -> None:
    database = (tmp_path / "host.sqlite3").resolve()
    binding = (tmp_path / "host.binding.json").resolve()
    initialize_runtime_database(
        database,
        binding,
        environment_id="RC5_OFFLINE_TEST",
        source_commit="test-source",
    )
    payload = json.loads(binding.read_text(encoding="utf-8"))
    payload["database_instance_id"] = "00000000-0000-0000-0000-000000000000"
    binding.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeDatabaseIdentityError, match="instance"):
        validate_runtime_database(
            database,
            binding,
            expected_environment_id="RC5_OFFLINE_TEST",
        )


def test_disaster_restore_preserves_environment_and_rejects_cross_environment(
    tmp_path: Path,
) -> None:
    database = (tmp_path / "host.sqlite3").resolve()
    binding = (tmp_path / "host.binding.json").resolve()
    initialize_runtime_database(
        database,
        binding,
        environment_id="RC5_OFFLINE_TEST",
        source_commit="test-source",
    )

    with pytest.raises(RuntimeDatabaseIdentityError, match="cannot change"):
        bind_runtime_database(
            database,
            binding,
            environment_id="RC5_OTHER",
            source_commit="test-source",
            mode="RESTORE",
            backup_epoch="backup-other",
        )
