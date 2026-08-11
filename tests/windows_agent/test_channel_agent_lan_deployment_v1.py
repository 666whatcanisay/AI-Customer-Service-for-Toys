from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8-sig")


def test_lan_host_start_is_tls_scoped_and_human_confirmed() -> None:
    script = _text("scripts/windows/Start-ChannelAgentLanHost.ps1")

    assert "provision_channel_agent_tls.py" in script
    assert "channel-agent-host-key.encrypted.pem" in script
    assert "CHANNEL_ENGINE_TLS_PRIVATE_KEY_CREDENTIAL_REFERENCE" in script
    assert "run_channel_engine_production_host.py" in script
    assert "-nodes" not in script
    assert "-Profile Private" in script
    assert "-RemoteAddress LocalSubnet" in script
    assert "generate_pairing_code" in script
    assert "只能使用一次" in script
    assert "人工确认" in script
    assert "start_lan_ai_customer_service.ps1" in script
    assert "CHANNEL_ENGINE_AGENT_CONTROL_V2_ENABLED" in script
    assert "provision_channel_agent_service_credential.py" in script
    assert "CHANNEL_ENGINE_AI_CS_SERVICE_CONTROL_ENABLED" in script
    assert "CHANNEL_AGENT_SERVICE_CREDENTIAL_REFERENCE" in script
    assert "CHANNEL_AGENT_CA_CERTIFICATE_FILE" in script


def test_lan_discovery_contains_public_trust_data_but_no_credential_material() -> None:
    script = _text("scripts/windows/Start-ChannelAgentLanHost.ps1")
    candidate_block = script.split("$candidateJson =", 1)[1].split(
        "$discoveryOut =", 1
    )[0]

    assert "certificate_sha256" in candidate_block
    assert "ca_certificate_pem" in candidate_block
    assert "customer_service_url" in candidate_block
    assert "pairingCode" not in candidate_block
    assert "privateKey" not in candidate_block
    assert "credential" not in candidate_block.casefold()


def test_lan_stop_preserves_durable_business_records() -> None:
    script = _text("scripts/windows/Stop-ChannelAgentLanHost.ps1")

    assert "Receipt 与审计记录未删除" in script
    assert "Remove-Item -LiteralPath $statePath" in script
    assert "Remove-Item -LiteralPath $repoRoot" not in script
    assert "Remove-Item -LiteralPath $runtimeRoot" not in script


def test_cleanup_script_is_preview_first_and_exactly_scoped() -> None:
    script = _text("scripts/windows/Clear-ChannelAgentBuildResidue.ps1")

    assert "[switch]$Apply" in script
    assert "AI-CS-Channel-Execution-Engine" in script
    assert "package-acceptance-*" in script
    assert "__pycache__" in script
    assert "浏览器 Profile" in script
    assert "Remove-Item -LiteralPath $resolved" in script
