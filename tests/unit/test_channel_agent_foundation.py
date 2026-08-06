from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from channel_engine.agent import (
    AgentBrowserConfig,
    AgentChannelConfig,
    AgentComponentStatus,
    AgentConfigError,
    AgentEnvironment,
    AgentLifecycleStage,
    AgentLifecycleError,
    AgentNodeStatus,
    AgentSafetyConfig,
    AgentServerConfig,
    AgentStoreBindingError,
    AgentStoreStatus,
    ChannelAgentConfig,
    ChannelAgentService,
    FakeAgentBrowserController,
    FakeAgentChannelRuntimeProbe,
    FakeAgentServerConnector,
    StaticAgentKillSwitch,
    StoreBinding,
    load_channel_agent_config,
)


def _binding(store_id: str = "pdd-agent-store-001") -> StoreBinding:
    return StoreBinding(
        store_id=store_id,
        store_name=f"Fake Store {store_id}",
        credential_reference=f"secret-ref://pdd/agent/{store_id}",
    )


def _config(
    tmp_path: Path,
    *,
    store: StoreBinding | None = None,
    kill_switch: bool = False,
) -> ChannelAgentConfig:
    return ChannelAgentConfig(
        node_id="channel-agent-test-node",
        node_name="Channel Agent Test Node",
        server=AgentServerConfig(
            server_url="http://127.0.0.1:18021",
            agent_token_reference="secret-ref://ai-cs/agent/test-token",
        ),
        browser=AgentBrowserConfig(
            chrome_path=(tmp_path / "fake-chrome.exe").resolve(),
            profile_root=(tmp_path / "browser-profiles").resolve(),
        ),
        channel=AgentChannelConfig(store_binding=store),
        safety=AgentSafetyConfig(
            runtime_mode=AgentEnvironment.MOCK,
            dry_run=True,
            kill_switch=kill_switch,
        ),
    )


def _service(
    config: ChannelAgentConfig,
    *,
    server: FakeAgentServerConnector | None = None,
    browser: FakeAgentBrowserController | None = None,
    channel: FakeAgentChannelRuntimeProbe | None = None,
    kill_switch: StaticAgentKillSwitch | None = None,
):
    active_server = server or FakeAgentServerConnector()
    active_browser = browser or FakeAgentBrowserController()
    active_channel = channel or FakeAgentChannelRuntimeProbe()
    active_kill = kill_switch or StaticAgentKillSwitch()
    service = ChannelAgentService(
        config,
        active_server,
        active_browser,
        active_channel,
        kill_switch_provider=active_kill,
    )
    return service, active_server, active_browser, active_channel, active_kill


def test_typed_json_config_load_and_secret_value_rejection(tmp_path) -> None:
    config = _config(tmp_path, store=_binding())
    config_path = tmp_path / "channel-agent.json"
    config_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")

    loaded = load_channel_agent_config(config_path)

    assert loaded == config
    assert loaded.fingerprint() == config.fingerprint()
    assert loaded.channel.store_binding is not None
    assert loaded.channel.store_binding.store_id == "pdd-agent-store-001"
    payload = config.model_dump(mode="json")
    payload["server"]["agent_token"] = "raw-agent-token"
    bad_path = tmp_path / "bad-channel-agent.json"
    bad_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AgentConfigError):
        load_channel_agent_config(bad_path)
    yaml_path = tmp_path / "scattered.yaml"
    yaml_path.write_text("node: unsafe", encoding="utf-8")
    with pytest.raises(AgentConfigError, match="typed JSON"):
        load_channel_agent_config(yaml_path)


def test_config_requires_absolute_dedicated_browser_profile(tmp_path) -> None:
    with pytest.raises(ValidationError, match="absolute"):
        AgentBrowserConfig(
            chrome_path=Path("chrome.exe"),
            profile_root=(tmp_path / "profiles").resolve(),
        )
    with pytest.raises(ValidationError, match="default Chrome profile"):
        AgentBrowserConfig(
            chrome_path=(tmp_path / "fake-chrome.exe").resolve(),
            profile_root=Path("C:/Users/Test/AppData/Local/Google/Chrome/User Data"),
        )


