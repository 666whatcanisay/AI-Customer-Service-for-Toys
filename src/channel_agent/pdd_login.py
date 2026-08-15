from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol, runtime_checkable
from urllib.parse import parse_qs, urlsplit, urlunsplit

import websocket
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .browser import (
    BrowserControlError,
    BrowserSessionStatus,
    ChannelAgentBrowserManager,
)
from .logger import SafeAgentLogger


PDD_LOGIN_OBSERVATION_VERSION = "1.0"
PDD_LOGIN_EVENT_TYPE = "browser.login.state_changed"
PDD_OFFICIAL_ORIGIN = "https://mms.pinduoduo.com"
PDD_CUSTOMER_SERVICE_PATH = "/chat-merchant/index.html"
_MAX_CDP_BYTES = 1_048_576
_STORE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class PDDLoginObservationError(RuntimeError):
    pass


class PDDLoginTargetUnavailable(PDDLoginObservationError):
    pass


class PDDLoginReadError(PDDLoginObservationError):
    pass


class PDDLoginState(StrEnum):
    PDD_LOGIN_PAGE = "PDD_LOGIN_PAGE"
    WAITING_QR_SCAN = "WAITING_QR_SCAN"
    PDD_LOGIN_SUCCESS = "PDD_LOGIN_SUCCESS"
    OPENING_CUSTOMER_SERVICE = "OPENING_CUSTOMER_SERVICE"
    CUSTOMER_SERVICE_READY = "CUSTOMER_SERVICE_READY"
    LOGIN_FAILED = "LOGIN_FAILED"


class PDDLoginModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PDDStoreIdentity(PDDLoginModel):
    platform: Literal["PDD"] = "PDD"
    login_status: Literal["SUCCESS"] = "SUCCESS"
    store_id: str = Field(min_length=1, max_length=64)
    store_name: str | None = Field(default=None, min_length=1, max_length=128)
    identity_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    observed_at: AwareDatetime
    source: Literal["READ_ONLY_PUBLIC_PAGE"] = "READ_ONLY_PUBLIC_PAGE"

    @field_validator("store_id")
    @classmethod
    def validate_store_id(cls, value: str) -> str:
        normalized = value.strip()
        if _STORE_ID.fullmatch(normalized) is None:
            raise ValueError("PDD store id has an invalid public identifier format")
        return normalized

    @field_validator("store_name")
    @classmethod
    def validate_store_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if (
            not normalized
            or any(ord(character) < 32 for character in normalized)
            or _PHONE.search(normalized)
            or _EMAIL.search(normalized)
        ):
            raise ValueError("PDD store name is unsafe or contains personal data")
        return normalized


