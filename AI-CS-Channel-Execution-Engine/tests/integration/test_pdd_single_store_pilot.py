from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from channel_engine.app import create_app
from channel_engine.channel import (
    FakePDDHTTPSender,
    FakePDDHTTPSenderMode,
    LedgerExecutionAuthorizationService,
    PDDControlledSendExecutionAdapter,
    PDDProductionExecutionGate,
    PDDProductionSafetyService,
    PDDSendTransport,
)
from channel_engine.config import Settings
from channel_engine.control.gate import PersistentExecutionControlGate
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionWorker
from channel_engine.gateway import FakeGateway
from channel_engine.models import DecisionState, ExecutionState, ReceiptOutcome
from channel_engine.models.entities import utc_now
from channel_engine.pilot import (
    PDD_PILOT_TARGET_STORE_NAME,
    FakePilotBrowserPort,
    FakePilotInboundPort,
    FakePilotKillSwitch,
    FakePilotStoreIdentityProbe,
    PDDPilotRuntime,
    PDDPilotSendPreflightGate,
    PilotApprovalError,
    PilotApprovalService,
    PilotBrowserStatus,
    PilotConfigError,
    PilotEvidenceType,
    PilotGatewayCapture,
    PilotLiveActivationError,
    PilotLiveActivationService,
    PilotLiveCapabilitySnapshot,
    PilotLiveFinalStatus,
    PilotObservedStore,
    PilotPDDSendSessionProvider,
    PilotPersistenceService,
    PilotReadinessLatch,
    PilotRuntimeError,
    PilotRuntimeState,
    PilotSafetyStatus,
    PilotSendLimitExceeded,
    PilotStoreConfig,
    PilotStoreStatus,
    load_pilot_store_config,
)
from channel_engine.channel import NormalizedMessage
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage import (
    SqlAlchemyUnitOfWork,
    create_engine_and_session,
    create_schema,
)


def _config(*, send_limit: int = 5) -> PilotStoreConfig:
    return PilotStoreConfig(
        store_id="pdd-wanqu-lego-verified",
        store_name=PDD_PILOT_TARGET_STORE_NAME,
        credential_reference="secret-ref://pdd/pilot/wanqu-lego/session",
        send_limit=send_limit,
        approval_required=True,
        auto_reply=False,
    )


def _observed(config: PilotStoreConfig, *, store_id: str | None = None):
    return PilotObservedStore(
        store_id=store_id or config.store_id,
        store_name=config.store_name,
        observed_at=utc_now(),
        source="verified-selector-contract:test",
    )


def _foundation(
    tmp_path: Path,
    *,
    browser_status: PilotBrowserStatus = PilotBrowserStatus.CONNECTED,
    observed_store_id: str | None = None,
    send_limit: int = 5,
):
    engine, session_factory = create_engine_and_session(
        f"sqlite:///{(tmp_path / 'pilot.sqlite3').as_posix()}"
    )
    create_schema(engine)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    config = _config(send_limit=send_limit)
    browser = FakePilotBrowserPort(browser_status)
    store_probe = FakePilotStoreIdentityProbe(
        _observed(config, store_id=observed_store_id)
    )
    inbound = FakePilotInboundPort()
    kill_switch = FakePilotKillSwitch()
    gateway = PilotGatewayCapture(FakeGateway())
    persistence = PilotPersistenceService(uow_factory)
    readiness = PilotReadinessLatch()
    execution_gate = PDDProductionExecutionGate(
        delegate=PersistentExecutionControlGate()
    )
    approval = PilotApprovalService(
        uow_factory,
        ApprovalPolicy(),
        execution_gate,
        config,
    )
    conversation = ConversationService(
        uow_factory,
        gateway,
        decision_context_provider=lambda _message: {
            "pilot_store_id": config.store_id,
            "pilot_mode": True,
        },
    )
    runtime = PDDPilotRuntime(
        config,
        browser,
        store_probe,
        inbound,
        gateway,
        conversation,
        approval,
        persistence,
        kill_switch,
        readiness,
        uow_factory=uow_factory,
    )
    safety = PDDProductionSafetyService(uow_factory)
    sender = FakePDDHTTPSender()
    transport = PDDSendTransport(
        LedgerExecutionAuthorizationService(uow_factory),
        PilotPDDSendSessionProvider(config, runtime.browser_snapshot),
        sender,
        safety_gate=PDDPilotSendPreflightGate(
            config,
            persistence,
            kill_switch,
            readiness,
            dry_run=True,
        ),
        receipt_store=safety.receipt_store,
    )
    worker = ExecutionWorker(
        uow_factory,
        PDDControlledSendExecutionAdapter(transport),
        "pilot-test-worker",
        control_gate=execution_gate,
    )
    runtime.worker = worker
    return {
        "engine": engine,
        "uow_factory": uow_factory,
        "config": config,
        "browser": browser,
        "store_probe": store_probe,
        "inbound": inbound,
        "kill_switch": kill_switch,
        "gateway": gateway,
        "persistence": persistence,
        "approval": approval,
        "safety": safety,
        "sender": sender,
        "transport": transport,
        "worker": worker,
        "runtime": runtime,
    }


