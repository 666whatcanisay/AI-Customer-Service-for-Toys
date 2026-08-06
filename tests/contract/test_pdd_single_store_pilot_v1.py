from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from channel_engine.pilot import (
    PDD_PILOT_CONTRACT_VERSION,
    PDDPilotSendPreflightGate,
    PilotBrowserLaunchConfig,
    PilotEvidence,
    PilotEvidenceType,
    PilotStoreConfig,
    build_manual_login_browser_port,
)
from channel_engine.models.entities import utc_now


def test_pilot_store_config_contract_is_frozen_and_default_safe() -> None:
    schema = PilotStoreConfig.model_json_schema()
    required = set(schema["required"])

    assert PDD_PILOT_CONTRACT_VERSION == "1.0"
    assert {
        "store_id",
        "store_name",
        "credential_reference",
    } <= required
    config = PilotStoreConfig(
        store_id="pdd-pilot-store",
        store_name="玩趣乐园积木店",
        credential_reference="secret-ref://pdd/pilot/store/session",
    )
    assert config.send_limit == 1
    assert config.approval_required is True
    assert config.auto_reply is False
    assert config.environment == "PILOT"
    with pytest.raises(ValidationError):
        PilotStoreConfig(
            store_id="pdd-pilot-store",
            store_name="玩趣乐园积木店",
            credential_reference="raw-cookie-value",
        )


def test_pilot_evidence_contract_rejects_secret_material() -> None:
    with pytest.raises(ValidationError, match="sensitive"):
        PilotEvidence(
            evidence_id="pilot-evidence-secret-test",
            idempotency_key="pilot:evidence:secret-test",
            evidence_type=PilotEvidenceType.STARTUP,
            store_id="pdd-pilot-store",
            correlation_id="pilot-secret-test",
            payload={"cookie": "cookie=unsafe"},
            recorded_at=utc_now(),
        )


def test_real_transport_requires_non_dry_run_explicit_pilot_gate() -> None:
    config = PilotStoreConfig(
        store_id="pdd-pilot-store",
        store_name="玩趣乐园积木店",
        credential_reference="secret-ref://pdd/pilot/store/session",
    )

    with pytest.raises(ValueError, match="dry-run"):
        PDDPilotSendPreflightGate(
            config,
            persistence=object(),  # type: ignore[arg-type]
            kill_switch=object(),  # type: ignore[arg-type]
            readiness=object(),  # type: ignore[arg-type]
            dry_run=True,
            allow_real_platform_transport=True,
        )

    serialized = json.dumps(config.model_dump(mode="json"), ensure_ascii=False)
    assert "raw-cookie" not in serialized


def test_real_browser_builder_requires_evidence_supplied_https_rules(tmp_path) -> None:
    store = PilotStoreConfig(
        store_id="pdd-pilot-store",
        store_name="玩趣乐园积木店",
        credential_reference="secret-ref://pdd/pilot/store/session",
    )
    launch = PilotBrowserLaunchConfig(
        merchant_chat_url="https://verified.example.test/merchant/chat",
        authenticated_path_prefix="/merchant/chat",
        login_path_prefix="/login",
        selector_contract_version="verified-pilot-selector.v1",
    )

    port = build_manual_login_browser_port(
        store,
        launch,
        chrome_path=(tmp_path / "chrome.exe").resolve(),
        profile_root=(tmp_path / "profiles").resolve(),
    )

    assert port.real_browser_capable is True
    assert launch.origin == "https://verified.example.test"
    with pytest.raises(ValidationError, match="HTTPS"):
        PilotBrowserLaunchConfig(
            merchant_chat_url="http://unsafe.example.test/chat",
            authenticated_path_prefix="/chat",
            login_path_prefix="/login",
            selector_contract_version="verified-pilot-selector.v1",
        )
