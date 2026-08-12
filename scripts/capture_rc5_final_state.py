#!/usr/bin/env python3
"""Capture a secret-free, read-only RC5 release and runtime snapshot.

The command intentionally does not start or stop services, open a browser, read a
PDD page, or mutate a database.  It is used to prove source/build/package/runtime
consistency and to compare protected Agent state before and after validation.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AI_CS_ROOT = ROOT.parent / "AI-CS"
GATEWAY_SHA256 = "e5ac64a82d2a7ccd19d3ece9bcc076242b55b6c205c85626786e8b1b7478f4b5"
EXCLUDED_NAMES = {".git", ".runtime", ".venv", "__pycache__", "node_modules", "dist"}
SECRET_KEY_PATTERN = re.compile(
    r"(?:authorization|bootstrap|cookie|credential|password|secret|session|token)",
    re.IGNORECASE,
)


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def production_tree_sha256(root: Path, relative_paths: Iterable[str]) -> dict[str, Any]:
    """Hash path names and file bytes in a stable, explicitly scoped order."""

    files: list[Path] = []
    for relative in relative_paths:
        candidate = root / relative
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            files.extend(
                path
                for path in candidate.rglob("*")
                if path.is_file() and not EXCLUDED_NAMES.intersection(path.parts)
            )
    unique = sorted(set(files), key=lambda path: path.relative_to(root).as_posix())
    digest = hashlib.sha256()
    for path in unique:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return {"sha256": digest.hexdigest(), "file_count": len(unique)}


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def git_snapshot(root: Path) -> dict[str, Any]:
    def run(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip()

    try:
        return {
            "head": run("rev-parse", "HEAD"),
            "branch": run("branch", "--show-current"),
            "dirty_paths": run("status", "--short").splitlines(),
        }
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"error": type(exc).__name__}


def extract_python_constant(path: Path, name: str) -> str | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(rf"^{re.escape(name)}\s*=\s*[\"']([^\"']+)", content, re.MULTILINE)
    return match.group(1) if match else None


def extract_toml_version(path: Path) -> str | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^version\s*=\s*["\']([^"\']+)', content, re.MULTILINE)
    return match.group(1) if match else None


def package_snapshot(package_root: Path, archive: Path | None = None) -> dict[str, Any]:
    manifest = read_json(package_root / "release-manifest.json") or {}
    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    declared = {
        item.get("path"): item.get("sha256")
        for item in files
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    return {
        "root": str(package_root),
        "version": manifest.get("version"),
        "agent_runtime_version": manifest.get("agent_runtime_version"),
        "gateway_contract_sha256": manifest.get("gateway_contract_sha256"),
        "manifest_sha256": sha256_file(package_root / "release-manifest.json"),
        "executable_sha256": sha256_file(package_root / "ChannelAgent.exe"),
        "runtime_sha256": sha256_file(package_root / "app" / "channel-agent.pyz"),
        "archive_sha256": sha256_file(archive) if archive else None,
        "declared_executable_sha256": declared.get("ChannelAgent.exe"),
        "declared_runtime_sha256": declared.get("app/channel-agent.pyz"),
        "file_count": len(files),
    }


def sqlite_snapshot(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if not path.is_file() or path.stat().st_size == 0:
        return result | {"size": path.stat().st_size if path.exists() else 0, "revision": None}
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
            revision_row = connection.execute(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).fetchone()
            table_count = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        return result | {
            "size": path.stat().st_size,
            "revision": revision_row[0] if revision_row else None,
            "table_count": int(table_count),
            "integrity": integrity,
            "foreign_key_violations": foreign_keys,
        }
    except sqlite3.Error as exc:
        return result | {"size": path.stat().st_size, "error": type(exc).__name__}


def process_alive(pid: Any) -> bool:
    try:
        numeric_pid = int(pid)
    except (TypeError, ValueError):
        return False
    if numeric_pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
            process_query_limited_information, False, numeric_pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        return True
    try:
        os.kill(numeric_pid, 0)
    except OSError:
        return False
    return True


def desktop_ui_edge_pids(data_root: Path) -> list[int]:
    if os.name != "nt":
        return []
    marker = str((data_root / "browser" / "assistant-ui").resolve()).replace("'", "''")
    script = (
        "$items=@(Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" "
        f"| Where-Object {{ $_.CommandLine -and $_.CommandLine.Contains('{marker}') }} "
        "| Select-Object ProcessId,ParentProcessId); $items | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        payload = result.stdout.strip()
        if not payload:
            return []
        value = json.loads(payload)
        rows = value if isinstance(value, list) else [value]
        process_ids = {int(item["ProcessId"]) for item in rows}
        roots = [
            int(item["ProcessId"])
            for item in rows
            if int(item["ParentProcessId"]) not in process_ids
        ]
        return sorted(roots)
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return []


def profile_identity(path: Path) -> dict[str, Any]:
    entries: list[str] = []
    for relative in (".", "Local State", "Default", "Default/Network", "Default/Sessions"):
        candidate = path if relative == "." else path / relative
        if not candidate.exists():
            entries.append(f"{relative}|missing")
            continue
        kind = "directory" if candidate.is_dir() else "file"
        entries.append(f"{relative}|{kind}|{candidate.stat().st_ctime_ns}")
    payload = "\n".join(entries).encode("utf-8")
    file_count = sum(1 for item in path.rglob("*") if item.is_file()) if path.is_dir() else 0
    return {
        "exists": path.is_dir(),
        "identity_sha256": hashlib.sha256(payload).hexdigest(),
        "file_count": file_count,
    }


def protected_runtime_snapshot(data_root: Path) -> dict[str, Any]:
    config_path = data_root / "config" / "agent.json"
    binding_path = data_root / "runtime" / "agent-binding.json"
    state_path = data_root / "runtime" / "channel-agent-state.json"
    config = read_json(config_path) or {}
    binding = read_json(binding_path) or {}
    state = read_json(state_path) or {}
    profile_reference = state.get("browser_profile_reference")
    profile_path = data_root / str(profile_reference) if profile_reference else data_root / "missing"
    pdd_root = data_root / "runtime" / "pdd-login"
    pdd_files = sorted(
        item.relative_to(pdd_root).as_posix() for item in pdd_root.rglob("*") if item.is_file()
    ) if pdd_root.is_dir() else []
    desktop_pids = desktop_ui_edge_pids(data_root)
    return {
        "data_root": str(data_root),
        "agent_id": state.get("agent_id") or config.get("agent_id") or binding.get("agent_id"),
        "device_id": state.get("device_id") or config.get("device_id") or binding.get("device_id"),
        "agent_version": state.get("agent_version"),
        "identity_status": state.get("identity_status") or binding.get("identity_status"),
        "binding_revision": state.get("binding_revision") or binding.get("binding_revision"),
        "authorized_store_ids": state.get("authorized_store_ids") or binding.get("authorized_store_ids"),
        "active_store_id": state.get("active_store_id") or config.get("store_reference"),
        "runtime_mode": config.get("runtime_mode"),
        "development_mode": config.get("development_mode"),
        "browser_enabled": config.get("browser_enabled"),
        "real_send_enabled": config.get("real_send_enabled"),
        "runtime_pid": state.get("pid"),
        "runtime_process_alive": process_alive(state.get("pid")),
        "browser_pid": state.get("browser_pid"),
        "browser_process_alive": process_alive(state.get("browser_pid")),
        "desktop_ui_edge_pids": desktop_pids,
        "desktop_ui_edge_alive": bool(desktop_pids) and all(process_alive(pid) for pid in desktop_pids),
        "browser_profile_reference": profile_reference,
        "profile": profile_identity(profile_path),
        "pdd_session_file_count": len(pdd_files),
        "protected_file_sha256": {
            "config/agent.json": sha256_file(config_path),
            "runtime/agent-binding.json": sha256_file(binding_path),
            "runtime/bootstrap-device.json": sha256_file(data_root / "runtime" / "bootstrap-device.json"),
        },
    }


def assert_secret_free(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            hash_container = path.endswith("protected_file_sha256")
            if (
                SECRET_KEY_PATTERN.search(str(key))
                and not str(key).endswith("_sha256")
                and not hash_container
            ):
                allowed = {
                    "pdd_session_file_count",
                    "identity_status",
                    "profile_identity_sha256",
                }
                if key not in allowed:
                    raise ValueError(f"secret-like field is not allowed in evidence: {path}.{key}")
            assert_secret_free(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_secret_free(item, f"{path}[{index}]")


def command_version(arguments: list[str]) -> str | None:
    try:
        result = subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (result.stdout or result.stderr).strip().splitlines()[0]


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    ai_cs_root = args.ai_cs_root.resolve()
    data_root = args.data_root.resolve()
    installed_root = args.installed_root.resolve()
    package_root = args.package_root.resolve()
    source_agent = extract_python_constant(ROOT / "src/channel_agent/version.py", "AGENT_VERSION")
    source_engine = extract_python_constant(ROOT / "src/channel_engine/__init__.py", "__version__")
    return {
        "schema_version": "rc5-final-state.v1",
        "captured_at": datetime.now(UTC).isoformat(),
        "scope": "READ_ONLY_OFFLINE_NO_REAL_PDD",
        "gateway_contract_sha256": GATEWAY_SHA256,
        "source": {
            "engine_version": source_engine,
            "agent_version": source_agent,
            "pyproject_version": extract_toml_version(ROOT / "pyproject.toml"),
            "engine_git": git_snapshot(ROOT),
            "ai_cs_git": git_snapshot(ai_cs_root),
            "engine_production_tree": production_tree_sha256(
                ROOT,
                ("src/channel_agent", "src/channel_engine", "packaging/windows-client-v2", "packaging/windows-client-v1", "deploy/channel-agent-foundation"),
            ),
            "ai_cs_production_tree": production_tree_sha256(
                ai_cs_root,
                ("backend/app", "platform_backend/app", "platform_backend/migrations", "contracts", "frontend/src", "admin_web/src"),
            ),
        },
        "package": package_snapshot(package_root, args.archive.resolve() if args.archive else None),
        "installed": package_snapshot(installed_root),
        "runtime": protected_runtime_snapshot(data_root),
        "databases": {
            "current_runtime": sqlite_snapshot(args.current_database.resolve()),
            "historical_0013": sqlite_snapshot(args.historical_database.resolve()),
        },
        "environment": {
            "os": sys.platform,
            "python": sys.version.split()[0],
            "node": command_version(["node", "--version"]),
            "npm": command_version(["npm.cmd" if os.name == "nt" else "npm", "--version"]),
            "git": command_version(["git", "--version"]),
        },
        "scope_boundaries": {
            "real_pdd_read": "NOT IN SCOPE",
            "real_pdd_send": "NOT IN SCOPE",
            "code_signing": "NOT IN SCOPE",
            "enterprise_certificate": "NOT IN SCOPE",
            "windows_service": "NOT IN SCOPE",
            "release_tag": "NOT IN SCOPE",
        },
    }


def parser() -> argparse.ArgumentParser:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ROOT / ".runtime"))
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--ai-cs-root", type=Path, default=DEFAULT_AI_CS_ROOT)
    result.add_argument("--data-root", type=Path, default=local_app_data / "AI-CS/ChannelAgent")
    result.add_argument("--installed-root", type=Path, default=local_app_data / "Programs/AI-CS/ChannelAgent")
    result.add_argument("--package-root", type=Path, default=ROOT / "dist/windows-client-v2/AI-CS-Channel-Agent")
    result.add_argument("--archive", type=Path, default=ROOT / "dist/windows-client-v2/AI-CS-Channel-Agent-2.0.0rc5-windows-x64.zip")
    result.add_argument(
        "--current-database",
        type=Path,
        default=DEFAULT_AI_CS_ROOT / ".runtime/r027-ux-acceptance-data-v1/runtime/platform.sqlite3",
    )
    result.add_argument(
        "--historical-database",
        type=Path,
        default=DEFAULT_AI_CS_ROOT / ".runtime/phase-e/data/standard-platform.sqlite3",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    snapshot = build_snapshot(args)
    assert_secret_free(snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
