from __future__ import annotations

import argparse
import json
from pathlib import Path

from channel_agent.pdd_page_port import build_sanitized_pdd_replay_fixture
from channel_agent.pdd_replay_approval import publish_immutable_fixture


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a minimal sanitized PDD replay from one bounded read-only capture."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--message-id", action="append", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    raw_bytes = args.input.read_bytes()
    if len(raw_bytes) > 2 * 1024 * 1024:
        raise SystemExit("raw read-only capture exceeds two MiB")
    raw = json.loads(raw_bytes)
    if not isinstance(raw, dict):
        raise SystemExit("raw read-only capture must be an object")
    fixture = build_sanitized_pdd_replay_fixture(
        scan=raw["scan"],
        capture=raw["capture"],
        role_map=raw["role_map"],
        target_conversation_id=args.conversation_id,
        allowed_message_ids=tuple(args.message_id),
    )
    publish_immutable_fixture(
        args.output,
        (fixture.model_dump_json(indent=2) + "\n").encode("utf-8"),
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "fixture": str(args.output.resolve()),
                "fixture_id": fixture.fixture_id,
                "message_count": len(fixture.capture["messages"]),
                "source": fixture.source,
                "sanitized": fixture.sanitized,
                "privacy_processed": True,
                "manual_review_required": True,
                "replay_export_allowed": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