def _message(suffix: str) -> NormalizedMessage:
    return NormalizedMessage(
        channel="pdd",
        conversation_id=f"pilot-conversation-{suffix}",
        external_message_id=f"pilot-message-{suffix}",
        sender="pilot-fake-customer",
        content=f"Pilot customer question {suffix}",
        timestamp=utc_now(),
    )


def _intake(foundation, suffix: str):
    foundation["inbound"].enqueue(_message(suffix))
    return foundation["runtime"].poll_message()


def test_pilot_config_is_strict_reference_only_and_hard_caps_send_limit(
    tmp_path,
) -> None:
    config = _config()
    path = tmp_path / "pilot.json"
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")

    assert load_pilot_store_config(path) == config
    assert config.store_name == "玩趣乐园积木店"
    assert config.auto_reply is False
    assert config.approval_required is True
    with pytest.raises(ValidationError):
        _config(send_limit=6)
    payload = config.model_dump(mode="json")
    payload["credential"] = "raw-cookie-value"
    bad = tmp_path / "bad-pilot.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PilotConfigError):
        load_pilot_store_config(bad)


def test_browser_waits_for_human_login_then_validates_exact_store(tmp_path) -> None:
    foundation = _foundation(
        tmp_path,
        browser_status=PilotBrowserStatus.LOGIN_REQUIRED,
    )
    runtime = foundation["runtime"]

    waiting = runtime.start()
    assert waiting.runtime_state is PilotRuntimeState.WAITING_FOR_LOGIN
    assert waiting.browser is PilotBrowserStatus.LOGIN_REQUIRED
    assert foundation["browser"].automatic_login_count == 0

    foundation["browser"].set_status(PilotBrowserStatus.CONNECTED)
    ready = runtime.check()
    assert ready.runtime_state is PilotRuntimeState.READY
    assert ready.store_status is PilotStoreStatus.MATCHED
    assert ready.node == "ONLINE"
    assert foundation["store_probe"].page_write_count == 0


def test_store_mismatch_fails_closed_before_message_or_send(tmp_path) -> None:
    foundation = _foundation(tmp_path, observed_store_id="pdd-wrong-store")

    status = foundation["runtime"].start()

    assert status.runtime_state is PilotRuntimeState.BLOCKED
    assert status.store_status is PilotStoreStatus.MISMATCH
    assert status.reason_code == "PILOT_STORE_MISMATCH"
    with pytest.raises(PilotRuntimeError, match="not ready"):
        foundation["runtime"].poll_message()
    assert foundation["sender"].send_count == 0


def test_message_to_decision_persists_required_evidence_before_ack(tmp_path) -> None:
    foundation = _foundation(tmp_path)
    assert foundation["runtime"].start().runtime_state is PilotRuntimeState.READY

    result = _intake(foundation, "evidence")

    assert result is not None
    assert result.requires_approval is True
    assert foundation["inbound"].acked == [
        ("pilot-conversation-evidence", "pilot-message-evidence")
    ]
    evidence = foundation["runtime"].evidence()
    message = next(
        item for item in evidence if item.evidence_type is PilotEvidenceType.MESSAGE_RECEIVED
    )
    decision = next(
        item for item in evidence if item.evidence_type is PilotEvidenceType.DECISION_CREATED
    )
    assert message.payload["external_message_id"] == "pilot-message-evidence"
    assert message.payload["conversation_id"] == "pilot-conversation-evidence"
    assert "timestamp" in message.payload
    assert decision.payload["decision_id"] == result.decision_id
    assert decision.payload["context"]["pilot_store_id"] == foundation["config"].store_id
    assert decision.payload["answer"] == result.answer
    assert decision.payload["citations"] == []


def test_manual_approval_is_required_and_click_runs_exact_execution(tmp_path) -> None:
    foundation = _foundation(tmp_path)
    foundation["runtime"].start()
    intake = _intake(foundation, "manual")
    assert intake is not None

    with foundation["uow_factory"]() as uow:
        decision = uow.require_repository().get_decision(intake.decision_id)
    assert decision.state is DecisionState.WAITING_APPROVAL
    assert foundation["sender"].send_count == 0
    with pytest.raises(PilotApprovalError):
        foundation["runtime"].approve_and_execute(intake.decision_id, "  ")

    executed = foundation["runtime"].approve_and_execute(
        intake.decision_id,
        "pilot-human",
    )

    assert executed.execution_state == ExecutionState.SUCCESS.value
    assert executed.receipt_outcome == ReceiptOutcome.SUCCESS.value
    assert executed.customer_message_sent is False
    assert foundation["sender"].send_count == 1
    assert foundation["sender"].real_platform_call_count == 0
    replay = foundation["runtime"].approve_and_execute(
        intake.decision_id,
        "pilot-human",
    )
    assert replay.receipt_id == executed.receipt_id
    assert foundation["sender"].send_count == 1


