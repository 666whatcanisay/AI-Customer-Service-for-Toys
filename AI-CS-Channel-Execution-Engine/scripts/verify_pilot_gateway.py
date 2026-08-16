from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from channel_engine.gateway import (
    GatewayAdapterConfig,
    GatewayEnvironment,
    ProductionGatewayClient,
)


def _wait_for_openapi(port: int, process: subprocess.Popen[bytes]) -> dict:
    deadline = time.monotonic() + 15.0
    url = f"http://127.0.0.1:{port}/openapi.json"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("isolated AI-CS process exited before route verification")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:  # noqa: S310
                return json.loads(response.read(2_000_000))
        except Exception:
            time.sleep(0.2)
    raise TimeoutError("isolated AI-CS did not expose OpenAPI within 15 seconds")


def _assert_port_available(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"verification port {port} is already in use") from exc


def verify(
    ai_backend: Path,
    *,
    port: int,
    client_id: str = "channel-engine",
    key_id: str = "pilot-env-v1",
) -> dict[str, object]:
    backend = ai_backend.expanduser().resolve()
    python = backend / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        raise RuntimeError("AI-CS backend virtual environment is unavailable")
    _assert_port_available(port)

    secret = secrets.token_urlsafe(48)
    with tempfile.TemporaryDirectory(
        prefix="ai-cs-pilot-gateway-",
        ignore_cleanup_errors=True,
    ) as temporary:
        temp = Path(temporary)
        environment = os.environ.copy()
        environment.update(
            {
                "GATEWAY_ENABLED": "true",
                "GATEWAY_CLIENT_ID": client_id,
                "GATEWAY_KEY_ID": key_id,
                "GATEWAY_HMAC_SECRET": secret,
                "GATEWAY_STATE_PATH": str(temp / "gateway-state.sqlite3"),
                "LOG_DIR": str(temp / "logs"),
            }
        )
        process = subprocess.Popen(
            (
                str(python),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-access-log",
            ),
            cwd=backend,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            ),
        )
        try:
            specification = _wait_for_openapi(port, process)
            paths = set(specification.get("paths", {}))
            config = GatewayAdapterConfig(
                environment=GatewayEnvironment.MOCK,
                base_url=f"http://127.0.0.1:{port}",
                client_id=client_id,
                key_id=key_id,
                timeout_seconds=5.0,
            )
            with ProductionGatewayClient(config, secret.encode("utf-8")) as client:
                health_deadline = time.monotonic() + 15.0
                health = client.health_check()
                while health.status.value != "HEALTHY" and time.monotonic() < health_deadline:
                    time.sleep(0.5)
                    health = client.health_check()
            return {
                "verification_mode": "ISOLATED_EPHEMERAL_INSTANCE",
                "port": port,
                "client_id": client_id,
                "key_id": key_id,
                "decision_route": "/gateway/v1/decisions" in paths,
                "health_route": "/gateway/v1/health" in paths,
                "signed_health_verified": health.reachable,
                "health_status": health.status.value,
                "contract_version": health.contract_version,
                "gateway_version": health.gateway_version,
                "capability_version": health.capability_version,
                "real_ai_cs_connected": health.real_ai_cs_connected,
                "secret_persisted_by_verifier": False,
                "decision_requested": False,
            }
        finally:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
            # Windows can release the FileHandler lock shortly after process exit.
            time.sleep(0.2)
            secret = ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify AI-CS Gateway V1 without persisting credentials."
    )
    parser.add_argument("--ai-backend", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18021)
    parser.add_argument("--client-id", default="channel-engine")
    parser.add_argument("--key-id", default="pilot-env-v1")
    args = parser.parse_args()
    result = verify(
        args.ai_backend,
        port=args.port,
        client_id=args.client_id,
        key_id=args.key_id,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    required = (
        result["decision_route"],
        result["health_route"],
        result["signed_health_verified"],
    )
    return 0 if all(required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
