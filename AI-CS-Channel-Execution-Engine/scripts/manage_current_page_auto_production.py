from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if os.name == "nt":
    import winreg

from channel_agent.binding import atomic_write_bytes
from channel_agent.current_page_production import CurrentPageProductionConfig

ROOT = Path(__file__).resolve().parents[1]
AI_CS_ROOT = ROOT.parent / "AI-CS"
CATALOG_STORE_ID = "c-store-6639df2982014226"
CATALOG_TENANT_ID = "c-tenant-6639df2982014226be2f5164ba642a72"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Install and operate the current-active-conversation-only AUTO "
            "production supervisor."
        )
    )
    parser.add_argument(
        "action", choices=("install", "start", "status", "stop", "remove-autostart")
    )
    parser.add_argument("--ai-cs-root", default=str(AI_CS_ROOT))
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--catalog-store-id", default=CATALOG_STORE_ID)
    parser.add_argument("--catalog-tenant-id", default=CATALOG_TENANT_ID)
    parser.add_argument("--no-autostart", action="store_true")
    parser.add_argument("--no-start", action="store_true")
    return parser


def _data_root(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("LOCALAPPDATA_UNAVAILABLE")
    return Path(local_app_data).resolve() / "AI-CS" / "ChannelAgent"


AUTOSTART_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE_NAME = "AI-CS-Current-Page-Auto"


def _legacy_startup_path() -> Path | None:
    app_data = os.environ.get("APPDATA")
    if not app_data:
        return None
    return (
        Path(app_data).resolve()
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
        / "AI-CS-Current-Page-Auto.cmd"
    )


def _gateway_key_reference(ai_cs_root: Path) -> Path:
    preferred = (
        ai_cs_root
        / ".runtime"
        / "r027-ux-acceptance-data-v1"
        / "runtime"
        / "managed"
        / "secrets"
        / "gateway-hmac-rc1.secret"
    )
    if preferred.is_file():
        return preferred
    candidates = sorted(
        (ai_cs_root / ".runtime").glob("**/gateway-hmac*.secret"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("CURRENT_PAGE_GATEWAY_KEY_REFERENCE_NOT_FOUND")
    return candidates[0]


def _build_config(
    *,
    ai_cs_root: Path,
    data_root: Path,
    catalog_store_id: str,
    catalog_tenant_id: str,
) -> CurrentPageProductionConfig:
    local_app_data = Path(os.environ["LOCALAPPDATA"]).resolve()
    return CurrentPageProductionConfig(
        ce_root=ROOT,
        ai_cs_root=ai_cs_root,
        ai_cs_config_path=(
            ai_cs_root
            / ".runtime"
            / "r027-ux-acceptance-data-v1"
            / "ux-acceptance.local.ps1"
        ),
        data_root=data_root,
        python_executable=Path(sys.executable).resolve(),
        agent_executable=(
            local_app_data
            / "Programs"
            / "AI-CS"
            / "ChannelAgent"
            / "ChannelAgent.exe"
        ),
        engine_database_path=ROOT / ".runtime" / "channel-engine.sqlite3",
        assistant_root=(
            ROOT
            / ".runtime"
            / "rc5-hotstart-validation"
            / "20260811-233205"
            / "host-offline-runtime"
        ),
        host_evidence_root=ROOT / ".runtime" / "current-page-production",
        gateway_key_reference=_gateway_key_reference(ai_cs_root),
        send_selector_contract=(
            data_root / "runtime" / "controlled-send-selector-contract.json"
        ),
        catalog_store_id=catalog_store_id,
        catalog_tenant_id=catalog_tenant_id,
    )


def _config_path(data_root: Path) -> Path:
    return data_root / "config" / "current-page-production.json"


def _pid_path(data_root: Path) -> Path:
    return data_root / "runtime" / "current-page-production-supervisor.pid"


def _status_path(data_root: Path) -> Path:
    return data_root / "runtime" / "current-page-production-supervisor.json"


def _owner_path(data_root: Path) -> Path:
    return data_root / "runtime" / "current-page-production-supervisor.owner"


def _pid_running(process_id: int) -> bool:
    if process_id <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, process_id)
        if not process:
            return False
        ctypes.windll.kernel32.CloseHandle(process)
        return True
    try:
        os.kill(process_id, 0)
    except OSError:
        return False
    return True


def _lock_owner_pid(data_root: Path) -> int:
    try:
        process_id = int(_owner_path(data_root).read_text(encoding="ascii").strip())
    except (OSError, UnicodeError, ValueError):
        return 0
    return process_id if _pid_running(process_id) else 0


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _fresh_supervisor_status(data_root: Path) -> dict[str, Any] | None:
    value = _read_json(_status_path(data_root))
    try:
        updated_at = datetime.fromisoformat(str(value["updated_at"]))
        age = (datetime.now(UTC) - updated_at.astimezone(UTC)).total_seconds()
    except (KeyError, TypeError, ValueError):
        return None
    if (
        value.get("schema_version") == "current-page-auto-production-status.v1"
        and value.get("supervisor_active") is True
        and 0 <= age <= 15
    ):
        return value
    return None


def _write_config(config: CurrentPageProductionConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(
        path,
        json.dumps(
            config.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )


def _autostart_command(manager: Path, data_root: Path) -> str:
    executable = Path(sys.executable).resolve()
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.is_file():
        executable = pythonw
    return subprocess.list2cmdline(
        [str(executable), str(manager), "start", "--data-root", str(data_root)]
    )


def _install_autostart(manager: Path, data_root: Path) -> str:
    if os.name != "nt":
        raise RuntimeError("CURRENT_PAGE_AUTOSTART_REQUIRES_WINDOWS")
    command = _autostart_command(manager, data_root)
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        AUTOSTART_REGISTRY_PATH,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, AUTOSTART_VALUE_NAME, 0, winreg.REG_SZ, command)
    legacy = _legacy_startup_path()
    if legacy is not None:
        legacy.unlink(missing_ok=True)
    return f"HKCU\\{AUTOSTART_REGISTRY_PATH}\\{AUTOSTART_VALUE_NAME}"


def _autostart_installed() -> bool:
    if os.name != "nt":
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            AUTOSTART_REGISTRY_PATH,
            0,
            winreg.KEY_QUERY_VALUE,
        ) as key:
            value, value_type = winreg.QueryValueEx(key, AUTOSTART_VALUE_NAME)
    except FileNotFoundError:
        return False
    return bool(value_type == winreg.REG_SZ and str(value).strip())


def _remove_autostart() -> str:
    if os.name == "nt":
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                AUTOSTART_REGISTRY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, AUTOSTART_VALUE_NAME)
        except FileNotFoundError:
            pass
    legacy = _legacy_startup_path()
    if legacy is not None:
        legacy.unlink(missing_ok=True)
    return f"HKCU\\{AUTOSTART_REGISTRY_PATH}\\{AUTOSTART_VALUE_NAME}"


def _start(data_root: Path) -> dict[str, Any]:
    existing = _fresh_supervisor_status(data_root)
    if existing is not None:
        return {"started": True, "already_running": True, "status": existing}
    existing_process_id = _lock_owner_pid(data_root)
    if existing_process_id:
        return {
            "started": True,
            "already_running": True,
            "process_id": existing_process_id,
        }
    config_path = _config_path(data_root)
    if not config_path.is_file():
        raise RuntimeError("CURRENT_PAGE_PRODUCTION_NOT_INSTALLED")
    config = CurrentPageProductionConfig.load(config_path)
    from channel_agent.current_page_production import CurrentPageProductionSupervisor

    CurrentPageProductionSupervisor(config).validate_installation()
    runtime_root = data_root / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    stdout = (runtime_root / "current-page-production-supervisor.stdout.log").open(
        "ab"
    )
    stderr = (runtime_root / "current-page-production-supervisor.stderr.log").open(
        "ab"
    )
    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_current_page_auto_production.py"),
                "--config",
                str(config_path),
                "--poll-seconds",
                "2",
            ],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )
    finally:
        stdout.close()
        stderr.close()
    deadline = time.monotonic() + 5.0
    owner_process_id = 0
    while time.monotonic() < deadline:
        owner_process_id = _lock_owner_pid(data_root)
        if owner_process_id:
            break
        if process.poll() is not None:
            raise RuntimeError("CURRENT_PAGE_PRODUCTION_START_FAILED")
        time.sleep(0.1)
    effective_process_id = owner_process_id or process.pid
    atomic_write_bytes(
        _pid_path(data_root), str(effective_process_id).encode("ascii")
    )
    return {
        "started": True,
        "already_running": False,
        "process_id": effective_process_id,
    }


