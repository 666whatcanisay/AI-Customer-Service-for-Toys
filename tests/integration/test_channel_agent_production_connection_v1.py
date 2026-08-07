from __future__ import annotations

import io
import socket
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from typing import Callable

import uvicorn
from fastapi import FastAPI

from channel_agent import windows_app
from channel_agent.binding import (
    AgentBindingStore,
    AgentEnrollmentGrantRequest,
)
from channel_agent.client import ChannelEngineClient
from channel_agent.config import ChannelAgentConfig
from channel_agent.contract import AgentRuntimeStatus, ManagedAgentConfig
from channel_agent.identity import AgentIdentityActivationRequest, AgentOnlineStatus
from channel_agent.windows import (
    WindowsAgentHost,
    WindowsClientProcessStatus,
)
from channel_engine.agent.binding_repository import SqlAlchemyAgentIdentityRepository
from channel_engine.agent.node_api import (
    ChannelAgentNodeRegistry,
    create_channel_agent_node_router,
)
from channel_engine.security.rbac import OperatorPrincipal, OperatorRole
from channel_engine.storage import create_engine_and_session, create_schema


CODE = "E" * 32


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _start_server(app: FastAPI, port: int) -> tuple[uvicorn.Server, Thread]:
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="critical",
            access_log=False,
        )
    )
    worker = Thread(target=server.run, name="channel-engine-test-server")
    worker.start()
    _wait_until(lambda: bool(server.started), "Channel Engine did not start")
    return server, worker


def _stop_server(server: uvicorn.Server, worker: Thread) -> None:
    server.should_exit = True
    worker.join(timeout=5)
    assert worker.is_alive() is False


