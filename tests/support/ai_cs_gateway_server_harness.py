from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from pathlib import Path


def main() -> None:
    backend_path = Path(os.environ["CONTROLLED_AI_CS_BACKEND"]).resolve()
    runtime_path = Path(os.environ["CONTROLLED_AI_CS_RUNTIME"]).resolve()
    host = os.environ.get("CONTROLLED_AI_CS_HOST", "127.0.0.1")
    port = int(os.environ["CONTROLLED_AI_CS_PORT"])
    secret = os.environ["CONTROLLED_AI_CS_SECRET"]
    runtime_path.mkdir(parents=True, exist_ok=True)
    for name in ("knowledge", "vectors", "logs"):
        (runtime_path / name).mkdir(exist_ok=True)
    secret_path = runtime_path / "gateway-hmac.secret"
    secret_path.write_text(secret + "\n", encoding="utf-8")

    sys.path.insert(0, str(backend_path))

    import uvicorn

    from app.config.settings import Settings
    from app.main import create_app

    class ControlledRag:
        model_configured = True

        def warm_up(self) -> None:
            return None

        def query(self, question, context=None):
            if question == "__CONTROLLED_AI_CS_TIMEOUT__":
                time.sleep(
                    float(
                        os.environ.get(
                            "CONTROLLED_AI_CS_DELAY_SECONDS",
                            "0.5",
                        )
                    )
                )
            return {
                "answer": "[REAL AI-CS CONTROLLED] Human approval is required.",
                "action": "CONTROLLED_ANSWER",
                "risk_level": "LOW",
                "warnings": [],
                "required_fields": [],
                "sources": [{"source": "controlled-synthetic-fixture"}],
                "request_id": "ai-cs-controlled-provider-request",
            }

        def close(self) -> None:
            return None

    settings = replace(
        Settings.from_env(),
        backend_root=runtime_path,
        project_root=runtime_path,
        knowledge_base_path=runtime_path / "knowledge",
        vector_db_path=runtime_path / "vectors",
        log_dir=runtime_path / "logs",
        host=host,
        port=port,
        gateway_enabled=True,
        gateway_client_id="channel-engine",
        gateway_key_id="controlled-integration-key",
        gateway_hmac_secret="",
        gateway_hmac_secret_file=secret_path,
        gateway_state_path=runtime_path / "gateway-state.sqlite3",
    )
    application = create_app(
        settings=settings,
        rag_factory=lambda _settings: ControlledRag(),
    )
    uvicorn.run(
        application,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
