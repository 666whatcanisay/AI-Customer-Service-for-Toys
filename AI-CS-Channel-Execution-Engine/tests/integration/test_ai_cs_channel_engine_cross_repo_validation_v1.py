from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


EXPECTED_CONTRACT_SHA256 = (
    "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
)


def test_frozen_gateway_contract_v1_is_compatible_across_repositories(
    tmp_path: Path,
) -> None:
    channel_root = Path(__file__).resolve().parents[2]
    ai_cs_root = channel_root.parent / "AI-CS"
    ai_cs_python = ai_cs_root / "backend" / ".venv" / "Scripts" / "python.exe"
    if not ai_cs_root.is_dir() or not ai_cs_python.is_file():
        pytest.skip("sibling AI-CS validation runtime is unavailable")

    output = tmp_path / "cross-repo-validation.json"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            os.fspath(Path(sys.executable)),
            str(channel_root / "scripts" / "validate_ai_cs_channel_engine_integration_v1.py"),
            "--ai-cs-root",
            str(ai_cs_root),
            "--channel-engine-root",
            str(channel_root),
            "--ai-cs-python",
            str(ai_cs_python),
            "--output",
            str(output),
        ],
        cwd=channel_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["final_status"] == "AI_CS_CHANNEL_ENGINE_INTEGRATION_VALIDATED"
    assert evidence["validation_result"] == "PASS"
    assert evidence["contract"]["actual_canonical_sha256"] == (
        EXPECTED_CONTRACT_SHA256
    )
    assert evidence["contract"]["schema_objects_identical"] is True
    assert evidence["contract"]["generated_models_identical"] is True
    assert evidence["summary"] == {
        "total": 10,
        "passed": 10,
        "failed": 0,
        "all_fail_closed": True,
    }
    assert evidence["trace_contract"]["complete"] is True
    assert not any(evidence["side_effect_attestation"].values())
    assert evidence["contains_secret_material"] is False
    assert evidence["contains_customer_data"] is False
