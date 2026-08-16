from __future__ import annotations

import argparse
import json
from pathlib import Path

from channel_agent.current_page_production import (
    CurrentPageProductionConfig,
    CurrentPageProductionSupervisor,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Own the single-machine current-conversation PDD AUTO runtime. "
            "This process never navigates to another conversation."
        )
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = CurrentPageProductionConfig.load(Path(args.config).resolve())
    supervisor = CurrentPageProductionSupervisor(
        config,
        poll_seconds=max(args.poll_seconds, 0.25),
    )
    if args.once:
        supervisor.validate_installation()
        print(json.dumps(supervisor.run_once(), ensure_ascii=False, indent=2))
        return 0
    supervisor.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
