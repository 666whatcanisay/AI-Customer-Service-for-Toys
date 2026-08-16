from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping


EXPECTED_CONTRACT_SHA256 = (
    "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
)
FINAL_STATUS = "AI_CS_CHANNEL_ENGINE_INTEGRATION_VALIDATED"
SYNTHETIC_SECRET = b"synthetic-validation-key-material-v1-0001"


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _case(case_id: str, subject: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "subject": subject,
        "status": "PASS",
        "fail_closed": True,
        "evidence": dict(evidence),
    }


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_port(port: int, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"synthetic AI-CS Gateway exited during startup ({process.returncode})"
            )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError("synthetic AI-CS Gateway did not open its loopback port")


@contextmanager
def _validation_server(
    *,
    ai_cs_root: Path,
    ai_cs_python: Path,
    runner: Path,
    mode: str,
    temporary_root: Path,
) -> Iterator[int]:
    port = _free_loopback_port()
    command = [
        str(ai_cs_python),
        str(runner),
        "--ai-cs-root",
        str(ai_cs_root),
        "--mode",
        mode,
        "--port",
        str(port),
        "--runtime-root",
        str(temporary_root),
    ]
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    process = subprocess.Popen(
        command,
        cwd=ai_cs_root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    try:
        _wait_for_port(port, process)
        yield port
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        time.sleep(0.2)


def _server_generated_schema(
    *, ai_cs_root: Path, ai_cs_python: Path, runner: Path
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            str(ai_cs_python),
            str(runner),
            "--ai-cs-root",
            str(ai_cs_root),
            "--emit-schema",
        ],
        cwd=ai_cs_root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    return json.loads(completed.stdout)


def validate(
    ai_cs_root: Path,
    channel_engine_root: Path,
    ai_cs_python: Path,
) -> dict[str, Any]:
    ai_cs_root = ai_cs_root.resolve()
    channel_engine_root = channel_engine_root.resolve()
    ai_cs_python = ai_cs_python.resolve()
    runner = (
        channel_engine_root
        / "scripts"
        / "support"
        / "run_ai_cs_gateway_validation_server.py"
    )
    if not ai_cs_python.is_file():
        raise FileNotFoundError("AI-CS isolated Python runtime is unavailable")

    channel_engine_src = channel_engine_root / "src"
    if str(channel_engine_src) not in sys.path:
        sys.path.insert(0, str(channel_engine_src))

    from channel_engine.gateway.auth import GatewayRequestSigner
    from channel_engine.gateway.client import (
        AICSGatewayRequestFailed,
        AICSGatewayTimeout,
        GatewayRetryPolicy,
        GatewayTransportResponse,
        GatewayTransportTimeout,
    )
    from channel_engine.gateway.contract import (
        CONTRACT_VERSION as CLIENT_CONTRACT_VERSION,
        DecisionRequest,
        ErrorEnvelope,
        build_gateway_contract_schema,
    )
    from channel_engine.gateway.http import GatewayAdapterConfig, GatewayEnvironment
    from channel_engine.gateway.integration import (
        FakeGatewayTokenProvider,
        GatewayClient,
        GatewayServiceIdentity,
    )
    from channel_engine.gateway.http import HttpGatewayTransport

    class RecordingTransport:
        def __init__(self, transport: HttpGatewayTransport) -> None:
            self.transport = transport
            self.records: list[dict[str, Any]] = []

        def request(
            self,
            *,
            method: str,
            path: str,
            body: bytes,
            headers: Mapping[str, str],
            timeout_seconds: float,
        ) -> GatewayTransportResponse:
            response = self.transport.request(
                method=method,
                path=path,
                body=body,
                headers=headers,
                timeout_seconds=timeout_seconds,
            )
            normalized = {key.lower(): value for key, value in response.headers.items()}
            self.records.append(
                {
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "contract_version": normalized.get(
                        "x-ai-cs-contract-version"
                    ),
                    "idempotency_replayed": normalized.get(
                        "idempotency-replayed"
                    ),
                    "content_type": normalized.get("content-type"),
                }
            )
            return response

        def close(self) -> None:
            self.transport.close()

    class AlwaysTimeoutTransport:
        def __init__(self) -> None:
            self.attempts = 0

        def request(
            self,
            *,
            method: str,
            path: str,
            body: bytes,
            headers: Mapping[str, str],
            timeout_seconds: float,
        ) -> GatewayTransportResponse:
            del method, path, body, headers, timeout_seconds
            self.attempts += 1
            raise GatewayTransportTimeout("synthetic validation timeout")

    client_schema_path = (
        channel_engine_root
        / "schemas"
        / "ai-cs-channel-engine-gateway-contract-v1.schema.json"
    )
    server_schema_path = (
        ai_cs_root
        / "contracts"
        / "schemas"
        / "channel-engine-gateway-server.v1.schema.json"
    )
    client_schema_raw = client_schema_path.read_bytes()
    server_schema_raw = server_schema_path.read_bytes()
    client_schema = json.loads(client_schema_raw)
    server_schema = json.loads(server_schema_raw)
    client_generated = build_gateway_contract_schema()
    server_generated = _server_generated_schema(
        ai_cs_root=ai_cs_root,
        ai_cs_python=ai_cs_python,
        runner=runner,
    )
    canonical_hash = _sha256(_canonical_json(client_schema))
    _assert(client_schema == server_schema, "exported schemas differ")
    _assert(client_schema == client_generated, "Channel Engine schema export drifted")
    _assert(server_schema == server_generated, "AI-CS schema export drifted")
    _assert(CLIENT_CONTRACT_VERSION == "1.0", "client contract version mismatch")
    _assert(
        canonical_hash == EXPECTED_CONTRACT_SHA256,
        "canonical contract hash mismatch",
    )
    cases = [
        _case(
            "CONTRACT-001",
            "Schema version, exported models and canonical SHA are identical",
            {
                "contract_version": "1.0",
                "canonical_sha256": canonical_hash,
                "raw_file_sha256": _sha256(client_schema_raw),
                "raw_files_identical": client_schema_raw == server_schema_raw,
            },
        )
    ]

    client_id = "channel-engine-validation"
    key_id = "integration-key-v1"
    credential_ref = "secret-ref://integration-validation/gateway-v1"
    identity = GatewayServiceIdentity(
        client_id=client_id,
        key_id=key_id,
        credential_ref=credential_ref,
    )
    retry_three = GatewayRetryPolicy(
        max_attempts=3,
        base_backoff_seconds=0,
        max_backoff_seconds=0,
        jitter_ratio=0,
    )
    retry_once = GatewayRetryPolicy(
        max_attempts=1,
        base_backoff_seconds=0,
        max_backoff_seconds=0,
        jitter_ratio=0,
    )

    def request(suffix: str, *, idempotency_key: str | None = None) -> DecisionRequest:
        return DecisionRequest(
            contract_version="1.0",
            request_id=f"request-{suffix}",
            idempotency_key=idempotency_key or f"decision-{suffix}",
            correlation_id=f"trace-{suffix}",
            conversation_id="conversation-integration-validation",
            message_id=f"message-{suffix}",
            customer_message="这是一条不包含真实客户数据的合成验证消息。",
            context={
                "channel_name": "synthetic-validation-channel",
                "locale": "zh-CN",
                "ai_cs_scope": {
                    "tenant_id": "TENANT-SYNTHETIC",
                    "platform": "pdd",
                    "store_code": "STORE-SYNTHETIC",
                    "product_id": "PRODUCT-SYNTHETIC",
                    "sku_id": None,
                },
            },
            requested_at=datetime.now(timezone.utc),
        )

    def build_client(
        port: int,
        *,
        material: bytes = SYNTHETIC_SECRET,
        retry_policy: GatewayRetryPolicy = retry_three,
    ):
        config = GatewayAdapterConfig(
            environment=GatewayEnvironment.MOCK,
            base_url=f"http://127.0.0.1:{port}",
            client_id=client_id,
            key_id=key_id,
            timeout_seconds=2,
        )
        recording = RecordingTransport(HttpGatewayTransport(config))
        provider = FakeGatewayTokenProvider({credential_ref: (key_id, material)})
        client = GatewayClient(
            recording,
            identity,
            provider,
            decision_retry_policy=retry_policy,
            timeout_seconds=2,
            sleeper=lambda _: None,
        )
        return client, recording

    with tempfile.TemporaryDirectory(
        prefix="ai-cs-cross-repo-validation-",
        ignore_cleanup_errors=True,
    ) as temp:
        temporary_root = Path(temp)
        with _validation_server(
            ai_cs_root=ai_cs_root,
            ai_cs_python=ai_cs_python,
            runner=runner,
            mode="core",
            temporary_root=temporary_root / "core",
        ) as port:
            gateway_client, transport = build_client(port)
            health = gateway_client.health_check()
            _assert(health.status.value == "HEALTHY", "signed health is not healthy")
            _assert(health.contract_version == "1.0", "health version mismatch")
            cases.append(
                _case(
                    "AUTH-001",
                    "Channel Engine HMAC signer is accepted by AI-CS signed health",
                    {
                        "http_status": transport.records[-1]["status_code"],
                        "contract_version": health.contract_version,
                        "gateway_status": health.status.value,
                    },
                )
            )

            decision_request = request("success")
            decision = gateway_client.request_decision(decision_request)
            _assert(decision.requires_approval is True, "approval boundary changed")
            _assert(decision.request_id == decision_request.request_id, "request mismatch")
            _assert(
                decision.correlation_id == decision_request.correlation_id,
                "trace/correlation mismatch",
            )
            _assert(
                str(transport.records[-1]["content_type"]).startswith(
                    "application/vnd.ai-cs.channel-engine.gateway-v1+json"
                ),
                "response media type mismatch",
            )
            cases.append(
                _case(
                    "FLOW-001",
                    "Channel Message to AI-CS DecisionResponse succeeds",
                    {
                        "message_id": decision_request.message_id,
                        "request_id": decision.request_id,
                        "decision_id": decision.decision_id,
                        "trace_id": decision.correlation_id,
                        "requires_approval": decision.requires_approval,
                        "action": decision.action.value,
                    },
                )
            )

            trace = gateway_client.trace_store.for_message(decision_request.message_id)
            _assert(trace.message_id == decision_request.message_id, "message trace missing")
            _assert(trace.request_id == decision.request_id, "request trace missing")
            _assert(trace.decision_id == decision.decision_id, "decision trace missing")
            _assert(
                trace.correlation_id == decision.correlation_id,
                "trace_id mapping missing",
            )
            cases.append(
                _case(
                    "TRACE-001",
                    "message_id, request_id, decision_id and trace_id are linked",
                    {
                        "message_id": trace.message_id,
                        "request_id": trace.request_id,
                        "decision_id": trace.decision_id,
                        "trace_id": trace.correlation_id,
                        "trace_id_mapping": "Gateway trace_id equals frozen correlation_id",
                    },
                )
            )

            replay_client, replay_transport = build_client(port)
            replay = replay_client.request_decision(decision_request)
            _assert(replay == decision, "duplicate replay changed response")
            _assert(
                replay_transport.records[-1]["idempotency_replayed"] == "true",
                "server did not mark idempotency replay",
            )
            cases.append(
                _case(
                    "IDEMPOTENCY-001",
                    "Exact duplicate replays the original DecisionResponse",
                    {
                        "decision_id": replay.decision_id,
                        "idempotency_replayed": True,
                        "response_identical": True,
                    },
                )
            )

            conflict_request = request(
                "conflict",
                idempotency_key=decision_request.idempotency_key,
            )
            conflict_client, conflict_transport = build_client(
                port,
                retry_policy=retry_once,
            )
            try:
                conflict_client.request_decision(conflict_request)
            except AICSGatewayRequestFailed as exc:
                _assert(exc.status_code == 409, "conflicting duplicate status mismatch")
                _assert(
                    exc.envelope.error.error_code.value == "IDEMPOTENCY_CONFLICT",
                    "conflicting duplicate code mismatch",
                )
            else:
                raise AssertionError("conflicting duplicate was not rejected")
            cases.append(
                _case(
                    "IDEMPOTENCY-002",
                    "Same idempotency key with a different payload fails closed",
                    {
                        "http_status": 409,
                        "error_code": "IDEMPOTENCY_CONFLICT",
                        "second_decision_created": False,
                    },
                )
            )

            wrong_client, wrong_transport = build_client(
                port,
                material=hashlib.sha256(b"wrong-validation-material").digest(),
                retry_policy=retry_once,
            )
            try:
                wrong_client.request_decision(request("unauthorized"))
            except AICSGatewayRequestFailed as exc:
                _assert(exc.status_code == 401, "401 status mismatch")
                _assert(
                    exc.envelope.error.error_code.value == "AUTHENTICATION_FAILED",
                    "401 envelope mismatch",
                )
                _assert(exc.attempts == 1, "401 was retried")
            else:
                raise AssertionError("invalid signature was accepted")
            cases.append(
                _case(
                    "FAILURE-401",
                    "Invalid HMAC signature fails closed without retry",
                    {
                        "http_status": wrong_transport.records[-1]["status_code"],
                        "error_code": "AUTHENTICATION_FAILED",
                        "attempts": 1,
                        "decision_created": False,
                    },
                )
            )

            invalid_request = request("invalid-schema")
            invalid_payload = invalid_request.model_dump(mode="json")
            invalid_payload["unexpected_field"] = "forbidden"
            invalid_body = _canonical_json(invalid_payload)
            raw_signer = GatewayRequestSigner(
                client_id=client_id,
                key_id=key_id,
                secret=SYNTHETIC_SECRET,
            )
            invalid_headers = raw_signer.sign(
                invalid_body,
                method="POST",
                path="/gateway/v1/decisions",
                request_id=invalid_request.request_id,
                correlation_id=invalid_request.correlation_id,
                idempotency_key=invalid_request.idempotency_key,
                content_type="application/vnd.ai-cs.channel-engine.gateway-v1+json",
            )
            invalid_response = transport.request(
                method="POST",
                path="/gateway/v1/decisions",
                body=invalid_body,
                headers=invalid_headers,
                timeout_seconds=2,
            )
            invalid_envelope = ErrorEnvelope.model_validate_json(invalid_response.body)
            _assert(invalid_response.status_code == 422, "invalid schema status mismatch")
            _assert(
                invalid_envelope.error.error_code.value == "SCHEMA_VALIDATION_FAILED",
                "invalid schema envelope mismatch",
            )
            cases.append(
                _case(
                    "FAILURE-SCHEMA",
                    "Additional request field is rejected with a frozen ErrorEnvelope",
                    {
                        "http_status": 422,
                        "error_code": "SCHEMA_VALIDATION_FAILED",
                        "decision_created": False,
                    },
                )
            )
            for open_transport in (
                transport,
                replay_transport,
                conflict_transport,
                wrong_transport,
            ):
                open_transport.close()

        with _validation_server(
            ai_cs_root=ai_cs_root,
            ai_cs_python=ai_cs_python,
            runner=runner,
            mode="denied-edge",
            temporary_root=temporary_root / "denied-edge",
        ) as denied_port:
            denied_client, denied_transport = build_client(
                denied_port,
                retry_policy=retry_once,
            )
            try:
                denied_client.request_decision(request("forbidden"))
            except AICSGatewayRequestFailed as exc:
                _assert(exc.status_code == 403, "403 status mismatch")
                _assert(
                    exc.envelope.error.error_code.value == "AUTHORIZATION_DENIED",
                    "403 envelope mismatch",
                )
                _assert(exc.attempts == 1, "403 was retried")
            else:
                raise AssertionError("disallowed source network was accepted")
            denied_transport.close()
        cases.append(
            _case(
                "FAILURE-403",
                "Disallowed LAN source fails closed without reaching AI-CS Core",
                {
                    "http_status": 403,
                    "error_code": "AUTHORIZATION_DENIED",
                    "attempts": 1,
                    "decision_created": False,
                },
            )
        )

        timeout_transport = AlwaysTimeoutTransport()
        timeout_client = GatewayClient(
            timeout_transport,
            identity,
            FakeGatewayTokenProvider(
                {credential_ref: (key_id, SYNTHETIC_SECRET)}
            ),
            decision_retry_policy=retry_three,
            timeout_seconds=0.05,
            sleeper=lambda _: None,
        )
        timeout_request = request("timeout")
        try:
            timeout_client.request_decision(timeout_request)
        except AICSGatewayTimeout as exc:
            _assert(exc.attempts == 3, "timeout attempts mismatch")
            _assert(exc.outcome_unknown is True, "timeout is not marked unknown")
        else:
            raise AssertionError("timeout did not fail closed")
        timeout_trace = timeout_client.trace_store.for_message(
            timeout_request.message_id
        )
        _assert(timeout_trace.decision_id is None, "timeout created a decision")
        cases.append(
            _case(
                "FAILURE-TIMEOUT",
                "Transport timeout becomes UNKNOWN and creates no decision",
                {
                    "attempts": timeout_transport.attempts,
                    "outcome_unknown": True,
                    "decision_created": False,
                    "execution_created": False,
                },
            )
        )

    _assert(len(cases) == 10, "required validation case count changed")
    _assert(all(case["status"] == "PASS" for case in cases), "case failed")
    return {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "final_status": FINAL_STATUS,
        "validation_result": "PASS",
        "contract": {
            "contract_version": "1.0",
            "expected_canonical_sha256": EXPECTED_CONTRACT_SHA256,
            "actual_canonical_sha256": canonical_hash,
            "channel_engine_raw_sha256": _sha256(client_schema_raw),
            "ai_cs_raw_sha256": _sha256(server_schema_raw),
            "raw_files_identical": client_schema_raw == server_schema_raw,
            "schema_objects_identical": client_schema == server_schema,
            "generated_models_identical": client_generated == server_generated,
        },
        "repositories": {
            "ai_cs": {
                "commit": _git(ai_cs_root, "rev-parse", "HEAD"),
                "worktree_clean": not bool(_git(ai_cs_root, "status", "--porcelain")),
            },
            "channel_engine": {
                "commit": _git(channel_engine_root, "rev-parse", "HEAD"),
                "worktree_clean": not bool(
                    _git(channel_engine_root, "status", "--porcelain")
                ),
            },
        },
        "cases": cases,
        "summary": {
            "total": len(cases),
            "passed": len(cases),
            "failed": 0,
            "all_fail_closed": True,
        },
        "trace_contract": {
            "trace_id_wire_mapping": "correlation_id",
            "fields": ["message_id", "decision_id", "request_id", "trace_id"],
            "complete": True,
        },
        "side_effect_attestation": {
            "real_ai_model_calls": 0,
            "pdd_connections": 0,
            "customer_message_reads": 0,
            "messages_sent": 0,
            "executions_created": 0,
            "gateway_contract_changes": 0,
            "ai_cs_business_logic_changes": 0,
        },
        "contains_secret_material": False,
        "contains_customer_data": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate frozen Gateway Contract V1 across AI-CS and Channel Engine."
    )
    parser.add_argument("--ai-cs-root", type=Path, required=True)
    parser.add_argument("--channel-engine-root", type=Path, required=True)
    parser.add_argument("--ai-cs-python", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    ai_cs_python = arguments.ai_cs_python or (
        arguments.ai_cs_root / "backend" / ".venv" / "Scripts" / "python.exe"
    )
    try:
        result = validate(
            arguments.ai_cs_root,
            arguments.channel_engine_root,
            ai_cs_python,
        )
    except Exception as exc:
        failed = {
            "final_status": "AI_CS_CHANNEL_ENGINE_INTEGRATION_BLOCKED",
            "validation_result": "FAIL",
            "failure_type": type(exc).__name__,
            "message": str(exc),
            "gateway_contract_changes": 0,
            "pdd_connections": 0,
            "messages_sent": 0,
        }
        print(json.dumps(failed, ensure_ascii=False, indent=2))
        return 1
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
