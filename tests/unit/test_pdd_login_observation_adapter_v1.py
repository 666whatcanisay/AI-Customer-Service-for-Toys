from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread

import pytest
from pydantic import ValidationError

from channel_agent.browser import BrowserSessionState, BrowserSessionStatus
from channel_agent.config import ChannelAgentConfig
from channel_agent.contract import AgentRuntimeStatus
from channel_agent.identity import AgentIdentityStatus
from channel_agent.logger import SafeAgentLogger
from channel_agent.pdd_login import (
    FixedReadOnlyPDDEvaluator,
    PDDCDPPageTarget,
    PDDLoginObservation,
    PDDLoginObservationAdapter,
    PDDLoginReadError,
    PDDLoginSessionReference,
    PDDLoginSessionStore,
    PDDLoginState,
    _is_identity_observation_path,
)
from channel_agent.runtime import AgentRuntimeSnapshot
from channel_agent.windows import WindowsAgentHost, WindowsClientProcessStatus

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
LOGIN_URL = "https://mms.pinduoduo.com/login/"
CUSTOMER_SERVICE_URL = "https://mms.pinduoduo.com/chat-merchant/index.html#/"


class AdvancingClock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> datetime:
        self.value += timedelta(seconds=1)
        return self.value


def test_session_store_concurrent_writes_use_distinct_temporary_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "runtime" / "pdd-login" / "session.json"
    stores = (PDDLoginSessionStore(path), PDDLoginSessionStore(path))
    values = (
        PDDLoginSessionReference(
            browser_id="browser:one",
            agent_id="agent-pdd-observe",
            login_state=PDDLoginState.WAITING_QR_SCAN,
            observed_at=NOW,
            reason_code="PDD_WAITING_FOR_HUMAN_QR_SCAN",
        ),
        PDDLoginSessionReference(
            browser_id="browser:two",
            agent_id="agent-pdd-observe",
            login_state=PDDLoginState.CUSTOMER_SERVICE_READY,
            observed_at=NOW + timedelta(seconds=1),
            reason_code="PDD_CUSTOMER_SERVICE_READY",
        ),
    )
    original_write_bytes = Path.write_bytes
    measurement_lock = Lock()
    active_writers = 0
    max_active_writers = 0

    def synchronized_write(candidate: Path, payload: bytes) -> int:
        nonlocal active_writers, max_active_writers
        if candidate.parent != path.parent or not candidate.name.endswith(".tmp"):
            return original_write_bytes(candidate, payload)
        with measurement_lock:
            active_writers += 1
            max_active_writers = max(max_active_writers, active_writers)
        try:
            time.sleep(0.03)
            return original_write_bytes(candidate, payload)
        finally:
            with measurement_lock:
                active_writers -= 1

    monkeypatch.setattr(Path, "write_bytes", synchronized_write)
    errors: list[Exception] = []

    def save(index: int) -> None:
        try:
            stores[index].save(values[index])
        except PDDLoginReadError as exc:  # pragma: no cover - assertion reports it
            errors.append(exc)

    workers = [Thread(target=save, args=(index,)) for index in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)

    assert errors == []
    assert not any(worker.is_alive() for worker in workers)
    assert max_active_writers == 1
    assert PDDLoginSessionStore(path).load() in values
    assert list(path.parent.glob(".*.tmp")) == []


