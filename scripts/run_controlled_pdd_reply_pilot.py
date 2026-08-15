from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from channel_agent.controlled_auto_runtime import (
    ControlledAutoDecisionLedger,
    ControlledAutoRuntimeStateV1,
    ControlledAutoRuntimeStateStore,
)
from channel_agent.binding import atomic_write_bytes
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
            "Operate human-confirmed, exact-answer Pilot, or per-message "
            "quality-gated LOW-risk sends through the sole approved-reply endpoint."
        )
    )
    parser.add_argument("--data-root", default=".runtime/pdd-login-observation-v1")
    parser.add_argument(
        "--assistant-root",
        default=None,
        help="Override the Host assistant runtime containing the durable buffer/feed.",
    )
    parser.add_argument("--bridge-url", default="http://127.0.0.1:8430")
    parser.add_argument("--allowed-origin", default="http://127.0.0.1:8421")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_policy_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--policy-revision", type=int, required=True)
        command.add_argument("--whitelist-revision", required=True)

    def add_auto_policy_mode(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--policy-mode",
            choices=("AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"),
            default="AUTO_ALL_MESSAGES_V1",
        )

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

    arm_pilot = subparsers.add_parser("arm-general-auto-pilot")
    add_policy_arguments(arm_pilot)
    add_auto_policy_mode(arm_pilot)
    arm_pilot.add_argument("--operator-reference", required=True)

    general_auto = subparsers.add_parser("send-general-auto-once")
    add_policy_arguments(general_auto)
    add_auto_policy_mode(general_auto)
    general_auto.add_argument("--operator-reference", required=True)
    general_auto.add_argument(
        "--deployment-scope",
        choices=("PILOT", "PRODUCTION_AUTO"),
        required=True,
    )
    general_auto.add_argument("--execute-real-send", action="store_true")

    kill_switch = subparsers.add_parser("enable-kill-switch")
    kill_switch.add_argument("--operator-reference", required=True)
    kill_switch.add_argument("--reason", required=True)

    activate = subparsers.add_parser("activate-production-auto")
    add_policy_arguments(activate)
    add_auto_policy_mode(activate)
    activate.add_argument("--operator-reference", required=True)
    activate.add_argument("--ai-cs-store-id", required=True)
    activate.add_argument("--platform-store-id", required=True)
    activate.add_argument("--reason", required=True)
    activate.add_argument("--confirmation-phrase", required=True)

    prepare_resume = subparsers.add_parser("prepare-production-auto-resume")
    add_policy_arguments(prepare_resume)
    add_auto_policy_mode(prepare_resume)
    prepare_resume.add_argument("--operator-reference", required=True)
    prepare_resume.add_argument("--ai-cs-store-id", required=True)
    prepare_resume.add_argument("--platform-store-id", required=True)
    prepare_resume.add_argument("--reason", required=True)

    production = subparsers.add_parser("run-production-auto")
    production.add_argument("--operator-reference", required=True)
    production.add_argument("--poll-seconds", type=float, default=0.5)
    production.add_argument("--exit-after-successes", type=int, default=0)
    production.add_argument("--execute-real-send", action="store_true")

    subparsers.add_parser("status")
    subparsers.add_parser("revoke")
    sync_feed = subparsers.add_parser("sync-feed")
    sync_feed.add_argument(
        "--policy-mode",
        choices=("MANUAL_CONFIRM", "AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"),
        default="MANUAL_CONFIRM",
    )
    return parser


def _orchestrator(args: argparse.Namespace) -> ControlledReplyPilotOrchestrator:
    data_root = Path(args.data_root).resolve()
    assistant_root = _assistant_root(data_root, args.assistant_root)
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
        store_identity_provider=lambda: _current_store_identity(data_root),
    )


def _assistant_root(data_root: Path, override: str | None = None) -> Path:
    return (
        Path(override).resolve()
        if override
        else data_root / "runtime" / "real-pdd-assistant"
    )


