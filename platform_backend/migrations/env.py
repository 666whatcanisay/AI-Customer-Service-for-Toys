from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database import Base
from app.ingestion import models  # noqa: F401
from app.suggestions import models as suggestion_models  # noqa: F401
from app.experience_cases import models as experience_case_models  # noqa: F401
from app.ai_feedback import models as ai_feedback_models  # noqa: F401
from app.customer_efficiency import models as customer_efficiency_models  # noqa: F401
from app.customer_identity import models as customer_identity_models  # noqa: F401
from app.test_catalog import models as test_catalog_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url", os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
)
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