class PDDLoginObservation(PDDLoginModel):
    observation_version: Literal["1.0"] = PDD_LOGIN_OBSERVATION_VERSION
    observation_id: str = Field(min_length=1, max_length=160)
    browser_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    login_state: PDDLoginState
    page_origin: Literal["https://mms.pinduoduo.com"] | None = None
    page_path: str | None = Field(default=None, max_length=512)
    page_ready: bool
    customer_service_shell_present: bool = False
    store_identity: PDDStoreIdentity | None = None
    store_reference: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    observed_at: AwareDatetime
    reason_code: str = Field(min_length=3, max_length=128)
    human_action_required: bool
    read_only: Literal[True] = True
    page_write_operations: Literal[0] = 0
    customer_messages_read: Literal[0] = 0
    navigation_operations: int = Field(default=0, ge=0, le=1)

    def public_view(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class PDDLoginSessionReference(PDDLoginModel):
    schema_version: Literal["1.0"] = PDD_LOGIN_OBSERVATION_VERSION
    browser_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    login_state: PDDLoginState
    candidate_fingerprint: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    candidate_observation_count: int = Field(default=0, ge=0, le=10)
    store_reference: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    observed_at: AwareDatetime
    reason_code: str = Field(min_length=3, max_length=128)
    contains_credentials: Literal[False] = False
    contains_customer_data: Literal[False] = False


class PDDLoginStateChangedEvent(PDDLoginModel):
    event_version: Literal["1.0"] = PDD_LOGIN_OBSERVATION_VERSION
    event_id: str = Field(min_length=1, max_length=160)
    event_type: Literal["browser.login.state_changed"] = PDD_LOGIN_EVENT_TYPE
    agent_id: str = Field(min_length=1, max_length=128)
    browser_id: str = Field(min_length=1, max_length=128)
    before: PDDLoginState | None
    after: PDDLoginState
    store_reference: str | None = Field(
        default=None, pattern=r"^sha256:[a-f0-9]{64}$"
    )
    timestamp: AwareDatetime
    reason_code: str = Field(min_length=3, max_length=128)
    contains_credentials: Literal[False] = False
    contains_customer_data: Literal[False] = False


class PDDLoginSessionStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> PDDLoginSessionReference | None:
        if not self.path.exists():
            return None
        try:
            raw = self.path.read_bytes()
            if len(raw) > 1024 * 1024:
                raise PDDLoginReadError("PDD login session reference exceeds one MiB")
            return PDDLoginSessionReference.model_validate_json(raw)
        except PDDLoginObservationError:
            raise
        except Exception as exc:
            raise PDDLoginReadError("PDD login session reference is invalid") from exc

    def save(self, value: PDDLoginSessionReference) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = value.model_dump_json(indent=2).encode("utf-8") + b"\n"
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, self.path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise PDDLoginReadError("PDD login session reference cannot be saved") from exc


@runtime_checkable
class PDDLoginEventSink(Protocol):
    def publish(self, event: PDDLoginStateChangedEvent) -> None: ...


class LocalPDDLoginEventStore:
    """Append-only local event evidence without public store identity values."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = RLock()

    def publish(self, event: PDDLoginStateChangedEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = event.model_dump_json() + "\n"
        with self._lock:
            try:
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                raise PDDLoginReadError("PDD login event cannot be persisted") from exc


@dataclass(frozen=True, slots=True)
class PDDCDPPageTarget:
    target_id: str
    websocket_url: str
    page_url: str
    page_origin: str
    page_path: str


@runtime_checkable
class PDDCDPTargetResolverPort(Protocol):
    def resolve(self, profile_path: Path) -> PDDCDPPageTarget: ...


@runtime_checkable
class PDDReadOnlyEvaluatorPort(Protocol):
    def capture_public_login_metadata(
        self, target: PDDCDPPageTarget
    ) -> Mapping[str, object]: ...


class EdgePDDTargetResolver:
    """Resolve exactly one official PDD page from Edge's loopback CDP endpoint."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 1.0,
        max_response_bytes: int = _MAX_CDP_BYTES,
    ) -> None:
        if timeout_seconds <= 0 or max_response_bytes < 1:
            raise ValueError("PDD target resolver limits must be positive")
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def resolve(self, profile_path: Path) -> PDDCDPPageTarget:
        port = self._read_port(profile_path)
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/list",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                payload = response.read(self._max_response_bytes + 1)
        except (OSError, urllib.error.URLError) as exc:
            raise PDDLoginTargetUnavailable("Edge CDP endpoint is unavailable") from exc
        if len(payload) > self._max_response_bytes:
            raise PDDLoginTargetUnavailable("Edge target list exceeded the safety limit")
        try:
            raw_targets = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PDDLoginTargetUnavailable("Edge target list is invalid") from exc
        if not isinstance(raw_targets, list):
            raise PDDLoginTargetUnavailable("Edge target list must be an array")
        matches: list[PDDCDPPageTarget] = []
        for raw in raw_targets:
            if not isinstance(raw, dict) or raw.get("type") != "page":
                continue
            target_id = raw.get("id")
            page_url = raw.get("url")
            websocket_url = raw.get("webSocketDebuggerUrl")
            if not all(
                isinstance(item, str)
                for item in (target_id, page_url, websocket_url)
            ):
                continue
            assert isinstance(target_id, str)
            assert isinstance(page_url, str)
            assert isinstance(websocket_url, str)
            parsed = urlsplit(page_url)
            origin = _origin(parsed)
            priority = _observation_path_priority(parsed.path)
            if origin != PDD_OFFICIAL_ORIGIN or priority < 0:
                continue
            self._validate_websocket(websocket_url, port)
            matches.append(
                PDDCDPPageTarget(
                    target_id=target_id,
                    websocket_url=websocket_url,
                    page_url=page_url,
                    page_origin=origin,
                    page_path=parsed.path or "/",
                )
            )
        if matches:
            highest_priority = max(
                _observation_path_priority(item.page_path) for item in matches
            )
            matches = [
                item
                for item in matches
                if _observation_path_priority(item.page_path) == highest_priority
            ]
        if len(matches) != 1:
            raise PDDLoginTargetUnavailable(
                "expected exactly one official PDD page target"
            )
        return matches[0]

    @staticmethod
    def _read_port(profile_path: Path) -> int:
        try:
            first = (profile_path / "DevToolsActivePort").read_text(
                encoding="utf-8"
            ).splitlines()[0]
            port = int(first)
        except (FileNotFoundError, OSError, IndexError, ValueError) as exc:
            raise PDDLoginTargetUnavailable("Edge debugging port is not ready") from exc
        if not 1 <= port <= 65535:
            raise PDDLoginTargetUnavailable("Edge debugging port is invalid")
        return port

    @staticmethod
    def _validate_websocket(value: str, expected_port: int) -> None:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "ws"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.port != expected_port
            or not parsed.path.startswith("/devtools/page/")
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise PDDLoginTargetUnavailable("Edge page endpoint escaped loopback policy")


