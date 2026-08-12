import json
from pathlib import Path
import os
import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from app.runtime_database_identity import (
    DatabaseIdentityError,
    bind_runtime_database,
    validate_runtime_database,
)


def _migrated_database(tmp_path: Path) -> Path:
    os.environ.pop("DATABASE_URL", None)
    path = tmp_path / "platform.sqlite3"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "head")
    return path


def test_new_instance_binds_internal_identity_and_sidecar(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    binding = tmp_path / "platform.binding.json"

    created = bind_runtime_database(
        database,
        binding,
        environment_id="RC5_ACCEPTANCE",
        source_commit="a" * 40,
        mode="NEW_INSTANCE",
    )
    verified = validate_runtime_database(
        database, binding, expected_environment_id="RC5_ACCEPTANCE"
    )

    assert verified == created
    payload = json.loads(binding.read_text(encoding="utf-8"))
    assert payload["database_instance_id"] == created.database_instance_id
    assert payload["canonical_path"] == str(database.resolve())
    assert "database_sha256" not in payload


def test_normal_business_write_does_not_break_identity(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    binding = tmp_path / "platform.binding.json"
    identity = bind_runtime_database(
        database,
        binding,
        environment_id="RC5_ACCEPTANCE",
        source_commit="b" * 40,
        mode="NEW_INSTANCE",
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE runtime_database_identity SET created_by_source_commit = ?",
            ("c" * 40,),
        )
    assert (
        validate_runtime_database(
            database, binding, expected_environment_id="RC5_ACCEPTANCE"
        ).database_instance_id
        == identity.database_instance_id
    )


def test_sidecar_path_or_environment_mismatch_fails_closed(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    binding = tmp_path / "platform.binding.json"
    bind_runtime_database(
        database,
        binding,
        environment_id="RC5_ACCEPTANCE",
        source_commit="c" * 40,
        mode="NEW_INSTANCE",
    )
    payload = json.loads(binding.read_text(encoding="utf-8"))
    payload["canonical_path"] = str(tmp_path / "other.sqlite3")
    binding.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DatabaseIdentityError, match="canonical path"):
        validate_runtime_database(
            database, binding, expected_environment_id="RC5_ACCEPTANCE"
        )


def test_clone_gets_new_id_but_restore_preserves_id(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    binding = tmp_path / "platform.binding.json"
    original = bind_runtime_database(
        database,
        binding,
        environment_id="RC5_ACCEPTANCE",
        source_commit="d" * 40,
        mode="NEW_INSTANCE",
    )
    restored = bind_runtime_database(
        database,
        binding,
        environment_id="RC5_ACCEPTANCE",
        source_commit="e" * 40,
        mode="RESTORE",
        backup_epoch="backup-20260812-001",
    )
    assert restored.database_instance_id == original.database_instance_id
    assert restored.restore_generation == 1
    assert restored.restored_from_backup_epoch == "backup-20260812-001"

    cloned = bind_runtime_database(
        database,
        binding,
        environment_id="RC5_CLONE",
        source_commit="f" * 40,
        mode="NEW_INSTANCE",
    )
    assert cloned.database_instance_id != original.database_instance_id
    assert cloned.restore_generation == 0


def test_upgrade_preserves_logical_database_identity(tmp_path: Path) -> None:
    database = _migrated_database(tmp_path)
    binding = tmp_path / "platform.binding.json"
    original = bind_runtime_database(
        database,
        binding,
        environment_id="RC5_ACCEPTANCE",
        source_commit="1" * 40,
        mode="NEW_INSTANCE",
    )

    upgraded = bind_runtime_database(
        database,
        binding,
        environment_id="RC5_ACCEPTANCE",
        source_commit="2" * 40,
        mode="UPGRADE",
    )

    assert upgraded.database_instance_id == original.database_instance_id
    assert upgraded.restore_generation == original.restore_generation
    assert upgraded.created_by_source_commit == original.created_by_source_commit


def test_restore_cannot_move_logical_database_between_environments(
    tmp_path: Path,
) -> None:
    database = _migrated_database(tmp_path)
    binding = tmp_path / "platform.binding.json"
    bind_runtime_database(
        database,
        binding,
        environment_id="RC5_ACCEPTANCE",
        source_commit="3" * 40,
        mode="NEW_INSTANCE",
    )

    with pytest.raises(DatabaseIdentityError, match="cannot change"):
        bind_runtime_database(
            database,
            binding,
            environment_id="RC5_OTHER",
            source_commit="4" * 40,
            mode="RESTORE",
            backup_epoch="backup-other",
        )