def test_manual_runner_claims_only_the_selected_execution(tmp_path) -> None:
    foundation = _foundation(tmp_path)
    foundation["runtime"].start()
    first = _intake(foundation, "exact-1")
    second = _intake(foundation, "exact-2")
    assert first is not None and second is not None
    first_execution = foundation["approval"].approve_and_reserve(
        first.decision_id,
        "pilot-human",
    )
    second_execution = foundation["approval"].approve_and_reserve(
        second.decision_id,
        "pilot-human",
    )

    result = foundation["worker"].run_execution(second_execution.execution_id)

    assert result is not None
    assert result.execution_id == second_execution.execution_id
    with foundation["uow_factory"]() as uow:
        first_state = uow.require_repository().get_execution(
            first_execution.execution_id
        ).state
    assert first_state is ExecutionState.PENDING


def test_send_limit_blocks_second_execution_before_sender(tmp_path) -> None:
    foundation = _foundation(tmp_path, send_limit=1)
    foundation["runtime"].start()
    first = _intake(foundation, "limit-1")
    second = _intake(foundation, "limit-2")
    assert first is not None and second is not None
    foundation["runtime"].approve_and_execute(first.decision_id, "pilot-human")

    with pytest.raises(PilotSendLimitExceeded):
        foundation["runtime"].approve_and_execute(
            second.decision_id,
            "pilot-human",
        )

    assert foundation["runtime"].status().today_send == 1
    assert foundation["sender"].send_count == 1
    with foundation["uow_factory"]() as uow:
        decision = uow.require_repository().get_decision(second.decision_id)
    assert decision.state is DecisionState.WAITING_APPROVAL


def test_receipt_and_pilot_evidence_survive_service_reconstruction(tmp_path) -> None:
    foundation = _foundation(tmp_path)
    foundation["runtime"].start()
    intake = _intake(foundation, "durable")
    assert intake is not None
    executed = foundation["runtime"].approve_and_execute(
        intake.decision_id,
        "pilot-human",
    )

    durable_receipt = PDDProductionSafetyService(
        foundation["uow_factory"]
    ).receipt_store.get_by_execution_id(executed.execution_id)
    durable_evidence = PilotPersistenceService(
        foundation["uow_factory"]
    ).list_evidence(foundation["config"].store_id)

    assert durable_receipt is not None
    assert durable_receipt.receipt.outcome is ReceiptOutcome.SUCCESS
    assert any(
        item.evidence_type is PilotEvidenceType.RECEIPT_RECORDED
        and item.payload["receipt_id"] == executed.receipt_id
        for item in durable_evidence
    )


def test_kill_switch_immediately_blocks_approval_and_send(tmp_path) -> None:
    foundation = _foundation(tmp_path)
    foundation["runtime"].start()
    intake = _intake(foundation, "kill")
    assert intake is not None

    blocked = foundation["runtime"].enable_kill_switch(
        operator="pilot-operator",
        reason="PILOT_EMERGENCY_STOP",
    )

    assert blocked.runtime_state is PilotRuntimeState.BLOCKED
    assert blocked.safety is PilotSafetyStatus.KILL_SWITCH
    with pytest.raises(PilotRuntimeError) as exc_info:
        foundation["runtime"].approve_and_execute(
            intake.decision_id,
            "pilot-human",
        )
    assert exc_info.value.error_code == "PILOT_KILL_SWITCH_ENABLED"
    assert foundation["sender"].send_count == 0