class FakeBrowser:
    def __init__(self, root: Path, agent_id: str = "agent-pdd-observe") -> None:
        self.root = root.resolve()
        self.opens = 0
        self.navigations: list[str] = []
        self.login_results: list[bool] = []
        self.closed = False
        self.resources_closed = False
        self.state = BrowserSessionState(
            browser_id="browser:pdd-observe",
            agent_id=agent_id,
            profile_path=str((self.root / "browser" / "isolated-profile").resolve()),
            status=BrowserSessionStatus.STOPPED,
            created_at=NOW,
            last_seen=NOW,
        )

    def open_browser(self) -> BrowserSessionState:
        self.opens += 1
        Path(self.state.profile_path).mkdir(parents=True, exist_ok=True)
        self.state = self.state.model_copy(
            update={"status": BrowserSessionStatus.OPENED, "pid": 8181}
        )
        return self.state

    def navigate(self, url: str) -> BrowserSessionState:
        self.navigations.append(url)
        self.state = self.state.model_copy(
            update={"status": BrowserSessionStatus.WAITING_LOGIN}
        )
        return self.state

    def browser_status(self) -> BrowserSessionState:
        return self.state

    def apply_login_observation(
        self, *, authenticated: bool, observation_reference: str
    ) -> BrowserSessionState:
        assert observation_reference.startswith("sha256:")
        self.login_results.append(authenticated)
        self.state = self.state.model_copy(
            update={
                "status": (
                    BrowserSessionStatus.READY
                    if authenticated
                    else BrowserSessionStatus.WAITING_LOGIN
                )
            }
        )
        return self.state

    def close_browser(self) -> BrowserSessionState:
        self.closed = True
        self.state = self.state.model_copy(
            update={"status": BrowserSessionStatus.STOPPED, "pid": None}
        )
        return self.state

    def recover(self) -> BrowserSessionState:
        return self.state

    def close_resources(self) -> None:
        self.resources_closed = True


class MutableTargetResolver:
    def __init__(self, target: PDDCDPPageTarget) -> None:
        self.target = target
        self.calls = 0

    def resolve(self, profile_path: Path) -> PDDCDPPageTarget:
        self.calls += 1
        assert profile_path.is_absolute()
        return self.target


class MutableEvaluator:
    def __init__(self, metadata: dict[str, object]) -> None:
        self.metadata = metadata

    def capture_public_login_metadata(
        self, target: PDDCDPPageTarget
    ) -> dict[str, object]:
        return self.metadata


def target(url: str, path: str) -> PDDCDPPageTarget:
    return PDDCDPPageTarget(
        target_id="target-pdd",
        websocket_url="ws://127.0.0.1:9222/devtools/page/target-pdd",
        page_url=url,
        page_origin="https://mms.pinduoduo.com",
        page_path=path,
    )


def make_observer(
    tmp_path: Path,
    *,
    page_target: PDDCDPPageTarget | None = None,
    metadata: dict[str, object] | None = None,
) -> tuple[
    PDDLoginObservationAdapter,
    FakeBrowser,
    MutableTargetResolver,
    MutableEvaluator,
]:
    browser = FakeBrowser(tmp_path / "data")
    resolver = MutableTargetResolver(
        page_target or target(LOGIN_URL, "/login/")
    )
    evaluator = MutableEvaluator(
        metadata or {"ready_state": "complete", "title": "拼多多商家后台"}
    )
    observer = PDDLoginObservationAdapter(
        agent_id="agent-pdd-observe",
        data_root=tmp_path / "data",
        login_url=LOGIN_URL,
        customer_service_url=CUSTOMER_SERVICE_URL,
        browser=browser,  # type: ignore[arg-type]
        logger=SafeAgentLogger(tmp_path / "data" / "logs" / "pdd-login.jsonl"),
        target_resolver=resolver,
        evaluator=evaluator,
        clock=AdvancingClock(),
    )
    return observer, browser, resolver, evaluator


def test_pdd_login_observation_requires_explicit_browser_and_official_url() -> None:
    base = {
        "server_url": "https://channel-engine.example",
        "agent_id": "agent-pdd-observe",
        "device_id": "device-pdd-observe",
    }
    assert ChannelAgentConfig(**base).pdd_login_observation_enabled is False
    with pytest.raises(ValidationError):
        ChannelAgentConfig(**base, pdd_login_observation_enabled=True)
    with pytest.raises(ValidationError):
        ChannelAgentConfig(
            **base,
            browser_enabled=True,
            pdd_login_observation_enabled=True,
            pdd_login_url="https://evil.example/login/",
        )
    config = ChannelAgentConfig(
        **base,
        browser_enabled=True,
        pdd_login_observation_enabled=True,
        pdd_login_url=LOGIN_URL,
        pdd_customer_service_url=CUSTOMER_SERVICE_URL,
    )
    assert config.pdd_login_url == LOGIN_URL
    assert config.pdd_customer_service_url == CUSTOMER_SERVICE_URL


