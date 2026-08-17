from __future__ import annotations

import json

import pytest

from channel_agent.pdd_login import PDDCDPPageTarget
from channel_agent.pdd_readonly_driver import (
    PDDReadOnlyDriverError,
    ReadOnlyCDPEvaluator,
)


class _Connection:
    def __init__(self, response: dict[str, object]) -> None:
        self._response = response
        self.commands: list[dict[str, object]] = []
        self.closed = False

    def send(self, command: str) -> None:
        parsed = json.loads(command)
        self.commands.append(parsed)
        self._response["id"] = parsed["id"]

    def recv(self) -> str:
        return json.dumps(self._response)

    def close(self) -> None:
        self.closed = True


def _target() -> PDDCDPPageTarget:
    return PDDCDPPageTarget(
        target_id="pdd-page",
        websocket_url="ws://127.0.0.1:9222/devtools/page/pdd-page",
        page_url="https://mms.pinduoduo.com/chat-merchant/index.html#/",
        page_origin="https://mms.pinduoduo.com",
        page_path="/chat-merchant/index.html",
    )


def test_each_fresh_cdp_connection_uses_a_connection_local_command_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = [
        _Connection({"result": {"result": {"value": {"read": 1}}}}),
        _Connection({"result": {"result": {"value": {"read": 2}}}}),
    ]
    used: list[_Connection] = []

    def connect(*_args: object, **_kwargs: object) -> _Connection:
        connection = pending.pop(0)
        used.append(connection)
        return connection

    monkeypatch.setattr(
        "channel_agent.pdd_readonly_driver.websocket.create_connection",
        connect,
    )
    evaluator = ReadOnlyCDPEvaluator()

    assert evaluator.evaluate(_target(), "({read: 1})") == {"read": 1}
    assert evaluator.evaluate(_target(), "({read: 2})") == {"read": 2}

    # Both calls used separate websocket connections.  Their identifiers do
    # not inherit a sequence from a connection that has already been closed.
    assert [connection.commands[0]["id"] for connection in used] == [1, 1]
    assert all(connection.closed for connection in used)


def test_transient_missing_value_reopens_channel_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = [
        _Connection({"result": {"result": {"type": "undefined"}}}),
        _Connection({"result": {"result": {"value": {"messages": 1}}}}),
    ]
    used: list[_Connection] = []
    delays: list[float] = []

    def connect(*_args: object, **_kwargs: object) -> _Connection:
        connection = created.pop(0)
        used.append(connection)
        return connection

    monkeypatch.setattr(
        "channel_agent.pdd_readonly_driver.websocket.create_connection", connect
    )
    monkeypatch.setattr(
        "channel_agent.pdd_readonly_driver.sleep", lambda value: delays.append(value)
    )

    result = ReadOnlyCDPEvaluator(transient_attempts=2).evaluate(
        _target(), "({messages: 1})"
    )

    assert result == {"messages": 1}
    assert [connection.commands[0]["id"] for connection in used] == [1, 1]
    assert all(connection.closed for connection in used)
    assert delays == [0.075]


def test_repeated_missing_value_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = [
        _Connection({"result": {"result": {"type": "undefined"}}}),
        _Connection({"result": {"result": {"type": "undefined"}}}),
    ]
    monkeypatch.setattr(
        "channel_agent.pdd_readonly_driver.websocket.create_connection",
        lambda *_args, **_kwargs: created.pop(0),
    )
    monkeypatch.setattr("channel_agent.pdd_readonly_driver.sleep", lambda _value: None)

    with pytest.raises(PDDReadOnlyDriverError, match="transient retry"):
        ReadOnlyCDPEvaluator(transient_attempts=2).evaluate(_target(), "void 0")