class FixedReadOnlyPDDEvaluator:
    """Runs one fixed metadata expression with no click, input or message access."""

    _EXPRESSION = r"""
(() => {
  const names = ['data-store-name','data-shop-name','data-mall-name'];
  const ids = ['data-store-id','data-shop-id','data-mall-id','data-merchant-id'];
  const collect = (attributes) => {
    const out = {};
    for (const attribute of attributes) {
      const values = [];
      for (const element of document.querySelectorAll(`[${attribute}]`)) {
        if (values.length >= 5) break;
        const value = String(element.getAttribute(attribute) || '').trim().slice(0, 128);
        if (value) values.push(value);
      }
      out[attribute] = [...new Set(values)];
    }
    return out;
  };
  return {
    ready_state: String(document.readyState || ''),
    title: String(document.title || '').trim().slice(0, 256),
    customer_service_shell_present: Boolean(document.querySelector('#root, #app')),
    identity_attributes: {...collect(ids), ...collect(names)},
    identity_state: {
      current_mall_id: String(localStorage.getItem('currentMallId') || '').trim().slice(0, 64),
      global_mall_id: (
        typeof window.global_mall_id === 'string' ||
        typeof window.global_mall_id === 'number'
      ) ? String(window.global_mall_id).trim().slice(0, 64) : '',
      public_store_name: String(
        document.querySelector('.user-name-name')?.firstChild?.nodeValue || ''
      ).replace(/\s+/g, ' ').trim().slice(0, 128)
    }
  };
})()
""".strip()

    def __init__(
        self,
        *,
        timeout_seconds: float = 2.0,
        max_response_bytes: int = _MAX_CDP_BYTES,
    ) -> None:
        if timeout_seconds <= 0 or max_response_bytes < 1:
            raise ValueError("PDD evaluator limits must be positive")
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._sequence = 0
        self._lock = RLock()

    def capture_public_login_metadata(
        self, target: PDDCDPPageTarget
    ) -> Mapping[str, object]:
        with self._lock:
            self._sequence += 1
            command_id = self._sequence
        command = json.dumps(
            {
                "id": command_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": self._EXPRESSION,
                    "returnByValue": True,
                    "awaitPromise": False,
                    "includeCommandLineAPI": False,
                    "silent": True,
                },
            },
            separators=(",", ":"),
        )
        connection = None
        try:
            connection = websocket.create_connection(
                target.websocket_url,
                timeout=self._timeout,
                suppress_origin=True,
                http_proxy_host=None,
            )
            connection.send(command)
            while True:
                raw = connection.recv()
                if not isinstance(raw, str):
                    raise PDDLoginReadError("Edge returned a binary CDP response")
                if len(raw.encode("utf-8")) > self._max_response_bytes:
                    raise PDDLoginReadError("Edge CDP response exceeded the safety limit")
                response = json.loads(raw)
                if not isinstance(response, dict) or response.get("id") != command_id:
                    continue
                if "error" in response:
                    raise PDDLoginReadError("Edge rejected the read-only observation")
                result = response.get("result")
                remote = result.get("result") if isinstance(result, dict) else None
                value = remote.get("value") if isinstance(remote, dict) else None
                if not isinstance(value, dict):
                    raise PDDLoginReadError("Edge returned invalid login metadata")
                return value
        except PDDLoginObservationError:
            raise
        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
            websocket.WebSocketException,
        ) as exc:
            raise PDDLoginTargetUnavailable("Edge read-only CDP channel failed") from exc
        finally:
            if connection is not None:
                connection.close()


