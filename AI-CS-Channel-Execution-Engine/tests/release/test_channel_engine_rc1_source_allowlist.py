from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/releases/RC1-Source-Allowlist.json"


def test_rc1_source_allowlist_is_explicit_and_fail_closed() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["release"] == "0.1.0rc1"
    assert manifest["release_tag"] == "channel-engine-v0.1.0rc1"
    assert manifest["gateway_contract"]["unchanged"] is True
    assert manifest["classification"]["must_delete"] == 0
    assert manifest["contains_secret_material"] is False
    assert manifest["contains_customer_data"] is False
    assert manifest["real_send_enabled"] is False

    staging = manifest["staging_allowlist"]
    assert staging == sorted(set(staging))
    assert ".gitignore" in staging
    assert "scripts/build_rc1_source_allowlist.py" in staging
    assert "docs/releases/RC1-Source-Allowlist.json" in staging
    assert not any(path.startswith("evidence/") for path in staging)
    assert not any(path.startswith("docs/reports/") for path in staging)
    assert not any(path.endswith(".html") for path in staging)
    assert not any(path.endswith((".sqlite", ".sqlite3", ".log")) for path in staging)


def test_every_rc1_repository_allowlist_path_exists() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for relative in manifest["repository_allowlist"]:
        assert (ROOT / relative).is_file(), relative


def test_production_package_exclusions_remain_frozen() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    composition = json.loads(
        (ROOT / "packaging/windows-agent/production-composition.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(manifest["policy"]["package_excluded"]) == set(composition["excluded"])