def test_launch_opens_isolated_browser_and_waits_for_human_qr(tmp_path: Path) -> None:
    observer, browser, _resolver, _evaluator = make_observer(tmp_path)
    try:
        launched = observer.launch()
        waiting = observer.observe()

        assert launched.login_state is PDDLoginState.PDD_LOGIN_PAGE
        assert waiting.login_state is PDDLoginState.WAITING_QR_SCAN
        assert waiting.human_action_required is True
        assert waiting.page_write_operations == 0
        assert waiting.customer_messages_read == 0
        assert launched.navigation_operations == 1
        assert browser.opens == 1
        assert browser.navigations == [LOGIN_URL]
        assert browser.login_results == [False]
        profile = Path(browser.state.profile_path)
        assert profile.is_relative_to((tmp_path / "data").resolve())
    finally:
        observer.close_resources()


def test_relaunch_reuses_existing_waiting_login_tab(tmp_path: Path) -> None:
    observer, browser, resolver, _evaluator = make_observer(tmp_path)
    try:
        observer.launch()
        first_waiting = observer.observe()
        resolver.calls = 0

        relaunched = observer.launch()

        assert first_waiting.login_state is PDDLoginState.WAITING_QR_SCAN
        assert relaunched.login_state is PDDLoginState.WAITING_QR_SCAN
        assert resolver.calls == 1
        assert browser.opens == 2
        assert browser.navigations == [LOGIN_URL]
    finally:
        observer.close_resources()


def test_relaunch_with_new_browser_session_does_not_probe_stale_login_state(
    tmp_path: Path,
) -> None:
    observer, browser, resolver, _evaluator = make_observer(tmp_path)
    try:
        first = observer.launch()
        assert first.browser_id == "browser:pdd-observe"
        browser.close_browser()
        browser.state = browser.state.model_copy(
            update={
                "browser_id": "browser:pdd-reopened",
                "status": BrowserSessionStatus.STOPPED,
                "pid": None,
            }
        )
        resolver.calls = 0
        browser.navigations.clear()

        reopened = observer.launch()

        assert reopened.browser_id == "browser:pdd-reopened"
        assert reopened.login_state is PDDLoginState.PDD_LOGIN_PAGE
        assert resolver.calls == 0
        assert browser.navigations == [LOGIN_URL]
    finally:
        observer.close_resources()


def test_login_success_opens_customer_service_and_detects_ready_shell(
    tmp_path: Path,
) -> None:
    post_login = target(
        "https://mms.pinduoduo.com/aftersales/aftersale_list?mall_id=store_1001",
        "/aftersales/aftersale_list",
    )
    observer, browser, _resolver, _evaluator = make_observer(
        tmp_path,
        page_target=post_login,
        metadata={"ready_state": "complete", "title": "玩趣乐园积木店 - 拼多多"},
    )
    try:
        observer.launch()
        opening = observer.observe()
        assert opening.login_state is PDDLoginState.OPENING_CUSTOMER_SERVICE
        assert opening.navigation_operations == 1
        assert browser.navigations == [LOGIN_URL, CUSTOMER_SERVICE_URL]
        still_opening = observer.observe()
        assert still_opening.login_state is PDDLoginState.OPENING_CUSTOMER_SERVICE
        assert still_opening.navigation_operations == 0
        assert browser.navigations == [LOGIN_URL, CUSTOMER_SERVICE_URL]
        resolver = _resolver
        evaluator = _evaluator
        resolver.target = target(CUSTOMER_SERVICE_URL, "/chat-merchant/index.html")
        evaluator.metadata = {
            "ready_state": "complete",
            "title": "多多客服",
            "customer_service_shell_present": True,
        }
        ready = observer.observe()

        assert ready.login_state is PDDLoginState.CUSTOMER_SERVICE_READY
        assert opening.store_identity is not None
        assert ready.customer_service_shell_present is True
        authenticated_event = next(
            line
            for line in (
                tmp_path / "data" / "events" / "pdd-login-events.jsonl"
            ).read_text("utf-8").splitlines()
            if '"after":"PDD_LOGIN_SUCCESS"' in line
        )
        assert authenticated_event
        detected_identity = opening.store_identity
        assert detected_identity is not None
        assert detected_identity.model_dump(
            include={"platform", "login_status", "store_id", "store_name"}
        ) == {
            "platform": "PDD",
            "login_status": "SUCCESS",
            "store_id": "store_1001",
            "store_name": "玩趣乐园积木店",
        }
        assert browser.login_results == [True, True, True]

        session_path = next((tmp_path / "data" / "runtime" / "pdd-login").glob("*.json"))
        events_path = tmp_path / "data" / "events" / "pdd-login-events.jsonl"
        persisted = (session_path.read_text("utf-8") + events_path.read_text("utf-8"))
        assert "store_1001" not in persisted
        assert "玩趣乐园积木店" not in persisted
        assert "sha256:" in persisted
        assert "browser.login.state_changed" in persisted
    finally:
        observer.close_resources()


