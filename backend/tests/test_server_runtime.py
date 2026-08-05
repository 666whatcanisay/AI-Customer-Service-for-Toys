from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.gateway.runtime import server_runtime_console_schema


def test_checked_in_server_runtime_console_schema_matches_runtime_model() -> None:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "schemas"
        / "ai-cs-server-runtime-console.v1.schema.json"
    )

    assert json.loads(schema_path.read_text(encoding="utf-8")) == (
        server_runtime_console_schema()
    )


def test_server_runtime_console_reports_disabled_gateway_without_sensitive_data(
    api_client,
) -> None:
    client, _ = api_client

    response = client.get("/api/admin/server-runtime")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "ai-cs.server-runtime-console.v1",
        "server": {
            "status": "READY",
            "version": "ai-cs-server-runtime.rc1",
            "runtime_mode": "standard",
        },
        "gateway": {
            "enabled": False,
            "status": "DISABLED",
            "version": "ai-cs-gateway.v1",
            "contract_version": "1.0",
            "configuration_state": "DISABLED",
        },
    }
    serialized = response.text.lower()
    assert "secret" not in serialized
    assert "state_path" not in serialized
    assert "client_id" not in serialized


def test_standard_runtime_resolves_gateway_secret_by_file_reference(tmp_path) -> None:
    secret_path = tmp_path / "gateway-hmac.secret"
    secret_path.write_text("x" * 32 + "\n", encoding="utf-8")
    settings = replace(
        Settings.from_env(),
        gateway_hmac_secret="",
        gateway_hmac_secret_file=secret_path,
    )

    assert settings.gateway_secret_bytes() == b"x" * 32
    assert "x" * 32 not in repr(settings)


def test_standard_runtime_rejects_inline_gateway_secret() -> None:
    settings = replace(
        Settings.from_env(),
        gateway_hmac_secret="x" * 32,
        gateway_hmac_secret_file=None,
    )

    with pytest.raises(ValueError, match="inline secrets are forbidden"):
        settings.gateway_secret_bytes()