def test_agent_start_runs_ordered_lifecycle_and_becomes_online(tmp_path) -> None:
    service, server, browser, channel, _kill = _service(
        _config(tmp_path, store=_binding())
    )

    status = service.start()

    assert status.node.status is AgentNodeStatus.ONLINE
    assert status.node.last_heartbeat is not None
    assert status.server_status.status is AgentComponentStatus.HEALTHY
    assert status.browser_status.status is AgentComponentStatus.HEALTHY
    assert status.channel_status.status is AgentComponentStatus.HEALTHY
    assert status.store_status is AgentStoreStatus.BOUND
    assert status.dry_run is True
    assert server.connect_count == 1
    assert server.real_server_connection is False
    assert browser.start_count == 1
    assert browser.real_browser_started is False
    assert channel.real_channel_connection is False
    assert channel.real_send_count == 0
    assert [event.stage for event in service.lifecycle_events()] == [
        AgentLifecycleStage.ENVIRONMENT_CHECK,
        AgentLifecycleStage.SERVER_CONNECT,
        AgentLifecycleStage.CONFIG_LOAD,
        AgentLifecycleStage.BROWSER_CHECK,
        AgentLifecycleStage.CHANNEL_CHECK,
        AgentLifecycleStage.READY,
    ]
    assert service.health().ready is True


def test_server_disconnect_transitions_offline_then_recovers(tmp_path) -> None:
    service, server, _browser, _channel, _kill = _service(
        _config(tmp_path, store=_binding())
    )
    assert service.start().node.status is AgentNodeStatus.ONLINE
    server.set_available(False)

    offline = service.check()

    assert offline.node.status is AgentNodeStatus.OFFLINE
    assert offline.server_status.status is AgentComponentStatus.UNAVAILABLE
    assert service.health().status == "offline"
    server.set_available(True)
    recovered = service.check()
    assert recovered.node.status is AgentNodeStatus.ONLINE
    assert server.connect_count == 2


def test_kill_switch_blocks_channel_readiness(tmp_path) -> None:
    switch = StaticAgentKillSwitch(enabled=True)
    service, _server, _browser, channel, _switch = _service(
        _config(tmp_path, store=_binding()),
        kill_switch=switch,
    )

    blocked = service.start()

    assert blocked.node.status is AgentNodeStatus.DEGRADED
    assert blocked.kill_switch is True
    assert blocked.channel_status.status is AgentComponentStatus.BLOCKED
    assert blocked.channel_status.reason_code == "AGENT_KILL_SWITCH_ENABLED"
    assert channel.health_count == 0
    assert channel.real_send_count == 0
    switch.set_enabled(False)
    assert service.check().node.status is AgentNodeStatus.ONLINE


def test_browser_unavailable_keeps_agent_degraded_and_channel_blocked(
    tmp_path,
) -> None:
    browser = FakeAgentBrowserController(available=False)
    service, _server, _browser, channel, _kill = _service(
        _config(tmp_path, store=_binding()),
        browser=browser,
    )

    status = service.start()

    assert status.node.status is AgentNodeStatus.DEGRADED
    assert status.browser_status.status is AgentComponentStatus.UNAVAILABLE
    assert status.channel_status.status is AgentComponentStatus.BLOCKED
    assert status.channel_status.reason_code == "AGENT_BROWSER_UNAVAILABLE"
    assert channel.health_count == 0


def test_store_unbound_degrades_node_and_single_store_rule_is_enforced(
    tmp_path,
) -> None:
    service, _server, _browser, channel, _kill = _service(_config(tmp_path))

    status = service.start()

    assert status.node.status is AgentNodeStatus.DEGRADED
    assert status.store_status is AgentStoreStatus.UNBOUND
    assert status.channel_status.reason_code == "AGENT_STORE_UNBOUND"
    assert channel.health_count == 0
    service.stop()
    bound = service.bind_store(_binding())
    assert bound.store_status is AgentStoreStatus.BOUND
    with pytest.raises(AgentStoreBindingError, match="one store"):
        service.bind_store(_binding("pdd-agent-store-002"))
    unbound = service.unbind_store()
    assert unbound.store_status is AgentStoreStatus.UNBOUND


def test_config_reload_requires_stopped_node(tmp_path) -> None:
    first = _config(tmp_path, store=_binding())
    service, _server, _browser, _channel, _kill = _service(first)
    service.start()
    second = first.model_copy(update={"node_name": "Reloaded Agent Node"})

    with pytest.raises(AgentLifecycleError, match="stop Agent"):
        service.reload_config(second)

    service.stop()
    reloaded = service.reload_config(second)
    assert reloaded.node.node_name == "Reloaded Agent Node"
    assert reloaded.config_fingerprint == second.fingerprint()