def _wait_until(
    predicate: Callable[[], bool],
    message: str,
    *,
    timeout_seconds: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(message)


def _application(registry: ChannelAgentNodeRegistry) -> FastAPI:
    app = FastAPI()
    app.include_router(create_channel_agent_node_router(registry))
    return app


def _admin() -> OperatorPrincipal:
    return OperatorPrincipal(
        principal_id="admin-production-connection-v1",
        roles=frozenset({OperatorRole.ADMIN}),
        identity_provider="production-connection-test",
        authenticated_at=datetime.now(UTC),
    )


def _run_host(host: WindowsAgentHost) -> tuple[Thread, list[int]]:
    result: list[int] = []
    stop = Event()
    worker = Thread(
        target=lambda: result.append(host.run(stop)),
        name="channel-agent-windows-host",
    )
    worker.start()
    return worker, result


def test_windows_agent_complete_connection_survives_engine_and_agent_restart(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database = tmp_path / "channel-engine.sqlite3"
    engine, session_factory = create_engine_and_session(
        f"sqlite:///{database.as_posix()}"
    )
    create_schema(engine)
    managed = ManagedAgentConfig(
        revision="production-connection-v1",
        heartbeat_interval_seconds=0.05,
    )
    repository = SqlAlchemyAgentIdentityRepository(session_factory)
    registry = ChannelAgentNodeRegistry(
        managed_config=managed,
        identity_repository=repository,
        binding_code_factory=lambda: CODE,
    )
    port = _free_loopback_port()
    server, server_thread = _start_server(_application(registry), port)
    data_root = tmp_path / "windows-agent"
    config_path = data_root / "config" / "agent.json"
    config_path.parent.mkdir(parents=True)
    config = ChannelAgentConfig(
        server_url=f"http://127.0.0.1:{port}",
        agent_id="agent-production-connection-001",
        device_id="device-production-connection-001",
        connect_timeout_seconds=0.2,
        heartbeat_interval_seconds=0.05,
        log_directory=data_root / "logs",
    )
    config_path.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")
    bootstrap = ChannelEngineClient(config)
    bootstrap.register(
        hostname="windows-service-desk-001",
        status=AgentRuntimeStatus.STARTING,
        timestamp=datetime.now(UTC),
    )
    bootstrap.close()
    host = WindowsAgentHost(config_path, data_root, poll_interval_seconds=0.02)
    agent_thread, first_result = _run_host(host)
    _wait_until(
        lambda: (
            host.state_store.load().process_status
            is WindowsClientProcessStatus.RUNNING
            and host.state_store.load().identity_status.value == "UNBOUND"
        ),
        "Unbound Agent did not reach ONLINE before enrollment",
    )
    grant = registry.issue_enrollment_grant(
        AgentEnrollmentGrantRequest(
            agent_id=config.agent_id,
            device_id=config.device_id,
            user_reference="user-production-connection-001",
            store_references=("store-production-a", "store-production-b"),
            reason="approved production connection validation",
        ),
        _admin(),
    )
    monkeypatch.setattr(windows_app.sys, "stdin", io.StringIO(grant.binding_code + "\n"))

    enrolled = windows_app.main(
        [
            "enroll",
            "--data-root",
            str(data_root),
            "--config",
            str(config_path),
            "--binding-code-stdin",
        ]
    )
    activated = registry.activate_identity(
        config.agent_id,
        AgentIdentityActivationRequest(reason="binding verified for validation"),
        _admin(),
    )

    _wait_until(
        lambda: (
            host.state_store.load().process_status
            is WindowsClientProcessStatus.RUNNING
            and host.state_store.load().identity_status.value == "ACTIVE"
            and host.state_store.load().store_ids
            == ("store-production-a", "store-production-b")
        ),
        "Agent did not reach ONLINE with the authoritative binding",
    )
    online = registry.get_agent(config.agent_id, _admin())

    _stop_server(server, server_thread)
    _wait_until(
        lambda: host.state_store.load().process_status
        is WindowsClientProcessStatus.DEGRADED,
        "Agent did not enter DEGRADED during the network outage",
    )

    restarted_registry = ChannelAgentNodeRegistry(
        managed_config=managed,
        identity_repository=SqlAlchemyAgentIdentityRepository(session_factory),
    )
    restarted_server, restarted_server_thread = _start_server(
        _application(restarted_registry),
        port,
    )
    _wait_until(
        lambda: (
            host.state_store.load().process_status
            is WindowsClientProcessStatus.RUNNING
            and restarted_registry.snapshot(config.agent_id) is not None
        ),
        "Agent did not re-register and recover after the Engine restart",
    )
    recovered = restarted_registry.get_agent(config.agent_id, _admin())

    host.request_stop()
    agent_thread.join(timeout=5)
    assert agent_thread.is_alive() is False
    stopped = restarted_registry.get_agent(config.agent_id, _admin())

    restarted_host = WindowsAgentHost(
        config_path,
        data_root,
        poll_interval_seconds=0.02,
    )
    second_agent_thread, second_result = _run_host(restarted_host)
    _wait_until(
        lambda: restarted_host.state_store.load().process_status
        is WindowsClientProcessStatus.RUNNING,
        "Agent did not reconnect after its local process restart",
    )
    after_agent_restart = restarted_registry.get_agent(config.agent_id, _admin())
    binding = AgentBindingStore(
        data_root / "runtime" / "agent-binding.json"
    ).load()
    restarted_host.request_stop()
    second_agent_thread.join(timeout=5)
    _stop_server(restarted_server, restarted_server_thread)
    engine.dispose()

    assert enrolled == 0
    assert activated.production_eligible is True
    assert online.online_status is AgentOnlineStatus.ONLINE
    assert online.identity.user_id == "user-production-connection-001"
    assert online.identity.effective_store_ids == (
        "store-production-a",
        "store-production-b",
    )
    assert recovered.online_status is AgentOnlineStatus.ONLINE
    assert recovered.identity.binding_revision == activated.binding_revision
    assert stopped.online_status is AgentOnlineStatus.OFFLINE
    assert after_agent_restart.online_status is AgentOnlineStatus.ONLINE
    assert binding is not None
    assert binding.user_id == "user-production-connection-001"
    assert binding.store_ids == ("store-production-a", "store-production-b")
    assert first_result == [0]
    assert second_result == [0]
    assert restarted_host.state_store.load().process_status \
        is WindowsClientProcessStatus.STOPPED
