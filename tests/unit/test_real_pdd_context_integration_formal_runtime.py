from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import channel_agent.binding as binding_module
from channel_agent.config import ChannelAgentConfig, save_agent_config
from channel_agent.identity import AgentIdentityStatus
from channel_agent.observation_stages import ObservationStage
from channel_agent.pdd_login import PDDLoginState
from channel_agent.windows import WindowsClientState, WindowsStateStore

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_real_pdd_context_integration.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "run_real_pdd_context_integration", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_runtime(tmp_path: Path, *, ready: bool = True) -> Path:
    config_path = tmp_path / "config" / "agent.json"
    save_agent_config(
        config_path,
        ChannelAgentConfig(
            server_url="https://127.0.0.1:18443",
            agent_id="agent-1",
            device_id="device-1",
            device_credential_reference="wincred://channel-agent/device-1",
            runtime_mode="PRODUCTION",
            user_reference="user-1",
            store_reference="store-1",
            store_references=("store-1",),
            browser_enabled=True,
            pdd_login_observation_enabled=True,
            pdd_login_url="https://mms.pinduoduo.com/login/",
            pdd_customer_service_url=(
                "https://mms.pinduoduo.com/chat-merchant/index.html#/"
            ),
            customer_assistant_enabled=True,
            message_observation_enabled=True,
            observation_stage=ObservationStage.AI_SUGGESTIONS,
            pdd_observation_evidence_path=tmp_path / "selector-evidence.json",
        ),
    )
    WindowsStateStore(
        tmp_path / "runtime" / "channel-agent-state.json"
    ).save(
        WindowsClientState(
            agent_id="agent-1",
            device_id="device-1",
            identity_status=AgentIdentityStatus.ACTIVE,
            pdd_login_state=(
                PDDLoginState.CUSTOMER_SERVICE_READY
                if ready
                else PDDLoginState.PDD_LOGIN_PAGE
            ),
            message_observation_enabled=True,
            observer_status="STOPPED",
        )
    )
    return config_path


def test_formal_status_uses_signed_host_projection_without_legacy_observer(
    tmp_path: Path, monkeypatch
) -> None:
    runner = _load_runner()
    config_path = _write_runtime(tmp_path)
    closed: list[bool] = []

    class FakeClient:
        def __init__(self, config) -> None:
            assert config.agent_id == "agent-1"

        def fetch_assistant_conversations(self, *, limit: int):
            assert limit == 100
            return SimpleNamespace(
                conversations=(
                    SimpleNamespace(
                        store_id="store-1",
                        conversation_id="conversation-a",
                        revision=2,
                        status="WAITING_APPROVAL",
                        processing_stage="WAITING_CONFIRMATION",
                        quality_status="PASS",
                        policy_mode="MANUAL_CONFIRM",
                    ),
                    SimpleNamespace(
                        store_id="store-1",
                        conversation_id="conversation-b",
                        revision=1,
                        status="EXECUTION_PREPARED",
                        processing_stage="EXECUTION_PREPARED",
                        quality_status="PASS",
                        policy_mode="AUTO_LOW_RISK",
                    ),
                )
            )

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(runner, "ChannelEngineClient", FakeClient)
    monkeypatch.setattr(
        runner,
        "_build_observer",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy observer must not be constructed")
        ),
    )

    result = runner._formal_status(tmp_path, config_path)

    assert result["runtime_owner"] == "WINDOWS_AGENT"
    assert result["projection_source"] == "SIGNED_HOST"
    assert result["assistant_conversation_count"] == 2
    assert result["legacy_runtime_started"] is False
    assert result["real_send_enabled"] is False
    assert closed == [True]
    assert all(
        item["scope_reference"].startswith("sha256:")
        for item in result["assistant_conversations"]
    )


def test_formal_restart_is_human_intent_idempotent_and_does_not_start_legacy_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    runner = _load_runner()
    config_path = _write_runtime(tmp_path)
    monkeypatch.setattr(
        runner,
        "_build_observer",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy observer must not be constructed")
        ),
    )

    first = runner._queue_formal_observer_restart(tmp_path, config_path)
    second = runner._queue_formal_observer_restart(tmp_path, config_path)
    request = json.loads(
        (tmp_path / "runtime" / "pdd-observer-restart.request").read_text(
            encoding="utf-8"
        )
    )

    assert first["status"] == "RESTART_REQUESTED"
    assert second["status"] == "ALREADY_REQUESTED"
    assert first["human_intent"] is True
    assert first["real_send_enabled"] is False
    assert first["legacy_runtime_started"] is False
    assert request["human_intent"] is True
    assert request["schema_version"] == (
        "channel-agent-pdd-observer-restart-request.v1"
    )


def test_formal_restart_fails_closed_when_workspace_is_not_ready(tmp_path: Path) -> None:
    runner = _load_runner()
    config_path = _write_runtime(tmp_path, ready=False)

    try:
        runner._queue_formal_observer_restart(tmp_path, config_path)
    except RuntimeError as exc:
        assert "workspace is not ready" in str(exc)
    else:
        raise AssertionError("restart must fail closed")


def test_formal_main_bypasses_legacy_checkpoint_and_observer(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    runner = _load_runner()
    config_path = _write_runtime(tmp_path)
    expected = {
        "schema_version": "real-pdd-formal-runtime-status.v1",
        "assistant_conversation_count": 0,
    }
    monkeypatch.setattr(runner, "_formal_status", lambda *_: expected)
    monkeypatch.setattr(
        runner,
        "SQLitePDDWorkspaceCheckpoint",
        lambda *_: (_ for _ in ()).throw(
            AssertionError("legacy checkpoint must not be constructed")
        ),
    )
    monkeypatch.setattr(
        runner,
        "_build_observer",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy observer must not be constructed")
        ),
    )

    assert runner.main(
        [
            "formal-status",
            "--data-root",
            str(tmp_path),
            "--config",
            str(config_path),
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out) == expected


def test_formal_restart_rejects_unsafe_existing_request(tmp_path: Path) -> None:
    runner = _load_runner()
    config_path = _write_runtime(tmp_path)
    request = tmp_path / "runtime" / "pdd-observer-restart.request"
    request.write_text(
        json.dumps(
            {
                "schema_version": "channel-agent-pdd-observer-restart-request.v1",
                "requested_at": datetime.now(UTC).isoformat(),
                "human_intent": False,
            }
        ),
        encoding="utf-8",
    )

    try:
        runner._queue_formal_observer_restart(tmp_path, config_path)
    except RuntimeError as exc:
        assert "request is invalid" in str(exc)
    else:
        raise AssertionError("unsafe existing request must fail closed")


def test_runtime_json_write_retries_transient_windows_sharing_conflict(
    tmp_path: Path, monkeypatch
) -> None:
    runner = _load_runner()
    destination = tmp_path / "runtime" / "assistant-feed.json"
    original_replace = binding_module._atomic_replace
    attempts = 0

    def transient_replace(source: Path, target: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("synthetic Windows sharing violation")
        original_replace(source, target)

    monkeypatch.setattr(binding_module, "_atomic_replace", transient_replace)
    runner._atomic_json(destination, {"phase": "READY", "real_send": False})

    assert attempts == 3
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "phase": "READY",
        "real_send": False,
    }
    assert list(destination.parent.glob(f".{destination.name}.*.tmp")) == []
