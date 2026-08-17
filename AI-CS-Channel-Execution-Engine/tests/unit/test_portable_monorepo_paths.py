from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


ENGINE_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ENGINE_ROOT / "scripts/manage_current_page_auto_production.py"
START_SCRIPT_PATH = ENGINE_ROOT / "scripts/windows/Start-AiCs-CurrentPage.ps1"
SPEC = importlib.util.spec_from_file_location(
    "manage_current_page_auto_production", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


def test_default_ai_cs_root_is_the_monorepo_root() -> None:
    expected = ENGINE_ROOT.parent
    assert manager.AI_CS_ROOT == expected
    assert manager._is_ai_cs_root(expected)


def test_manager_help_loads_channel_agent_without_installed_project() -> None:
    result = subprocess.run(
        [sys.executable, str(MODULE_PATH), "--help"],
        cwd=ENGINE_ROOT.parent,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()


def test_explicit_start_resumes_a_prior_operator_safe_stop() -> None:
    script = START_SCRIPT_PATH.read_text(encoding="utf-8-sig")

    assert "operator-safe-stop.request" in script
    assert "Remove-Item -LiteralPath $operatorPausePath" in script


def test_ai_cs_config_prefers_standard_runtime(tmp_path: Path) -> None:
    standard = tmp_path / ".runtime/phase-e/config/green-standard.local.ps1"
    legacy = tmp_path / ".runtime/r027-ux-acceptance-data-v1/ux-acceptance.local.ps1"
    standard.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    legacy.write_text("@{}", encoding="utf-8")
    standard.write_text("@{}", encoding="utf-8")

    assert manager._ai_cs_config_path(tmp_path) == standard.resolve()


def test_ai_cs_config_fails_without_runtime_config(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="CURRENT_PAGE_AI_CS_CONFIG_NOT_FOUND"):
        manager._ai_cs_config_path(tmp_path)
