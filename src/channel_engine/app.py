from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated

import uvicorn
from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field

from channel_engine import __version__
from channel_engine.agent import (
    AgentNodeStatus,
    ChannelAgentFirstLaunchService,
    ChannelAgentConfig,
    ChannelAgentService,
    FakeAgentBrowserController,
    FakeAgentChannelRuntimeProbe,
    FakeAgentServerConnector,
    PDDProductionKillSwitchProvider,
    create_agent_router,
    default_channel_agent_config,
    load_channel_agent_config,
)
from channel_engine.agent.node_api import (
    ChannelAgentNodeRegistry,
    create_channel_agent_node_router,
)
from channel_engine.agent.binding_repository import SqlAlchemyAgentIdentityRepository
from channel_engine.channel import (
    AdapterRegistry,
    ChannelManager,
    ChannelManagerStatus,
    FakeChannelAdapter,
    FakePDDAdapter,
    FakePDDHTTPSender,
    FakePDDInboundMessage,
    LedgerExecutionAuthorizationService,
    PDDControlledSendExecutionAdapter,
    PDDProductionExecutionGate,
    PDDProductionSafetyService,
    PDDSendTransport,
)
from channel_engine.config import Settings
from channel_engine.control.gate import PersistentExecutionControlGate
from channel_engine.control.health import (
    ControlPlaneHealthAggregator,
    WorkerRuntimeMonitor,
)
from channel_engine.control.models import (
    ChannelEngineHealth,
    ComponentHealthState,
    ControlPlaneStatus,
    GatewayStatus,
)
from channel_engine.control.service import ControlPlaneService
from channel_engine.conversation import ConversationService, IntakeResult
from channel_engine.execution import (
    ExecutionCoordinator,
    ExecutionEnqueued,
    ExecutionWorker,
    FakeExecutor,
    RejectionOutcome,
    WorkerOwnershipRegistry,
)
from channel_engine.environment import (
    EnvironmentProfile,
    StagingAction,
    StagingSafetyDenied,
    StagingSafetyGuard,
)
from channel_engine.gateway import (
    AICSGateway,
    AICSGatewayClient,
    GatewayRequestSigner,
    MockAICSServer,
    MockAICSTransport,
)
from channel_engine.models import Decision
from channel_engine.models.entities import utc_now
from channel_engine.monitor import HealthStatus, foundation_health
from channel_engine.observability import (
    StructuredEvent,
    StructuredEventStatus,
    StructuredEventType,
)
from channel_engine.observability.api import create_observability_router
from channel_engine.observability.actions import OperationsApprovalService
from channel_engine.observability.service import ObservabilityService
from channel_engine.outbox import FakeEventPublisher, OutboxPublisher
from channel_engine.pdd_adapter import (
    PDDReceiveTransportDescriptor,
    PDDRuntimeStatusMonitor,
    PDDTransportOrigin,
    create_pdd_runtime_status_router,
)
from channel_engine.pilot import (
    FakePilotBrowserPort,
    FakePilotInboundPort,
    FakePilotStoreIdentityProbe,
    PDDPilotKillSwitchAdapter,
    PDDPilotRuntime,
    PDDPilotSendPreflightGate,
    PilotApprovalService,
    PilotGatewayCapture,
    PilotLiveActivationService,
    PilotLiveCapabilitySnapshot,
    PilotPDDSendSessionProvider,
    PilotPersistenceService,
    PilotReadinessLatch,
    PilotStoreConfig,
    create_pilot_router,
    default_pilot_store_config,
    load_pilot_store_config,
)
from channel_engine.policy import ApprovalPolicy
from channel_engine.reliability import (
    BrowserHealthProbe,
    ChannelRuntimeManager,
    ComponentHealth as ReliabilityComponentHealth,
    FakeBrowserAdapter as ReliabilityFakeBrowserAdapter,
    HeartbeatManager,
    ProbeReading,
    RuntimeComponent,
    RuntimeRecoveryCoordinator,
    RuntimeReliabilityStore,
    StorageHealthProbe,
    create_runtime_reliability_router,
)
from channel_engine.session import (
    ChannelInstanceManager,
    ChannelSessionRuntimeHealthProbe,
    ChannelSessionStore,
    CredentialReference,
    FakeCredentialProvider,
    MessageReliabilityService,
    SessionHeartbeatScheduler,
    create_channel_session_router,
)
from channel_engine.security.rbac import (
    FileBackedAgentOperatorIdentityProvider,
    OperatorIdentityProvider,
)
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
    sender: str = Field(default="api-customer", min_length=1, max_length=255)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: str = Field(min_length=1, max_length=160)


