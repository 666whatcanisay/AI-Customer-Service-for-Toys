from pathlib import Path

import pytest

from scripts.capture_rc5_final_state import assert_secret_free, production_tree_sha256


def test_production_tree_hash_is_stable_and_content_sensitive(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "b.py").write_text("b\n", encoding="utf-8")
    (source / "a.py").write_text("a\n", encoding="utf-8")

    first = production_tree_sha256(tmp_path, ("src",))
    second = production_tree_sha256(tmp_path, ("src",))
    assert first == second
    assert first["file_count"] == 2

    (source / "a.py").write_text("changed\n", encoding="utf-8")
    assert production_tree_sha256(tmp_path, ("src",))["sha256"] != first["sha256"]


def test_secret_like_fields_cannot_enter_release_evidence() -> None:
    assert_secret_free({"runtime": {"pdd_session_file_count": 2}})
    assert_secret_free(
        {"runtime": {"protected_file_sha256": {"runtime/bootstrap-device.json": "a" * 64}}}
    )
    with pytest.raises(ValueError, match="secret-like field"):
        assert_secret_free({"runtime": {"bootstrap_token": "must-not-serialize"}})
