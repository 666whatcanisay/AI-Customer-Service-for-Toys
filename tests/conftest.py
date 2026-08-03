from __future__ import annotations

from collections.abc import Callable

import pytest

from channel_engine.execution import FakeExecutor
from channel_engine.gateway import FakeGateway
from channel_engine.storage import (
    SqlAlchemyUnitOfWork,
    create_engine_and_session,
    create_schema,
)


@pytest.fixture
def foundation(tmp_path):
    database_url = f"sqlite:///{(tmp_path / 'foundation.sqlite3').as_posix()}"
    engine, session_factory = create_engine_and_session(database_url)
    create_schema(engine)
    gateway = FakeGateway()
    executor = FakeExecutor()

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    yield {
        "engine": engine,
        "session_factory": session_factory,
        "uow_factory": uow_factory,
        "gateway": gateway,
        "executor": executor,
        "database_url": database_url,
    }
    engine.dispose()
