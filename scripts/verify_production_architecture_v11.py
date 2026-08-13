from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_GATEWAY_SHA256 = (
    "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
)
EXPECTED_ENGINE_VERSION = "0.2.0rc3"
EXPECTED_AGENT_VERSION = "2.0.0rc5"
EXPECTED_CONTROL_VERSION = "2.1"


def _result(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {"gate": name, "status": "PASS" if passed else "BLOCKED", "detail": detail}


def _canonical_gateway_sha() -> str:
    schema = json.loads(
        (ROOT / "schemas/ai-cs-channel-engine-gateway-contract-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _literal_assignment(path: Path, name: str) -> str | None:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    if isinstance(statement.value, ast.Constant) and isinstance(
                        statement.value.value, str
                    ):
                        return statement.value.value
    return None


def _package_gate(
    package_root: Path | None = None,
    archive: Path | None = None,
) -> tuple[bool, str, str | None]:
    package_root = package_root or ROOT / "dist/windows-client-v2/AI-CS-Channel-Agent"
    manifest_path = package_root / "release-manifest.json"
    archive = archive or ROOT / (
        "dist/windows-client-v2/"
        f"AI-CS-Channel-Agent-{EXPECTED_AGENT_VERSION}-windows-x64.zip"
    )
    if not manifest_path.is_file() or not archive.is_file():
        return False, "coordinated Windows package has not been built", None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if (
        manifest.get("version") != EXPECTED_AGENT_VERSION
        or manifest.get("agent_runtime_version") != EXPECTED_AGENT_VERSION
        or manifest.get("agent_control_protocol") != EXPECTED_CONTROL_VERSION
        or manifest.get("channel_engine_compatibility") != EXPECTED_ENGINE_VERSION
        or manifest.get("gateway_contract_sha256") != EXPECTED_GATEWAY_SHA256
    ):
        return False, "package manifest version is inconsistent", None
    paths = {str(item["path"]) for item in manifest.get("files", ())}
    forbidden = tuple(
        item
        for item in paths
        if any(
            marker in item.casefold()
            for marker in ("channel_engine", "ai_cs_agent", "sandbox", "discovery", "fake")
        )
    )
    if forbidden:
        return False, f"package contains forbidden entries: {forbidden[:3]}", None
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    return True, f"manifest files={len(paths)}, forbidden=0", archive_sha


def _selector_evidence_gate(path: Path | None) -> tuple[bool, str, str | None]:
    if path is None:
        return False, "no operator-verified PRODUCTION selector evidence supplied", None
    from channel_engine.browser.selectors import (
        SelectorCapability,
        SelectorContract,
        SelectorEvidenceEnvironment,
        SelectorContractState,
    )

    contract = SelectorContract.model_validate_json(path.read_bytes())
    evidence = contract.verification_evidence
    passed = bool(
        contract.state is SelectorContractState.VERIFIED
        and evidence is not None
        and evidence.environment is SelectorEvidenceEnvironment.PRODUCTION
        and SelectorCapability.SEND_MESSAGE in evidence.capability_boundary
        and evidence.expires_at > datetime.now(UTC)
    )
    return (
        passed,
        "operator-verified production send evidence is active"
        if passed
        else "selector evidence is not active PRODUCTION SEND_MESSAGE evidence",
        evidence.evidence_hash if passed and evidence is not None else None,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selector-evidence-json", type=Path)
    parser.add_argument("--require-production-selector-evidence", action="store_true")
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    checks: list[dict[str, str]] = []
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    engine_version = project["project"]["version"]
    agent_version = _literal_assignment(ROOT / "src/channel_agent/version.py", "AGENT_VERSION")
    control_version = _literal_assignment(
        ROOT / "src/channel_agent/version.py", "AGENT_CONTROL_PROTOCOL_VERSION"
    )
    checks.append(
        _result(
            "COORDINATED_VERSION",
            (engine_version, agent_version, control_version)
            == (EXPECTED_ENGINE_VERSION, EXPECTED_AGENT_VERSION, EXPECTED_CONTROL_VERSION),
            f"engine={engine_version}, agent={agent_version}, control={control_version}",
        )
    )
    gateway_sha = _canonical_gateway_sha()
    checks.append(
        _result(
            "GATEWAY_CONTRACT_FROZEN",
            gateway_sha == EXPECTED_GATEWAY_SHA256,
            f"canonical_sha256={gateway_sha}",
        )
    )

    production_source = (ROOT / "src/channel_engine/production_app.py").read_text(
        encoding="utf-8"
    )
    production_tree = ast.parse(production_source)
    imported_modules: set[str] = set()
    route_literals: set[str] = set()
    for node in ast.walk(production_tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("/")
        ):
            route_literals.add(node.value)
    legacy_absent = not any(
        route.startswith("/channel-agent/v1") for route in route_literals
    ) and not any(
        module == "channel_engine.app"
        or any(marker in module.casefold() for marker in (".pilot", ".sandbox", ".fake"))
        for module in imported_modules
    )
    checks.append(
        _result(
            "PRODUCTION_V1_UNMOUNTED",
            legacy_absent,
            "production Host composition contains no legacy/Fake/Pilot router",
        )
    )

    from channel_agent.config import ChannelAgentConfig
    from channel_engine.execution.receipt_facts import (
        assert_unknown_receipt_details,
        unknown_receipt_details,
    )

    unknown = unknown_receipt_details(transport_triggered=True)
    assert_unknown_receipt_details(unknown)
    checks.append(
        _result(
            "UNKNOWN_RECEIPT_SEMANTICS",
            unknown["customer_message_sent"] is None
            and unknown["automatic_retry_allowed"] is False
            and unknown["reconciliation_required"] is True,
            "delivery fact=null, auto-retry=false, reconciliation=true",
        )
    )
    config = ChannelAgentConfig(
        server_url="https://127.0.0.1:18443",
        agent_id="release-gate-agent",
        device_id="release-gate-device",
    )
    checks.append(
        _result(
            "SAFETY_LOCKS",
            config.manual_approval_required
            and not config.auto_reply_enabled
            and not config.real_send_enabled
            and not config.real_platform_activation_allowed,
            "manual approval required; auto reply, real send and activation disabled",
        )
    )
    package_passed, package_detail, archive_sha = _package_gate(
        args.package_root,
        args.archive,
    )
    checks.append(_result("WINDOWS_PACKAGE_BOUNDARY", package_passed, package_detail))
    selector_passed, selector_detail, selector_hash = _selector_evidence_gate(
        args.selector_evidence_json
    )
    checks.append(_result("PRODUCTION_SELECTOR_EVIDENCE", selector_passed, selector_detail))

    software_gate_names = {
        "COORDINATED_VERSION",
        "GATEWAY_CONTRACT_FROZEN",
        "PRODUCTION_V1_UNMOUNTED",
        "UNKNOWN_RECEIPT_SEMANTICS",
        "SAFETY_LOCKS",
        "WINDOWS_PACKAGE_BOUNDARY",
    }
    software_ready = all(
        item["status"] == "PASS" for item in checks if item["gate"] in software_gate_names
    )
    controlled_pilot_ready = software_ready and selector_passed
    payload = {
        "schema_version": "production-architecture-gates.v1.1",
        "generated_at": datetime.now(UTC).isoformat(),
        "software_rc": "PASS" if software_ready else "BLOCKED",
        "real_platform_decision": (
            "READY_FOR_CONTROLLED_PILOT" if controlled_pilot_ready else "BLOCKED"
        ),
        "gateway_contract_sha256": gateway_sha,
        "windows_archive_sha256": archive_sha,
        "selector_evidence_hash": selector_hash,
        "checks": checks,
        "real_platform_side_effects": 0,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not software_ready:
        return 1
    if args.require_production_selector_evidence and not selector_passed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
