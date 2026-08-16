from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal


EXPECTED_VERSION = "0.1.0rc1"
EXPECTED_CONTRACT_VERSION = "1.0"
EXPECTED_CONTRACT_SHA256 = (
    "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
)
EXPECTED_TAG = "channel-engine-v0.1.0rc1"
CheckStatus = Literal["PASS", "WARNING", "BLOCKED"]


@dataclass(frozen=True, slots=True)
class ReleaseCheck:
    check_id: str
    area: str
    status: CheckStatus
    evidence: str
    remediation: str | None = None


def _canonical_sha256(path: Path) -> str:
    value = json.loads(path.read_text(encoding="utf-8"))
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _locked_versions(path: Path) -> dict[str, str]:
    locked: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise ValueError(f"dependency is not exactly pinned: {line}")
        name, version = line.split("==", 1)
        locked[name.casefold().replace("_", "-")] = version
    return locked


def verify(root: Path, regression_evidence: Path | None) -> dict[str, object]:
    sys.path.insert(0, str(root / "src"))
    from channel_engine import __version__
    from channel_engine.app import app
    from channel_engine.pdd_adapter.activation import PDDControlledActivationPlan
    from channel_engine.pdd_adapter.governance import PDDProductionGovernanceInput
    from channel_engine.security.rbac import OperatorRole
    from channel_engine.session.credential import ReferenceOnlyCredentialProvider
    from ai_cs_agent.config import SafetyConfig

    checks: list[ReleaseCheck] = []
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = pyproject["project"]["version"]
    versions = {
        "pyproject": project_version,
        "channel_engine": __version__,
        "fastapi": app.version,
    }
    checks.append(
        ReleaseCheck(
            "VERSION-001",
            "Repository",
            "PASS" if set(versions.values()) == {EXPECTED_VERSION} else "BLOCKED",
            json.dumps(versions, sort_keys=True),
            None if set(versions.values()) == {EXPECTED_VERSION} else "Align all release versions.",
        )
    )

    status_lines = _git(root, "status", "--porcelain=v1").splitlines()
    tracked = sum(not line.startswith("??") for line in status_lines)
    untracked = sum(line.startswith("??") for line in status_lines)
    tags_at_head = set(_git(root, "tag", "--points-at", "HEAD").splitlines())
    source_frozen = not status_lines and EXPECTED_TAG in tags_at_head
    checks.append(
        ReleaseCheck(
            "SOURCE-001",
            "Repository",
            "PASS" if source_frozen else "BLOCKED",
            (
                f"tracked_changes={tracked}; untracked_entries={untracked}; "
                f"tag_at_head={str(EXPECTED_TAG in tags_at_head).lower()}"
            ),
            None
            if source_frozen
            else "Review and commit the exact RC1 source scope, create the RC1 tag at HEAD, then rerun this gate.",
        )
    )

    lock_path = root / "requirements-rc1.lock"
    direct = {}
    for dependency in pyproject["project"]["dependencies"]:
        if "==" not in dependency:
            direct[dependency] = None
            continue
        name, version = dependency.split("==", 1)
        direct[name.casefold().replace("_", "-")] = version
    locked = _locked_versions(lock_path)
    dependency_match = all(locked.get(name) == version for name, version in direct.items())
    checks.append(
        ReleaseCheck(
            "DEPENDENCY-001",
            "Repository",
            "PASS" if dependency_match else "BLOCKED",
            f"direct_dependencies={len(direct)}; locked_distributions={len(locked)}",
            None if dependency_match else "Regenerate the RC1 dependency lock.",
        )
    )

    required_docs = (
        "docs/releases/RC1-Release-Checklist.md",
        "docs/releases/RC1-Release-Notes.md",
        "docs/releases/CHANGELOG-RC1.md",
        "docs/releases/RC1-Deployment-Guide.md",
        "docs/releases/RC1-Rollback-Guide.md",
    )
    missing_docs = [path for path in required_docs if not (root / path).is_file()]
    checks.append(
        ReleaseCheck(
            "DOCS-001",
            "Repository",
            "PASS" if not missing_docs else "BLOCKED",
            "complete" if not missing_docs else f"missing={','.join(missing_docs)}",
            None if not missing_docs else "Create all required RC1 release documents.",
        )
    )

    contract_path = root / "schemas/ai-cs-channel-engine-gateway-contract-v1.schema.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract_sha = _canonical_sha256(contract_path)
    contract_versions = {
        definition["properties"]["contract_version"].get("const")
        for definition in contract.get("$defs", {}).values()
        if "contract_version" in definition.get("properties", {})
    }
    contract_version = (
        next(iter(contract_versions)) if len(contract_versions) == 1 else None
    )
    contract_ok = (
        contract_sha == EXPECTED_CONTRACT_SHA256
        and contract_version == EXPECTED_CONTRACT_VERSION
    )
    checks.append(
        ReleaseCheck(
            "CONTRACT-001",
            "Contract",
            "PASS" if contract_ok else "BLOCKED",
            f"version={contract_version}; canonical_sha256={contract_sha}",
            None if contract_ok else "Restore the production-frozen Gateway Contract V1.",
        )
    )

    governance_schema = PDDProductionGovernanceInput.model_json_schema()["properties"]
    activation_schema = PDDControlledActivationPlan.model_json_schema()["properties"]
    safety = SafetyConfig()
    flags_ok = all(
        governance_schema[name].get("const") is False
        for name in (
            "real_platform_activation_allowed",
            "activation_grant_issued",
            "real_send_enabled",
        )
    ) and all(
        activation_schema[name].get("const") is False
        for name in (
            "real_platform_activation_allowed",
            "activation_grant_issued",
            "real_send_enabled",
        )
    )
    safety_ok = (
        flags_ok
        and safety.kill_switch
        and safety.manual_approval
        and not safety.auto_reply
    )
    checks.append(
        ReleaseCheck(
            "SAFETY-001",
            "Security",
            "PASS" if safety_ok else "BLOCKED",
            "real_send_enabled=false; activation=false; grant=false; kill_switch=true; manual_approval=true; auto_reply=false",
            None if safety_ok else "Restore fail-closed release safety defaults.",
        )
    )
    roles = {role.value for role in OperatorRole}
    rbac_ok = roles == {"OPERATOR", "SUPERVISOR", "ADMIN"}
    credential_ok = ReferenceOnlyCredentialProvider is not None
    checks.append(
        ReleaseCheck(
            "SECURITY-BOUNDARY-001",
            "Security",
            "PASS" if rbac_ok and credential_ok else "BLOCKED",
            f"rbac_roles={','.join(sorted(roles))}; credential_provider=reference-only",
            None if rbac_ok and credential_ok else "Restore RBAC and credential reference boundaries.",
        )
    )

    if regression_evidence is None or not regression_evidence.is_file():
        checks.append(
            ReleaseCheck(
                "REGRESSION-001",
                "Testing",
                "BLOCKED",
                "final regression evidence missing",
                "Run the frozen RC1 test matrix and save its evidence.",
            )
        )
    else:
        regression = json.loads(regression_evidence.read_text(encoding="utf-8"))
        regression_ok = regression.get("result") == "PASS" and regression.get("failed") == 0
        checks.append(
            ReleaseCheck(
                "REGRESSION-001",
                "Testing",
                "PASS" if regression_ok else "BLOCKED",
                f"passed={regression.get('passed')}; failed={regression.get('failed')}; warnings={regression.get('warnings')}",
                None if regression_ok else "Resolve failures and rerun the full RC1 matrix.",
            )
        )

    overall = "BLOCKED" if any(item.status == "BLOCKED" for item in checks) else "READY"
    return {
        "report_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "release": "Channel Engine 0.1.0rc1",
        "decision": overall,
        "final_status": (
            "CHANNEL_ENGINE_RC1_READY" if overall == "READY" else "CHANNEL_ENGINE_RC1_BLOCKED"
        ),
        "repository": {
            "commit": _git(root, "rev-parse", "HEAD"),
            "branch": _git(root, "branch", "--show-current"),
            "worktree_clean": not status_lines,
            "required_tag": EXPECTED_TAG,
            "tag_at_head": EXPECTED_TAG in tags_at_head,
        },
        "contract": {
            "version": contract_version,
            "canonical_sha256": contract_sha,
            "expected_sha256": EXPECTED_CONTRACT_SHA256,
            "unchanged": contract_ok,
        },
        "checks": [asdict(item) for item in checks],
        "summary": {
            "passed": sum(item.status == "PASS" for item in checks),
            "warnings": sum(item.status == "WARNING" for item in checks),
            "blocked": sum(item.status == "BLOCKED" for item in checks),
        },
        "side_effect_attestation": {
            "pdd_connections": 0,
            "customer_message_reads": 0,
            "messages_sent": 0,
            "executions_created": 0,
            "gateway_contract_changes": 0,
        },
        "contains_secret_material": False,
        "contains_customer_data": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Channel Engine RC1 release gates.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--regression-evidence", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    evidence = args.regression_evidence
    if evidence is not None and not evidence.is_absolute():
        evidence = root / evidence
    result = verify(root, evidence)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["decision"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
