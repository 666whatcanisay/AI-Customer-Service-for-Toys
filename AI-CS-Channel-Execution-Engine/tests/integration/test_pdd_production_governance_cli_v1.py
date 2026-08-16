from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from pdd_governance_support import governance_input


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "scripts" / "check_pdd_production_activation_governance.py"


def environment() -> dict[str, str]:
    values = os.environ.copy()
    values["PYTHONPATH"] = os.pathsep.join(
        (str(REPOSITORY / "src"), str(REPOSITORY / "tests"))
    )
    return values


def test_governance_cli_schema_is_offline_and_versioned() -> None:
    completed = subprocess.run(
        (sys.executable, str(SCRIPT), "--schema"),
        cwd=REPOSITORY,
        env=environment(),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["title"] == "PDDProductionGovernanceInput"
    assert completed.stderr == ""


def test_governance_cli_generates_bundle_and_six_scenario_drill(tmp_path) -> None:
    source = tmp_path / "governance-input.json"
    source.write_text(
        governance_input().model_dump_json(indent=2),
        encoding="utf-8",
    )

    completed = subprocess.run(
        (sys.executable, str(SCRIPT), "--input", str(source), "--drill"),
        cwd=REPOSITORY,
        env=environment(),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["decision"]["decision"] == "READY"
    assert payload["decision"]["real_platform_activation_allowed"] is False
    assert payload["evidence_bundle"]["contains_credential_material"] is False
    assert len(payload["synthetic_drill"]["results"]) == 6
    assert payload["synthetic_drill"]["real_platform_operations"] == 0
    assert completed.stderr == ""


def test_governance_cli_invalid_input_is_blocked_without_traceback(tmp_path) -> None:
    source = tmp_path / "invalid-governance-input.json"
    source.write_text(
        '{"real_platform_activation_allowed": true}',
        encoding="utf-8",
    )

    completed = subprocess.run(
        (sys.executable, str(SCRIPT), "--input", str(source)),
        cwd=REPOSITORY,
        env=environment(),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert payload["decision"] == "BLOCKED"
    assert payload["real_platform_activation_allowed"] is False
    assert payload["activation_grant_issued"] is False
    assert payload["real_send_enabled"] is False
    assert "Traceback" not in completed.stderr


def test_governance_cli_builds_truthful_offline_conditional_snapshot() -> None:
    completed = subprocess.run(
        (
            sys.executable,
            str(SCRIPT),
            "--offline-snapshot",
            "--source-commit",
            "b2c64d54987f1f066a02de8e9e667d5cc0f9857c",
            "--regression-total",
            "500",
            "--regression-passed",
            "500",
            "--regression-warnings",
            "1",
        ),
        cwd=REPOSITORY,
        env=environment(),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["decision"]["decision"] == "CONDITIONAL_READY"
    assert payload["decision"]["real_platform_activation_allowed"] is False
    assert payload["evidence_bundle"]["real_platform_operations"] == 0
    assert payload["synthetic_drill"] is None
    assert completed.stderr == ""
