#!/usr/bin/env python3
"""Operate the fixed RC5 multi-turn acceptance conversation safely.

This is a validation/evidence tool, not a product simulator.  It never starts a
browser, reads PDD, creates an Execution, or invokes a send adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from channel_agent.client import ChannelEngineClient  # noqa: E402
from channel_agent.config import load_agent_config  # noqa: E402
from channel_agent.edge_spool import DurableEdgeSpool, EdgeObservation  # noqa: E402
from channel_agent.observation_runtime import PersistAckObservationForwarder  # noqa: E402
from channel_agent.providers import ChannelAgentProviderIngress, SyntheticPDDProvider  # noqa: E402
from channel_agent.security import WindowsDPAPITransientPayloadProtector  # noqa: E402
from channel_engine.provider import NormalizedChannelObservation  # noqa: E402


CONVERSATION_ID = "rc5-multiturn-acceptance-20260812-01"
PROVIDER_ID = "rc5-multiturn-codex-customer"
DATA_CLASS = "SYNTHETIC_ACCEPTANCE"
OLD_PREFIXES = ("rc5-current-", "rc5-ui-")
DEFAULT_RUNTIME_ROOT = (
    ROOT / ".runtime/rc5-hotstart-validation/20260811-233205/host-offline-runtime"
)
DEFAULT_EVIDENCE_ROOT = ROOT / ".runtime" / CONVERSATION_ID
DEFAULT_AGENT_DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", ROOT / ".runtime")) / (
    "AI-CS/ChannelAgent"
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


def _matches_old(conversation_id: str) -> bool:
    return any(conversation_id.startswith(prefix) for prefix in OLD_PREFIXES)


def _target_conversations(host_database: Path) -> list[str]:
    with _ro(host_database) as connection:
        rows = connection.execute(
            "SELECT DISTINCT conversation_id,payload FROM channel_agent_observations"
        ).fetchall()
    targets: list[str] = []
    for conversation_id, raw_payload in rows:
        payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
        provider_kind = payload.get("provider_kind") if isinstance(payload, dict) else None
        provider_id = payload.get("provider_id") if isinstance(payload, dict) else None
        known_old_test = _matches_old(str(conversation_id)) and provider_kind in {
            "SYNTHETIC_PDD",
            "RECORDED_REPLAY",
        }
        fixed_acceptance = (
            str(conversation_id) == CONVERSATION_ID
            and provider_kind == "SYNTHETIC_PDD"
            and provider_id == PROVIDER_ID
        )
        if known_old_test or fixed_acceptance:
            targets.append(str(conversation_id))
    return sorted(set(targets))


def _placeholders(values: list[str]) -> str:
    if not values:
        raise ValueError("an empty SQL target list is forbidden")
    return ",".join("?" for _ in values)


def _count_scope(connection: sqlite3.Connection, table: str, targets: list[str]) -> int:
    if not targets:
        return 0
    columns = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if "conversation_id" not in columns:
        return 0
    return int(
        connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE conversation_id IN ({_placeholders(targets)})",
            targets,
        ).fetchone()[0]
    )


def _scope_inventory(args: argparse.Namespace) -> dict[str, Any]:
    host = args.host_database.resolve()
    buffer = args.runtime_root.resolve() / "conversation-buffer.sqlite3"
    offline = args.runtime_root.resolve() / "offline-control.sqlite3"
    journal = args.agent_data_root.resolve() / "runtime/assistant-events.sqlite3"
    targets = _target_conversations(host)
    result: dict[str, Any] = {
        "schema_version": "rc5-multiturn-cleanup-inventory.v1",
        "captured_at": datetime.now(UTC).isoformat(),
        "target_prefixes": list(OLD_PREFIXES),
        "target_conversations": targets,
        "fixed_conversation_id": CONVERSATION_ID,
        "fixed_provider_id": PROVIDER_ID,
        "databases": {},
    }
    specifications = {
        "host": (
            host,
            (
                "channel_agent_observations",
                "channel_agent_assistant_events",
                "channel_agent_assistant_snapshots",
            ),
        ),
        "buffer": (buffer, ("assistant_buffer_messages", "assistant_buffer_turns")),
        "offline": (
            offline,
            (
                "conversation_revisions",
                "offline_observation_revisions",
                "offline_reply_decisions",
                "execution_preparations",
            ),
        ),
    }
    for label, (path, tables) in specifications.items():
        with _ro(path) as connection:
            result["databases"][label] = {
                "path": str(path),
                "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
                "target_counts": {
                    table: _count_scope(connection, table, targets) for table in tables
                },
                "fixed_counts": {
                    table: _count_scope(connection, table, [CONVERSATION_ID])
                    for table in tables
                },
            }
    with _ro(offline) as connection:
        trace_ids = [
            row[0]
            for row in connection.execute(
                f"SELECT DISTINCT trace_id FROM offline_observation_revisions "
                f"WHERE conversation_id IN ({_placeholders(targets)})",
                targets,
            ).fetchall()
        ] if targets else []
        result["databases"]["offline"]["target_counts"].update(
            {
                "pipeline_trace_steps": (
                    int(
                        connection.execute(
                            f"SELECT COUNT(*) FROM pipeline_trace_steps "
                            f"WHERE trace_id IN ({_placeholders(trace_ids)})",
                            trace_ids,
                        ).fetchone()[0]
                    )
                    if trace_ids
                    else 0
                ),
                "context_history_audits": (
                    int(
                        connection.execute(
                            f"SELECT COUNT(*) FROM context_history_audits "
                            f"WHERE trace_id IN ({_placeholders(trace_ids)})",
                            trace_ids,
                        ).fetchone()[0]
                    )
                    if trace_ids
                    and connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name='context_history_audits'"
                    ).fetchone()
                    else 0
                ),
            }
        )
        result["safety_counts"] = {
            "offline_receipts_total": int(
                connection.execute("SELECT COUNT(*) FROM offline_receipts").fetchone()[0]
            ),
            "real_receipt_success": int(
                connection.execute(
                    "SELECT COUNT(*) FROM offline_receipts "
                    "WHERE receipt_kind='REAL' AND outcome='SUCCESS'"
                ).fetchone()[0]
            ),
        }
    with _ro(host) as connection:
        result["safety_counts"].update(
            {
                "executions_total": int(
                    connection.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
                ),
                "execution_receipts_total": int(
                    connection.execute("SELECT COUNT(*) FROM execution_receipts").fetchone()[0]
                ),
                "channel_agent_receipts_total": int(
                    connection.execute("SELECT COUNT(*) FROM channel_agent_receipts").fetchone()[0]
                ),
            }
        )
        fixed = connection.execute(
            "SELECT COUNT(*),COALESCE(MIN(source_sequence),0),COALESCE(MAX(source_sequence),0) "
            "FROM channel_agent_observations WHERE conversation_id=?",
            (CONVERSATION_ID,),
        ).fetchone()
        result["fixed_cursor_baseline"] = {
            "observation_count": int(fixed[0]),
            "minimum_sequence": int(fixed[1]),
            "maximum_sequence": int(fixed[2]),
            "expected_initial_sequence": 0,
        }
    if journal.is_file():
        with _ro(journal) as connection:
            event_count = 0
            for (payload_json,) in connection.execute(
                "SELECT payload_json FROM assistant_events"
            ).fetchall():
                payload = json.loads(payload_json)
                if payload.get("conversation_id") in targets:
                    event_count += 1
            cursor_count = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM assistant_read_cursors "
                    f"WHERE conversation_id IN ({_placeholders(targets)})",
                    targets,
                ).fetchone()[0]
            ) if targets else 0
        result["databases"]["agent_journal"] = {
            "path": str(journal),
            "target_counts": {
                "assistant_events": event_count,
                "assistant_read_cursors": cursor_count,
            },
        }
    return result


def _inventory(args: argparse.Namespace) -> int:
    result = _scope_inventory(args)
    _write_json(args.output, result)
    print(args.output)
    return 0


def _cleanup_old(args: argparse.Namespace) -> int:
    before = _scope_inventory(args)
    targets = list(before["target_conversations"])
    if not args.execute:
        before["mode"] = "DRY_RUN"
        _write_json(args.output, before)
        print(args.output)
        return 0
    if not targets:
        raise RuntimeError("cleanup execute requires a non-empty dry-run target list")
    host = args.host_database.resolve()
    buffer = args.runtime_root.resolve() / "conversation-buffer.sqlite3"
    offline = args.runtime_root.resolve() / "offline-control.sqlite3"
    journal = args.agent_data_root.resolve() / "runtime/assistant-events.sqlite3"
    placeholders = _placeholders(targets)

    with _ro(offline) as connection:
        target_decision_ids = [
            str(row[0])
            for row in connection.execute(
                f"SELECT decision_id FROM offline_reply_decisions "
                f"WHERE conversation_id IN ({placeholders})",
                targets,
            ).fetchall()
        ]

    with sqlite3.connect(offline) as connection:
        connection.execute("BEGIN IMMEDIATE")
        trace_ids = [
            row[0]
            for row in connection.execute(
                f"SELECT DISTINCT trace_id FROM offline_observation_revisions "
                f"WHERE conversation_id IN ({placeholders})",
                targets,
            ).fetchall()
        ]
        if trace_ids:
            trace_placeholders = _placeholders(trace_ids)
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='context_history_audits'"
            ).fetchone():
                connection.execute(
                    f"DELETE FROM context_history_audits "
                    f"WHERE trace_id IN ({trace_placeholders})",
                    trace_ids,
                )
            connection.execute(
                f"DELETE FROM pipeline_trace_steps WHERE trace_id IN ({trace_placeholders})",
                trace_ids,
            )
        for table in (
            "execution_preparations",
            "offline_reply_decisions",
            "offline_observation_revisions",
            "conversation_revisions",
        ):
            connection.execute(
                f"DELETE FROM {table} WHERE conversation_id IN ({placeholders})",
                targets,
            )
        connection.commit()

    with sqlite3.connect(buffer) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            f"DELETE FROM assistant_buffer_messages WHERE conversation_id IN ({placeholders})",
            targets,
        )
        connection.execute(
            f"DELETE FROM assistant_buffer_turns WHERE conversation_id IN ({placeholders})",
            targets,
        )
        connection.commit()

    with sqlite3.connect(host) as connection:
        connection.execute("BEGIN IMMEDIATE")
        decision_rows = (
            connection.execute(
                f"SELECT decision_id,conversation_id,message_id FROM decisions "
                f"WHERE decision_id IN ({_placeholders(target_decision_ids)})",
                target_decision_ids,
            ).fetchall()
            if target_decision_ids
            else []
        )
        # Scope core cleanup through the offline decision ids captured before
        # deletion; unrelated production decisions are never selected.
        core_decision_ids = [str(row[0]) for row in decision_rows]
        core_conversation_ids = sorted({str(row[1]) for row in decision_rows})
        core_message_ids = sorted({str(row[2]) for row in decision_rows})
        aggregate_ids = core_decision_ids + core_message_ids
        if aggregate_ids:
            aggregate_placeholders = _placeholders(aggregate_ids)
            event_ids = [
                row[0]
                for row in connection.execute(
                    f"SELECT event_id FROM events WHERE aggregate_id IN ({aggregate_placeholders})",
                    aggregate_ids,
                ).fetchall()
            ]
            if event_ids:
                event_placeholders = _placeholders(event_ids)
                connection.execute(
                    f"DELETE FROM transactional_outbox WHERE event_id IN ({event_placeholders})",
                    event_ids,
                )
                connection.execute(
                    f"DELETE FROM events WHERE event_id IN ({event_placeholders})",
                    event_ids,
                )
        if core_decision_ids:
            connection.execute(
                f"DELETE FROM decisions WHERE decision_id IN ({_placeholders(core_decision_ids)})",
                core_decision_ids,
            )
        if core_message_ids:
            connection.execute(
                f"DELETE FROM messages WHERE message_id IN ({_placeholders(core_message_ids)})",
                core_message_ids,
            )
        if core_conversation_ids:
            connection.execute(
                f"DELETE FROM conversations WHERE conversation_id IN ({_placeholders(core_conversation_ids)})",
                core_conversation_ids,
            )
        connection.execute(
            f"DELETE FROM channel_agent_assistant_snapshots "
            f"WHERE conversation_id IN ({placeholders})",
            targets,
        )
        connection.execute(
            f"DELETE FROM channel_agent_assistant_events "
            f"WHERE conversation_id IN ({placeholders})",
            targets,
        )
        connection.execute(
            f"DELETE FROM channel_agent_observations "
            f"WHERE conversation_id IN ({placeholders})",
            targets,
        )
        connection.commit()

    if journal.is_file():
        with sqlite3.connect(journal) as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT sequence_id,payload_json FROM assistant_events"
            ).fetchall()
            sequence_ids = [
                int(sequence_id)
                for sequence_id, payload_json in rows
                if json.loads(payload_json).get("conversation_id") in targets
            ]
            if sequence_ids:
                connection.execute(
                    f"DELETE FROM assistant_events WHERE sequence_id IN "
                    f"({_placeholders([str(item) for item in sequence_ids])})",
                    sequence_ids,
                )
            connection.execute(
                f"DELETE FROM assistant_read_cursors WHERE conversation_id IN ({placeholders})",
                targets,
            )
            connection.commit()

    after = _scope_inventory(args)
    result = {
        "schema_version": "rc5-multiturn-cleanup-result.v1",
        "mode": "EXECUTED",
        "data_class": DATA_CLASS,
        "real_customer": False,
        "external_side_effect": False,
        "before": before,
        "after": after,
        "passed": (
            not after["target_conversations"]
            and after["fixed_cursor_baseline"]["observation_count"] == 0
            and after["safety_counts"] == before["safety_counts"]
        ),
    }
    _write_json(args.output, result)
    print(args.output)
    return 0 if result["passed"] else 2


def _inject(args: argparse.Namespace) -> int:
    config = load_agent_config(args.config)
    if args.sequence < 1:
        raise ValueError("source sequence must start at 1")
    if not config.store_reference:
        raise RuntimeError("the protected Agent has no active store binding")
    now = datetime.now(UTC)
    external_message_id = f"rc5-multiturn-20260812-01-{args.sequence:02d}"
    product = {
        "product_id": "C-PRODUCT-0ff808af95ce419db9be49427f1c4813",
        "product_name": "离线验收商品",
        "attributes": {"适用年龄": "5岁以上", "材质": "ABS"},
    }
    order = json.loads(args.order_json) if args.order_json else {}
    value = NormalizedChannelObservation.synthetic(
        provider_id=PROVIDER_ID,
        store_id=config.store_reference,
        store_name="RC5多轮离线验收店铺",
        catalog_tenant_id=args.catalog_tenant_id,
        catalog_platform="pinduoduo",
        conversation_id=CONVERSATION_ID,
        external_message_id=external_message_id,
        source_sequence=args.sequence,
        content=args.content,
        timestamp=now,
        product=product,
        order=order,
    )
    client = ChannelEngineClient(config)
    spool = DurableEdgeSpool(
        args.evidence_root.resolve() / "edge-spool.sqlite3",
        WindowsDPAPITransientPayloadProtector(),
    )
    forwarder = PersistAckObservationForwarder(client, spool)
    acknowledgements: list[dict[str, Any]] = []

    def submit(submission: Any) -> object:
        edge = EdgeObservation(
            observation_id=submission.observation_id,
            agent_id=submission.agent_id,
            device_id=submission.device_id,
            store_id=submission.store_id,
            platform_store_id=submission.payload.get("platform_store_id") or None,
            conversation_id=submission.conversation_id,
            external_message_id=submission.external_message_id,
            source_cursor=submission.source_cursor,
            source_sequence=submission.source_sequence,
            payload=submission.payload,
            captured_at=submission.captured_at,
            expires_at=submission.captured_at + timedelta(minutes=30),
        )
        acknowledgement = forwarder(edge)
        acknowledgements.append(acknowledgement.model_dump(mode="json"))
        return acknowledgement

    ingress = ChannelAgentProviderIngress(
        SyntheticPDDProvider((value,), provider_id=PROVIDER_ID),
        agent_id=config.agent_id,
        device_id=config.device_id,
        submit=submit,
    )
    submitted = ingress.scan_once(limit=1)
    deadline = time.monotonic() + args.timeout_seconds
    snapshot = None
    while time.monotonic() < deadline:
        response = client.fetch_assistant_snapshot(
            store_id=config.store_reference,
            conversation_id=CONVERSATION_ID,
        )
        candidate = response.snapshot
        if candidate is not None and candidate.current_question == args.content:
            snapshot = candidate
            break
        time.sleep(0.5)
    if snapshot is None:
        raise RuntimeError("the fixed conversation did not reach a new assistant snapshot")
    trace = client.fetch_assistant_trace(snapshot.trace_id) if snapshot.trace_id else None
    result = {
        "schema_version": "rc5-multiturn-turn-result.v1",
        "captured_at": datetime.now(UTC).isoformat(),
        "data_class": DATA_CLASS,
        "provider_id": PROVIDER_ID,
        "real_customer": False,
        "external_side_effect": False,
        "conversation_id": CONVERSATION_ID,
        "external_message_id": external_message_id,
        "source_cursor": value.source_cursor,
        "source_sequence": value.source_sequence,
        "content_sha256": hashlib.sha256(args.content.encode("utf-8")).hexdigest(),
        "submitted_count": submitted,
        "acknowledgements": acknowledgements,
        "edge_spool_pending_count": len(tuple(spool.pending())),
        "snapshot": snapshot.model_dump(mode="json"),
        "trace": trace.model_dump(mode="json") if trace else None,
        "safety": {
            "real_send": snapshot.safety.real_send,
            "execution_count": snapshot.safety.execution_count,
            "send_count": snapshot.safety.send_count,
            "receipt_count": snapshot.safety.receipt_count,
        },
    }
    output = args.evidence_root.resolve() / f"turn-{args.sequence:02d}.json"
    _write_json(output, result)
    print(output)
    client.close()
    return 0


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--host-database", type=Path, default=ROOT / ".runtime/channel-engine.sqlite3"
    )
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--agent-data-root", type=Path, default=DEFAULT_AGENT_DATA_ROOT)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("inventory")
    _common(inventory)
    inventory.add_argument("--output", type=Path, required=True)
    inventory.set_defaults(handler=_inventory)

    cleanup = commands.add_parser("cleanup-old")
    _common(cleanup)
    cleanup.add_argument("--output", type=Path, required=True)
    cleanup.add_argument("--execute", action="store_true")
    cleanup.set_defaults(handler=_cleanup_old)

    inject = commands.add_parser("inject-turn")
    inject.add_argument("--config", type=Path, required=True)
    inject.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    inject.add_argument("--sequence", type=int, required=True)
    inject.add_argument("--content", required=True)
    inject.add_argument("--order-json")
    inject.add_argument(
        "--catalog-tenant-id",
        default="c-tenant-6639df2982014226be2f5164ba642a72",
    )
    inject.add_argument("--timeout-seconds", type=float, default=90.0)
    inject.set_defaults(handler=_inject)
    return parser


if __name__ == "__main__":
    namespace = _parser().parse_args()
    raise SystemExit(namespace.handler(namespace))
