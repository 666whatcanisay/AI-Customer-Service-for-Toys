from __future__ import annotations

import argparse
import json
from pathlib import Path

from channel_agent.pdd_replay_approval import (
    approve_replay_fixture,
    initialize_approval_registry,
    validate_replay_approval,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage immutable real PDD Replay approvals.")
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--registry", type=Path, required=True)
    initialize.add_argument("--key", type=Path, required=True)
    approve = commands.add_parser("approve")
    approve.add_argument("--fixture", type=Path, required=True)
    approve.add_argument("--registry", type=Path, required=True)
    approve.add_argument("--key", type=Path, required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--reason", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--fixture", type=Path, required=True)
    verify.add_argument("--registry", type=Path, required=True)
    verify.add_argument("--key", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "init":
        initialize_approval_registry(args.registry, args.key)
        result = {"status": "PASS", "registry": str(args.registry.resolve())}
    elif args.command == "approve":
        manifest = approve_replay_fixture(
            args.fixture,
            args.registry,
            args.key,
            reviewer_reference=args.reviewer,
            approval_reason=args.reason,
        )
        result = {
            "status": "PASS",
            "approval_id": manifest.approval_id,
            "fixture_sha256": manifest.fixture_sha256,
            "replay_export_allowed": True,
        }
    else:
        manifest = validate_replay_approval(args.fixture, args.registry, args.key)
        result = {
            "status": "PASS",
            "approval_id": manifest.approval_id,
            "fixture_sha256": manifest.fixture_sha256,
        }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
