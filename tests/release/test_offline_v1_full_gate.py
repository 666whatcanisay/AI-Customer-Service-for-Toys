from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_full_gate_rebuilds_every_shipped_web_surface() -> None:
    gate = (
        ROOT / "scripts" / "windows" / "Invoke-Rc5OfflineStabilityVerification.ps1"
    ).read_text(encoding="utf-8")

    assert "'assistant-ui-build'" in gate
    assert "@('run','build')" in gate
    assert "'assistant-agent-ui-build'" in gate
    assert "@('run','build:agent')" in gate
    assert "'admin-ui-build'" in gate