class PDDLoginObservationAdapter:
    """PDD login-only adapter. It has no customer-message or write capability."""

    observe_only = True
    page_write_operations = 0
    customer_messages_read = 0

    def __init__(
        self,
        *,
        agent_id: str,
        data_root: str | Path,
        login_url: str,
        customer_service_url: str,
        browser: ChannelAgentBrowserManager,
        logger: SafeAgentLogger,
        target_resolver: PDDCDPTargetResolverPort | None = None,
        evaluator: PDDReadOnlyEvaluatorPort | None = None,
        event_sink: PDDLoginEventSink | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.agent_id = agent_id
        self.data_root = Path(data_root).resolve()
        self.login_url = _validate_login_url(login_url)
        self.customer_service_url = _validate_customer_service_url(
            customer_service_url
        )
        self._browser = browser
        self._logger = logger
        self._resolver = target_resolver or EdgePDDTargetResolver()
        self._evaluator = evaluator or FixedReadOnlyPDDEvaluator()
        digest = hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:16]
        self._store = PDDLoginSessionStore(
            self.data_root / "runtime" / "pdd-login" / f"{digest}.json"
        )
        self._events = event_sink or LocalPDDLoginEventStore(
            self.data_root / "events" / "pdd-login-events.jsonl"
        )
        self._clock = clock
        self._lock = RLock()

    def launch(self) -> PDDLoginObservation:
        with self._lock:
            previous = self._store.load()
            browser = self._browser.open_browser()
            # Reuse an already authenticated customer-service tab after Agent restart.
            # This avoids creating a redundant login/home tab and preserves the human
            # session.  Observation remains read-only; fallback navigation is used only
            # when no authenticated PDD page can be identified.
            # A persisted login observation belongs to one browser session.  When
            # the operator closes the dedicated Edge window and explicitly opens
            # it again, open_browser() creates a new browser_id.  Do not probe the
            # new process using stale state from the closed session; navigate it to
            # the login page first and let the next read-only refresh classify it.
            if previous is not None and previous.browser_id == browser.browser_id:
                existing = self.observe()
                if existing.login_state in {
                    PDDLoginState.PDD_LOGIN_PAGE,
                    PDDLoginState.WAITING_QR_SCAN,
                    PDDLoginState.PDD_LOGIN_SUCCESS,
                    PDDLoginState.OPENING_CUSTOMER_SERVICE,
                    PDDLoginState.CUSTOMER_SERVICE_READY,
                }:
                    return existing
            browser = self._browser.navigate(self.login_url)
            now = self._clock()
            observation = PDDLoginObservation(
                observation_id=f"pdd-login-observation:{uuid.uuid4()}",
                browser_id=browser.browser_id,
                agent_id=self.agent_id,
                login_state=PDDLoginState.PDD_LOGIN_PAGE,
                page_origin=PDD_OFFICIAL_ORIGIN,
                page_path=urlsplit(self.login_url).path,
                page_ready=False,
                observed_at=now,
                reason_code="PDD_LOGIN_NAVIGATION_REQUESTED",
                human_action_required=True,
                navigation_operations=1,
            )
            self._save_and_emit(observation, previous=self._store.load())
            return observation

    def observe(self) -> PDDLoginObservation:
        with self._lock:
            previous = self._store.load()
            browser = self._browser.browser_status()
            if browser.status not in {
                BrowserSessionStatus.OPENED,
                BrowserSessionStatus.WAITING_LOGIN,
                BrowserSessionStatus.READY,
            }:
                return self._failed(
                    browser.browser_id,
                    previous,
                    "PDD_BROWSER_NOT_AVAILABLE",
                )
            try:
                target = self._resolver.resolve(Path(browser.profile_path))
                metadata = self._evaluator.capture_public_login_metadata(target)
                observation = self._classify(browser.browser_id, target, metadata, previous)
            except (PDDLoginObservationError, BrowserControlError) as exc:
                self._logger.error("PDD_LOGIN_OBSERVATION_FAILED", exc)
                return self._failed(
                    browser.browser_id,
                    previous,
                    type(exc).__name__.upper(),
                )
            if observation.login_state is PDDLoginState.PDD_LOGIN_SUCCESS:
                navigation_requested = (
                    previous is None
                    or previous.login_state
                    is not PDDLoginState.OPENING_CUSTOMER_SERVICE
                )
                if navigation_requested:
                    self._save_and_emit(observation, previous=previous)
                    try:
                        self._browser.navigate(self.customer_service_url)
                    except BrowserControlError as exc:
                        self._logger.error("PDD_CUSTOMER_SERVICE_NAVIGATION_FAILED", exc)
                        return self._failed(
                            browser.browser_id,
                            self._store.load(),
                            "PDD_CUSTOMER_SERVICE_NAVIGATION_FAILED",
                        )
                observation = PDDLoginObservation(
                    observation_id=f"pdd-login-observation:{uuid.uuid4()}",
                    browser_id=browser.browser_id,
                    agent_id=self.agent_id,
                    login_state=PDDLoginState.OPENING_CUSTOMER_SERVICE,
                    page_origin=PDD_OFFICIAL_ORIGIN,
                    page_path=urlsplit(self.customer_service_url).path,
                    page_ready=False,
                    store_identity=observation.store_identity,
                    store_reference=observation.store_reference,
                    observed_at=self._clock(),
                    reason_code=(
                        "PDD_CUSTOMER_SERVICE_NAVIGATION_REQUESTED"
                        if navigation_requested
                        else "PDD_CUSTOMER_SERVICE_PAGE_STILL_LOADING"
                    ),
                    human_action_required=False,
                    navigation_operations=1 if navigation_requested else 0,
                )
                previous = self._store.load()
            elif (
                observation.login_state is PDDLoginState.CUSTOMER_SERVICE_READY
                and (
                    previous is None
                    or previous.login_state
                    not in {
                        PDDLoginState.PDD_LOGIN_SUCCESS,
                        PDDLoginState.OPENING_CUSTOMER_SERVICE,
                        PDDLoginState.CUSTOMER_SERVICE_READY,
                    }
                )
            ):
                # A user may already have opened the official customer-service tab.
                # Preserve the explicit lifecycle without navigating or reading content.
                detected_login = PDDLoginObservation(
                    observation_id=f"pdd-login-observation:{uuid.uuid4()}",
                    browser_id=browser.browser_id,
                    agent_id=self.agent_id,
                    login_state=PDDLoginState.PDD_LOGIN_SUCCESS,
                    page_origin=PDD_OFFICIAL_ORIGIN,
                    page_path=observation.page_path,
                    page_ready=True,
                    observed_at=self._clock(),
                    reason_code="PDD_AUTHENTICATED_CUSTOMER_SERVICE_PAGE_DETECTED",
                    human_action_required=False,
                )
                self._save_and_emit(detected_login, previous=previous)
                opening = PDDLoginObservation(
                    observation_id=f"pdd-login-observation:{uuid.uuid4()}",
                    browser_id=browser.browser_id,
                    agent_id=self.agent_id,
                    login_state=PDDLoginState.OPENING_CUSTOMER_SERVICE,
                    page_origin=PDD_OFFICIAL_ORIGIN,
                    page_path=observation.page_path,
                    page_ready=True,
                    customer_service_shell_present=True,
                    observed_at=self._clock(),
                    reason_code="PDD_CUSTOMER_SERVICE_PAGE_ALREADY_OPEN",
                    human_action_required=False,
                )
                self._save_and_emit(opening, previous=self._store.load())
                previous = self._store.load()
                observation = observation.model_copy(
                    update={"observed_at": self._clock()}
                )
            self._save_and_emit(observation, previous=previous)
            reference = _observation_reference(observation.observation_id)
            self._browser.apply_login_observation(
                authenticated=observation.login_state
                in {
                    PDDLoginState.PDD_LOGIN_SUCCESS,
                    PDDLoginState.OPENING_CUSTOMER_SERVICE,
                    PDDLoginState.CUSTOMER_SERVICE_READY,
                },
                observation_reference=reference,
            )
            return observation

    def session_reference(self) -> PDDLoginSessionReference | None:
        return self._store.load()

    def close_resources(self) -> None:
        self._logger.close()

    def _classify(
        self,
        browser_id: str,
        target: PDDCDPPageTarget,
        metadata: Mapping[str, object],
        previous: PDDLoginSessionReference | None,
    ) -> PDDLoginObservation:
        now = self._clock()
        ready_state = metadata.get("ready_state")
        page_ready = ready_state in {"interactive", "complete"}
        shell_present = metadata.get("customer_service_shell_present") is True
        safe_path = target.page_path[:512]
        if _is_login_path(target.page_path):
            state = (
                PDDLoginState.WAITING_QR_SCAN
                if page_ready
                else PDDLoginState.PDD_LOGIN_PAGE
            )
            reason = (
                "PDD_WAITING_FOR_HUMAN_QR_SCAN"
                if page_ready
                else "PDD_LOGIN_PAGE_LOADING"
            )
            return PDDLoginObservation(
                observation_id=f"pdd-login-observation:{uuid.uuid4()}",
                browser_id=browser_id,
                agent_id=self.agent_id,
                login_state=state,
                page_origin=PDD_OFFICIAL_ORIGIN,
                page_path=safe_path,
                page_ready=page_ready,
                observed_at=now,
                reason_code=reason,
                human_action_required=True,
            )
        candidate = _extract_public_store_identity(target.page_url, metadata, now)
        if _is_customer_service_path(target.page_path):
            state = (
                PDDLoginState.CUSTOMER_SERVICE_READY
                if page_ready and shell_present
                else PDDLoginState.OPENING_CUSTOMER_SERVICE
            )
            return PDDLoginObservation(
                observation_id=f"pdd-login-observation:{uuid.uuid4()}",
                browser_id=browser_id,
                agent_id=self.agent_id,
                login_state=state,
                page_origin=PDD_OFFICIAL_ORIGIN,
                page_path=safe_path,
                page_ready=page_ready,
                customer_service_shell_present=shell_present,
                store_identity=candidate,
                store_reference=(
                    candidate.identity_reference if candidate is not None else None
                ),
                observed_at=now,
                reason_code=(
                    "PDD_CUSTOMER_SERVICE_SHELL_READY"
                    if state is PDDLoginState.CUSTOMER_SERVICE_READY
                    else "PDD_CUSTOMER_SERVICE_PAGE_LOADING"
                ),
                human_action_required=False,
            )
        return PDDLoginObservation(
            observation_id=f"pdd-login-observation:{uuid.uuid4()}",
            browser_id=browser_id,
            agent_id=self.agent_id,
            login_state=(
                PDDLoginState.PDD_LOGIN_SUCCESS
                if page_ready
                else PDDLoginState.PDD_LOGIN_PAGE
            ),
            page_origin=PDD_OFFICIAL_ORIGIN,
            page_path=safe_path,
            page_ready=page_ready,
            store_identity=candidate,
            store_reference=(
                candidate.identity_reference if candidate is not None else None
            ),
            observed_at=now,
            reason_code=(
                "PDD_LOGIN_SUCCESS_ADMIN_PAGE_DETECTED"
                if page_ready
                else "PDD_ADMIN_PAGE_LOADING"
            ),
            human_action_required=False,
        )

    def _failed(
        self,
        browser_id: str,
        previous: PDDLoginSessionReference | None,
        reason_code: str,
    ) -> PDDLoginObservation:
        observation = PDDLoginObservation(
            observation_id=f"pdd-login-observation:{uuid.uuid4()}",
            browser_id=browser_id,
            agent_id=self.agent_id,
            login_state=PDDLoginState.LOGIN_FAILED,
            page_ready=False,
            observed_at=self._clock(),
            reason_code=reason_code[:128],
            human_action_required=True,
        )
        self._save_and_emit(observation, previous=previous)
        return observation

    def _save_and_emit(
        self,
        observation: PDDLoginObservation,
        *,
        previous: PDDLoginSessionReference | None,
    ) -> None:
        fingerprint = observation.store_reference
        candidate_count = 0
        if observation.login_state in {
            PDDLoginState.PDD_LOGIN_SUCCESS,
            PDDLoginState.OPENING_CUSTOMER_SERVICE,
            PDDLoginState.CUSTOMER_SERVICE_READY,
        } and fingerprint is not None:
            candidate_count = (
                previous.candidate_observation_count + 1
                if previous is not None
                and previous.candidate_fingerprint == fingerprint
                else 1
            )
        session = PDDLoginSessionReference(
            browser_id=observation.browser_id,
            agent_id=observation.agent_id,
            login_state=observation.login_state,
            candidate_fingerprint=fingerprint,
            candidate_observation_count=min(candidate_count, 10),
            store_reference=observation.store_reference,
            observed_at=observation.observed_at,
            reason_code=observation.reason_code,
        )
        self._store.save(session)
        before = previous.login_state if previous is not None else None
        if before is not observation.login_state:
            event = PDDLoginStateChangedEvent(
                event_id=f"pdd-login-event:{uuid.uuid4()}",
                agent_id=observation.agent_id,
                browser_id=observation.browser_id,
                before=before,
                after=observation.login_state,
                store_reference=observation.store_reference,
                timestamp=observation.observed_at,
                reason_code=observation.reason_code,
            )
            self._events.publish(event)
            self._logger.event(
                PDD_LOGIN_EVENT_TYPE,
                "SUCCESS",
                {
                    "agent_id": observation.agent_id,
                    "browser_id": observation.browser_id,
                    "before": before.value if before is not None else None,
                    "after": observation.login_state.value,
                    "store_reference": observation.store_reference,
                    "reason_code": observation.reason_code,
                    "read_only": True,
                },
            )


