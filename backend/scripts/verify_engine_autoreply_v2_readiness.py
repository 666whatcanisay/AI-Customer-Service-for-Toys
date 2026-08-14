from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.reply_router.contracts import (
    EngineAutoreplyAcceptanceStatus,
    EngineAutoreplyV2AcceptanceV1,
)


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ROOT = ROOT / "contracts" / "candidates" / "reply-router-v1"
AI_CS_GATEWAY_SCHEMA = (
    ROOT / "contracts" / "schemas" / "channel-engine-gateway-server.v1.schema.json"
)
ENGINE_GATEWAY_SCHEMA = Path("schemas/ai-cs-channel-engine-gateway-contract-v1.schema.json")
ENGINE_ACCEPTANCE_ADAPTER = Path("scripts/verify_ai_cs_autoreply_v2.py")
RAW_GATEWAY_SHA256 = "fef35afb67dcd5027d7aa59ff35e5b6035a4130c5c1957ab41d4397d5fa67b80"
CANONICAL_GATEWAY_SHA256 = (
    "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
)


def canonical_json_sha256(raw: bytes) -> str:
    parsed = json.loads(raw)
    canonical = json.dumps(
        parsed,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def candidate_manifest_sha256(candidate_root: Path = CANDIDATE_ROOT) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path
        for directory in (candidate_root / "schemas", candidate_root / "fixtures")
        for path in directory.glob("*.json")
    )
    if not files:
        raise ValueError("reply-router candidate schemas and fixtures are missing")
    for path in files:
        relative = path.relative_to(candidate_root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def resolve_engine_commit(engine_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", os.fspath(engine_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    commit = completed.stdout.strip().lower()
    if completed.returncode != 0 or len(commit) not in {40, 64}:
        raise ValueError("Engine source commit cannot be resolved")
    if any(character not in "0123456789abcdef" for character in commit):
        raise ValueError("Engine source commit is not hexadecimal")
    return commit


def engine_worktree_fingerprint(engine_root: Path) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            os.fspath(engine_root),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ],
        capture_output=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("Engine worktree state cannot be resolved")
    return hashlib.sha256(completed.stdout).hexdigest()


def _check(status: str, evidence_code: str) -> dict[str, str]:
    return {"status": status, "evidence_code": evidence_code}


def audit_engine_readiness(
    engine_root: Path,
    *,
    engine_python: Path | None = None,
    candidate_root: Path = CANDIDATE_ROOT,
    ai_cs_gateway_schema: Path = AI_CS_GATEWAY_SCHEMA,
) -> dict[str, Any]:
    checks: dict[str, dict[str, str]] = {}
    blockers: list[str] = []
    manifest_sha = candidate_manifest_sha256(candidate_root)

    try:
        worktree_before = engine_worktree_fingerprint(engine_root)
    except ValueError:
        worktree_before = None
        blockers.append("ENGINE_WORKTREE_UNRESOLVED")

    try:
        engine_commit = resolve_engine_commit(engine_root)
        checks["engine_source_identity"] = _check("PASS", "ENGINE_COMMIT_RESOLVED")
    except ValueError:
        engine_commit = None
        checks["engine_source_identity"] = _check("FAIL", "ENGINE_COMMIT_UNRESOLVED")
        blockers.append("ENGINE_COMMIT_UNRESOLVED")

    engine_gateway_schema = engine_root / ENGINE_GATEWAY_SCHEMA
    if not ai_cs_gateway_schema.is_file() or not engine_gateway_schema.is_file():
        checks["gateway_schema"] = _check("FAIL", "GATEWAY_SCHEMA_MISSING")
        blockers.append("GATEWAY_SCHEMA_MISSING")
        raw_sha = None
        canonical_sha = None
    else:
        ai_raw = ai_cs_gateway_schema.read_bytes()
        engine_raw = engine_gateway_schema.read_bytes()
        raw_sha = hashlib.sha256(ai_raw).hexdigest()
        canonical_sha = canonical_json_sha256(ai_raw)
        gateway_valid = (
            ai_raw == engine_raw
            and raw_sha == RAW_GATEWAY_SHA256
            and canonical_sha == CANONICAL_GATEWAY_SHA256
            and canonical_json_sha256(engine_raw) == CANONICAL_GATEWAY_SHA256
        )
        if gateway_valid:
            checks["gateway_schema"] = _check("PASS", "GATEWAY_V1_FROZEN_EQUAL")
        else:
            checks["gateway_schema"] = _check("FAIL", "GATEWAY_V1_DRIFT")
            blockers.append("GATEWAY_V1_DRIFT")

    adapter_path = engine_root / ENGINE_ACCEPTANCE_ADAPTER
    if not adapter_path.is_file():
        checks["engine_acceptance_adapter"] = _check(
            "FAIL", "ENGINE_ACCEPTANCE_ADAPTER_MISSING"
        )
        blockers.append("ENGINE_ACCEPTANCE_ADAPTER_MISSING")
        adapter_report = None
    elif engine_commit is None or raw_sha is None or canonical_sha is None:
        checks["engine_acceptance_adapter"] = _check(
            "FAIL", "ENGINE_ACCEPTANCE_PREREQUISITE_FAILED"
        )
        blockers.append("ENGINE_ACCEPTANCE_PREREQUISITE_FAILED")
        adapter_report = None
    else:
        python_path = engine_python or engine_root / ".venv" / "Scripts" / "python.exe"
        if not python_path.is_file():
            checks["engine_acceptance_adapter"] = _check(
                "FAIL", "ENGINE_ACCEPTANCE_PYTHON_MISSING"
            )
            blockers.append("ENGINE_ACCEPTANCE_PYTHON_MISSING")
            adapter_report = None
        else:
            with tempfile.TemporaryDirectory(prefix="ai-cs-autoreply-v2-") as directory:
                output = Path(directory) / "engine-acceptance.json"
                environment = os.environ.copy()
                environment.pop("PYTHONPATH", None)
                environment["PYTHONDONTWRITEBYTECODE"] = "1"
                environment["AI_CS_AUTOREPLY_ACCEPTANCE_OFFLINE_ONLY"] = "1"
                completed = subprocess.run(
                    [
                        os.fspath(python_path),
                        os.fspath(adapter_path),
                        "--candidate-root",
                        os.fspath(candidate_root),
                        "--candidate-manifest-sha256",
                        manifest_sha,
                        "--gateway-schema",
                        os.fspath(ai_cs_gateway_schema),
                        "--gateway-raw-sha256",
                        raw_sha,
                        "--gateway-canonical-sha256",
                        canonical_sha,
                        "--engine-commit",
                        engine_commit,
                        "--offline-only",
                        "--output",
                        os.fspath(output),
                    ],
                    cwd=engine_root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=120,
                    check=False,
                )
                try:
                    if completed.returncode != 0 or not output.is_file():
                        raise ValueError("Engine acceptance adapter failed")
                    adapter_report = EngineAutoreplyV2AcceptanceV1.model_validate_json(
                        output.read_text(encoding="utf-8")
                    )
                    if (
                        adapter_report.engine_commit != engine_commit
                        or adapter_report.candidate_manifest_sha256 != manifest_sha
                        or adapter_report.gateway_raw_sha256 != raw_sha
                        or adapter_report.gateway_canonical_sha256 != canonical_sha
                        or adapter_report.final_status
                        is not EngineAutoreplyAcceptanceStatus.PASS
                    ):
                        raise ValueError("Engine acceptance evidence does not match inputs")
                except (OSError, ValueError, ValidationError):
                    checks["engine_acceptance_adapter"] = _check(
                        "FAIL", "ENGINE_ACCEPTANCE_EVIDENCE_INVALID"
                    )
                    blockers.append("ENGINE_ACCEPTANCE_EVIDENCE_INVALID")
                    adapter_report = None
                else:
                    checks["engine_acceptance_adapter"] = _check(
                        "PASS", "ENGINE_AUTOREPLY_V2_ACCEPTED"
                    )

    try:
        worktree_after = engine_worktree_fingerprint(engine_root)
    except ValueError:
        worktree_after = None
        if "ENGINE_WORKTREE_UNRESOLVED" not in blockers:
            blockers.append("ENGINE_WORKTREE_UNRESOLVED")
    worktree_unchanged = (
        worktree_before is not None
        and worktree_after is not None
        and worktree_before == worktree_after
    )
    if worktree_unchanged:
        checks["engine_worktree"] = _check("PASS", "ENGINE_WORKTREE_UNCHANGED")
    else:
        checks["engine_worktree"] = _check(
            "FAIL", "ENGINE_WORKTREE_CHANGED_DURING_ACCEPTANCE"
        )
        blockers.append("ENGINE_WORKTREE_CHANGED_DURING_ACCEPTANCE")

    final_status = "PASS" if not blockers else "FAIL"
    return {
        "schema_version": "ai-cs-engine-autoreply-v2-readiness-audit.v1",
        "final_status": final_status,
        "engine_commit": engine_commit,
        "candidate_manifest_sha256": manifest_sha,
        "gateway_wire": "1.0",
        "gateway_raw_sha256": raw_sha,
        "gateway_canonical_sha256": canonical_sha,
        "contract_status": "UNCOORDINATED_CANDIDATE",
        "checks": checks,
        "blocker_codes": sorted(set(blockers)),
        "adapter_final_status": (
            adapter_report.final_status.value if adapter_report is not None else None
        ),
        "side_effect_attestation": {
            "engine_source_modified_by_ai_cs": not worktree_unchanged,
            "runtime_started_by_ai_cs": False,
            "pdd_connected_by_ai_cs": False,
            "real_send_attempted_by_ai_cs": False,
        },
        "contains_secret_material": False,
        "contains_customer_data": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Card 6 verifier for Engine Autoreply V2 integration"
    )
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--engine-python", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_engine_readiness(
        args.engine_root.resolve(),
        engine_python=args.engine_python.resolve() if args.engine_python else None,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if report["final_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
