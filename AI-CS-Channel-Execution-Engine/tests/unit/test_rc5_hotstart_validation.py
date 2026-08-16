from __future__ import annotations

import importlib.util
from pathlib import Path

from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_rc5_hotstart_validation.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_rc5_hotstart_validation", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Snapshot(BaseModel):
    status: str


def test_json_ready_recursively_serializes_models_nested_in_evidence() -> None:
    runner = _load_runner()

    assert runner._json_ready(
        {
            "snapshot": _Snapshot(status="EXECUTION_PREPARED"),
            "items": (_Snapshot(status="WAITING_APPROVAL"),),
        }
    ) == {
        "snapshot": {"status": "EXECUTION_PREPARED"},
        "items": [{"status": "WAITING_APPROVAL"}],
    }
