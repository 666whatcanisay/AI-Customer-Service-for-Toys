from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "scripts" / "check_pdd_controlled_activation.py"


def environment() -> dict[str, str]:
    values = os.environ.copy()
    values["PYTHONPATH"] = str(REPOSITORY / "src")
    return values


def test_offline_check_cli_exposes_schema_without_platform_calls() -> None:
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
    assert payload["title"] == "PDDControlledActivationCheckInput"
    assert "plan" in payload["required"]
    assert completed.stderr == ""


def test_offline_check_cli_fails_closed_for_invalid_input(tmp_path) -> None:
    invalid = tmp_path / "invalid-activation-input.json"
    invalid.write_text('{"plan": {"real_platform_activation_allowed": true}}')

    completed = subprocess.run(
        (sys.executable, str(SCRIPT), "--input", str(invalid)),
        cwd=REPOSITORY,
        env=environment(),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert payload["activation_authorized"] is False
    assert payload["error_code"] == "PDD_ACTIVATION_CHECK_INPUT_INVALID"
    assert "Traceback" not in completed.stderr
