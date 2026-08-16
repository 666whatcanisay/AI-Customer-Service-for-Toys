from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any


CLIENT_ID = "channel-engine-validation"
KEY_ID = "integration-key-v1"
SYNTHETIC_SECRET = b"synthetic-validation-key-material-v1-0001"


def _install_ai_cs(ai_cs_root: Path) -> None:
    backend = str((ai_cs_root / "backend").resolve())
    if backend not in sys.path:
        sys.path.insert(0, backend)


def _core_app(runtime_root: Path):
    from app.config.settings import Settings
    from app.main import create_app

    class StubRag:
        model_configured = True

        def warm_up(self) -> None:
            return None

        def query(self, question: str, context: object | None = None) -> dict[str, Any]:
            del question, context
            return {
                "answer": "这是仅供人工确认的合成验证建议。",
                "action": "DIRECT_ANSWER",
                "risk_level": "LOW",
                "sources": [{"synthetic": True}],
                "model": "synthetic-validation-model",
                "latency_ms": 1.0,
                "request_id": "ai-validation-request",
                "warnings": ["SUGGESTION_ONLY", "AUTO_SEND_DISABLED"],
                "required_fields": [],
            }

        def close(self) -> None:
            return None

    runtime_root.mkdir(parents=True, exist_ok=True)
    secret_path = runtime_root / "gateway-hmac.material"
    secret_path.write_bytes(SYNTHETIC_SECRET + b"\n")
    settings = replace(
        Settings.from_env(),
        backend_root=runtime_root,
        project_root=runtime_root,
        knowledge_base_path=runtime_root / "knowledge",
        vector_db_path=runtime_root / "vectors",
        log_dir=runtime_root / "logs",
        gateway_enabled=True,
        gateway_client_id=CLIENT_ID,
        gateway_key_id=KEY_ID,
        gateway_hmac_secret="",
        gateway_hmac_secret_file=secret_path,
        gateway_state_path=runtime_root / "gateway-state.sqlite3",
    )
    return create_app(settings=settings, rag_factory=lambda active: StubRag())


def _denied_edge_app():
    from app.gateway.lan_proxy import (
        GatewayLanProxyConfig,
        create_gateway_lan_proxy_app,
    )

    config = GatewayLanProxyConfig.build(
        bind_address="192.168.1.11",
        port=18080,
        interface_network="192.168.1.0/24",
        allowed_networks=["192.168.1.0/24"],
        upstream_origin="http://127.0.0.1:8000",
    )
    return create_gateway_lan_proxy_app(
        config,
        client_host_resolver=lambda _: "10.0.0.8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai-cs-root", type=Path, required=True)
    parser.add_argument("--emit-schema", action="store_true")
    parser.add_argument("--mode", choices=("core", "denied-edge"))
    parser.add_argument("--port", type=int)
    parser.add_argument("--runtime-root", type=Path)
    arguments = parser.parse_args()
    _install_ai_cs(arguments.ai_cs_root)
    if arguments.emit_schema:
        from app.gateway.contract import gateway_contract_schema

        print(
            json.dumps(
                gateway_contract_schema(),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    if arguments.mode is None or arguments.port is None or arguments.runtime_root is None:
        parser.error("--mode, --port and --runtime-root are required for server mode")
    import uvicorn

    application = (
        _core_app(arguments.runtime_root)
        if arguments.mode == "core"
        else _denied_edge_app()
    )
    uvicorn.run(
        application,
        host="127.0.0.1",
        port=arguments.port,
        log_level="error",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
