from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field

from channel_engine.channel import ChannelMessage
from channel_engine.config import Settings
from channel_engine.conversation import ConversationService, IntakeResult
from channel_engine.execution import (
    ExecutionCoordinator,
    ExecutionOutcome,
    FakeExecutor,
    RejectionOutcome,
)
from channel_engine.gateway import FakeGateway
from channel_engine.models import Decision
from channel_engine.monitor import HealthStatus, foundation_health
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage import (
    RecordNotFound,
    SqlAlchemyUnitOfWork,
    create_engine_and_session,
    create_schema,
)


class FakeMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_external_ref: str = Field(min_length=1, max_length=255)
    external_message_id: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=8_000)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: str = Field(min_length=1, max_length=160)


class RejectionRequest(ApprovalRequest):
    reason: str = Field(min_length=1, max_length=1_000)


def create_app(
    settings: Settings | None = None,
    gateway: FakeGateway | None = None,
    executor: FakeExecutor | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    engine, session_factory = create_engine_and_session(active_settings.database_url)
    active_gateway = gateway or FakeGateway()
    active_executor = executor or FakeExecutor()

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    conversation_service = ConversationService(uow_factory, active_gateway)
    execution_coordinator = ExecutionCoordinator(
        uow_factory, active_executor, ApprovalPolicy()
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        create_schema(engine)
        yield
        engine.dispose()

    application = FastAPI(
        title="AI-CS Channel Execution Engine",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.get("/health", response_model=HealthStatus)
    def health() -> HealthStatus:
        return foundation_health(active_settings)

    @application.post("/v1/fake-channel/messages", response_model=IntakeResult)
    def receive_fake_message(payload: FakeMessageRequest) -> IntakeResult:
        try:
            return conversation_service.receive(
                ChannelMessage(
                    channel_name="fake-channel",
                    conversation_external_ref=payload.conversation_external_ref,
                    external_message_id=payload.external_message_id,
                    text=payload.text,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/v1/decisions/{decision_id}", response_model=Decision)
    def get_decision(
        decision_id: Annotated[str, Path(min_length=1, max_length=80)],
    ) -> Decision:
        try:
            with uow_factory() as uow:
                return uow.require_repository().get_decision(decision_id)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/v1/decisions/{decision_id}/approve", response_model=ExecutionOutcome
    )
    def approve(
        decision_id: Annotated[str, Path(min_length=1, max_length=80)],
        payload: ApprovalRequest,
    ) -> ExecutionOutcome:
        try:
            return execution_coordinator.approve_and_execute(decision_id, payload.operator)
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post(
        "/v1/decisions/{decision_id}/reject", response_model=RejectionOutcome
    )
    def reject(
        decision_id: Annotated[str, Path(min_length=1, max_length=80)],
        payload: RejectionRequest,
    ) -> RejectionOutcome:
        try:
            return execution_coordinator.reject(
                decision_id, payload.operator, payload.reason
            )
        except RecordNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    application.state.settings = active_settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.fake_executor = active_executor
    return application


app = create_app()


def run() -> None:
    uvicorn.run("channel_engine.app:app", host="127.0.0.1", port=18020, reload=False)