class RejectionRequest(ApprovalRequest):
    reason: str = Field(min_length=1, max_length=1_000)


def create_app(
    settings: Settings | None = None,
    gateway: AICSGateway | None = None,
    executor: FakeExecutor | None = None,
    agent_config: ChannelAgentConfig | None = None,
    agent_service: ChannelAgentService | None = None,
    first_launch_service: ChannelAgentFirstLaunchService | None = None,
    agent_node_registry: ChannelAgentNodeRegistry | None = None,
    agent_operator_identity_provider: OperatorIdentityProvider | None = None,
    pilot_config: PilotStoreConfig | None = None,
    pilot_runtime: PDDPilotRuntime | None = None,
    pilot_live_capabilities: PilotLiveCapabilitySnapshot | None = None,
    pdd_receive_transport: PDDReceiveTransportDescriptor | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    if active_settings.environment_profile.profile is EnvironmentProfile.PRODUCTION:
        if (
            pdd_receive_transport is None
            or pdd_receive_transport.origin is not PDDTransportOrigin.PRODUCTION
            or pdd_receive_transport.fake_transport
        ):
            raise ValueError(
                "PDD_PRODUCTION_RECEIVE_TRANSPORT_DESCRIPTOR_REQUIRED"
            )
    engine, session_factory = create_engine_and_session(active_settings.database_url)
    mock_ai_cs_server: MockAICSServer | None = None
    gateway_client: AICSGatewayClient | None = None
    if gateway is None:
        mock_secret = secrets.token_bytes(32)
        mock_ai_cs_server = MockAICSServer(
            {("channel-engine", "foundation-runtime"): mock_secret}
        )
        gateway_client = AICSGatewayClient(
            MockAICSTransport(mock_ai_cs_server),
            GatewayRequestSigner(
                client_id="channel-engine",
                key_id="foundation-runtime",
                secret=mock_secret,
            ),
        )
        active_gateway: AICSGateway = gateway_client
    else:
        active_gateway = gateway
    active_executor = executor or FakeExecutor()
    fake_pdd_adapter = FakePDDAdapter()
    adapter_registry = AdapterRegistry()
    if active_settings.environment_profile.profile is not EnvironmentProfile.PRODUCTION:
        adapter_registry.register(fake_pdd_adapter)
    staging_guard = (
        StagingSafetyGuard(active_settings.environment_profile)
        if active_settings.environment_profile.profile is EnvironmentProfile.STAGING
        else None
    )

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    control_plane = ControlPlaneService(uow_factory)
    pdd_safety = PDDProductionSafetyService(uow_factory)
    execution_control_gate = PersistentExecutionControlGate()
    worker_monitor = WorkerRuntimeMonitor(active_settings.execution_worker_id)
    worker_ownership = WorkerOwnershipRegistry(
        uow_factory,
        active_settings.execution_worker_id,
        lease_duration=timedelta(
            seconds=active_settings.worker_ownership_lease_seconds
        ),
    )
    conversation_service = ConversationService(uow_factory, active_gateway)
    execution_coordinator = ExecutionCoordinator(
        uow_factory,
        ApprovalPolicy(),
        control_gate=execution_control_gate,
    )
    execution_worker = ExecutionWorker(
        uow_factory,
        active_executor,
        active_settings.execution_worker_id,
        lease_duration=timedelta(seconds=active_settings.execution_lease_seconds),
        control_gate=execution_control_gate,
        on_loop_started=worker_monitor.mark_running,
        on_loop_stopped=worker_monitor.mark_stopped,
        ownership_registry=worker_ownership,
    )
    fake_event_publisher = FakeEventPublisher()
    outbox_publisher = OutboxPublisher(
        uow_factory,
        fake_event_publisher,
        active_settings.outbox_publisher_id,
        max_attempts=active_settings.outbox_max_attempts,
    )

    def gateway_status() -> GatewayStatus:
        if gateway_client is None:
            return GatewayStatus(
                health=ComponentHealthState.HEALTHY,
                reachable=True,
                gateway_version=getattr(active_gateway, "version", "injected-gateway"),
                checked_at=utc_now(),
            )
        health = gateway_client.health_check()
        return GatewayStatus(
            health=(
                ComponentHealthState.HEALTHY
                if health.status.value == "HEALTHY"
                else ComponentHealthState.DEGRADED
            ),
            reachable=health.reachable,
            gateway_version=health.gateway_version,
            checked_at=health.checked_at,
        )

    control_health = ControlPlaneHealthAggregator(
        uow_factory,
        control_plane,
        adapter_registry,
        gateway_status,
        worker_monitor,
        service_name=active_settings.service_name,
        environment=active_settings.environment,
    )
    reliability_store = RuntimeReliabilityStore(uow_factory)
    reliability_browser = ReliabilityFakeBrowserAdapter()
    channel_manager = ChannelManager()
    managed_fake_channel = FakeChannelAdapter(
        channel="fake",
        store_id="fake-store",
    )
    channel_manager.register(managed_fake_channel)

    def reliability_gateway_probe():
        status = gateway_status()
        reachable = (
            status.reachable
            and status.health is ComponentHealthState.HEALTHY
        )
        return ProbeReading(
            health=(
                ReliabilityComponentHealth.HEALTHY
                if reachable
                else ReliabilityComponentHealth.UNHEALTHY
            ),
            available=reachable,
            reason_code=(
                "AI_CS_GATEWAY_HEALTHY"
                if reachable
                else "AI_CS_GATEWAY_UNHEALTHY"
            ),
        )

    session_store = ChannelSessionStore(uow_factory)
    fake_credential_reference = CredentialReference(
        credential_ref="fake-vault://channel/fake-store",
        provider="fake-vault",
        version="v1",
    )
    fake_credential_provider = FakeCredentialProvider(
        (fake_credential_reference,)
    )
    message_reliability = MessageReliabilityService(
        uow_factory,
        session_store,
    )
    channel_instance_manager = ChannelInstanceManager(
        session_store,
        fake_credential_provider,
        message_reliability,
    )
    session_heartbeat_scheduler = SessionHeartbeatScheduler(
        channel_instance_manager,
        session_store,
        BrowserHealthProbe(reliability_browser),
        reliability_gateway_probe,
        interval_seconds=30,
    )
    reliability_channel_probe = ChannelSessionRuntimeHealthProbe(
        session_heartbeat_scheduler
    )

    reliability_heartbeat = HeartbeatManager(
        "channel-engine-runtime",
        reliability_store,
        {
            RuntimeComponent.CHANNEL: reliability_channel_probe,
            RuntimeComponent.BROWSER: BrowserHealthProbe(reliability_browser),
            RuntimeComponent.GATEWAY: reliability_gateway_probe,
            RuntimeComponent.STORAGE: StorageHealthProbe(uow_factory),
        },
    )

    def record_runtime_recovery(event) -> None:
        event_type = {
            "RECOVERING": StructuredEventType.RECOVERY_STARTED,
            "RECOVERED": StructuredEventType.RECOVERY_COMPLETED,
            "MANUAL_INTERVENTION": (
                StructuredEventType.RECOVERY_MANUAL_INTERVENTION
            ),
        }[event.state.value]
        event_status = {
            "RECOVERING": StructuredEventStatus.PENDING,
            "RECOVERED": StructuredEventStatus.SUCCESS,
            "MANUAL_INTERVENTION": StructuredEventStatus.BLOCKED,
        }[event.state.value]
        with uow_factory() as uow:
            uow.require_repository().append_observability_event(
                StructuredEvent(
                    event_id=f"ops-{event.recovery_event_id}",
                    event_type=event_type,
                    trace_id=event.recovery_id,
                    timestamp=event.occurred_at,
                    status=event_status,
                    metadata={
                        "component": event.component.value,
                        "attempt": event.attempt,
                        "reason_code": event.reason_code,
                    },
                )
            )

    reliability_recovery = RuntimeRecoveryCoordinator(
        "channel-engine-runtime",
        reliability_store,
        {
            RuntimeComponent.CHANNEL: channel_instance_manager.recover_all,
            RuntimeComponent.BROWSER: lambda: (
                reliability_browser.recover()
                and channel_instance_manager.recover_all()
            ),
        },
        max_attempts=2,
        event_observer=record_runtime_recovery,
    )

    def record_channel_state(state: str) -> None:
        event_status = (
            StructuredEventStatus.SUCCESS
            if state == "CONNECTED"
            else (
                StructuredEventStatus.FAILED
                if state == "FAILED"
                else StructuredEventStatus.INFO
            )
        )
        with uow_factory() as uow:
            repo = uow.require_repository()
            repo.append_observability_event(
                StructuredEvent(
                    event_type=StructuredEventType.SESSION_CHANGED,
                    trace_id="channel-instance-fake-store",
                    store_id="fake-store",
                    status=event_status,
                    metadata={
                        "session_state": state,
                        "reason_code": f"CHANNEL_SESSION_{state}",
                    },
                )
            )
            if state == "CONNECTED":
                repo.append_observability_event(
                    StructuredEvent(
                        event_type=StructuredEventType.CHANNEL_CONNECTED,
                        trace_id="channel-instance-fake-store",
                        store_id="fake-store",
                        status=StructuredEventStatus.SUCCESS,
                        metadata={
                            "channel_name": "fake",
                            "reason_code": "CHANNEL_ADAPTER_CONNECTED",
                        },
                    )
                )

    channel_runtime = ChannelRuntimeManager(
        "channel-engine-runtime",
        reliability_browser,
        reliability_heartbeat,
        reliability_recovery,
        reliability_store,
        channel_start=channel_instance_manager.start_all,
        channel_stop=channel_instance_manager.stop_all,
        on_channel_state=record_channel_state,
    )
    observability = ObservabilityService(
        uow_factory,
        runtime_status=channel_runtime.dashboard,
        control_health=control_health.snapshot,
    )
    operations_approval = OperationsApprovalService(execution_coordinator)
    pdd_runtime_status = PDDRuntimeStatusMonitor()
    active_agent = agent_service or ChannelAgentService(
        agent_config or default_channel_agent_config(),
        FakeAgentServerConnector(),
        FakeAgentBrowserController(),
        FakeAgentChannelRuntimeProbe(),
        kill_switch_provider=PDDProductionKillSwitchProvider(pdd_safety),
    )
    if pilot_runtime is None:
        active_pilot_config = pilot_config or default_pilot_store_config()
        pilot_browser = FakePilotBrowserPort()
        pilot_store_probe = FakePilotStoreIdentityProbe()
        pilot_inbound = FakePilotInboundPort()
        pilot_gateway = PilotGatewayCapture(active_gateway)
        pilot_persistence = PilotPersistenceService(uow_factory)
        pilot_kill_switch = PDDPilotKillSwitchAdapter(
            pdd_safety,
            global_control_plane=control_plane,
        )
        pilot_readiness = PilotReadinessLatch()
        pilot_execution_gate = PDDProductionExecutionGate(
            delegate=PersistentExecutionControlGate()
        )
        pilot_approval = PilotApprovalService(
            uow_factory,
            ApprovalPolicy(),
            pilot_execution_gate,
            active_pilot_config,
        )
        active_pilot = PDDPilotRuntime(
            active_pilot_config,
            pilot_browser,
            pilot_store_probe,
            pilot_inbound,
            pilot_gateway,
            ConversationService(uow_factory, pilot_gateway),
            pilot_approval,
            pilot_persistence,
            pilot_kill_switch,
            pilot_readiness,
            uow_factory=uow_factory,
        )
        pilot_session = PilotPDDSendSessionProvider(
            active_pilot_config,
            active_pilot.browser_snapshot,
        )
        pilot_send_gate = PDDPilotSendPreflightGate(
            active_pilot_config,
            pilot_persistence,
            pilot_kill_switch,
            pilot_readiness,
            dry_run=True,
        )
        pilot_transport = PDDSendTransport(
            LedgerExecutionAuthorizationService(uow_factory),
            pilot_session,
            FakePDDHTTPSender(),
            safety_gate=pilot_send_gate,
            receipt_store=pdd_safety.receipt_store,
        )
        active_pilot.worker = ExecutionWorker(
            uow_factory,
            PDDControlledSendExecutionAdapter(pilot_transport),
            "single-store-pilot-worker",
            control_gate=pilot_execution_gate,
        )
    else:
        active_pilot = pilot_runtime
    pilot_live = PilotLiveActivationService(
        active_pilot,
        pilot_live_capabilities,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        create_schema(engine)
        channel_instance_manager.create_instance(
            instance_id="channel-instance-fake-store",
            platform="fake",
            store_id="fake-store",
            adapter_type="FakeChannelAdapter",
            credential_ref=fake_credential_reference,
            adapter=managed_fake_channel,
        )
        record_channel_state("CREATED")
        session_heartbeat_scheduler.start()
        try:
            yield
        finally:
            session_heartbeat_scheduler.stop()
            if channel_runtime.status().state.value != "STOPPED":
                channel_runtime.stop()
            if active_pilot.status().runtime_state.value not in {
                "INIT",
                "STOPPED",
            }:
                active_pilot.stop()
            if active_agent.status().node.status not in {
                AgentNodeStatus.INIT,
                AgentNodeStatus.STOPPED,
            }:
                active_agent.stop()
            engine.dispose()

    application = FastAPI(
        title="AI-CS Channel Agent Node",
        version=__version__,
        lifespan=lifespan,
    )
    application.include_router(
        create_agent_router(active_agent, first_launch_service)
    )
    active_agent_node_registry = agent_node_registry or ChannelAgentNodeRegistry(
        identity_repository=SqlAlchemyAgentIdentityRepository(session_factory)
    )
    active_agent_operator_identity_provider = agent_operator_identity_provider
    if (
        active_agent_operator_identity_provider is None
        and active_settings.agent_operator_session_file is not None
    ):
        active_agent_operator_identity_provider = (
            FileBackedAgentOperatorIdentityProvider(
                active_settings.agent_operator_session_file,
                principal_id=active_settings.agent_operator_principal_id,
            )
        )
    application.state.channel_agent_node_registry = active_agent_node_registry
    application.include_router(
        create_channel_agent_node_router(
            active_agent_node_registry,
            identity_provider=active_agent_operator_identity_provider,
        )
    )
    application.include_router(create_pilot_router(active_pilot, pilot_live))
    application.include_router(create_runtime_reliability_router(channel_runtime))
    application.include_router(
        create_channel_session_router(
            channel_instance_manager,
            session_heartbeat_scheduler,
        )
    )
    application.include_router(
        create_observability_router(observability, operations_approval)
    )
    application.include_router(
        create_pdd_runtime_status_router(pdd_runtime_status.snapshot)
    )

    @application.get("/health", response_model=HealthStatus)
    def health() -> HealthStatus:
        return foundation_health(active_settings)

    @application.get("/control/v1/status", response_model=ControlPlaneStatus)
    def control_status() -> ControlPlaneStatus:
        return control_plane.status()

    @application.get("/control/v1/health", response_model=ChannelEngineHealth)
    def control_health_status() -> ChannelEngineHealth:
        return control_health.snapshot()

    @application.get("/runtime/v1/adapters", response_model=ChannelManagerStatus)
    def runtime_adapter_status() -> ChannelManagerStatus:
        return channel_manager.status()

    @application.post("/v1/fake-channel/messages", response_model=IntakeResult)
    def receive_fake_message(payload: FakeMessageRequest) -> IntakeResult:
        try:
            if active_settings.environment_profile.profile is EnvironmentProfile.PRODUCTION:
                raise HTTPException(
                    status_code=404,
                    detail="FAKE_CHANNEL_DISABLED_IN_PRODUCTION",
                )
            if staging_guard is not None:
                credential = active_settings.environment_profile.credential_reference
                assert credential is not None
                staging_guard.assert_allowed(
                    account_ref=credential.account_ref,
                    conversation_id=payload.conversation_external_ref,
                    action=StagingAction.OBSERVE_MESSAGE,
                )
                staging_guard.assert_allowed(
                    account_ref=credential.account_ref,
                    conversation_id=payload.conversation_external_ref,
                    action=StagingAction.REQUEST_DECISION,
                )
            raw = FakePDDInboundMessage(
                chat_id=payload.conversation_external_ref,
                message_id=payload.external_message_id,
                buyer_id=payload.sender,
                body=payload.text,
            )
            enqueued = fake_pdd_adapter.enqueue_customer_message(raw)
            inbound = (
                fake_pdd_adapter.receive_message()
                if enqueued
                else fake_pdd_adapter.normalize_message(raw)
            )
            if inbound is None:
                raise RuntimeError("fake PDD adapter lost an enqueued message")
            return conversation_service.receive(inbound)
        except StagingSafetyDenied as exc:
            raise HTTPException(status_code=403, detail=exc.reason_code) from exc
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
        "/v1/decisions/{decision_id}/approve",
        response_model=ExecutionEnqueued,
        status_code=202,
    )
    def approve(
        decision_id: Annotated[str, Path(min_length=1, max_length=80)],
        payload: ApprovalRequest,
    ) -> ExecutionEnqueued:
        try:
            if staging_guard is not None:
                with uow_factory() as uow:
                    repo = uow.require_repository()
                    decision = repo.get_decision(decision_id)
                    conversation = repo.get_conversation(decision.conversation_id)
                credential = active_settings.environment_profile.credential_reference
                assert credential is not None
                staging_guard.assert_allowed(
                    account_ref=credential.account_ref,
                    conversation_id=conversation.external_ref,
                    action=StagingAction.SIMULATE_SEND_MESSAGE,
                )
            return execution_coordinator.approve_and_enqueue(decision_id, payload.operator)
        except StagingSafetyDenied as exc:
            raise HTTPException(status_code=403, detail=exc.reason_code) from exc
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
    application.state.execution_worker = execution_worker
    application.state.fake_event_publisher = fake_event_publisher
    application.state.outbox_publisher = outbox_publisher
    application.state.fake_pdd_adapter = fake_pdd_adapter
    application.state.adapter_registry = adapter_registry
    application.state.ai_cs_gateway = active_gateway
    application.state.gateway_client = gateway_client
    application.state.mock_ai_cs_server = mock_ai_cs_server
    application.state.control_plane = control_plane
    application.state.execution_control_gate = execution_control_gate
    application.state.worker_monitor = worker_monitor
    application.state.worker_ownership = worker_ownership
    application.state.control_health = control_health
    application.state.environment_profile = active_settings.environment_profile
    application.state.staging_safety_guard = staging_guard
    application.state.pdd_safety = pdd_safety
    application.state.channel_agent = active_agent
    application.state.pdd_pilot = active_pilot
    application.state.pdd_pilot_live = pilot_live
    application.state.channel_runtime = channel_runtime
    application.state.runtime_reliability_store = reliability_store
    application.state.runtime_heartbeat = reliability_heartbeat
    application.state.runtime_recovery = reliability_recovery
    application.state.runtime_browser = reliability_browser
    application.state.runtime_channel_probe = reliability_channel_probe
    application.state.channel_manager = channel_manager
    application.state.managed_fake_channel = managed_fake_channel
    application.state.channel_session_store = session_store
    application.state.channel_instance_manager = channel_instance_manager
    application.state.message_reliability = message_reliability
    application.state.session_heartbeat_scheduler = session_heartbeat_scheduler
    application.state.fake_credential_provider = fake_credential_provider
    application.state.observability = observability
    application.state.operations_approval = operations_approval
    application.state.pdd_runtime_status = pdd_runtime_status
    return application


app = create_app()


def run() -> None:
    uvicorn.run("channel_engine.app:app", host="127.0.0.1", port=18020, reload=False)


def run_agent() -> None:
    config_path = os.getenv("CHANNEL_AGENT_CONFIG_PATH")
    config = (
        load_channel_agent_config(config_path)
        if config_path
        else default_channel_agent_config()
    )
    pilot_config_path = os.getenv("PDD_PILOT_CONFIG_PATH")
    active_pilot_config = (
        load_pilot_store_config(pilot_config_path)
        if pilot_config_path
        else default_pilot_store_config()
    )
    application = create_app(
        agent_config=config,
        pilot_config=active_pilot_config,
    )
    port = int(os.getenv("CHANNEL_AGENT_PORT", "18020"))
    uvicorn.run(application, host="127.0.0.1", port=port, reload=False)
