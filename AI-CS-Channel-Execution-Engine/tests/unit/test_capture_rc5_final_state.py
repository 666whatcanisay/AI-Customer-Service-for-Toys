from pathlib import Path

import pytest

from scripts.capture_rc5_final_state import (
    assert_secret_free,
    git_snapshot,
    package_snapshot,
    production_tree_sha256,
)


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


def test_package_snapshot_exposes_build_identity(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    identity = {
        "channel_agent_source": {"commit_sha": "a" * 40, "tree_sha": "b" * 40},
        "assistant_ui_source": {"commit_sha": "c" * 40, "tree_sha": "d" * 40},
    }
    (package / "release-manifest.json").write_text(
        __import__("json").dumps({"version": "2.0.0rc5", "build_identity": identity}),
        encoding="utf-8",
    )

    assert package_snapshot(package)["build_identity"] == identity


def test_git_snapshot_separates_evidence_head_from_implementation_head(
    tmp_path: Path,
) -> None:
    import subprocess

    def git(*arguments: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *arguments], check=True)

    git("init", "-q")
    git("config", "user.email", "rc5@example.invalid")
    git("config", "user.name", "RC5 Test")
    source = tmp_path / "src"
    source.mkdir()
    (source / "app.py").write_text("stable\n", encoding="utf-8")
    git("add", "src/app.py")
    git("commit", "-q", "-m", "implementation")
    implementation_head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (tmp_path / "evidence.md").write_text("evidence\n", encoding="utf-8")
    git("add", "evidence.md")
    git("commit", "-q", "-m", "evidence")

    snapshot = git_snapshot(tmp_path, ("src",))

    assert snapshot["head"] != implementation_head
    assert snapshot["implementation_head"] == implementation_head