def _stop(data_root: Path) -> dict[str, Any]:
    path = _pid_path(data_root)
    try:
        process_id = int(path.read_text(encoding="ascii").strip())
    except (OSError, UnicodeError, ValueError):
        process_id = 0
    if process_id > 0 and os.name == "nt":
        subprocess.run(
            ["taskkill.exe", "/PID", str(process_id), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    path.unlink(missing_ok=True)
    _status_path(data_root).unlink(missing_ok=True)
    _owner_path(data_root).unlink(missing_ok=True)
    return {"stopped": True, "process_id": process_id or None}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_root = _data_root(args.data_root)
    ai_cs_root = Path(args.ai_cs_root).resolve()
    manager = Path(__file__).resolve()
    if args.action == "install":
        config = _build_config(
            ai_cs_root=ai_cs_root,
            data_root=data_root,
            catalog_store_id=args.catalog_store_id,
            catalog_tenant_id=args.catalog_tenant_id,
        )
        from channel_agent.current_page_production import (
            CurrentPageProductionSupervisor,
        )

        CurrentPageProductionSupervisor(config).validate_installation()
        path = _config_path(data_root)
        _write_config(config, path)
        startup_path = None
        if not args.no_autostart:
            startup_path = _install_autostart(manager, data_root)
        result: dict[str, Any] = {
            "installed": True,
            "config_path": str(path),
            "startup_path": startup_path,
            "observation_scope": config.observation_scope,
            "automatic_navigation_enabled": False,
        }
        if not args.no_start:
            result["start"] = _start(data_root)
    elif args.action == "start":
        result = _start(data_root)
    elif args.action == "status":
        result = {
            "process_running": _fresh_supervisor_status(data_root) is not None,
            "status": _read_json(_status_path(data_root)),
            "config_path": str(_config_path(data_root)),
            "startup_installed": _autostart_installed(),
        }
    elif args.action == "stop":
        result = _stop(data_root)
    else:
        startup_path = _remove_autostart()
        result = {"startup_removed": True, "startup_path": startup_path}
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