def _runtime_store(
    data_root: Path,
    assistant_root: Path | None = None,
) -> ControlledAutoRuntimeStateStore:
    return ControlledAutoRuntimeStateStore(
        (assistant_root or _assistant_root(data_root))
        / "controlled-auto-runtime.sqlite3"
    )


def _sync_feed(
    orchestrator: ControlledReplyPilotOrchestrator,
    *,
    policy_mode: str,
    real_send_enabled: bool = False,
    auto_reply_enabled: bool = False,
) -> dict[str, object]:
    waiting = [
        (context, package)
        for context, package in orchestrator.buffer.stored_replies()
        if package.state == "WAITING_APPROVAL"
        and package.action == "SUGGEST_REPLY"
        and package.reply_content
    ]
    if not waiting:
        raise ControlledReplyPilotError(
            "no durable reply is waiting for approval",
            error_code="PILOT_REPLY_NOT_AVAILABLE",
        )
    context, package = max(waiting, key=lambda item: item[1].generated_at)
    current_ids = context.current_turn_message_ids
    if not current_ids:
        raise ControlledReplyPilotError(
            "the durable reply has no customer message identity",
            error_code="PILOT_REPLY_MESSAGE_ID_MISSING",
        )
    feed: dict[str, object] = {
        "safety": {
            "realSend": real_send_enabled,
            "autoReply": auto_reply_enabled,
        },
        "reply": {
            "decisionId": package.decision_id,
            "messageId": current_ids[-1],
            "conversationId": package.conversation_id,
            "answer": package.reply_content,
            "state": package.state,
            "qualityStatus": package.quality_gate_status,
            "policyMode": policy_mode,
            "action": package.ai_cs_action,
        },
        "updatedAt": datetime.now(UTC).isoformat(),
    }
    atomic_write_bytes(
        orchestrator.feed_path,
        json.dumps(
            feed,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )
    return feed


def _current_store_identity(data_root: Path) -> tuple[str, str]:
    value = json.loads(
        (data_root / "runtime" / "channel-agent-state.json").read_text(
            encoding="utf-8"
        )
    )
    ai_cs_store_id = value.get("active_store_id")
    platform_store_id = value.get("pdd_store_id")
    if (
        not isinstance(ai_cs_store_id, str)
        or not ai_cs_store_id.strip()
        or not isinstance(platform_store_id, str)
        or not platform_store_id.strip()
    ):
        raise ControlledReplyPilotError(
            "current double Store identity is unavailable",
            error_code="DOUBLE_STORE_IDENTITY_UNAVAILABLE",
        )
    return ai_cs_store_id.strip(), platform_store_id.strip()


def _public_status_path(data_root: Path) -> Path:
    return data_root / "runtime" / "controlled-auto-public-status.json"


def _toggle_request_path(data_root: Path) -> Path:
    return data_root / "runtime" / "controlled-auto-toggle.request"


def _repair_request_path(data_root: Path) -> Path:
    return data_root / "runtime" / "controlled-auto-repair.request"


def _publish_public_status(
    data_root: Path,
    state: ControlledAutoRuntimeStateV1,
    *,
    runner_active: bool,
    control_error_code: str | None = None,
) -> None:
    atomic_write_bytes(
        _public_status_path(data_root),
        json.dumps(
            {
                "schema_version": "controlled-auto-public-status.v1",
                "runtime_mode": state.runtime_mode,
                "production_real_send_enabled": (
                    state.production_real_send_enabled
                ),
                "controlled_store_auto_enabled": (
                    state.controlled_store_auto_enabled
                ),
                "policy_mode": state.policy_mode,
                "kill_switch_enabled": state.kill_switch_enabled,
                "ai_cs_store_id": state.ai_cs_store_id,
                "platform_store_id": state.platform_store_id,
                "state_revision": state.revision,
                "state_reason": state.reason,
                "runner_active": runner_active,
                "runner_pid": os.getpid(),
                "control_error_code": control_error_code,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )


def _retryable_production_candidate_error(error_code: str) -> bool:
    return error_code in {
        "PILOT_DOUBLE_STORE_IDENTITY_UNAVAILABLE",
    }


def _consume_desktop_toggle(
    data_root: Path,
    runtime_store: ControlledAutoRuntimeStateStore,
) -> tuple[ControlledAutoRuntimeStateV1, str | None]:
    request_path = _toggle_request_path(data_root)
    state = runtime_store.load()
    if not request_path.is_file():
        return state, None
    error_code: str | None = None
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        requested_at = datetime.fromisoformat(str(payload["requested_at"]))
        if requested_at.tzinfo is None:
            raise ValueError("toggle time must be timezone-aware")
        if (datetime.now(UTC) - requested_at.astimezone(UTC)).total_seconds() > 120:
            raise ControlledReplyPilotError(
                "desktop AUTO toggle expired",
                error_code="AUTO_TOGGLE_EXPIRED",
            )
        if payload.get("schema_version") != "controlled-auto-toggle-request.v1":
            raise ValueError("toggle schema is invalid")
        if payload.get("human_intent") is not True:
            raise ValueError("toggle requires human intent")
        target_enabled = payload.get("target_enabled")
        if not isinstance(target_enabled, bool):
            raise ValueError("toggle target is invalid")
        operator = str(payload.get("operator_reference") or "desktop-local-operator")
        if target_enabled:
            agent_state = json.loads(
                (data_root / "runtime" / "channel-agent-state.json").read_text(
                    encoding="utf-8"
                )
            )
            if (
                agent_state.get("identity_status") != "ACTIVE"
                or agent_state.get("pdd_login_state") != "CUSTOMER_SERVICE_READY"
                or agent_state.get("observer_status") != "OBSERVING"
            ):
                raise ControlledReplyPilotError(
                    "live PDD runtime is not ready for AUTO",
                    error_code="AUTO_RUNTIME_NOT_READY",
                )
            observed = _current_store_identity(data_root)
            frozen = (state.ai_cs_store_id, state.platform_store_id)
            if None in frozen or observed != frozen:
                raise ControlledReplyPilotError(
                    "live double Store identity does not match paused AUTO scope",
                    error_code="AUTO_STORE_SCOPE_MISMATCH",
                )
            if state.policy_mode not in {"AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"}:
                raise ControlledReplyPilotError(
                    "paused AUTO policy is not resumable",
                    error_code="AUTO_POLICY_NOT_RESUMABLE",
                )
            state = runtime_store.activate_production_auto(
                ai_cs_store_id=observed[0],
                platform_store_id=observed[1],
                policy_revision=state.policy_revision,
                whitelist_revision=state.whitelist_revision,
                operator=operator[:160],
                reason="USER_RESUMED_PRODUCTION_AUTO_FROM_DESKTOP",
                policy_mode=state.policy_mode,
            )
        else:
            state = runtime_store.pause_production_auto(
                operator=operator[:160],
                reason="USER_PAUSED_PRODUCTION_AUTO_FROM_DESKTOP",
            )
    except ControlledReplyPilotError as exc:
        error_code = exc.error_code
        state = runtime_store.load()
    except (KeyError, OSError, UnicodeError, ValueError, json.JSONDecodeError):
        error_code = "AUTO_TOGGLE_REQUEST_INVALID"
        state = runtime_store.load()
    finally:
        request_path.unlink(missing_ok=True)
    return state, error_code


def _consume_desktop_repair(
    data_root: Path,
    runtime_store: ControlledAutoRuntimeStateStore,
) -> tuple[ControlledAutoRuntimeStateV1, str | None]:
    """Repair only the paused AUTO scope after explicit local human intent."""

    request_path = _repair_request_path(data_root)
    state = runtime_store.load()
    if not request_path.is_file():
        return state, None
    error_code: str | None = None
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        requested_at = datetime.fromisoformat(str(payload["requested_at"]))
        if requested_at.tzinfo is None:
            raise ValueError("repair time must be timezone-aware")
        if (datetime.now(UTC) - requested_at.astimezone(UTC)).total_seconds() > 120:
            raise ControlledReplyPilotError(
                "desktop AUTO repair expired",
                error_code="AUTO_REPAIR_EXPIRED",
            )
        if payload.get("schema_version") != "controlled-auto-repair-request.v1":
            raise ValueError("repair schema is invalid")
        if payload.get("human_intent") is not True:
            raise ValueError("repair requires human intent")
        observed = _current_store_identity(data_root)
        requested = (
            str(payload.get("ai_cs_store_id") or "").strip(),
            str(payload.get("platform_store_id") or "").strip(),
        )
        if observed != requested:
            raise ControlledReplyPilotError(
                "live double Store identity changed during repair",
                error_code="AUTO_REPAIR_STORE_SCOPE_MISMATCH",
            )
        policy_mode = (
            state.policy_mode
            if state.policy_mode in {"AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"}
            else "AUTO_ALL_MESSAGES_V1"
        )
        state = runtime_store.prepare_production_auto_resume(
            ai_cs_store_id=observed[0],
            platform_store_id=observed[1],
            policy_revision=state.policy_revision,
            whitelist_revision=state.whitelist_revision,
            operator=str(
                payload.get("operator_reference") or "desktop-local-operator"
            )[:160],
            reason="USER_REPAIRED_PRODUCTION_AUTO_FROM_DESKTOP",
            policy_mode=policy_mode,
        )
    except ControlledReplyPilotError as exc:
        error_code = exc.error_code
        state = runtime_store.load()
    except (KeyError, OSError, UnicodeError, ValueError, json.JSONDecodeError):
        error_code = "AUTO_REPAIR_REQUEST_INVALID"
        state = runtime_store.load()
    finally:
        request_path.unlink(missing_ok=True)
    return state, error_code


def _renew_observer_if_needed(data_root: Path) -> None:
    state_path = data_root / "runtime" / "channel-agent-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return
    if (
        state.get("pdd_login_state") != "CUSTOMER_SERVICE_READY"
        or state.get("observer_status") != "SESSION_LIMIT_REACHED"
    ):
        return
    request_path = data_root / "runtime" / "pdd-observer-restart.request"
    if request_path.exists():
        return
    atomic_write_bytes(
        request_path,
        (json.dumps(
            {
                "schema_version": "channel-agent-pdd-observer-restart-request.v1",
                "requested_at": datetime.now(UTC).isoformat(),
                "human_intent": True,
                "reason": "PRODUCTION_AUTO_OBSERVER_SESSION_RENEWAL",
            },
            separators=(",", ":"),
        ) + "\n").encode("utf-8"),
    )


def _record_auto_reply_success(
    data_root: Path,
    *,
    decision_id: str,
    conversation_id: str,
    receipt_id: str,
) -> None:
    """Publish a privacy-minimal success index for the desktop projection.

    Reply text remains in the existing Host snapshot.  The local index only
    proves that this exact Decision reached a terminal successful Receipt, so
    the UI can stop presenting an already-sent reply as waiting for a human.
    """

    path = data_root / "runtime" / "controlled-auto-successes.json"
    records: list[dict[str, str]] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            isinstance(payload, dict)
            and payload.get("schema_version") == "controlled-auto-successes.v1"
            and isinstance(payload.get("items"), list)
        ):
            for item in payload["items"]:
                if (
                    isinstance(item, dict)
                    and item.get("decision_id") == decision_id
                    and item.get("conversation_id") == conversation_id
                    and item.get("receipt_id") == receipt_id
                ):
                    return
            records = [
                item
                for item in payload["items"]
                if isinstance(item, dict)
                and isinstance(item.get("decision_id"), str)
                and item.get("decision_id") != decision_id
            ]
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        records = []
    records.append(
        {
            "decision_id": decision_id,
            "conversation_id": conversation_id,
            "receipt_id": receipt_id,
            "sent_at": datetime.now(UTC).isoformat(),
        }
    )
    atomic_write_bytes(
        path,
        (json.dumps(
            {
                "schema_version": "controlled-auto-successes.v1",
                "items": records[-100:],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n").encode("utf-8"),
    )


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _require_execute_flag(args: argparse.Namespace) -> None:
    if not args.execute_real_send:
        raise ControlledReplyPilotError(
            "real send requires the explicit --execute-real-send flag",
            error_code="EXPLICIT_REAL_SEND_FLAG_REQUIRED",
        )


def _status(
    orchestrator: ControlledReplyPilotOrchestrator,
    runtime_store: ControlledAutoRuntimeStateStore,
) -> dict[str, object]:
    now = datetime.now(UTC)
    active = orchestrator.pilot_windows.active(now=now)
    runtime = runtime_store.load()
    return {
        "runtime": runtime.model_dump(mode="json"),
        "production_real_send_enabled": runtime.production_real_send_enabled,
        "controlled_pilot_send_enabled": runtime.controlled_pilot_send_enabled,
        "controlled_store_auto_enabled": runtime.controlled_store_auto_enabled,
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
    data_root = Path(args.data_root).resolve()
    assistant_root = _assistant_root(data_root, args.assistant_root)
    runtime_store = _runtime_store(data_root, assistant_root)
    try:
        if args.command == "sync-feed":
            _print(
                _sync_feed(
                    orchestrator,
                    policy_mode=args.policy_mode,
                )
            )
            return 0
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
        if args.command == "arm-general-auto-pilot":
            state = runtime_store.set_pilot(
                operator=args.operator_reference,
                reason="USER_ARMED_GENERAL_LOW_RISK_AUTO_PILOT",
                controlled_pilot_send_enabled=True,
                kill_switch_enabled=False,
                policy_revision=args.policy_revision,
                whitelist_revision=args.whitelist_revision,
                policy_mode=args.policy_mode,
            )
            _print(state.model_dump(mode="json"))
            return 0
        if args.command == "send-general-auto-once":
            _require_execute_flag(args)
            response = orchestrator.send_general_auto_current(
                operator_reference=args.operator_reference,
                policy_revision=args.policy_revision,
                whitelist_revision=args.whitelist_revision,
                deployment_scope=args.deployment_scope,
                policy_mode=args.policy_mode,
            )
            # Pilot and production share the immutable Decision ledger.  A
            # successful one-shot must not look like new work when the
            # production loop starts immediately afterwards.
            ledger = ControlledAutoDecisionLedger(
                assistant_root / "controlled-auto-decisions.sqlite3"
            )
            recorded_at = datetime.now(UTC)
            if ledger.claim_once(response.decision_id, now=recorded_at):
                ledger.finish(
                    response.decision_id,
                    outcome=response.outcome,
                    receipt_id=response.receipt_id,
                    now=recorded_at,
                )
            _print(response.model_dump(mode="json"))
            return 0 if response.outcome == "SUCCESS" else 4
        if args.command == "enable-kill-switch":
            state = runtime_store.enable_kill_switch(
                operator=args.operator_reference,
                reason=args.reason,
            )
            orchestrator.revoke()
            _print(state.model_dump(mode="json"))
            return 0
        if args.command == "activate-production-auto":
            observed = _current_store_identity(data_root)
            expected = (args.ai_cs_store_id.strip(), args.platform_store_id.strip())
            phrase = (
                f"ENABLE PRODUCTION AUTO {expected[0]} {expected[1]}"
            )
            if observed != expected:
                raise ControlledReplyPilotError(
                    "live double Store identity does not match the requested scope",
                    error_code="PRODUCTION_STORE_SCOPE_MISMATCH",
                )
            if args.confirmation_phrase.strip() != phrase:
                raise ControlledReplyPilotError(
                    "production AUTO confirmation phrase is invalid",
                    error_code="PRODUCTION_AUTO_CONFIRMATION_INVALID",
                )
            state = runtime_store.activate_production_auto(
                ai_cs_store_id=expected[0],
                platform_store_id=expected[1],
                policy_revision=args.policy_revision,
                whitelist_revision=args.whitelist_revision,
                operator=args.operator_reference,
                reason=args.reason,
                policy_mode=args.policy_mode,
            )
            _print(state.model_dump(mode="json"))
            return 0
        if args.command == "prepare-production-auto-resume":
            observed = _current_store_identity(data_root)
            expected = (args.ai_cs_store_id.strip(), args.platform_store_id.strip())
            if observed != expected:
                raise ControlledReplyPilotError(
                    "live double Store identity does not match the requested resume scope",
                    error_code="PRODUCTION_RESUME_SCOPE_MISMATCH",
                )
            state = runtime_store.prepare_production_auto_resume(
                ai_cs_store_id=expected[0],
                platform_store_id=expected[1],
                policy_revision=args.policy_revision,
                whitelist_revision=args.whitelist_revision,
                operator=args.operator_reference,
                reason=args.reason,
                policy_mode=args.policy_mode,
            )
            _print(state.model_dump(mode="json"))
            return 0
        if args.command == "run-production-auto":
            _require_execute_flag(args)
            ledger = ControlledAutoDecisionLedger(
                assistant_root / "controlled-auto-decisions.sqlite3"
            )
            successes = 0
            while True:
                state, repair_error = _consume_desktop_repair(
                    data_root, runtime_store
                )
                state, control_error = _consume_desktop_toggle(
                    data_root, runtime_store
                )
                control_error = repair_error or control_error
                _publish_public_status(
                    data_root,
                    state,
                    runner_active=True,
                    control_error_code=control_error,
                )
                if (
                    state.runtime_mode != "PRODUCTION_AUTO"
                    or not state.production_real_send_enabled
                    or not state.controlled_store_auto_enabled
                    or state.kill_switch_enabled
                ):
                    # The local desktop toggle pauses authorization, not the
                    # process that owns the toggle mailbox.  Staying alive is
                    # what makes a later explicit resume independent of Codex.
                    time.sleep(max(args.poll_seconds, 0.1))
                    continue
                _renew_observer_if_needed(data_root)
                # The formal Windows Agent persists new Decisions in the
                # shared durable buffer.  Refresh the small bridge feed from
                # that source on every production poll so unattended AUTO is
                # not dependent on somebody invoking ``sync-feed`` manually.
                try:
                    _sync_feed(
                        orchestrator,
                        policy_mode=state.policy_mode,
                        real_send_enabled=True,
                        auto_reply_enabled=True,
                    )
                except ControlledReplyPilotError as exc:
                    if exc.error_code == "PILOT_REPLY_NOT_AVAILABLE":
                        time.sleep(max(args.poll_seconds, 0.1))
                        continue
                    raise
                try:
                    candidate = orchestrator.current_general_auto_candidate(
                        policy_revision=state.policy_revision,
                        whitelist_revision=state.whitelist_revision,
                        policy_mode=state.policy_mode,
                    )
                except ControlledReplyPilotError as exc:
                    if exc.error_code == "PILOT_QUALITY_GATE_BLOCKED":
                        time.sleep(max(args.poll_seconds, 0.1))
                        continue
                    if _retryable_production_candidate_error(exc.error_code):
                        _publish_public_status(
                            data_root,
                            runtime_store.load(),
                            runner_active=True,
                            control_error_code=exc.error_code,
                        )
                        time.sleep(max(args.poll_seconds, 0.1))
                        continue
                    raise
                if candidate is None:
                    time.sleep(max(args.poll_seconds, 0.1))
                    continue
                if not ledger.claim_once(
                    candidate.decision_id,
                    now=datetime.now(UTC),
                ):
                    existing_receipt = ledger.successful_receipt(
                        candidate.decision_id
                    )
                    if existing_receipt is not None:
                        _record_auto_reply_success(
                            data_root,
                            decision_id=candidate.decision_id,
                            conversation_id=candidate.conversation_id,
                            receipt_id=existing_receipt,
                        )
                    time.sleep(max(args.poll_seconds, 0.1))
                    continue
                try:
                    response = orchestrator.send_general_auto_current(
                        operator_reference=args.operator_reference,
                        policy_revision=state.policy_revision,
                        whitelist_revision=state.whitelist_revision,
                        deployment_scope="PRODUCTION_AUTO",
                        expected_decision_id=candidate.decision_id,
                        policy_mode=state.policy_mode,
                    )
                except Exception:
                    ledger.finish(
                        candidate.decision_id,
                        outcome="BLOCKED",
                        receipt_id=None,
                        now=datetime.now(UTC),
                    )
                    runtime_store.enable_kill_switch(
                        operator="automatic-safety-controller",
                        reason="PRODUCTION_AUTO_SEND_PATH_FAILED",
                    )
                    _publish_public_status(
                        data_root,
                        runtime_store.load(),
                        runner_active=True,
                        control_error_code="PRODUCTION_AUTO_SEND_PATH_FAILED",
                    )
                    raise
                ledger.finish(
                    candidate.decision_id,
                    outcome=response.outcome,
                    receipt_id=response.receipt_id,
                    now=datetime.now(UTC),
                )
                if response.outcome != "SUCCESS":
                    paused = runtime_store.fail_closed_after_terminal(
                        outcome=response.outcome,
                        reason=response.error_code or "PRODUCTION_AUTO_SEND_NOT_CONFIRMED",
                    )
                    if (
                        paused.ai_cs_store_id is None
                        or paused.platform_store_id is None
                        or paused.policy_mode
                        not in {"AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"}
                    ):
                        try:
                            observed = _current_store_identity(data_root)
                            paused = runtime_store.prepare_production_auto_resume(
                                ai_cs_store_id=observed[0],
                                platform_store_id=observed[1],
                                policy_revision=state.policy_revision,
                                whitelist_revision=state.whitelist_revision,
                                operator="automatic-safety-controller",
                                reason=(
                                    f"{response.outcome}:"
                                    f"{response.error_code or 'PRODUCTION_AUTO_SEND_NOT_CONFIRMED'}"
                                )[:512],
                                policy_mode=(
                                    state.policy_mode
                                    if state.policy_mode
                                    in {"AUTO_LOW_RISK", "AUTO_ALL_MESSAGES_V1"}
                                    else "AUTO_ALL_MESSAGES_V1"
                                ),
                            )
                        except ControlledReplyPilotError:
                            pass
                    _publish_public_status(
                        data_root,
                        paused,
                        runner_active=True,
                        control_error_code=(
                            response.error_code
                            or "PRODUCTION_AUTO_SEND_NOT_CONFIRMED"
                        ),
                    )
                    _print(
                        {
                            "status": "PAUSED",
                            "reason": f"REAL_SEND_{response.outcome}",
                            "receipt_id": response.receipt_id,
                        }
                    )
                    time.sleep(max(args.poll_seconds, 0.1))
                    continue
                _record_auto_reply_success(
                    data_root,
                    decision_id=candidate.decision_id,
                    conversation_id=candidate.conversation_id,
                    receipt_id=response.receipt_id,
                )
                successes += 1
                if args.exit_after_successes and successes >= args.exit_after_successes:
                    _print({"status": "COMPLETED", "successes": successes})
                    return 0
        if args.command == "status":
            _print(_status(orchestrator, runtime_store))
            return 0
        if args.command == "revoke":
            orchestrator.revoke()
            runtime_store.set_pilot(
                operator="user",
                reason="USER_REVOKED",
                controlled_pilot_send_enabled=False,
                kill_switch_enabled=True,
            )
            _print(_status(orchestrator, runtime_store))
            return 0
    except ControlledReplyPilotError as exc:
        _print({"status": "BLOCKED", "error_code": exc.error_code})
        return 4
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
