from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from ai_cs_agent.config import SafetyConfig
from channel_engine import __version__
from channel_engine.app import app
from channel_engine.pdd_adapter.activation import PDDControlledActivationPlan
from channel_engine.pdd_adapter.governance import PDDProductionGovernanceInput
from channel_engine.security.rbac import OperatorRole


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_VERSION = "0.2.0rc3"
EXPECTED_CONTRACT_SHA256 = (
    "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
)


def test_rc2_version_is_consistent() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == EXPECTED_VERSION
    assert __version__ == EXPECTED_VERSION
    assert app.version == EXPECTED_VERSION


def test_gateway_contract_v1_sha_is_frozen() -> None:
    schema = json.loads(
        (ROOT / "schemas/ai-cs-channel-engine-gateway-contract-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == EXPECTED_CONTRACT_SHA256
    contract_versions = {
        definition["properties"]["contract_version"]["const"]
        for definition in schema["$defs"].values()
        if "contract_version" in definition.get("properties", {})
    }
    assert contract_versions == {"1.0"}


def test_rc1_safety_flags_and_rbac_are_fail_closed() -> None:
    governance = PDDProductionGovernanceInput.model_json_schema()["properties"]
    activation = PDDControlledActivationPlan.model_json_schema()["properties"]
    for schema in (governance, activation):
        assert schema["real_platform_activation_allowed"]["const"] is False
        assert schema["activation_grant_issued"]["const"] is False
        assert schema["real_send_enabled"]["const"] is False
    safety = SafetyConfig()
    assert safety.kill_switch is True
    assert safety.manual_approval is True
    assert safety.auto_reply is False
    assert {role.value for role in OperatorRole} == {
        "OPERATOR",
        "SUPERVISOR",
        "ADMIN",
    }


def test_rc1_dependency_lock_covers_exact_direct_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    locked: dict[str, str] = {}
    for line in (ROOT / "requirements-rc1.lock").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==", 1)
        locked[name.casefold().replace("_", "-")] = version
    for dependency in project["project"]["dependencies"]:
        name, version = dependency.split("==", 1)
        assert locked[name.casefold().replace("_", "-")] == version


def test_rc1_release_document_set_is_complete() -> None:
    for relative in (
        "docs/releases/RC1-Release-Checklist.md",
        "docs/releases/RC1-Release-Notes.md",
        "docs/releases/CHANGELOG-RC1.md",
        "docs/releases/RC1-Deployment-Guide.md",
        "docs/releases/RC1-Rollback-Guide.md",
    ):
        assert (ROOT / relative).is_file(), relative
