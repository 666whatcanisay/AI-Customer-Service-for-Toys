from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_OUTPUT = "evidence/channel-engine-rc1-source-freeze/git-diff-cached.patch"
DEFAULT_SUMMARY = "evidence/channel-engine-rc1-source-freeze/cached-diff-summary.json"


def _git_bytes(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _git_text(root: Path, *args: str) -> str:
    return _git_bytes(root, *args).decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the complete staged RC1 candidate diff as ignored evidence."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT))
    parser.add_argument("--summary", type=Path, default=Path(DEFAULT_SUMMARY))
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    summary_path = args.summary if args.summary.is_absolute() else root / args.summary

    patch = _git_bytes(root, "diff", "--cached", "--binary", "--full-index")
    if not patch:
        raise RuntimeError("staged RC1 candidate is empty")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(patch)

    name_status = [
        line
        for line in _git_text(root, "diff", "--cached", "--name-status").splitlines()
        if line
    ]
    summary = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "base_commit": _git_text(root, "rev-parse", "HEAD").strip(),
        "staged_file_count": len(name_status),
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "patch_size": len(patch),
        "diff_stat": _git_text(root, "diff", "--cached", "--stat"),
        "name_status": name_status,
        "contract_diff": _git_text(
            root,
            "diff",
            "--cached",
            "--",
            "schemas/ai-cs-channel-engine-gateway-contract-v1.schema.json",
        ),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "patch": output.relative_to(root).as_posix(),
                "summary": summary_path.relative_to(root).as_posix(),
                "staged_file_count": summary["staged_file_count"],
                "patch_sha256": summary["patch_sha256"],
                "patch_size": summary["patch_size"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