def _extract_public_store_identity(
    page_url: str,
    metadata: Mapping[str, object],
    observed_at: datetime,
) -> PDDStoreIdentity | None:
    parsed = urlsplit(page_url)
    query = parse_qs(parsed.query, keep_blank_values=False)
    ids: set[str] = set()
    for key in ("store_id", "shop_id", "mall_id", "merchant_id"):
        for value in query.get(key, ()):
            normalized = value.strip()
            if _STORE_ID.fullmatch(normalized):
                ids.add(normalized)
    attributes = metadata.get("identity_attributes")
    if isinstance(attributes, Mapping):
        for key in (
            "data-store-id",
            "data-shop-id",
            "data-mall-id",
            "data-merchant-id",
        ):
            values = attributes.get(key)
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str) and _STORE_ID.fullmatch(value.strip()):
                        ids.add(value.strip())
    identity_state = metadata.get("identity_state")
    if isinstance(identity_state, Mapping):
        for key in ("current_mall_id", "global_mall_id"):
            value = identity_state.get(key)
            if isinstance(value, str) and _STORE_ID.fullmatch(value.strip()):
                ids.add(value.strip())
    names: set[str] = set()
    if isinstance(attributes, Mapping):
        for key in ("data-store-name", "data-shop-name", "data-mall-name"):
            values = attributes.get(key)
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str):
                        candidate = _safe_store_name(value)
                        if candidate:
                            names.add(candidate)
    if isinstance(identity_state, Mapping):
        value = identity_state.get("public_store_name")
        if isinstance(value, str):
            candidate = _safe_store_name(value)
            if candidate:
                names.add(candidate)
    title = metadata.get("title")
    if isinstance(title, str):
        candidate = _store_name_from_title(title)
        if candidate:
            names.add(candidate)
    if len(ids) != 1 or len(names) > 1:
        return None
    store_id = next(iter(ids))
    store_name = next(iter(names)) if names else None
    reference = "sha256:" + hashlib.sha256(
        f"PDD\0{store_id}".encode("utf-8")
    ).hexdigest()
    return PDDStoreIdentity(
        store_id=store_id,
        store_name=store_name,
        identity_reference=reference,
        observed_at=observed_at,
    )


