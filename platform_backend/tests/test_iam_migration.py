from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.iam.service import PERMISSIONS_BY_ROLE


def _config(database_path: Path) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_0013_upgrade_downgrade_upgrade_is_additive_and_seeds_fixed_roles(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "iam-v1.sqlite3"
    config = _config(database_path)
    command.upgrade(config, "0012_internal_production_finalization_v1")
    command.upgrade(config, "0013_user_management_v1")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert {
        "users", "roles", "permissions", "role_permissions", "user_roles",
        "user_store_bindings", "user_sessions",
    }.issubset(set(inspect(engine).get_table_names()))
    with engine.connect() as connection:
        user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
        assert "must_change_password" in user_columns
        roles = connection.execute(text("SELECT role_name FROM roles ORDER BY role_name")).scalars().all()
        assert roles == ["ADMIN", "CUSTOMER_SERVICE", "OPERATOR"]
        permissions = connection.execute(text(
            "SELECT permission_name FROM permissions ORDER BY permission_name"
        )).scalars().all()
        assert permissions == sorted(set().union(*PERMISSIONS_BY_ROLE.values()))
        mappings = set(connection.execute(text(
            "SELECT roles.role_name, permissions.permission_name "
            "FROM role_permissions "
            "JOIN roles ON roles.id = role_permissions.role_id "
            "JOIN permissions ON permissions.id = role_permissions.permission_id"
        )).all())
        assert mappings == {
            (role.value, permission_name)
            for role, permission_names in PERMISSIONS_BY_ROLE.items()
            for permission_name in permission_names
        }
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0013_user_management_v1"
    engine.dispose()

    command.downgrade(config, "0012_internal_production_finalization_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    assert "users" not in inspect(engine).get_table_names()
    assert "permissions" not in inspect(engine).get_table_names()
    engine.dispose()

    command.upgrade(config, "0013_user_management_v1")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM roles")) == 3
        assert connection.scalar(text("SELECT count(*) FROM permissions")) == 12
        assert connection.scalar(text("SELECT count(*) FROM role_permissions")) == 23
    engine.dispose()
