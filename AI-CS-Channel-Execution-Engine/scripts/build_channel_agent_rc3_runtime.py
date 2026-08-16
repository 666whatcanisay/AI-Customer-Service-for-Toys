from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


EXPECTED_BASELINE_SHA256 = (
    "a2f5f89f3656eeab2ad46deea39805de8d067e8978f5ee6f80e0f3839d75a31a"
)
ALLOWED_MEMBERS = {
    "channel_agent/binding.py": Path("src/channel_agent/binding.py"),
    "channel_agent/version.py": Path("src/channel_agent/version.py"),
    "channel_agent/windows.py": Path("src/channel_agent/windows.py"),
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the minimal ChannelAgent 2.0.0rc3 runtime from the installed RC1 pyz."
    )
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()

    baseline = args.baseline.resolve()
    repo_root = args.repo_root.resolve()
    output = args.output.resolve()
    evidence = args.evidence.resolve()
    baseline_hash = file_sha256(baseline)
    if baseline_hash != EXPECTED_BASELINE_SHA256:
        raise SystemExit(
            f"Refusing non-baseline runtime: expected {EXPECTED_BASELINE_SHA256}, got {baseline_hash}"
        )

    replacements: dict[str, bytes] = {}
    for member, relative_source in ALLOWED_MEMBERS.items():
        source = repo_root / relative_source
        payload = source.read_bytes()
        if member.endswith("version.py") and b'AGENT_VERSION = "2.0.0rc3"' not in payload:
            raise SystemExit("RC3 version constant is missing")
        if member.endswith("windows.py"):
            required = (
                b'WINDOWS_CLIENT_VERSION = "2.0.0rc3"',
                b'error_code="LOCAL_STATE_TEMPORARILY_LOCKED"',
                b"RLock",
            )
            if any(value not in payload for value in required):
                raise SystemExit("RC3 Windows state reliability patch is incomplete")
        if member.endswith("binding.py") and b"def _atomic_replace(" not in payload:
            raise SystemExit("RC3 atomic replace wrapper is missing")
        replacements[member] = payload

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".pending")
    temporary.unlink(missing_ok=True)
    before: dict[str, str] = {}
    after: dict[str, str] = {}
    with zipfile.ZipFile(baseline, "r") as source_archive:
        names = source_archive.namelist()
        missing = sorted(set(ALLOWED_MEMBERS) - set(names))
        if missing:
            raise SystemExit(f"Baseline runtime is missing patch members: {missing}")
        with zipfile.ZipFile(temporary, "w") as target_archive:
            for info in source_archive.infolist():
                original = source_archive.read(info.filename)
                before[info.filename] = sha256(original)
                payload = replacements.get(info.filename, original)
                after[info.filename] = sha256(payload)
                target_archive.writestr(info, payload)

    changed = sorted(name for name in before if before[name] != after[name])
    if changed != sorted(ALLOWED_MEMBERS):
        temporary.unlink(missing_ok=True)
        raise SystemExit(
            f"Minimal runtime diff gate failed: expected {sorted(ALLOWED_MEMBERS)}, got {changed}"
        )
    temporary.replace(output)
    rc3_hash = file_sha256(output)

    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "baseline_sha256": baseline_hash,
                "rc3_sha256": rc3_hash,
                "allowed_members": sorted(ALLOWED_MEMBERS),
                "changed_members": changed,
                "member_hashes": {
                    member: {"before": before[member], "after": after[member]}
                    for member in changed
                },
                "unchanged_member_count": len(before) - len(changed),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"runtime={output}")
    print(f"runtime_sha256={rc3_hash}")
    print(f"changed_members={','.join(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
