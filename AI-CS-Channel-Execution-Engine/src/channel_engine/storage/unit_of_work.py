from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from .repository import ChannelEngineRepository


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None
        self.repository: ChannelEngineRepository | None = None

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        self.repository = ChannelEngineRepository(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        assert self.session is not None
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()

    def require_repository(self) -> ChannelEngineRepository:
        if self.repository is None:
            raise RuntimeError("unit of work is not active")
        return self.repository
