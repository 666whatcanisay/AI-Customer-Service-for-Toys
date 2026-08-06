from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


RELEASE = "0.1.0rc1"
TAG = "channel-engine-v0.1.0rc1"
CONTRACT_SHA256 = "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
OUTPUT_PATH = "docs/releases/RC1-Source-Allowlist.json"

INCLUDED_ROOT_FILES = {
    ".gitattributes",
    ".gitignore",
    "README.md",
    "pyproject.toml",
    "requirements-rc1.lock",
}
INCLUDED_PREFIXES = (
    "src/",
    "tests/",
    "schemas/",
    "scripts/",
    "packaging/",
)
INCLUDED_DEPLOY = {
    "deploy/staging/deployment-manifest.json",
    "deploy/staging/runtime-config.json",
    "deploy/windows-agent-rc/agent.example.json",
}
EXCLUDED_PREFIXES = ("evidence/", "docs/reports/")
EXCLUDED_PATHS = {
    "deploy/channel-agent.example.json",
    "deploy/pdd-pilot-ai-cs-gateway.json",
    "deploy/pdd-pilot-environment.json",
    "deploy/pdd-single-store-pilot.example.json",
}
FORBIDDEN_SUFFIXES = (".sqlite", ".sqlite3", ".log", ".pyc", ".pyo", ".env")


def _git(root: Path, *args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line for line in completed.stdout.splitlines() if line]


def _included(path: str) -> bool:
    if path in INCLUDED_ROOT_FILES or path == OUTPUT_PATH:
        return True
    if path in INCLUDED_DEPLOY:
        return True
    if path.startswith("docs/"):
        return not path.startswith(EXCLUDED_PREFIXES) and (
            path.endswith(".md") or path.endswith(".csv") or path == OUTPUT_PATH
        )
    return path.startswith(INCLUDED_PREFIXES)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_contract_hash(path: Path) -> str:
    value = json.loads(path.read_text(encoding="utf-8"))
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def build(root: Path) -> dict[str, object]:
    tracked = set(_git(root, "ls-files"))
    untracked = set(_git(root, "ls-files", "--others", "--exclude-standard"))
    modified = {
        line[3:]
        for line in _git(root, "status", "--porcelain=v1", "-uall")
        if not line.startswith("??")
    }

    selected_untracked = {path for path in untracked if _included(path)}
    unclassified = sorted(path for path in untracked if not _included(path))
    if unclassified:
        raise RuntimeError(f"unclassified untracked RC inputs: {unclassified}")

    repository_allowlist = sorted(tracked | selected_untracked | {OUTPUT_PATH})
    staging_allowlist = sorted(modified | selected_untracked | {OUTPUT_PATH})

    forbidden = [
        path
        for path in repository_allowlist
        if path.startswith(EXCLUDED_PREFIXES)
        or path in EXCLUDED_PATHS
        or path.casefold().endswith(FORBIDDEN_SUFFIXES)
        or "/__pycache__/" in path
    ]
    if forbidden:
        raise RuntimeError(f"forbidden paths entered RC allowlist: {forbidden}")

    missing = [
        path
        for path in repository_allowlist
        if path != OUTPUT_PATH and not (root / path).is_file()
    ]
    if missing:
        raise RuntimeError(f"allowlisted paths are missing: {missing}")

    contract_hash = _canonical_contract_hash(
        root / "schemas/ai-cs-channel-engine-gateway-contract-v1.schema.json"
    )
    if contract_hash != CONTRACT_SHA256:
        raise RuntimeError("Gateway Contract canonical SHA changed")

    file_manifest: list[dict[str, object]] = []
    for path in repository_allowlist:
        source = root / path
        file_manifest.append(
            {
                "path": path,
                "sha256": None if path == OUTPUT_PATH else _sha256(source),
                "size": None if path == OUTPUT_PATH else source.stat().st_size,
            }
        )

    excluded_worktree_files = sorted(
        [
            *(
                path.relative_to(root).as_posix()
                for path in (root / "evidence").rglob("*")
                if path.is_file()
            ),
            *(
                path.relative_to(root).as_posix()
                for path in (root / "docs").glob("*.html")
                if path.is_file()
            ),
            *(
                path.relative_to(root).as_posix()
                for path in (root / "docs/reports").rglob("*")
                if path.is_file()
            ),
            *(path for path in sorted(EXCLUDED_PATHS) if (root / path).is_file()),
        ]
    )
    local_generated = [
        path
        for path in (".runtime", ".pytest_cache", ".coverage", "dist")
        if (root / path).exists()
    ]

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "release": RELEASE,
        "release_tag": TAG,
        "protected_anchor": _git(root, "rev-parse", "HEAD")[0],
        "gateway_contract": {
            "version": "1.0",
            "canonical_sha256": contract_hash,
            "unchanged": True,
        },
        "classification": {
            "must_enter_rc": len(repository_allowlist),
            "staging_candidate": len(staging_allowlist),
            "must_ignore": len(excluded_worktree_files),
            "must_delete": 0,
            "local_generated_present": len(local_generated),
        },
        "policy": {
            "included": [
                "source",
                "tests",
                "necessary Markdown/CSV documentation",
                "release and validation tools",
                "safe example/staging configuration",
                "Gateway Contract schema",
            ],
            "package_excluded": [
                "fake",
                "sandbox",
                "discovery",
                "experimental",
                "pdd",
                "pilot",
                "mock-server",
                "channel-send-implementation",
            ],
            "ignored": [
                "runtime",
                "evidence",
                "logs",
                "cache",
                "local data",
                "generated HTML",
                "report renderer manifests",
                "deferred local pilot configuration",
                "secret material",
            ],
            "deletion": "No unknown file is deleted; known generated local files remain ignored.",
        },
        "repository_allowlist": repository_allowlist,
        "staging_allowlist": staging_allowlist,
        "excluded_worktree_files": excluded_worktree_files,
        "local_generated_present": local_generated,
        "files": file_manifest,
        "contains_secret_material": False,
        "contains_customer_data": False,
        "real_send_enabled": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the explicit Channel Engine RC1 source allowlist.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path(OUTPUT_PATH))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    result = build(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": output.relative_to(root).as_posix(),
                "classification": result["classification"],
                "staging_candidate": len(result["staging_allowlist"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
