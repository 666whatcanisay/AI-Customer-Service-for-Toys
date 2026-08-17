from __future__ import annotations

from pathlib import Path


OPERATOR_PAUSE_REQUEST_NAME = "operator-safe-stop.request"


def operator_pause_path(data_root: str | Path) -> Path:
    return Path(data_root) / "runtime" / OPERATOR_PAUSE_REQUEST_NAME


def request_operator_pause(data_root: str | Path) -> Path:
    path = operator_pause_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("pause\n", encoding="ascii")
    return path


def clear_operator_pause(data_root: str | Path) -> None:
    operator_pause_path(data_root).unlink(missing_ok=True)


def operator_pause_requested(data_root: str | Path) -> bool:
    return operator_pause_path(data_root).is_file()


__all__ = [
    "OPERATOR_PAUSE_REQUEST_NAME",
    "clear_operator_pause",
    "operator_pause_path",
    "operator_pause_requested",
    "request_operator_pause",
]
