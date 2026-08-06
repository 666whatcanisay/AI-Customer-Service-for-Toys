from __future__ import annotations

import ast
import base64
import hashlib
import hmac
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ai_cs_agent.config import ServerConfig
import pytest

from ai_cs_agent.gateway import GatewayAuthenticationFailed, GatewayClient
from ai_cs_agent.security import CredentialMaterial


SECRET = b"0123456789abcdef0123456789abcdef"


class TestCredentialProvider:
    def acquire(self, reference: str) -> CredentialMaterial:
        return CredentialMaterial(reference, SECRET)


class SignedHealthHandler(BaseHTTPRequestHandler):
    seen_valid_signature = False

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/gateway/v1/health":
            self.send_error(404)
            return
        headers = self.headers
        authorization = headers["Authorization"]
        signature = authorization.rsplit("Signature=", 1)[1]
        canonical = "\n".join(
            (
                "HMAC-SHA256",
                "GET",
                self.path,
                headers["X-AI-CS-Contract-Version"],
                "channel-agent",
                "key-001",
                headers["X-AI-CS-Timestamp"],
                headers["X-AI-CS-Nonce"],
                headers["X-Request-ID"],
                headers["X-Correlation-ID"],
                headers["Idempotency-Key"],
                hashlib.sha256(b"").hexdigest(),
            )
        ).encode()
        expected = base64.urlsafe_b64encode(
            hmac.new(SECRET, canonical, hashlib.sha256).digest()
        ).decode().rstrip("=")
        type(self).seen_valid_signature = hmac.compare_digest(expected, signature)
        body = json.dumps(
            {
                "status": "HEALTHY",
                "service": "ai-cs-gateway",
                "contract_version": "1.0",
                "version": "test",
                "capabilities": ["decision-v1"],
                "reachable": True,
                "real_ai_cs_connected": True,
                "timestamp": "2026-08-05T00:00:00Z",
                "details": {},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-AI-CS-Contract-Version", "1.0")
        self.send_header("X-Request-ID", headers["X-Request-ID"])
        self.send_header("X-Correlation-ID", headers["X-Correlation-ID"])
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        return


class RejectedHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps(
            {
                "contract_version": "1.0",
                "error": {
                    "error_code": "AUTHENTICATION_FAILED",
                    "retryable": False,
                },
            }
        ).encode()
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        return


def test_signed_gateway_health_uses_frozen_contract() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), SignedHealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = GatewayClient(
            ServerConfig(
                address=f"http://127.0.0.1:{server.server_port}",
                client_id="channel-agent",
                key_id="key-001",
                credential_reference="wincred://AI-CS-Agent/Gateway/key-001",
                timeout_seconds=1,
            ),
            TestCredentialProvider(),
        )
        health = client.health_check()
        assert health.healthy
        assert SignedHealthHandler.seen_valid_signature
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_gateway_health_maps_401_to_authentication_exit_class() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), RejectedHealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = GatewayClient(
            ServerConfig(
                address=f"http://127.0.0.1:{server.server_port}",
                client_id="channel-agent",
                key_id="key-001",
                credential_reference="wincred://AI-CS-Agent/Gateway/key-001",
                timeout_seconds=1,
            ),
            TestCredentialProvider(),
        )
        with pytest.raises(GatewayAuthenticationFailed):
            client.health_check()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_production_import_graph_and_composition_exclude_experiments() -> None:
    root = Path(__file__).resolve().parents[2]
    source_root = root / "src" / "ai_cs_agent"
    forbidden_roots = {"channel_engine", "pdd", "sandbox", "discovery", "mock_server"}
    for path in source_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
                assert roots.isdisjoint(forbidden_roots), path
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_roots, path
    composition = json.loads(
        (root / "packaging" / "windows-agent" / "production-composition.json").read_text(
            encoding="utf-8"
        )
    )
    assert all(path.startswith("src/ai_cs_agent/") for path in composition["source_allowlist"])
    assert {"fake", "sandbox", "discovery", "pdd"}.issubset(composition["excluded"])


def test_source_and_config_examples_do_not_contain_plaintext_credentials() -> None:
    root = Path(__file__).resolve().parents[2]
    paths = list((root / "src" / "ai_cs_agent").glob("*.py")) + [
        root / "deploy" / "windows-agent-rc" / "agent.example.json"
    ]
    config = json.loads(paths[-1].read_text(encoding="utf-8"))
    flattened = json.dumps(config).casefold()
    assert '"password"' not in flattened
    assert '"secret"' not in flattened
    assert '"token"' not in flattened
    assert '"cookie"' not in flattened
    for path in paths[:-1]:
        text = path.read_text(encoding="utf-8")
        assert re.search(
            r"(?im)^\s*(secret|password|cookie|token)\s*=\s*['\"]", text
        ) is None, path


def test_windows_package_builder_normalizes_batch_for_cmd() -> None:
    root = Path(__file__).resolve().parents[2]
    builder = (root / "scripts" / "build_windows_agent_rc.ps1").read_text(
        encoding="utf-8"
    )
    assert '[System.Text.UTF8Encoding]::new($true)' in builder
    assert '$launcherContent -replace "`r?`n", "`r`n"' in builder
    assert "'raise SystemExit(main())'" in builder
    assert "-m 'ai_cs_agent.cli:main'" not in builder
