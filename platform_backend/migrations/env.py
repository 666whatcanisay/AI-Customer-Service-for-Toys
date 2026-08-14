from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
configured_url = config.get_main_option("sqlalchemy.url")
if configured_url == "driver://explicit-database-url-required":
    configured_url = os.getenv("DATABASE_URL", "").strip()
    if not configured_url:
        raise RuntimeError("DATABASE_URL is required for Alembic migration commands")
config.set_main_option("sqlalchemy.url", configured_url)
# app.database constructs the SQLAlchemy engine during import.  Point it at the
# exact Alembic target first so migration tooling can never create platform.db.
os.environ["DATABASE_URL"] = config.get_main_option("sqlalchemy.url")
os.environ.setdefault("PLATFORM_REQUIRE_DATABASE_IDENTITY", "false")

from app.database import Base
from app.ingestion import models  # noqa: F401
from app.suggestions import models as suggestion_models  # noqa: F401
from app.experience_cases import models as experience_case_models  # noqa: F401
from app.ai_feedback import models as ai_feedback_models  # noqa: F401
from app.knowledge_materials import models as knowledge_material_models  # noqa: F401
from app.test_catalog import models as test_catalog_models  # noqa: F401
from app.customer_feedback_loop import models as customer_feedback_loop_models  # noqa: F401
from app.knowledge_publishing import models as knowledge_publishing_models  # noqa: F401
from app.iam import models as iam_models  # noqa: F401
from app.workspace import models as workspace_models  # noqa: F401
from app.desktop_agent import models as desktop_agent_models  # noqa: F401
from app.store_platform_bindings import models as store_platform_binding_models  # noqa: F401
from app.reply_rules import models as reply_rule_models  # noqa: F401
from app.reply_readiness import models as reply_readiness_models  # noqa: F401

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
