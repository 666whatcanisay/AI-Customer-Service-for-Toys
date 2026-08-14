from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PLATFORM_BACKEND = ROOT / "platform_backend"
FIXTURE = (
    ROOT
    / "contracts"
    / "candidates"
    / "pdd-reply-readiness-v1"
    / "fixtures"
    / "pdd-reply-readiness-input.valid.json"
)


_A_SERVER_SOURCE = r"""
import os
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from app.api.routes import router
from app.config.settings import Settings
from app.reply_readiness.evaluator import ReplyReadinessEvaluator
from app.reply_router.contracts import ReplyRulePublicationV1, canonical_sha256
from app.reply_router.publication_store import ReplyRuleSnapshotStore

root = Path(os.environ["SYNTHETIC_HTTP_ROOT"])
store = ReplyRuleSnapshotStore(root / "reply-rule-snapshots")
publication = {
    "schema_version": "reply-rule-publication.v1",
    "publication_id": "publication-synthetic-http-001",
    "idempotency_key": "publication-synthetic-http-001",
    "tenant_id": "TENANT-SYNTHETIC",
    "platform": "pdd",
    "snapshot_revision": 1,
    "rules": (),
    "produced_by": "synthetic-http-gate",
    "produced_at": datetime(2026, 8, 14, tzinfo=timezone.utc),
}
publication["snapshot_fingerprint"] = canonical_sha256(
    {
        "tenant_id": publication["tenant_id"],
        "platform": publication["platform"],
        "snapshot_revision": publication["snapshot_revision"],
        "rules": [],
    }
)
store.publish(ReplyRulePublicationV1.model_validate(publication))

app = FastAPI()
app.state.settings = Settings.from_env()
app.state.reply_readiness_evaluator = ReplyReadinessEvaluator(store)
app.include_router(router, prefix="/api")
uvicorn.run(
    app,
    host="127.0.0.1",
    port=int(os.environ["SYNTHETIC_HTTP_PORT"]),
    log_level="warning",
)
"""


_C_CLIENT_SOURCE = r"""
import hashlib
import json
import os
from pathlib import Path

from app.reply_readiness.ai_client import ReplyReadinessAiClient

payload = json.loads(Path(os.environ["SYNTHETIC_FIXTURE"]).read_text(encoding="utf-8"))
snapshot = {
    "tenant_id": "TENANT-SYNTHETIC",
    "platform": "pdd",
    "snapshot_revision": 1,
    "rules": [],
}
payload["reply_rule_snapshot_fingerprint"] = hashlib.sha256(
    json.dumps(
        snapshot,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()
result = ReplyReadinessAiClient(timeout_seconds=10).evaluate(payload)
assert result["run_id"] == payload["run_id"]
assert result["status"] == "COMPLETED"
assert payload["production_usable"] is False
assert payload["allow_auto_send"] is False
assert len(result["items"]) == 1
print(
    "SYNTHETIC_C_TO_A_REAL_HTTP_OK "
    f"run_id={result['run_id']} status={result['status']}"
)
"""


def _python_for(root: Path) -> Path:
    executable = root / ".venv" / "Scripts" / "python.exe"
    if not executable.is_file():
        raise RuntimeError(f"isolated Python runtime is missing: {executable}")
    return executable


def _available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_until_ready(port: int, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 15
    url = f"http://127.0.0.1:{port}/openapi.json"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    _, stderr = process.communicate(timeout=3)
    raise RuntimeError(f"synthetic A HTTP service failed to start: {stderr[-2000:]}")


def main() -> int:
    if not FIXTURE.is_file():
        raise RuntimeError(f"synthetic fixture is missing: {FIXTURE}")
    port = _available_loopback_port()
    with tempfile.TemporaryDirectory(prefix="ai-cs-readiness-http-") as raw_root:
        run_root = Path(raw_root).resolve()
        secret_path = run_root / "internal-service.secret"
        secret_path.write_text(
            "synthetic-http-secret-32-bytes-minimum-only",
            encoding="ascii",
        )
        common_env = os.environ.copy()
        common_env.update(
            {
                "INTERNAL_SERVICE_SECRET_FILE": str(secret_path),
                "SYNTHETIC_HTTP_PORT": str(port),
                "SYNTHETIC_HTTP_ROOT": str(run_root),
            }
        )
        server_env = common_env | {"PYTHONPATH": str(BACKEND)}
        process = subprocess.Popen(
            [str(_python_for(BACKEND)), "-c", _A_SERVER_SOURCE],
            cwd=BACKEND,
            env=server_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            _wait_until_ready(port, process)
            client_env = common_env | {
                "PYTHONPATH": str(PLATFORM_BACKEND),
                "DATABASE_URL": "sqlite://",
                "PLATFORM_REQUIRE_DATABASE_IDENTITY": "false",
                "AI_SERVICE_BASE_URL": f"http://127.0.0.1:{port}",
                "AI_SERVICE_TIMEOUT_SECONDS": "10",
                "SYNTHETIC_FIXTURE": str(FIXTURE),
            }
            completed = subprocess.run(
                [str(_python_for(PLATFORM_BACKEND)), "-c", _C_CLIENT_SOURCE],
                cwd=PLATFORM_BACKEND,
                env=client_env,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "synthetic C-to-A HTTP client failed: "
                    + completed.stderr[-2000:]
                )
            print(completed.stdout.strip())
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
