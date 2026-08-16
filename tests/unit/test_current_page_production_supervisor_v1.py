from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from channel_agent.current_page_production import (
    CURRENT_PAGE_SCOPE,
    CurrentPageProductionConfig,
    CurrentPageProductionSupervisor,
)


def config(tmp_path: Path, **changes: object) -> CurrentPageProductionConfig:
    values: dict[str, object] = {
        "ce_root": tmp_path / "ce",
        "ai_cs_root": tmp_path / "ai-cs",
        "ai_cs_config_path": tmp_path / "ai-cs" / "rc5.local.ps1",
        "data_root": tmp_path / "agent-data",
        "python_executable": tmp_path / "python.exe",
        "agent_executable": tmp_path / "ChannelAgent.exe",
        "engine_database_path": tmp_path / "channel-engine.sqlite3",
        "assistant_root": tmp_path / "assistant",
        "host_evidence_root": tmp_path / "host-evidence",
        "gateway_key_reference": tmp_path / "gateway.secret",
        "send_selector_contract": tmp_path / "send-selector.json",
        "catalog_store_id": "c-store-1",
        "catalog_tenant_id": "c-tenant-1",
    }
    values.update(changes)
    return CurrentPageProductionConfig.model_validate(values)


def create_installation(candidate: CurrentPageProductionConfig) -> None:
    required = [
        candidate.python_executable,
        candidate.agent_executable,
        candidate.engine_database_path,
        candidate.gateway_key_reference,
        candidate.send_selector_contract,
        candidate.ai_cs_root
        / "scripts"
        / "windows"
        / "start_ai_customer_service.ps1",
        candidate.ai_cs_config_path,
        candidate.ce_root
        / "scripts"
        / "windows"
        / "Start-Rc5HotValidationHost.ps1",
        candidate.ce_root
        / "scripts"
        / "run_channel_agent_assistant_bridge.py",
        candidate.ce_root
        / "scripts"
        / "run_controlled_pdd_reply_pilot.py",
    ]
    for path in required:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test")
    agent_config = candidate.data_root / "config" / "agent.json"
    agent_config.parent.mkdir(parents=True, exist_ok=True)
    agent_config.write_text(
        json.dumps(
            {
                "message_observation_enabled": True,
                "pdd_conversation_navigation_enabled": False,
            }
        ),
        encoding="utf-8",
    )


def test_config_permanently_disables_automatic_navigation(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    assert candidate.observation_scope == CURRENT_PAGE_SCOPE
    assert candidate.automatic_navigation_enabled is False
    with pytest.raises(ValidationError):
        config(tmp_path, automatic_navigation_enabled=True)
    with pytest.raises(ValidationError):
        config(tmp_path, bridge_port=18443)


def test_installation_rejects_agent_navigation(tmp_path: Path) -> None:
    candidate = config(tmp_path)
    create_installation(candidate)
    agent_config = candidate.data_root / "config" / "agent.json"
    value = json.loads(agent_config.read_text(encoding="utf-8"))
    value["pdd_conversation_navigation_enabled"] = True
    agent_config.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="AUTOMATIC_PDD_CONVERSATION_NAVIGATION_MUST_BE_DISABLED",
    ):
        CurrentPageProductionSupervisor(candidate).validate_installation()


