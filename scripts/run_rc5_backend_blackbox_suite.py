#!/usr/bin/env python3
"""RC5 backend-only, live-service black-box acceptance suite.

The suite never starts a browser, reads a PDD page, or invokes a send adapter.
Normal-path cases use the already-running services.  Failure and restart cases
run against cloned SQLite databases on isolated loopback ports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import xml.etree.ElementTree as ET
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from channel_agent.client import (  # noqa: E402
    AgentConnectionError,
    AgentRejectedError,
    ChannelEngineClient,
)
from channel_agent.config import ChannelAgentConfig, load_agent_config  # noqa: E402
from channel_agent.edge_spool import (  # noqa: E402
    DurableEdgeSpool,
    EdgeObservation,
    EdgeSpoolConflict,
)
from channel_agent.observation_runtime import PersistAckObservationForwarder  # noqa: E402
from channel_agent.providers import (  # noqa: E402
    ChannelAgentProviderIngress,
    RecordedReplayProvider,
    SyntheticPDDProvider,
    provider_observation_id,
)
from channel_agent.security import WindowsDPAPITransientPayloadProtector  # noqa: E402
from channel_agent.version import AGENT_VERSION  # noqa: E402
from channel_engine import __version__ as HOST_VERSION  # noqa: E402
from channel_engine.provider import NormalizedChannelObservation  # noqa: E402


def utc_now() -> datetime:
    return datetime.now(UTC)


def json_ready(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_ready(value), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as target_db:
        source_db.backup(target_db)


def sqlite_count(path: Path, table: str) -> int:
    if not path.exists():
        return 0
    with sqlite3.connect(path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            return 0
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def git_snapshot(path: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    try:
        return {
            "root": str(path),
            "sha": run("rev-parse", "HEAD"),
            "branch": run("branch", "--show-current"),
            "dirty_paths": run("status", "--short").splitlines(),
        }
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"root": str(path), "error": type(exc).__name__}


class TemporaryPlatformSessionLease(AbstractContextManager["TemporaryPlatformSessionLease"]):
    """A short-lived test session whose opaque token is never serialized."""

    def __init__(self, database: Path, user_id: str, *, ttl_minutes: int = 10) -> None:
        self.database = database
        self.user_id = user_id
        self.ttl_minutes = ttl_minutes
        self.session_id = str(uuid.uuid4())
        self._token: str | None = None
        self._created = False
        self.before_identity: dict[str, Any] | None = None
        self.after_identity: dict[str, Any] | None = None

    @staticmethod
    def _identity(connection: sqlite3.Connection, user_id: str) -> dict[str, Any]:
        user = connection.execute(
            "SELECT id, username, status, must_change_password FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if user is None:
            raise RuntimeError("temporary session user is unavailable")
        roles = [
            row[0]
            for row in connection.execute(
                """
                SELECT roles.role_name FROM roles
                JOIN user_roles ON user_roles.role_id=roles.id
                WHERE user_roles.user_id=? ORDER BY roles.role_name
                """,
                (user_id,),
            )
        ]
        stores = [
            {"store_id": int(row[0]), "is_default": bool(row[1])}
            for row in connection.execute(
                "SELECT store_id,is_default FROM user_store_bindings WHERE user_id=? ORDER BY store_id",
                (user_id,),
            )
        ]
        return {
            "id": user[0],
            "username": user[1],
            "status": user[2],
            "must_change_password": bool(user[3]),
            "roles": roles,
            "stores": stores,
        }

    def __enter__(self) -> "TemporaryPlatformSessionLease":
        token = "acs_v1_" + secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        created = utc_now()
        expires = created + timedelta(minutes=self.ttl_minutes)
        with sqlite3.connect(self.database) as connection:
            self.before_identity = self._identity(connection, self.user_id)
            if self.before_identity["status"] != "ACTIVE":
                raise RuntimeError("temporary session user is not active")
            if self.before_identity["must_change_password"]:
                raise RuntimeError("temporary session user requires a password change")
            connection.execute(
                """
                INSERT INTO user_sessions
                    (id,user_id,token_hash,created_at,expires_at,revoked_at)
                VALUES (?,?,?,?,?,NULL)
                """,
                (
                    self.session_id,
                    self.user_id,
                    token_hash,
                    created.isoformat(),
                    expires.isoformat(),
                ),
            )
            connection.commit()
        self._created = True
        self._token = token
        return self

    @property
    def authorization(self) -> str:
        if self._token is None:
            raise RuntimeError("temporary session lease is not active")
        return "Bearer " + self._token

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._token = None
        if not self._created:
            return
        with sqlite3.connect(self.database) as connection:
            connection.execute("DELETE FROM user_sessions WHERE id=?", (self.session_id,))
            connection.commit()
            if connection.execute(
                "SELECT 1 FROM user_sessions WHERE id=?", (self.session_id,)
            ).fetchone():
                raise RuntimeError("temporary session cleanup failed")
            self.after_identity = self._identity(connection, self.user_id)
        self._created = False
        if self.after_identity != self.before_identity:
            raise RuntimeError("temporary session changed user roles or Store binding")

    def public_facts(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "ttl_minutes": self.ttl_minutes,
            "user_id": self.user_id,
            "token_persisted_to_evidence": False,
            "identity_before": self.before_identity,
            "identity_after": self.after_identity,
        }


class PlatformClient:
    def __init__(self, base_url: str, authorization: str | None = None) -> None:
        headers = {"Authorization": authorization} if authorization else {}
        self.http = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(15),
            trust_env=False,
        )

    def close(self) -> None:
        self.http.close()

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"content_type": response.headers.get("content-type")}

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        expected: int | tuple[int, ...] = 200,
    ) -> dict[str, Any]:
        response = self.http.request(method, path, json=payload)
        allowed = (expected,) if isinstance(expected, int) else expected
        body = self._json(response)
        if response.status_code not in allowed:
            raise RuntimeError(f"platform request {path} returned {response.status_code}: {body}")
        return {"status_code": response.status_code, "body": body}

    def me(self) -> dict[str, Any]:
        return self.request("GET", "/api/v1/auth/me")["body"]

    def policy(self, store_id: int) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/workspace/reply-policy?store_id={store_id}")["body"]

    def set_policy(self, store_id: int, mode: str, revision: int) -> dict[str, Any]:
        return self.request(
            "PUT",
            "/api/v1/workspace/reply-policy",
            payload={
                "store_id": store_id,
                "mode": mode,
                "expected_revision": revision,
                "human_confirmed": True,
            },
        )["body"]

    def prepare(self, snapshot: Any, store_id: int) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/api/v1/workspace/decisions/{snapshot.decision_id}/execution-preparations",
            payload={
                "store_id": store_id,
                "conversation_id": snapshot.conversation_id,
                "customer_reference": snapshot.customer_reference,
                "human_confirmed": True,
            },
            expected=(200, 201),
        )["body"]


@dataclass
class Scenario:
    name: str
    required: bool
    started_at: str
    finished_at: str
    passed: bool
    evidence: Any = None
    error: dict[str, Any] | None = None


class Suite:
    def __init__(self, evidence_root: Path) -> None:
        self.evidence_root = evidence_root
        self.scenarios: list[Scenario] = []

    def run(self, name: str, action: Callable[[], Any], *, required: bool = True) -> Any:
        started = utc_now()
        try:
            evidence = action()
            result = Scenario(
                name, required, started.isoformat(), utc_now().isoformat(), True, evidence
            )
            return_value = evidence
        except Exception as exc:  # the report must survive every scenario failure
            result = Scenario(
                name,
                required,
                started.isoformat(),
                utc_now().isoformat(),
                False,
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "status_code": getattr(exc, "status_code", None),
                    "error_code": getattr(exc, "error_code", None),
                    "traceback": traceback.format_exc(limit=8),
                },
            )
            return_value = None
        self.scenarios.append(result)
        write_json(
            self.evidence_root / "scenarios" / f"{len(self.scenarios):02d}-{name}.json",
            result.__dict__,
        )
        state = "PASS" if result.passed else "FAIL"
        print(f"[{state}] {name}", flush=True)
        return return_value


def powershell(script: Path, **parameters: Any) -> dict[str, Any]:
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    for name, value in parameters.items():
        if value is None:
            continue
        command.extend(["-" + name, str(value)])
    stdout_fd, stdout_name = tempfile.mkstemp(prefix="rc5-ps-out-", suffix=".log")
    stderr_fd, stderr_name = tempfile.mkstemp(prefix="rc5-ps-err-", suffix=".log")
    os.close(stdout_fd)
    os.close(stderr_fd)
    stdout_path = Path(stdout_name)
    stderr_path = Path(stderr_name)
    try:
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            result = subprocess.run(
                command,
                stdout=stdout_handle,
                stderr=stderr_handle,
                timeout=180,
            )
        stdout = stdout_path.read_bytes().decode("utf-8", errors="replace")
        stderr = stderr_path.read_bytes().decode("utf-8", errors="replace")
    finally:
        try:
            stdout_path.unlink(missing_ok=True)
            stderr_path.unlink(missing_ok=True)
        except OSError:
            pass
    if result.returncode != 0:
        raise RuntimeError(f"{script.name} failed: {stderr.strip() or stdout.strip()}")
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError(f"{script.name} returned no JSON result: {stdout.strip()}")


class ShadowTopology:
    def __init__(self, args: argparse.Namespace, evidence_root: Path) -> None:
        self.args = args
        self.root = evidence_root / "shadow"
        self.host_database = self.root / "channel-engine.shadow.sqlite3"
        self.platform_database = self.root / "platform.shadow.sqlite3"
        self.offline_root = self.root / "host-offline-runtime"
        self.host_running = False
        self.platform_running = False

    def clone(self) -> dict[str, Any]:
        sqlite_backup(self.args.host_database, self.host_database)
        sqlite_backup(self.args.platform_database, self.platform_database)
        return {
            "host_database": str(self.host_database),
            "platform_database": str(self.platform_database),
            "source_databases_unchanged": True,
        }

    def start_host(self, *, gateway_url: str | None = None) -> dict[str, Any]:
        value = powershell(
            ROOT / "scripts" / "windows" / "Start-Rc5HotValidationHost.ps1",
            EvidenceRoot=self.root / "host-process",
            GatewayKeyReference=self.args.gateway_key,
            Port=self.args.shadow_host_port,
            DatabasePath=self.host_database,
            OfflineRuntimeRoot=self.offline_root,
            GatewayBaseUrl=gateway_url or self.args.ai_url,
        )
        self.host_running = True
        return value

    def stop_host(self) -> dict[str, Any]:
        value = powershell(
            ROOT / "scripts" / "windows" / "Stop-Rc5BackendShadowProcess.ps1",
            Port=self.args.shadow_host_port,
            Kind="host",
        )
        self.host_running = False
        return value

    def start_platform(self) -> dict[str, Any]:
        value = powershell(
            ROOT / "scripts" / "windows" / "Start-Rc5BackendShadowPlatform.ps1",
            AiCsRoot=self.args.ai_cs_root,
            DatabasePath=self.platform_database,
            EvidenceRoot=self.root / "platform-process",
            HostControlUrl=f"https://127.0.0.1:{self.args.shadow_host_port}",
            Port=self.args.shadow_platform_port,
        )
        self.platform_running = True
        return value

    def stop_platform(self) -> dict[str, Any]:
        value = powershell(
            ROOT / "scripts" / "windows" / "Stop-Rc5BackendShadowProcess.ps1",
            Port=self.args.shadow_platform_port,
            Kind="platform",
        )
        self.platform_running = False
        return value

    def cleanup(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        if self.platform_running:
            results["platform"] = self.stop_platform()
        if self.host_running:
            results["host"] = self.stop_host()
        results["ports_released"] = not any(
            _port_listening(port)
            for port in (self.args.shadow_host_port, self.args.shadow_platform_port)
        )
        return results


def _port_listening(port: int) -> bool:
    with httpx.Client(timeout=0.25, trust_env=False, verify=False) as client:
        for scheme in ("http", "https"):
            try:
                client.get(f"{scheme}://127.0.0.1:{port}/health")
                return True
            except httpx.HTTPError:
                pass
    return False


PRODUCTS = {
    "PDD-SM": {
        "product_id": "PDD-SM-P0002",
        "product_name": "离线验收玩具商品",
        "sku_reference": "PDD-SM-P0002-SKU-Q65",
        "sku_name": "巨型军舰礼袋基础款",
        "attributes": {"适用年龄": "5岁以上", "材质": "ABS"},
    },
    "c-store-6639df2982014226": {
        "product_id": "C-PRODUCT-0ff808af95ce419db9be49427f1c4813",
        "product_name": "离线验收商品",
        "attributes": {},
    },
}
STORE_NUMERIC = {"PDD-SM": 1, "c-store-6639df2982014226": 2}
STORE_CATALOG_SCOPE = {
    "PDD-SM": ("TENANT-PDD-SM-TEST", "pinduoduo"),
    "c-store-6639df2982014226": (
        "c-tenant-6639df2982014226be2f5164ba642a72",
        "pinduoduo",
    ),
}


def make_observation(
    case: str,
    store_id: str,
    conversation_id: str,
    *,
    sequence: int = 1,
    external_message_id: str | None = None,
    question: str = "请介绍一下这个商品适合的年龄和使用注意事项。",
    order: dict[str, object] | None = None,
) -> NormalizedChannelObservation:
    return NormalizedChannelObservation.synthetic(
        provider_id=f"rc5-{case}",
        store_id=store_id,
        store_name=f"RC5-{store_id}",
        catalog_tenant_id=STORE_CATALOG_SCOPE[store_id][0],
        catalog_platform=STORE_CATALOG_SCOPE[store_id][1],
        conversation_id=conversation_id,
        external_message_id=external_message_id or f"{case}-{conversation_id}-{sequence}",
        source_sequence=sequence,
        content=question,
        timestamp=utc_now() + timedelta(milliseconds=sequence),
        product=PRODUCTS[store_id],
        order=order or {},
    )


def edge_from_submission(submission: Any) -> EdgeObservation:
    return EdgeObservation(
        observation_id=submission.observation_id,
        agent_id=submission.agent_id,
        device_id=submission.device_id,
        store_id=submission.store_id,
        platform_store_id=submission.payload.get("platform_store_id") or None,
        conversation_id=submission.conversation_id,
        external_message_id=submission.external_message_id,
        source_cursor=submission.source_cursor,
        source_sequence=submission.source_sequence,
        payload=submission.payload,
        captured_at=submission.captured_at,
        expires_at=submission.captured_at + timedelta(minutes=30),
    )


def wait_snapshot(
    client: ChannelEngineClient,
    store_id: str,
    conversation_id: str,
    *,
    statuses: set[str] | None = None,
    timeout: float = 150,
) -> Any:
    deadline = time.monotonic() + timeout
    last = None
    last_connection_error: str | None = None
    while time.monotonic() < deadline:
        try:
            last = client.fetch_assistant_snapshot(
                store_id=store_id, conversation_id=conversation_id
            ).snapshot
            last_connection_error = None
        except AgentConnectionError as exc:
            # AI generation can temporarily occupy a single-worker validation
            # Host longer than the HTTP read timeout.  Snapshot polling is an
            # eventually-consistent read, so retry inside the overall deadline;
            # ingestion/ACK and execution calls still fail closed immediately.
            last_connection_error = str(exc)
            time.sleep(0.5)
            continue
        if last is not None and (statuses is None or last.status in statuses):
            return last
        time.sleep(0.5)
    raise RuntimeError(
        "assistant snapshot timed out; "
        f"last={last}, last_connection_error={last_connection_error}"
    )


def activate_store(config: ChannelAgentConfig, store_id: str) -> dict[str, Any]:
    client = ChannelEngineClient(config)
    try:
        client.fetch_config()
        identity = client.identity
        if identity is None:
            raise RuntimeError("Host did not return the Agent identity")
        before = identity.effective_active_store_id
        if before != store_id:
            identity = client.select_active_store(
                store_id,
                store_id,
                reason="RC5_BACKEND_BLACKBOX_SHADOW_SCOPE",
            )
        if identity.effective_active_store_id != store_id:
            raise RuntimeError("Host did not activate the requested shadow Store")
        return {
            "before": before,
            "after": identity.effective_active_store_id,
            "authorized_store_ids": identity.effective_store_ids,
        }
    finally:
        client.close()


def inject_case(
    config: ChannelAgentConfig,
    evidence_root: Path,
    case: str,
    store_id: str,
    *,
    question: str,
    replay: bool = False,
    rows: int = 1,
    expected_statuses: set[str] | None = None,
) -> dict[str, Any]:
    conversation_id = f"rc5-{case}-{uuid.uuid4().hex[:12]}"
    observations = tuple(
        make_observation(
            case,
            store_id,
            conversation_id,
            sequence=index,
            question=(question if index == 1 else "另外请补充说明使用时的注意事项。"),
            order=(
                {
                    "order_reference": "PDD-REPLAY-ORDER-0001",
                    "order_status": "SHIPPED",
                    "logistics_status": "NO_UPDATE_48H",
                    "aftersales_status": "NONE",
                }
                if replay
                else None
            ),
        )
        for index in range(1, rows + 1)
    )
    case_root = evidence_root / "case-data" / case
    case_root.mkdir(parents=True, exist_ok=True)
    if replay:
        fixture = case_root / "recorded-pdd-shaped-input.json"
        write_json(
            fixture,
            {
                "schema_version": "rc5-recorded-provider-replay.v1",
                "sanitized": True,
                "observations": [item.model_dump(mode="json") for item in observations],
            },
        )
        provider: Any = RecordedReplayProvider(fixture, provider_id="recorded-pdd-v1")
    else:
        fixture = None
        provider = SyntheticPDDProvider(observations, provider_id=f"rc5-{case}")
    client = ChannelEngineClient(config)
    spool = DurableEdgeSpool(
        case_root / "edge-spool.sqlite3", WindowsDPAPITransientPayloadProtector()
    )
    forwarder = PersistAckObservationForwarder(client, spool)
    acknowledgements: list[Any] = []
    local_trace_ids: list[str] = []

    def submit(submission: Any) -> object:
        ack = forwarder(edge_from_submission(submission))
        acknowledgements.append(ack)
        return ack

    ingress = ChannelAgentProviderIngress(
        provider,
        agent_id=config.agent_id,
        device_id=config.device_id,
        submit=submit,
        provider_read_trace=local_trace_ids.append,
    )
    submitted = ingress.scan_once(limit=100)
    snapshot = wait_snapshot(
        client,
        store_id,
        conversation_id,
        statuses=expected_statuses or {"WAITING_APPROVAL", "MANUAL_INTERVENTION", "EXECUTION_PREPARED"},
    )
    trace = client.fetch_assistant_trace(snapshot.trace_id) if snapshot.trace_id else None
    host_stages = {step.stage for step in trace.steps} if trace else set()
    required_host_stages = {
        "HOST_PERSIST",
        "BUFFERING",
        "CUSTOMER_CONTEXT",
        "AI_GENERATING",
        "QUALITY_GATE",
    }
    if not required_host_stages.issubset(host_stages):
        raise RuntimeError(f"pipeline trace is incomplete: {sorted(host_stages)}")
    if spool.pending():
        raise RuntimeError("edge spool still has unacknowledged observations")
    result = {
        "case": case,
        "provider": type(provider).__name__,
        "fixture": str(fixture) if fixture else None,
        "store_id": store_id,
        "conversation_id": conversation_id,
        "submitted": submitted,
        "provider_trace_ids": local_trace_ids,
        "acknowledgements": acknowledgements,
        "edge_spool_pending": 0,
        "snapshot": snapshot,
        "trace": trace,
    }
    client.close()
    return result


def approve_case(
    config: ChannelAgentConfig,
    platform: PlatformClient,
    injected: dict[str, Any],
) -> dict[str, Any]:
    snapshot = injected["snapshot"]
    if snapshot.status != "WAITING_APPROVAL" or snapshot.quality_status != "PASS":
        raise RuntimeError(f"case is not eligible for human approval: {snapshot.status}")
    preparation = platform.prepare(snapshot, STORE_NUMERIC[snapshot.store_id])
    client = ChannelEngineClient(config)
    try:
        after = wait_snapshot(
            client,
            snapshot.store_id,
            snapshot.conversation_id,
            statuses={"EXECUTION_PREPARED"},
            timeout=30,
        )
    finally:
        client.close()
    if preparation.get("authorization_kind") != "HUMAN":
        raise RuntimeError("manual preparation did not record HUMAN authorization")
    if preparation.get("state") != "READY":
        raise RuntimeError("manual preparation is not READY")
    if preparation.get("real_send_enabled") is not False:
        raise RuntimeError("manual preparation unexpectedly enabled real send")
    if after.safety.send_count or after.safety.receipt_count or after.safety.execution_count:
        raise RuntimeError("manual preparation created a send, receipt, or execution")
    return {
        "decision_id": snapshot.decision_id,
        "transition": [snapshot.status, "HUMAN_APPROVAL", after.status],
        "platform_preparation": preparation,
        "host_snapshot_after": after,
    }


def duplicate_and_conflict_case(
    config: ChannelAgentConfig, evidence_root: Path, store_id: str
) -> dict[str, Any]:
    conversation_id = f"rc5-dedup-{uuid.uuid4().hex[:12]}"
    observation = make_observation("dedup", store_id, conversation_id)
    submission_holder: list[Any] = []
    provider = SyntheticPDDProvider((observation,), provider_id="rc5-dedup")
    client = ChannelEngineClient(config)
    spool = DurableEdgeSpool(
        evidence_root / "case-data" / "dedup" / "edge-spool.sqlite3",
        WindowsDPAPITransientPayloadProtector(),
    )
    forwarder = PersistAckObservationForwarder(client, spool)

    def submit(submission: Any) -> object:
        submission_holder.append(submission)
        return forwarder(edge_from_submission(submission))

    ChannelAgentProviderIngress(
        provider,
        agent_id=config.agent_id,
        device_id=config.device_id,
        submit=submit,
    ).scan_once()
    first = wait_snapshot(client, store_id, conversation_id)
    same_ack = forwarder(edge_from_submission(submission_holder[0]))
    second = wait_snapshot(client, store_id, conversation_id)
    if first.revision != second.revision or first.decision_id != second.decision_id:
        raise RuntimeError("exact duplicate changed the assistant decision")

    conflicting = edge_from_submission(submission_holder[0]).model_copy(
        update={"payload": {**submission_holder[0].payload, "content": "冲突内容"}}
    )
    conflict_kind = None
    try:
        spool.persist(conflicting)
    except EdgeSpoolConflict:
        conflict_kind = "EDGE_SPOOL_CONFLICT"
    if conflict_kind is None:
        raise RuntimeError("same observation id with changed content was not rejected")
    client.close()
    return {
        "duplicate_ack": same_ack,
        "revision_before": first.revision,
        "revision_after": second.revision,
        "decision_unchanged": True,
        "conflict_result": conflict_kind,
    }


def host_outage_recovery_case(
    topology: ShadowTopology,
    config: ChannelAgentConfig,
    evidence_root: Path,
) -> dict[str, Any]:
    topology.stop_host()
    store_id = "PDD-SM"
    conversation_id = f"rc5-host-outage-{uuid.uuid4().hex[:12]}"
    observation = make_observation("host-outage", store_id, conversation_id)
    payload = observation.pdd_payload()
    edge = EdgeObservation(
        observation_id=provider_observation_id(observation),
        agent_id=config.agent_id,
        device_id=config.device_id,
        store_id=store_id,
        platform_store_id=observation.platform_store_id,
        conversation_id=conversation_id,
        external_message_id=observation.external_message_id,
        source_cursor=observation.source_cursor,
        source_sequence=observation.source_sequence,
        payload=payload,
        captured_at=observation.captured_at,
        expires_at=observation.captured_at + timedelta(minutes=30),
    )
    spool = DurableEdgeSpool(
        evidence_root / "case-data" / "host-outage" / "edge-spool.sqlite3",
        WindowsDPAPITransientPayloadProtector(),
    )
    spool.persist(edge)
    failed_closed = False
    client = ChannelEngineClient(config)
    try:
        PersistAckObservationForwarder(client, spool).recover_pending()
    except AgentConnectionError:
        failed_closed = True
    client.close()
    if not failed_closed or len(spool.pending()) != 1:
        raise RuntimeError("Host outage did not retain one pending encrypted observation")
    topology.start_host()
    recovered_client = ChannelEngineClient(config)
    recovered = PersistAckObservationForwarder(recovered_client, spool).recover_pending()
    snapshot = wait_snapshot(recovered_client, store_id, conversation_id)
    recovered_client.close()
    if recovered != 1 or spool.pending():
        raise RuntimeError("pending observation was not recovered exactly once")
    return {
        "failed_closed": True,
        "pending_during_outage": 1,
        "recovered_count": recovered,
        "pending_after_recovery": 0,
        "snapshot": snapshot,
    }


def restart_persistence_case(
    topology: ShadowTopology,
    config: ChannelAgentConfig,
    evidence_root: Path,
) -> dict[str, Any]:
    injected = inject_case(
        config,
        evidence_root,
        "host-restart-persistence",
        "PDD-SM",
        question="这个商品适合多大的孩子？",
    )
    before = injected["snapshot"]
    topology.stop_host()
    topology.start_host()
    client = ChannelEngineClient(config)
    after = wait_snapshot(client, before.store_id, before.conversation_id, timeout=30)
    client.close()
    if after.decision_id != before.decision_id or after.revision != before.revision:
        raise RuntimeError("Host restart did not preserve the assistant snapshot")
    return {"before": before, "after": after, "preserved": True}


def ai_gateway_failure_recovery_case(
    topology: ShadowTopology,
    config: ChannelAgentConfig,
    evidence_root: Path,
) -> dict[str, Any]:
    topology.stop_host()
    topology.start_host(gateway_url="http://127.0.0.1:9")
    store_id = "PDD-SM"
    conversation_id = f"rc5-ai-outage-{uuid.uuid4().hex[:12]}"
    observation = make_observation("ai-outage", store_id, conversation_id)
    client: ChannelEngineClient | None = None
    failed_trace = None
    try:
        client = ChannelEngineClient(config)
        spool = DurableEdgeSpool(
            evidence_root / "case-data" / "ai-outage" / "edge-spool.sqlite3",
            WindowsDPAPITransientPayloadProtector(),
        )
        forwarder = PersistAckObservationForwarder(client, spool)
        edge = EdgeObservation(
            observation_id=provider_observation_id(observation),
            agent_id=config.agent_id,
            device_id=config.device_id,
            store_id=store_id,
            platform_store_id=observation.platform_store_id,
            conversation_id=conversation_id,
            external_message_id=observation.external_message_id,
            source_cursor=observation.source_cursor,
            source_sequence=observation.source_sequence,
            payload=observation.pdd_payload(),
            captured_at=observation.captured_at,
            expires_at=observation.captured_at + timedelta(minutes=30),
        )
        acknowledgement = forwarder(edge)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                trace = client.fetch_assistant_trace(observation.trace_id)
            except AgentRejectedError as exc:
                if exc.status_code == 404:
                    time.sleep(0.25)
                    continue
                raise
            failed = next(
                (
                    step
                    for step in trace.steps
                    if step.stage == "AI_GENERATING" and step.state == "FAILED"
                ),
                None,
            )
            if failed is not None:
                failed_trace = trace
                break
            time.sleep(0.25)
        if failed_trace is None:
            raise RuntimeError("AI gateway outage did not produce a failed pipeline trace")
        failed_reason = next(
            step.reason_code
            for step in failed_trace.steps
            if step.stage == "AI_GENERATING" and step.state == "FAILED"
        )
        if "GATEWAY" not in failed_reason:
            raise RuntimeError(f"AI failure reason is not gateway-specific: {failed_reason}")
    finally:
        if client is not None:
            client.close()
        if topology.host_running:
            topology.stop_host()
        topology.start_host()

    recovered = inject_case(
        config,
        evidence_root,
        "ai-recovered",
        store_id,
        question="这个商品是什么材质？",
    )
    recovered_ai_step = next(
        (
            step
            for step in recovered["trace"].steps
            if step.stage == "AI_GENERATING"
        ),
        None,
    )
    if recovered_ai_step is None or recovered_ai_step.state != "SUCCEEDED":
        raise RuntimeError("AI gateway did not recover to AI_GENERATING=SUCCEEDED")
    return {
        "failed_trace": failed_trace,
        "failure_created_decision": False,
        "recovered_snapshot": recovered["snapshot"],
        "recovered_ai_step": recovered_ai_step,
    }


def auth_negative_cases(
    platform_url: str,
    platform: PlatformClient,
    config: ChannelAgentConfig,
    reference_snapshot: Any,
) -> dict[str, Any]:
    anonymous = PlatformClient(platform_url)
    no_token = anonymous.request("GET", "/api/v1/auth/me", expected=401)
    anonymous.close()
    false_confirmation = platform.request(
        "POST",
        f"/api/v1/workspace/decisions/{reference_snapshot.decision_id}/execution-preparations",
        payload={
            "store_id": STORE_NUMERIC[reference_snapshot.store_id],
            "conversation_id": reference_snapshot.conversation_id,
            "customer_reference": reference_snapshot.customer_reference,
            "human_confirmed": False,
        },
        expected=422,
    )
    wrong_store = platform.request(
        "GET", "/api/v1/workspace/reply-policy?store_id=999999", expected=403
    )
    unsigned = httpx.get(
        config.server_url + "/channel-agent/v2/assistant-conversations",
        verify=str(config.server_ca_certificate_path),
        timeout=5,
        trust_env=False,
    )
    if unsigned.status_code not in (401, 403):
        raise RuntimeError(f"unsigned Host request returned {unsigned.status_code}")
    return {
        "platform_missing_token": no_token,
        "human_confirmed_false": false_confirmation,
        "store_outside_scope": wrong_store,
        "unsigned_host_status": unsigned.status_code,
    }


def receipt_counts(host_db: Path, offline_root: Path) -> dict[str, int]:
    return {
        "core_executions": sqlite_count(host_db, "executions"),
        "core_execution_receipts": sqlite_count(host_db, "execution_receipts"),
        "agent_receipts": sqlite_count(host_db, "channel_agent_receipts"),
        "real_transport_receipts": sqlite_count(host_db, "pdd_send_transport_receipts"),
        "synthetic_offline_receipts": sqlite_count(
            offline_root / "offline-control.sqlite3", "offline_receipts"
        ),
        "execution_preparations": sqlite_count(
            offline_root / "offline-control.sqlite3", "execution_preparations"
        ),
    }


def secret_scan(root: Path) -> dict[str, Any]:
    forbidden = (b"acs_v1_", b"BEGIN PRIVATE KEY", b"BEGIN ENCRYPTED PRIVATE KEY")
    matches: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".sqlite3", ".db", ".pyc"}:
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if any(marker in raw for marker in forbidden):
            matches.append(str(path.relative_to(root)))
    return {"passed": not matches, "matches": matches, "patterns": 3}


def checked(value: Any, predicate: Callable[[Any], bool], message: str) -> Any:
    if not predicate(value):
        raise RuntimeError(message)
    return value


def render_reports(suite: Suite, metadata: dict[str, Any], cleanup: dict[str, Any]) -> dict[str, Path]:
    required = [item for item in suite.scenarios if item.required]
    passed = sum(item.passed for item in required)
    outcome = "PASS" if passed == len(required) else "FAIL"
    report = {
        "schema_version": "rc5-backend-blackbox-report.v1",
        "outcome": outcome,
        "generated_at": utc_now(),
        "summary": {
            "required_passed": passed,
            "required_total": len(required),
            "optional_passed": sum(item.passed for item in suite.scenarios if not item.required),
            "optional_total": sum(not item.required for item in suite.scenarios),
        },
        "metadata": metadata,
        "scenarios": [item.__dict__ for item in suite.scenarios],
        "cleanup": cleanup,
    }
    json_path = suite.evidence_root / "backend-blackbox-report.json"
    write_json(json_path, report)

    lines = [
        "# RC5 后端黑盒全链验收报告",
        "",
        f"结论：**{outcome}**（必测 {passed}/{len(required)} 通过）",
        "",
        "| 场景 | 必须 | 结果 |",
        "|---|---:|---:|",
    ]
    for item in suite.scenarios:
        lines.append(
            f"| {item.name} | {'是' if item.required else '否'} | {'PASS' if item.passed else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "安全边界：未启动 PDD 页面、未读取真实 PDD、未调用真实发送；所有批准只到 EXECUTION_PREPARED。",
            "",
            "详细证据见 `backend-blackbox-report.json` 与 `scenarios/`。",
        ]
    )
    md_path = suite.evidence_root / "backend-blackbox-report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    testsuite = ET.Element(
        "testsuite",
        name="rc5-backend-blackbox",
        tests=str(len(suite.scenarios)),
        failures=str(sum(not item.passed for item in suite.scenarios)),
    )
    for item in suite.scenarios:
        case = ET.SubElement(testsuite, "testcase", name=item.name)
        if not item.passed:
            failure = ET.SubElement(case, "failure", type=item.error["type"])
            failure.text = item.error["message"]
    junit_path = suite.evidence_root / "backend-blackbox-junit.xml"
    ET.ElementTree(testsuite).write(junit_path, encoding="utf-8", xml_declaration=True)
    return {"json": json_path, "markdown": md_path, "junit": junit_path}


def _health(url: str, *, verify: bool | str = True) -> dict[str, Any]:
    response = httpx.get(url, timeout=10, verify=verify, trust_env=False)
    return {"status_code": response.status_code, "body": response.json()}


def run(args: argparse.Namespace) -> int:
    evidence_root = args.evidence_root.resolve()
    evidence_root.mkdir(parents=True, exist_ok=False)
    suite = Suite(evidence_root)
    config = load_agent_config(args.config)
    shadow_config = config.model_copy(
        update={"server_url": f"https://127.0.0.1:{args.shadow_host_port}"}
    )
    topology = ShadowTopology(args, evidence_root)
    cleanup: dict[str, Any] = {}
    metadata: dict[str, Any] = {
        "started_at": utc_now(),
        "scope": "BACKEND_ONLY_NO_PDD_NO_REAL_SEND",
        "versions": {
            "agent": AGENT_VERSION,
            "host": HOST_VERSION,
            "engine_git": git_snapshot(ROOT),
            "ai_cs_git": git_snapshot(args.ai_cs_root),
            "installed_agent_manifest_sha256": sha256_file(
                args.installed_agent_root / "release-manifest.json"
            ),
            "installed_agent_pyz_sha256": sha256_file(
                args.installed_agent_root / "app" / "channel-agent.pyz"
            ),
        },
        "ports": {
            "current_host": args.current_host_port,
            "ai": args.ai_port,
            "current_platform": args.current_platform_port,
            "shadow_host": args.shadow_host_port,
            "shadow_platform": args.shadow_platform_port,
        },
    }

    suite.run(
        "version-and-safety-preflight",
        lambda: {
            "host": _health(
                f"https://127.0.0.1:{args.current_host_port}/health",
                verify=str(config.server_ca_certificate_path),
            ),
            "ai_cs": _health(args.ai_url + "/api/health"),
            "platform": _health(args.platform_url + "/health"),
            "agent_runtime_mode": config.runtime_mode,
            "development_profile": config.development_profile,
            "browser_enabled": config.browser_enabled,
            "pdd_login_url": config.pdd_login_url,
            "pdd_customer_service_url": config.pdd_customer_service_url,
            "real_send_enabled": False,
        },
    )

    current_lease: TemporaryPlatformSessionLease | None = None
    current_platform: PlatformClient | None = None
    try:
        current_lease = TemporaryPlatformSessionLease(args.platform_database, args.user_id)
        current_lease.__enter__()
        current_platform = PlatformClient(args.platform_url, current_lease.authorization)
        suite.run("current-platform-session", current_platform.me)
        current_policy = suite.run(
            "current-policy-is-manual",
            lambda: checked(
                current_platform.policy(STORE_NUMERIC["c-store-6639df2982014226"]),
                lambda item: item.get("mode") == "MANUAL_CONFIRM",
                "current Store policy must remain MANUAL_CONFIRM",
            ),
        )

        current_synthetic = suite.run(
            "current-synthetic-provider-to-quality-gate",
            lambda: inject_case(
                config,
                evidence_root,
                "current-synthetic",
                "c-store-6639df2982014226",
                question="请介绍一下这个商品的适用人群和注意事项。",
                rows=2,
            ),
        )
        current_ready = None
        if current_synthetic:
            current_ready = suite.run(
                "current-active-store-knowledge-and-quality-readiness",
                lambda: checked(
                    current_synthetic,
                    lambda item: (
                        item["snapshot"].status == "WAITING_APPROVAL"
                        and item["snapshot"].quality_status == "PASS"
                    ),
                    "current active Store is not publish/quality ready",
                ),
            )
        if current_ready:
            suite.run(
                "current-manual-confirm-to-execution-prepared",
                lambda: approve_case(config, current_platform, current_ready),
            )

        current_replay = suite.run(
            "current-recorded-pdd-replay-to-quality-gate",
            lambda: inject_case(
                config,
                evidence_root,
                "current-replay",
                "c-store-6639df2982014226",
                question="这个订单里的商品是什么材质？请说明依据。",
                replay=True,
            ),
        )
        if current_replay and current_replay["snapshot"].status == "WAITING_APPROVAL":
            suite.run(
                "current-replay-manual-confirm-to-execution-prepared",
                lambda: approve_case(config, current_platform, current_replay),
            )
    finally:
        if current_platform:
            current_platform.close()
        if current_lease:
            current_lease.__exit__(None, None, None)
            cleanup["current_session"] = current_lease.public_facts()

    suite.run("shadow-database-clone", topology.clone)
    suite.run("shadow-host-start", topology.start_host)
    suite.run("shadow-platform-start", topology.start_platform)

    shadow_lease: TemporaryPlatformSessionLease | None = None
    shadow_platform: PlatformClient | None = None
    original_shadow_policy: dict[str, Any] | None = None
    counts_before = receipt_counts(topology.host_database, topology.offline_root)
    try:
        shadow_lease = TemporaryPlatformSessionLease(topology.platform_database, args.user_id)
        shadow_lease.__enter__()
        shadow_platform = PlatformClient(args.shadow_platform_url, shadow_lease.authorization)
        suite.run("shadow-platform-session", shadow_platform.me)
        original_shadow_policy = suite.run(
            "shadow-policy-baseline",
            lambda: shadow_platform.policy(STORE_NUMERIC["PDD-SM"]),
        )
        suite.run(
            "shadow-activate-pdd-store",
            lambda: activate_store(shadow_config, "PDD-SM"),
        )

        manual_case = suite.run(
            "shadow-manual-full-chain",
            lambda: checked(
                inject_case(
                    shadow_config,
                    evidence_root,
                    "shadow-manual",
                    "PDD-SM",
                    question="这个商品适合多大的孩子使用？",
                ),
                lambda item: (
                    item["snapshot"].status == "WAITING_APPROVAL"
                    and item["snapshot"].quality_status == "PASS"
                ),
                "manual chain stopped before WAITING_APPROVAL",
            ),
        )
        if manual_case:
            suite.run(
                "negative-auth-and-confirmation-gates",
                lambda: auth_negative_cases(
                    args.shadow_platform_url,
                    shadow_platform,
                    shadow_config,
                    manual_case["snapshot"],
                ),
            )
            suite.run(
                "shadow-manual-approval-state-transition",
                lambda: approve_case(shadow_config, shadow_platform, manual_case),
            )

        shadow_replay = suite.run(
            "shadow-recorded-pdd-replay-full-chain",
            lambda: checked(
                inject_case(
                    shadow_config,
                    evidence_root,
                    "shadow-recorded-replay",
                    "PDD-SM",
                    question="这个订单里的大军舰拼好有多长？",
                    replay=True,
                ),
                lambda item: (
                    item["snapshot"].status == "WAITING_APPROVAL"
                    and item["snapshot"].quality_status == "PASS"
                ),
                "recorded replay stopped before WAITING_APPROVAL",
            ),
        )
        if shadow_replay:
            suite.run(
                "shadow-replay-manual-approval-state-transition",
                lambda: approve_case(shadow_config, shadow_platform, shadow_replay),
            )

        suite.run(
            "cursor-dedup-and-conflict-protection",
            lambda: duplicate_and_conflict_case(shadow_config, evidence_root, "PDD-SM"),
        )

        blocked = suite.run(
            "quality-gate-blocks-high-risk-request",
            lambda: checked(
                inject_case(
                    shadow_config,
                    evidence_root,
                    "quality-blocked",
                    "PDD-SM",
                    question="收到的商品缺少零件，马上给我退款并赔偿，否则我就投诉。",
                    expected_statuses={"MANUAL_INTERVENTION"},
                ),
                lambda item: item["snapshot"].quality_status == "BLOCKED",
                "high-risk request did not produce BLOCKED quality status",
            ),
        )

        policy = shadow_platform.policy(STORE_NUMERIC["PDD-SM"])
        auto_policy = suite.run(
            "switch-policy-manual-to-auto-low-risk",
            lambda: shadow_platform.set_policy(
                STORE_NUMERIC["PDD-SM"], "AUTO_LOW_RISK", int(policy["revision"])
            ),
        )
        if auto_policy:
            auto_case = suite.run(
                "auto-low-risk-to-execution-prepared",
                lambda: checked(
                    inject_case(
                        shadow_config,
                        evidence_root,
                        "auto-low-risk",
                        "PDD-SM",
                        question="Q65和Q66有什么区别？",
                ),
                    lambda item: (
                        item["snapshot"].safety.execution_prepared
                        and item["snapshot"].safety.auto_reply
                    ),
                    "AUTO_LOW_RISK did not create a safe prepared decision",
                ),
            )
            restored = suite.run(
                "restore-policy-to-manual-confirm",
                lambda: checked(
                    shadow_platform.set_policy(
                        STORE_NUMERIC["PDD-SM"],
                        "MANUAL_CONFIRM",
                        int(auto_policy["revision"]),
                    ),
                    lambda item: item.get("mode") == "MANUAL_CONFIRM",
                    "reply policy restore failed",
                ),
            )

        multi_a = suite.run(
            "multi-store-isolation-store-a",
            lambda: inject_case(
                shadow_config,
                evidence_root,
                "isolation-pdd",
                "PDD-SM",
                question="请说明商品材质。",
            ),
        )
        suite.run(
            "shadow-switch-active-store-for-isolation",
            lambda: activate_store(shadow_config, "c-store-6639df2982014226"),
        )
        multi_b = suite.run(
            "multi-store-isolation-store-b",
            lambda: inject_case(
                shadow_config,
                evidence_root,
                "isolation-c-store",
                "c-store-6639df2982014226",
                question="请说明这个商品的基本信息。",
            ),
        )
        suite.run(
            "multi-store-no-cross-talk",
            lambda: checked(
                {
                    "store_a": multi_a["snapshot"].store_id,
                    "store_b": multi_b["snapshot"].store_id,
                    "conversation_ids_distinct": (
                        multi_a["snapshot"].conversation_id
                        != multi_b["snapshot"].conversation_id
                    ),
                    "customer_references_distinct": (
                        multi_a["snapshot"].customer_reference
                        != multi_b["snapshot"].customer_reference
                    ),
                },
                lambda item: (
                    item["store_a"] != item["store_b"]
                    and item["conversation_ids_distinct"]
                    and item["customer_references_distinct"]
                ),
                "multi-Store isolation evidence is inconsistent",
            )
            if multi_a and multi_b
            else (_ for _ in ()).throw(RuntimeError("isolation prerequisites failed")),
        )
        suite.run(
            "shadow-restore-active-pdd-store",
            lambda: activate_store(shadow_config, "PDD-SM"),
        )

        suite.run(
            "host-restart-preserves-snapshot",
            lambda: restart_persistence_case(topology, shadow_config, evidence_root),
        )
        suite.run(
            "dpapi-spool-host-outage-and-recovery",
            lambda: host_outage_recovery_case(topology, shadow_config, evidence_root),
        )

        def platform_outage() -> dict[str, Any]:
            topology.stop_platform()
            try:
                failed = False
                try:
                    shadow_platform.policy(STORE_NUMERIC["PDD-SM"])
                except httpx.RequestError:
                    failed = True
                if not failed:
                    raise RuntimeError("platform outage did not fail closed")
            finally:
                topology.start_platform()
            recovered = shadow_platform.policy(STORE_NUMERIC["PDD-SM"])
            return {"failed_closed": True, "recovered_policy": recovered}

        suite.run("platform-outage-and-session-recovery", platform_outage)

        suite.run(
            "ai-gateway-failure-and-recovery",
            lambda: ai_gateway_failure_recovery_case(
                topology, shadow_config, evidence_root
            ),
        )
    finally:
        if shadow_platform and topology.platform_running:
            try:
                policy = shadow_platform.policy(STORE_NUMERIC["PDD-SM"])
                if policy.get("mode") != "MANUAL_CONFIRM":
                    shadow_platform.set_policy(
                        STORE_NUMERIC["PDD-SM"],
                        "MANUAL_CONFIRM",
                        int(policy["revision"]),
                    )
            except Exception as exc:
                cleanup["shadow_policy_restore_error"] = f"{type(exc).__name__}: {exc}"
        if shadow_platform:
            shadow_platform.close()
        if shadow_lease:
            shadow_lease.__exit__(None, None, None)
            cleanup["shadow_session"] = shadow_lease.public_facts()

    counts_after = receipt_counts(topology.host_database, topology.offline_root)
    suite.run(
        "synthetic-vs-real-receipt-and-send-isolation",
        lambda: {
            "before": counts_before,
            "after": counts_after,
            "real_execution_delta": counts_after["core_executions"] - counts_before["core_executions"],
            "real_receipt_delta": (
                counts_after["core_execution_receipts"]
                + counts_after["agent_receipts"]
                + counts_after["real_transport_receipts"]
                - counts_before["core_execution_receipts"]
                - counts_before["agent_receipts"]
                - counts_before["real_transport_receipts"]
            ),
            "expected": "only execution_preparations may increase",
        }
        if (
            counts_after["core_executions"] == counts_before["core_executions"]
            and counts_after["core_execution_receipts"] == counts_before["core_execution_receipts"]
            and counts_after["agent_receipts"] == counts_before["agent_receipts"]
            and counts_after["real_transport_receipts"] == counts_before["real_transport_receipts"]
            and counts_after["synthetic_offline_receipts"] == counts_before["synthetic_offline_receipts"]
        )
        else (_ for _ in ()).throw(RuntimeError("a send, execution, or receipt count changed")),
    )
    cleanup["shadow_topology"] = topology.cleanup()
    scan = suite.run("evidence-secret-scan", lambda: secret_scan(evidence_root))
    if scan and not scan["passed"]:
        suite.scenarios[-1].passed = False
        suite.scenarios[-1].error = {
            "type": "SecretScanFailed",
            "message": str(scan["matches"]),
        }
    cleanup["finished_at"] = utc_now()
    reports = render_reports(suite, metadata, cleanup)
    print(json.dumps({key: str(value) for key, value in reports.items()}, ensure_ascii=False))
    return 0 if all(item.passed for item in suite.scenarios if item.required) else 2


def parser() -> argparse.ArgumentParser:
    local = Path(os.environ["LOCALAPPDATA"])
    ai_cs_root = ROOT.parent / "AI-CS"
    value = argparse.ArgumentParser()
    value.add_argument(
        "--config",
        type=Path,
        default=local / "AI-CS" / "ChannelAgent" / "config" / "agent.json",
    )
    value.add_argument("--evidence-root", type=Path, required=True)
    value.add_argument("--ai-cs-root", type=Path, default=ai_cs_root)
    value.add_argument(
        "--host-database", type=Path, default=ROOT / ".runtime" / "channel-engine.sqlite3"
    )
    value.add_argument(
        "--platform-database",
        type=Path,
        default=ai_cs_root
        / ".runtime"
        / "r027-ux-acceptance-data-v1"
        / "runtime"
        / "platform.sqlite3",
    )
    value.add_argument(
        "--gateway-key",
        type=Path,
        default=ai_cs_root
        / ".runtime"
        / "r027-ux-acceptance-data-v1"
        / "runtime"
        / "managed"
        / "secrets"
        / "gateway-hmac-rc1.secret",
    )
    value.add_argument(
        "--installed-agent-root",
        type=Path,
        default=local / "Programs" / "AI-CS" / "ChannelAgent",
    )
    value.add_argument("--user-id", default="4d9757bc-7cf0-4ab1-ba1c-296501704799")
    value.add_argument("--current-host-port", type=int, default=18443)
    value.add_argument("--ai-port", type=int, default=8420)
    value.add_argument("--current-platform-port", type=int, default=8422)
    value.add_argument("--shadow-host-port", type=int, default=19443)
    value.add_argument("--shadow-platform-port", type=int, default=8522)
    value.add_argument("--ai-url", default="http://127.0.0.1:8420")
    value.add_argument("--platform-url", default="http://127.0.0.1:8422")
    value.add_argument("--shadow-platform-url", default="http://127.0.0.1:8522")
    return value


if __name__ == "__main__":
    raise SystemExit(run(parser().parse_args()))