def _store_name_from_title(value: str) -> str | None:
    title = " ".join(value.split())
    generic = {
        "\u9996\u9875",
        "\u4e3b\u8d26\u53f7",
        "\u591a\u591a\u5ba2\u670d",
        "\u5546\u5bb6\u540e\u53f0",
        "\u62fc\u591a\u591a\u5546\u5bb6\u540e\u53f0",
        "拼多多商家后台",
        "拼多多商家管理后台",
        "拼多多商家版",
        "商家后台",
        "拼多多",
    }
    if title in generic:
        return None
    for separator in (" - ", " | ", " — ", "_拼多多"):
        if separator in title:
            title = title.split(separator, 1)[0].strip()
            break
    return _safe_store_name(title)


def _safe_store_name(value: str) -> str | None:
    normalized = " ".join(value.split())
    if (
        not 1 <= len(normalized) <= 128
        or _PHONE.search(normalized)
        or _EMAIL.search(normalized)
        or normalized in {"拼多多", "商家后台", "拼多多商家后台"}
    ):
        return None
    return normalized


def _validate_login_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if (
        _origin(parsed) != PDD_OFFICIAL_ORIGIN
        or not parsed.path.startswith("/login")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("PDD login URL must use the official credential-free login path")
    return normalized


def _validate_customer_service_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    if (
        _origin(parsed) != PDD_OFFICIAL_ORIGIN
        or parsed.path != PDD_CUSTOMER_SERVICE_PATH
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment not in {"", "/"}
    ):
        raise ValueError(
            "PDD customer service URL must use the official credential-free path"
        )
    return normalized


def _origin(parts) -> str:
    if not parts.scheme or not parts.hostname:
        return ""
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    port = f":{parts.port}" if parts.port is not None else ""
    return f"{parts.scheme}://{host}{port}"


def _is_login_path(value: str) -> bool:
    return value.casefold().startswith("/login")


def _is_customer_service_path(value: str) -> bool:
    return value.casefold() == PDD_CUSTOMER_SERVICE_PATH


def _observation_path_priority(value: str) -> int:
    """Select a known shell only; a chat shell outranks an admin or login tab."""

    path = value.casefold()
    if path == PDD_CUSTOMER_SERVICE_PATH:
        return 3
    if path == "/home" or path.startswith("/aftersales/"):
        return 2
    if path.startswith("/login"):
        return 1
    return -1


def _is_identity_observation_path(value: str) -> bool:
    """Compatibility helper for allowlisted, metadata-only observation paths."""

    return _observation_path_priority(value) >= 0


def _observation_reference(observation_id: str) -> str:
    return "sha256:" + hashlib.sha256(observation_id.encode("utf-8")).hexdigest()


__all__ = [
    "EdgePDDTargetResolver",
    "FixedReadOnlyPDDEvaluator",
    "LocalPDDLoginEventStore",
    "PDDCDPPageTarget",
    "PDDLoginEventSink",
    "PDDLoginModel",
    "PDDLoginObservation",
    "PDDLoginObservationAdapter",
    "PDDLoginObservationError",
    "PDDLoginReadError",
    "PDDLoginSessionReference",
    "PDDLoginSessionStore",
    "PDDLoginState",
    "PDDLoginStateChangedEvent",
    "PDDLoginTargetUnavailable",
    "PDDStoreIdentity",
    "PDD_CUSTOMER_SERVICE_PATH",
]