def test_runtime_stays_before_bridge_until_current_page_is_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = CurrentPageProductionSupervisor(config(tmp_path))
    started: list[str] = []
    health = {
        "agent": True,
        "ai_gateway": True,
        "ai_platform": True,
        "host": True,
        "bridge": False,
        "runner": False,
    }
    monkeypatch.setattr(supervisor, "_component_health", lambda: health)
    monkeypatch.setattr(supervisor, "_live_scope_ready", lambda: False)
    monkeypatch.setattr(supervisor, "_start_agent", lambda: started.append("agent"))
    monkeypatch.setattr(supervisor, "_start_ai_cs", lambda: started.append("ai-cs"))
    monkeypatch.setattr(supervisor, "_start_host", lambda: started.append("host"))
    monkeypatch.setattr(supervisor, "_start_bridge", lambda: started.append("bridge"))
    monkeypatch.setattr(supervisor, "_start_runner", lambda: started.append("runner"))
    monkeypatch.setattr(
        supervisor, "_stop_child", lambda name: started.append(f"stop:{name}")
    )
    monkeypatch.setattr(supervisor, "_desired_auto_enabled", lambda: True)

    result = supervisor.run_once()

    assert started == ["stop:runner"]
    assert result["supervisor_state"] == "WAITING_FOR_CURRENT_PDD_CONVERSATION"
    assert result["desired_auto_reply_enabled"] is True
    assert result["observation_scope"] == CURRENT_PAGE_SCOPE
    assert result["automatic_navigation_enabled"] is False


def test_bridge_and_runner_commands_use_one_existing_send_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor = CurrentPageProductionSupervisor(config(tmp_path))
    commands: dict[str, list[str]] = {}

    def capture(
        name: str,
        command: list[str],
        *,
        cwd: Path,
        minimum_retry_seconds: float,
    ) -> None:
        del cwd, minimum_retry_seconds
        commands[name] = command

    monkeypatch.setattr(supervisor, "_start_child", capture)
    supervisor._start_bridge()
    supervisor._start_runner()

    assert "run_channel_agent_assistant_bridge.py" in " ".join(commands["bridge"])
    assert "--enable-controlled-send" in commands["bridge"]
    assert "run_controlled_pdd_reply_pilot.py" in " ".join(commands["runner"])
    assert "run-production-auto" in commands["runner"]
    assert "--execute-real-send" in commands["runner"]
    joined = " ".join(commands["bridge"] + commands["runner"]).casefold()
    assert "shift+tab" not in joined
    assert "navigate" not in joined
    assert "conversation-list" not in joined


def test_ai_cs_command_uses_the_frozen_rc5_runtime_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = config(tmp_path)
    supervisor = CurrentPageProductionSupervisor(candidate)
    commands: dict[str, list[str]] = {}

    def capture(
        name: str,
        command: list[str],
        *,
        cwd: Path,
        minimum_retry_seconds: float,
    ) -> None:
        del cwd, minimum_retry_seconds
        commands[name] = command

    monkeypatch.setattr(supervisor, "_start_child", capture)
    supervisor._start_ai_cs()

    command = commands["ai-cs-start"]
    assert "-ConfigPath" in command
    assert str(candidate.ai_cs_config_path) in command


@pytest.mark.parametrize(
    ("health", "live_scope", "expected"),
    [
        (
            {
                "agent": False,
                "ai_gateway": True,
                "ai_platform": True,
                "host": True,
                "bridge": False,
                "runner": False,
            },
            False,
            "STARTING",
        ),
        (
            {
                "agent": True,
                "ai_gateway": True,
                "ai_platform": True,
                "host": True,
                "bridge": False,
                "runner": False,
            },
            False,
            "WAITING_FOR_CURRENT_PDD_CONVERSATION",
        ),
        (
            {
                "agent": True,
                "ai_gateway": True,
                "ai_platform": True,
                "host": True,
                "bridge": True,
                "runner": False,
            },
            True,
            "RECOVERING_AUTO_COMPONENTS",
        ),
        (
            {
                "agent": True,
                "ai_gateway": True,
                "ai_platform": True,
                "host": True,
                "bridge": True,
                "runner": True,
            },
            True,
            "READY",
        ),
    ],
)
def test_supervisor_state_is_truthful(
    tmp_path: Path,
    health: dict[str, bool],
    live_scope: bool,
    expected: str,
) -> None:
    supervisor = CurrentPageProductionSupervisor(config(tmp_path))
    assert supervisor._classify_state(health, live_scope=live_scope) == expected
