from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .config import BrowserConfig
from .models import ComponentHealth, ComponentStatus, utc_now_text


class BrowserError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BrowserSnapshot:
    chrome_status: str
    chrome_path: str | None
    profile_status: str
    profile_reference: str
    process_status: str
    session_status: str
    checked_at: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "chrome_status": self.chrome_status,
            "chrome_path": self.chrome_path,
            "profile_status": self.profile_status,
            "profile_reference": self.profile_reference,
            "process_status": self.process_status,
            "session_status": self.session_status,
            "checked_at": self.checked_at,
        }


class WindowsBrowserManager:
    """Chrome and isolated-profile lifecycle without login or page automation."""

    MARKER_NAME = ".ai-cs-agent-profile.json"

    def __init__(self, home: Path, config: BrowserConfig) -> None:
        self.home = home.resolve()
        self.config = config

    def detect_chrome(self) -> Path:
        candidates: list[Path] = []
        if self.config.chrome_path:
            configured = Path(os.path.expandvars(self.config.chrome_path)).expanduser()
            candidates.append(configured)
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = os.environ.get(variable)
            if root:
                candidates.append(
                    Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
                )
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
            except OSError:
                continue
            if resolved.is_file() and resolved.name.casefold() == "chrome.exe":
                return resolved
        raise BrowserError("Chrome is not available at an approved location")

    def profile_path(self) -> Path:
        configured = Path(os.path.expandvars(self.config.profile_directory)).expanduser()
        path = configured if configured.is_absolute() else self.home / configured
        resolved = path.resolve()
        for default_root in self._default_profile_roots():
            if resolved == default_root or resolved.is_relative_to(default_root):
                raise BrowserError("the user default Chrome profile is forbidden")
        if resolved == self.home or not resolved.is_relative_to(self.home):
            raise BrowserError("browser profile must be isolated inside the Agent home")
        return resolved

    def initialize_profile(self) -> Path:
        path = self.profile_path()
        path.mkdir(parents=True, exist_ok=True)
        marker = path / self.MARKER_NAME
        value = {
            "schema_version": "1.0",
            "purpose": "AI-CS-Agent dedicated Chrome profile",
            "cookie_export_allowed": False,
            "created_or_checked_at": utc_now_text(),
        }
        temporary = marker.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, marker)
        return path

    def health_check(self) -> ComponentHealth:
        try:
            chrome = self.detect_chrome()
            profile = self.profile_path()
            status = ComponentStatus.HEALTHY if profile.exists() else ComponentStatus.DEGRADED
            return ComponentHealth(
                status=status,
                reason_code="BROWSER_READY" if profile.exists() else "PROFILE_NOT_INITIALIZED",
                details={
                    "chrome_available": True,
                    "profile_initialized": profile.exists(),
                    "process_running": False,
                    "login_observed": False,
                },
            )
        except BrowserError:
            return ComponentHealth(
                status=ComponentStatus.UNAVAILABLE,
                reason_code="CHROME_UNAVAILABLE",
                details={
                    "chrome_available": False,
                    "profile_initialized": False,
                    "process_running": False,
                    "login_observed": False,
                },
            )

    def snapshot(self) -> BrowserSnapshot:
        chrome = self.detect_chrome()
        profile = self.profile_path()
        return BrowserSnapshot(
            chrome_status="AVAILABLE",
            chrome_path=str(chrome),
            profile_status="INITIALIZED" if profile.exists() else "MISSING",
            profile_reference=self.config.profile_directory,
            process_status="STOPPED",
            session_status="AUTH_REQUIRED",
            checked_at=utc_now_text(),
        )

    @staticmethod
    def _default_profile_roots() -> tuple[Path, ...]:
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            return ()
        roots = [Path(local) / "Google" / "Chrome" / "User Data"]
        return tuple(path.resolve() for path in roots)