def test_logout_is_observed_without_page_write(tmp_path: Path) -> None:
    observer, _browser, resolver, evaluator = make_observer(
        tmp_path,
        page_target=target(
            CUSTOMER_SERVICE_URL, "/chat-merchant/index.html"
        ),
        metadata={
            "ready_state": "complete",
            "title": "多多客服",
            "customer_service_shell_present": True,
        },
    )
    try:
        observer.launch()
        assert observer.observe().login_state is PDDLoginState.CUSTOMER_SERVICE_READY
        event_rows = [
            json.loads(line)
            for line in (
                tmp_path / "data" / "events" / "pdd-login-events.jsonl"
            ).read_text("utf-8").splitlines()
        ]
        event_times = [row["timestamp"] for row in event_rows]
        assert event_times == sorted(event_times)
        resolver.target = target(LOGIN_URL, "/login/")
        evaluator.metadata = {"ready_state": "complete", "title": "拼多多商家后台"}

        logged_out = observer.observe()
        assert logged_out.login_state is PDDLoginState.WAITING_QR_SCAN
        assert logged_out.human_action_required is True
        assert logged_out.page_write_operations == 0
    finally:
        observer.close_resources()


def test_admin_page_proves_login_without_guessing_store_identity(tmp_path: Path) -> None:
    observer, _browser, _resolver, _evaluator = make_observer(
        tmp_path,
        page_target=target(
            "https://mms.pinduoduo.com/aftersales/aftersale_list",
            "/aftersales/aftersale_list",
        ),
        metadata={"ready_state": "complete", "title": "拼多多商家后台"},
    )
    try:
        observer.launch()
        observation = observer.observe()
        assert observation.login_state is PDDLoginState.OPENING_CUSTOMER_SERVICE
        assert observation.store_identity is None
        assert observation.human_action_required is False
    finally:
        observer.close_resources()


def test_home_page_proves_login_and_opens_customer_service(tmp_path: Path) -> None:
    observer, browser, _resolver, _evaluator = make_observer(
        tmp_path,
        page_target=target(
            "https://mms.pinduoduo.com/home",
            "/home",
        ),
        metadata={
            "ready_state": "complete",
            "title": "\u9996\u9875",
            "identity_state": {
                "current_mall_id": "328616090",
                "global_mall_id": "328616090",
                "public_store_name": "\u73a9\u5177\u4e50\u56ed\u79ef\u6728\u5e97",
            },
        },
    )
    try:
        observer.launch()
        observation = observer.observe()

        assert observation.login_state is PDDLoginState.OPENING_CUSTOMER_SERVICE
        assert observation.navigation_operations == 1
        assert browser.navigations == [LOGIN_URL, CUSTOMER_SERVICE_URL]
        assert observation.store_identity is not None
        assert observation.store_identity.store_id == "328616090"
        assert observation.store_identity.store_name == "\u73a9\u5177\u4e50\u56ed\u79ef\u6728\u5e97"
    finally:
        observer.close_resources()


