from __future__ import annotations

import importlib.util
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx

from channel_agent.client import AgentConnectionError, ChannelEngineClient
from channel_agent.config import ChannelAgentConfig
from channel_agent.control_v2 import DeviceRequestVerifier
from channel_agent.security import DeviceCredentialMaterial, InMemoryDeviceCredentialStore

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_rc5_backend_blackbox_suite.py"
SPEC = importlib.util.spec_from_file_location("rc5_backend_blackbox_suite", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _platform_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY, username TEXT, status TEXT,
                must_change_password INTEGER
            );
            CREATE TABLE roles (id INTEGER PRIMARY KEY, role_name TEXT);
            CREATE TABLE user_roles (user_id TEXT, role_id INTEGER);
            CREATE TABLE user_store_bindings (
                user_id TEXT, store_id INTEGER, is_default INTEGER
            );
            CREATE TABLE user_sessions (
                id TEXT PRIMARY KEY, user_id TEXT, token_hash TEXT,
                created_at TEXT, expires_at TEXT, revoked_at TEXT
            );
            INSERT INTO users VALUES ('user-1','operator','ACTIVE',0);
            INSERT INTO roles VALUES (1,'CUSTOMER_SERVICE');
            INSERT INTO user_roles VALUES ('user-1',1);
            INSERT INTO user_store_bindings VALUES ('user-1',7,1);
            """
        )


def test_temporary_session_lease_is_exact_and_opaque(tmp_path: Path) -> None:
    database = tmp_path / "platform.sqlite3"
    _platform_database(database)

    with MODULE.TemporaryPlatformSessionLease(database, "user-1") as lease:
        assert lease.authorization.startswith("Bearer acs_v1_")
        with sqlite3.connect(database) as connection:
            row = connection.execute(
                "SELECT token_hash FROM user_sessions WHERE id=?", (lease.session_id,)
            ).fetchone()
            assert row is not None
            assert "acs_v1_" not in row[0]

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM user_sessions").fetchone()[0] == 0
    assert "acs_v1_" not in str(lease.public_facts())
    assert lease.before_identity == lease.after_identity


def test_suite_records_failures_and_writes_junit(tmp_path: Path) -> None:
    suite = MODULE.Suite(tmp_path)
    assert suite.run("passing", lambda: {"ok": True}) == {"ok": True}
    assert suite.run(
        "failing", lambda: (_ for _ in ()).throw(RuntimeError("expected"))
    ) is None

    reports = MODULE.render_reports(suite, {"scope": "test"}, {"clean": True})
    assert reports["json"].is_file()
    assert reports["markdown"].is_file()
    assert reports["junit"].is_file()
    assert 'failures="1"' in reports["junit"].read_text(encoding="utf-8")


def test_secret_scan_rejects_session_tokens(tmp_path: Path) -> None:
    (tmp_path / "safe.json").write_text('{"reference":"wincred://safe"}', encoding="utf-8")
    assert MODULE.secret_scan(tmp_path)["passed"] is True
    (tmp_path / "leak.txt").write_text("acs_v1_example", encoding="utf-8")
    result = MODULE.secret_scan(tmp_path)
    assert result["passed"] is False
    assert result["matches"] == ["leak.txt"]


def test_trace_client_signs_the_host_decoded_colon_path(tmp_path: Path) -> None:
    secret = b"trace-path-signing-regression-secret-32bytes"
    reference = "wincred://AI-CS/ChannelAgent/test-host/test-device"
    credentials = InMemoryDeviceCredentialStore()
    credentials.put(reference, secret)
    verifier = DeviceRequestVerifier(
        lambda _agent_id, _device_id: DeviceCredentialMaterial(reference, secret)
    )
    trace_id = "trace:" + "a" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(trace_id)
        verifier.verify(
            request.method,
            request.url.path,
            request.content,
            dict(request.headers),
        )
        now = datetime.now(UTC).isoformat()
        return httpx.Response(
            200,
            json={
                "control_protocol_version": "2.1",
                "trace_id": trace_id,
                "steps": [
                    {
                        "trace_id": trace_id,
                        "stage": "HOST_PERSIST",
                        "state": "SUCCEEDED",
                        "reason_code": "HOST_ACK_COMMITTED",
                        "started_at": now,
                        "updated_at": now,
                        "duration_ms": 0,
                    }
                ],
                "server_time": now,
            },
        )

    transport = httpx.MockTransport(handler)
    http = httpx.Client(base_url="https://testserver", transport=transport)
    config = ChannelAgentConfig(
        server_url="https://testserver",
        agent_id="agent-001",
        device_id="device-001",
        device_credential_reference=reference,
        log_directory=tmp_path,
    )
    client = ChannelEngineClient(
        config, http_client=http, credential_store=credentials
    )
    assert client.fetch_assistant_trace(trace_id).trace_id == trace_id
    http.close()


def test_snapshot_poll_retries_transient_host_read_timeout(monkeypatch) -> None:
    class TransientClient:
        calls = 0

        def fetch_assistant_snapshot(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise AgentConnectionError("Channel Engine is unavailable")
            return SimpleNamespace(snapshot=SimpleNamespace(status="WAITING_APPROVAL"))

    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)
    client = TransientClient()
    snapshot = MODULE.wait_snapshot(
        client,
        "store-1",
        "conversation-1",
        statuses={"WAITING_APPROVAL"},
        timeout=1,
    )
    assert snapshot.status == "WAITING_APPROVAL"
    assert client.calls == 2