def test_pilot_dashboard_and_api_expose_manual_flow_without_send_endpoint(
    tmp_path,
) -> None:
    foundation = _foundation(tmp_path)
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'app.sqlite3').as_posix()}"
        ),
        pilot_runtime=foundation["runtime"],
    )
    foundation["inbound"].enqueue(_message("api"))

    with TestClient(application) as client:
        started = client.post("/pilot/start")
        polled = client.post("/pilot/messages/poll")
        approved = client.post(
            f"/pilot/decisions/{polled.json()['decision_id']}/approve",
            json={"operator": "pilot-api-human"},
        )
        status = client.get("/pilot/status")
        evidence = client.get("/pilot/evidence")
        ui = client.get("/pilot/ui")
        paths = client.get("/openapi.json").json()["paths"]

    assert started.json()["node"] == "ONLINE"
    assert started.json()["today_send"] == 0
    assert started.json()["send_limit"] == 5
    assert status.json()["store_name"] == "玩趣乐园积木店"
    assert status.json()["browser"] == "CONNECTED"
    assert status.json()["message"] == "READY"
    assert status.json()["ai"] == "READY"
    assert status.json()["safety"] == "PILOT_MODE"
    assert status.json()["today_send"] == 1
    assert status.json()["send_limit"] == 5
    assert approved.json()["receipt_outcome"] == "SUCCESS"
    assert evidence.status_code == 200 and len(evidence.json()) >= 7
    assert "人工确认并执行" in ui.text
    assert "/pilot/send" not in paths


def _verified_live_capabilities() -> PilotLiveCapabilitySnapshot:
    return PilotLiveCapabilitySnapshot(
        agent_online=True,
        runtime_storage_ready=True,
        clean_activation_database=True,
        browser_login_rules_verified=True,
        selector_contract_verified=True,
        store_identity_probe_verified=True,
        real_ai_cs_gateway=True,
        real_outbound_transport=True,
        evidence_sources=("test-evidence://controlled-live-harness",),
    )


class _DeclaredRealPilotBrowser(FakePilotBrowserPort):
    real_browser_capable = True


class _DeclaredRealPilotInbound(FakePilotInboundPort):
    real_platform_transport = True


def test_live_preflight_fails_closed_for_fake_default_composition(tmp_path) -> None:
    foundation = _foundation(tmp_path, send_limit=1)
    live = PilotLiveActivationService(foundation["runtime"])

    report = live.preflight()

    assert report.ready_for_manual_login is False
    assert report.maximum_replies == 1
    assert "PILOT_REAL_BROWSER_UNAVAILABLE" in report.blockers
    assert "PILOT_REAL_INBOUND_TRANSPORT_UNAVAILABLE" in report.blockers
    with pytest.raises(PilotLiveActivationError) as exc_info:
        live.start_manual_login()
    assert exc_info.value.error_code == "PILOT_LIVE_PREFLIGHT_BLOCKED"
    assert foundation["browser"].start_count == 0


def test_offline_complete_evidence_can_never_claim_live(tmp_path) -> None:
    foundation = _foundation(tmp_path, send_limit=1)
    foundation["runtime"].start()
    intake = _intake(foundation, "offline-not-live")
    assert intake is not None
    foundation["runtime"].approve_and_execute(intake.decision_id, "pilot-human")

    report = PilotLiveActivationService(foundation["runtime"]).evidence_report()

    assert report.final_status is PilotLiveFinalStatus.ACTIVATION_BLOCKED
    assert "PILOT_LIVE_REAL_SEND_RECEIPT_UNPROVEN" in report.blockers
    assert report.evidence_counts["RECEIPT_RECORDED"] == 1


def test_live_unknown_send_enables_kill_switch_and_stops(tmp_path) -> None:
    foundation = _foundation(tmp_path, send_limit=1)
    browser = _DeclaredRealPilotBrowser(PilotBrowserStatus.CONNECTED)
    inbound = _DeclaredRealPilotInbound()
    foundation["runtime"].browser = browser
    foundation["runtime"].inbound = inbound
    foundation["sender"].mode = FakePDDHTTPSenderMode.UNKNOWN
    live = PilotLiveActivationService(
        foundation["runtime"],
        _verified_live_capabilities(),
    )
    assert live.preflight().ready_for_manual_login is True
    live.start_manual_login()
    inbound.enqueue(_message("live-unknown"))
    intake = live.poll_one_message()
    assert intake is not None

    with pytest.raises(PilotLiveActivationError) as exc_info:
        live.approve_first_reply(intake.decision_id, "pilot-human")

    assert exc_info.value.error_code == "PILOT_SEND_UNKNOWN_STOP"
    assert foundation["kill_switch"].enabled() is True
    assert foundation["runtime"].status().runtime_state is PilotRuntimeState.STOPPED
    assert live.evidence_report().final_status is PilotLiveFinalStatus.STOPPED


def test_live_api_exposes_preflight_and_no_bare_send_endpoint(tmp_path) -> None:
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'live-api.sqlite3').as_posix()}"
        )
    )

    with TestClient(application) as client:
        report = client.get("/pilot/live/preflight")
        blocked = client.post("/pilot/live/start")
        paths = client.get("/openapi.json").json()["paths"]

    assert report.status_code == 200
    assert report.json()["ready_for_manual_login"] is False
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "PILOT_LIVE_PREFLIGHT_BLOCKED"
    assert "/pilot/live/send" not in paths