def test_customer_service_identity_can_use_stable_mall_id_without_name(
    tmp_path: Path,
) -> None:
    observer, _browser, _resolver, _evaluator = make_observer(
        tmp_path,
        page_target=target(CUSTOMER_SERVICE_URL, "/chat-merchant/index.html"),
        metadata={
            "ready_state": "complete",
            "title": "\u4e3b\u8d26\u53f7",
            "customer_service_shell_present": True,
            "identity_state": {
                "current_mall_id": "328616090",
                "global_mall_id": "328616090",
                "public_store_name": "",
            },
        },
    )
    try:
        observer.launch()
        observation = observer.observe()

        assert observation.login_state is PDDLoginState.CUSTOMER_SERVICE_READY
        assert observation.store_identity is not None
        assert observation.store_identity.store_id == "328616090"
        assert observation.store_identity.store_name is None
    finally:
        observer.close_resources()


def test_read_only_boundary_has_no_message_or_send_capability(tmp_path: Path) -> None:
    observer, _browser, _resolver, _evaluator = make_observer(tmp_path)
    try:
        for forbidden in (
            "read_messages",
            "read_customers",
            "send_message",
            "click_send",
            "auto_login",
            "set_cookie",
        ):
            assert hasattr(observer, forbidden) is False
        expression = FixedReadOnlyPDDEvaluator._EXPRESSION.casefold()
        for forbidden_token in (
            "textcontent",
            "innertext",
            ".click(",
            "message",
            "customer_message",
            "cookie",
            "token",
            "password",
        ):
            assert forbidden_token not in expression
    finally:
        observer.close_resources()


def test_observation_paths_are_strictly_allowlisted() -> None:
    assert _is_identity_observation_path("/login/") is True
    assert _is_identity_observation_path("/home") is True
    assert _is_identity_observation_path("/aftersales/aftersale_list") is True
    assert _is_identity_observation_path("/chat-merchant/index.html") is True
    assert _is_identity_observation_path("/orders/list") is False


class FakeRuntime:
    def __init__(self, config: ChannelAgentConfig) -> None:
        self.config = config
        self.status = AgentRuntimeStatus.STOPPED

    def start(self, *, background_heartbeat: bool = True) -> AgentRuntimeSnapshot:
        self.status = AgentRuntimeStatus.ONLINE
        return self.snapshot()

    def stop(self) -> AgentRuntimeSnapshot:
        self.status = AgentRuntimeStatus.STOPPED
        return self.snapshot()

    def close(self) -> None:
        self.status = AgentRuntimeStatus.STOPPED

    def snapshot(self) -> AgentRuntimeSnapshot:
        return AgentRuntimeSnapshot(
            agent_id=self.config.agent_id,
            device_id=self.config.device_id,
            user_id=None,
            store_id=None,
            store_ids=(),
            binding_revision=0,
            identity=None,
            identity_status=AgentIdentityStatus.UNBOUND,
            production_eligible=False,
            version="1.3.0",
            hostname="customer-service-pc",
            status=self.status,
            registered=self.status is AgentRuntimeStatus.ONLINE,
            registration_id=None,
            config_revision=None,
            last_heartbeat=NOW if self.status is AgentRuntimeStatus.ONLINE else None,
            consecutive_failures=0,
            last_error_code=None,
        )


class FakeHostPDDLogin:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.closed = False
        self.observation = PDDLoginObservation(
            observation_id="pdd-login-observation:host",
            browser_id=browser.state.browser_id,
            agent_id=browser.state.agent_id,
            login_state=PDDLoginState.WAITING_QR_SCAN,
            page_origin="https://mms.pinduoduo.com",
            page_path="/login/",
            page_ready=True,
            observed_at=NOW,
            reason_code="PDD_WAITING_FOR_HUMAN_QR_SCAN",
            human_action_required=True,
        )

    def launch(self) -> PDDLoginObservation:
        self.browser.open_browser()
        self.browser.navigate(LOGIN_URL)
        return self.observation

    def observe(self) -> PDDLoginObservation:
        return self.observation

    def close_resources(self) -> None:
        self.closed = True


