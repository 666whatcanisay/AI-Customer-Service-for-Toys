from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from channel_agent.controlled_reply_pilot import (
    ControlledReplyPilotError,
    ControlledReplyPilotOrchestrator,
    post_approved_reply_http,
)
from channel_agent.controlled_send_grant import ControlledPilotSendWindowStore
from channel_engine.customer_assistant import SQLiteConversationBuffer


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview and execute one human-confirmed or exact-answer AUTO Pilot "
            "through the existing approved-reply endpoint."
        )
    )
    parser.add_argument("--data-root", default=".runtime/pdd-login-observation-v1")
    parser.add_argument("--bridge-url", default="http://127.0.0.1:8430")
    parser.add_argument("--allowed-origin", default="http://127.0.0.1:8421")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_policy_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--policy-revision", type=int, required=True)
        command.add_argument("--whitelist-revision", required=True)

    preview_manual = subparsers.add_parser("preview-manual")
    add_policy_arguments(preview_manual)

    send_manual = subparsers.add_parser("send-manual")
    add_policy_arguments(send_manual)
    send_manual.add_argument("--confirmation-token", required=True)
    send_manual.add_argument("--operator-reference", required=True)
    send_manual.add_argument("--execute-real-send", action="store_true")

    preview_auto = subparsers.add_parser("preview-auto")
    add_policy_arguments(preview_auto)

    run_auto = subparsers.add_parser("run-auto-once")
    add_policy_arguments(run_auto)
    run_auto.add_argument("--confirmation-token", required=True)
    run_auto.add_argument("--operator-reference", required=True)
    run_auto.add_argument("--timeout-seconds", type=float, default=300.0)
    run_auto.add_argument("--execute-real-send", action="store_true")

    subparsers.add_parser("status")
    subparsers.add_parser("revoke")
    return parser


def _orchestrator(args: argparse.Namespace) -> ControlledReplyPilotOrchestrator:
    data_root = Path(args.data_root).resolve()
    assistant_root = data_root / "runtime" / "real-pdd-assistant"
    return ControlledReplyPilotOrchestrator(
        feed_path=assistant_root / "assistant-feed.json",
        buffer=SQLiteConversationBuffer(
            assistant_root / "conversation-buffer.sqlite3",
            clock=lambda: datetime.now(UTC),
        ),
        pilot_window_store=ControlledPilotSendWindowStore(
            assistant_root / "controlled-pilot-send-window.sqlite3"
        ),
        state_root=assistant_root / "controlled-reply-pilot",
        post_approved_reply=post_approved_reply_http(
            bridge_url=args.bridge_url,
            allowed_origin=args.allowed_origin,
        ),
    )


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _require_execute_flag(args: argparse.Namespace) -> None:
    if not args.execute_real_send:
        raise ControlledReplyPilotError(
            "real send requires the explicit --execute-real-send flag",
            error_code="EXPLICIT_REAL_SEND_FLAG_REQUIRED",
        )


def _status(orchestrator: ControlledReplyPilotOrchestrator) -> dict[str, object]:
    now = datetime.now(UTC)
    active = orchestrator.pilot_windows.active(now=now)
    return {
        "production_real_send_enabled": False,
        "controlled_pilot_send_enabled": active is not None,
        "active_window": (
            {
                "window_id": active.window_id,
                "mode": active.mode,
                "store_id": active.store_id,
                "test_buyer_hash": active.test_buyer_hash,
                "conversation_id": active.conversation_id,
                "expires_at": active.expires_at.isoformat(),
                "max_successes": active.max_successes,
            }
            if active is not None
            else None
        ),
        "manual_preview_present": orchestrator.manual_preview_path.is_file(),
        "auto_preview_present": orchestrator.auto_preview_path.is_file(),
        "stage_b_baseline_present": orchestrator.baseline_path.is_file(),
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    orchestrator = _orchestrator(args)
    try:
        if args.command == "preview-manual":
            preview, candidate, reply_text = orchestrator.preview_manual(
                policy_revision=args.policy_revision,
                whitelist_revision=args.whitelist_revision,
            )
            _print(
                {
                    "stage": "MANUAL_CONFIRM",
                    "confirmation_token": preview.confirmation_token,
                    "expires_at": preview.expires_at.isoformat(),
                    "target": candidate.model_dump(mode="json"),
                    "reply_text": reply_text,
                    "real_send_executed": False,
                }
            )
            return 0
        if args.command == "send-manual":
            _require_execute_flag(args)
            response = orchestrator.send_manual(
                confirmation_token=args.confirmation_token,
                operator_reference=args.operator_reference,
                policy_revision=args.policy_revision,
                whitelist_revision=args.whitelist_revision,
            )
            _print(response.model_dump(mode="json"))
            return 0
        if args.command == "preview-auto":
            preview, baseline, approved_reply = orchestrator.preview_auto(
                policy_revision=args.policy_revision,
                whitelist_revision=args.whitelist_revision,
            )
            _print(
                {
                    "stage": "AUTO_POLICY",
                    "confirmation_token": preview.confirmation_token,
                    "expires_at": preview.expires_at.isoformat(),
                    "stage_b_baseline": baseline.model_dump(mode="json"),
                    "approved_reply_text": approved_reply,
                    "real_send_executed": False,
                }
            )
            return 0
        if args.command == "run-auto-once":
            _require_execute_flag(args)
            response = orchestrator.run_auto_once(
                confirmation_token=args.confirmation_token,
                operator_reference=args.operator_reference,
                policy_revision=args.policy_revision,
                whitelist_revision=args.whitelist_revision,
                timeout_seconds=args.timeout_seconds,
            )
            _print(response.model_dump(mode="json"))
            return 0
        if args.command == "status":
            _print(_status(orchestrator))
            return 0
        if args.command == "revoke":
            orchestrator.revoke()
            _print(_status(orchestrator))
            return 0
    except ControlledReplyPilotError as exc:
        _print({"status": "BLOCKED", "error_code": exc.error_code})
        return 4
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
