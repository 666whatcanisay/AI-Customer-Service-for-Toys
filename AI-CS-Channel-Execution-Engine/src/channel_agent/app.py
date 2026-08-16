from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path
from threading import Event

from .config import AgentConfigError, load_agent_config
from .runtime import build_runtime


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI-CS Channel Agent Foundation V1")
    parser.add_argument(
        "command",
        choices=("run", "check-config"),
        nargs="?",
        default="run",
    )
    parser.add_argument(
        "--config",
        default="config/channel-agent.json",
        help="Path to the credential-free JSON configuration.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Register, send one heartbeat, then stop (validation only).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config_path = Path(args.config).resolve()
    try:
        config = load_agent_config(config_path)
    except AgentConfigError as exc:
        print(f"Channel Agent 配置错误：{exc}", file=sys.stderr)
        return 1

    if args.command == "check-config":
        print(json.dumps(config.public_view(), ensure_ascii=False, indent=2))
        return 0

    log_directory = config.log_directory
    if not log_directory.is_absolute():
        log_directory = config_path.parent / log_directory
    runtime = build_runtime(
        config,
        log_path=str(log_directory.resolve() / "channel-agent.jsonl"),
    )
    stop_event = Event()

    def request_stop(_signum=None, _frame=None) -> None:  # type: ignore[no-untyped-def]
        stop_event.set()

    for signame in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signame, None)
        if sig is not None:
            signal.signal(sig, request_stop)

    if args.once:
        snapshot = runtime.start(background_heartbeat=False)
        if snapshot.status.value != "ONLINE":
            runtime.close()
            return 2
        runtime.heartbeat_once()
        final = runtime.stop()
        runtime.close()
        return 0 if final.status.value == "STOPPED" else 4

    return runtime.run_forever(stop_event)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