class TransientFailingHostPDDLogin(FakeHostPDDLogin):
    def __init__(self, browser: FakeBrowser) -> None:
        super().__init__(browser)
        self.observe_calls = 0

    def observe(self) -> PDDLoginObservation:
        self.observe_calls += 1
        if self.observe_calls == 1:
            raise PDDLoginReadError("transient session persistence race")
        return self.observation


def test_windows_host_exposes_pdd_login_state_without_store_values(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    config_path = data_root / "config" / "agent.json"
    config_path.parent.mkdir(parents=True)
    config = ChannelAgentConfig(
        server_url="https://channel-engine.example",
        agent_id="agent-pdd-host",
        device_id="device-pdd-host",
        browser_enabled=True,
        pdd_login_observation_enabled=True,
        pdd_login_url=LOGIN_URL,
        pdd_customer_service_url=CUSTOMER_SERVICE_URL,
        heartbeat_interval_seconds=0.05,
    )
    config_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    browser = FakeBrowser(data_root, config.agent_id)
    pdd = FakeHostPDDLogin(browser)
    host = WindowsAgentHost(
        config_path,
        data_root,
        runtime_factory=lambda value, **_kwargs: FakeRuntime(value),  # type: ignore[arg-type]
        browser_factory=lambda _value, _root: browser,  # type: ignore[arg-type]
        pdd_login_factory=lambda _value, _root, _browser: pdd,  # type: ignore[arg-type]
        clock=lambda: NOW,
        poll_interval_seconds=0.02,
    )
    stop = Event()
    result: list[int] = []
    worker = Thread(target=lambda: result.append(host.run(stop)))
    worker.start()
    deadline = time.monotonic() + 2
    observed = False
    while time.monotonic() < deadline:
        state = host.state_store.load()
        if state.pdd_login_state is PDDLoginState.WAITING_QR_SCAN:
            observed = True
            break
        time.sleep(0.02)
    host.request_stop()
    worker.join(timeout=2)
    final = host.state_store.load()

    assert observed is True
    assert result == [0]
    assert pdd.closed is True
    assert final.pdd_login_observation_enabled is True
    assert final.pdd_login_state is PDDLoginState.WAITING_QR_SCAN
    assert final.pdd_store_reference is None
    serialized = host.state_store.path.read_text("utf-8").casefold()
    assert "cookie" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized


def test_windows_host_keeps_agent_and_edge_alive_after_transient_login_poll_error(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    config_path = data_root / "config" / "agent.json"
    config_path.parent.mkdir(parents=True)
    config = ChannelAgentConfig(
        server_url="https://channel-engine.example",
        agent_id="agent-pdd-host",
        device_id="device-pdd-host",
        browser_enabled=True,
        pdd_login_observation_enabled=True,
        pdd_login_url=LOGIN_URL,
        pdd_customer_service_url=CUSTOMER_SERVICE_URL,
        heartbeat_interval_seconds=0.05,
    )
    config_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    browser = FakeBrowser(data_root, config.agent_id)
    pdd = TransientFailingHostPDDLogin(browser)
    host = WindowsAgentHost(
        config_path,
        data_root,
        runtime_factory=lambda value, **_kwargs: FakeRuntime(value),  # type: ignore[arg-type]
        browser_factory=lambda _value, _root: browser,  # type: ignore[arg-type]
        pdd_login_factory=lambda _value, _root, _browser: pdd,  # type: ignore[arg-type]
        clock=lambda: NOW,
        poll_interval_seconds=0.02,
    )
    stop = Event()
    result: list[int] = []
    worker = Thread(target=lambda: result.append(host.run(stop)))
    worker.start()
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline and pdd.observe_calls < 2:
        time.sleep(0.02)

    try:
        assert pdd.observe_calls >= 2
        assert worker.is_alive()
        assert browser.closed is False
        assert host.state_store.load().process_status is WindowsClientProcessStatus.RUNNING
    finally:
        stop.set()
        host.request_stop()
        worker.join(timeout=2)
    assert result == [0]
    assert browser.closed is True
