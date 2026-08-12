#!/usr/bin/env python3
"""Run the RC5 offline hot-start black-box validation against a live Host.

This runner intentionally owns no PDD browser dependency and no send adapter.  It
feeds either synthetic messages or a recorded-PDD-shaped replay through the
provider-neutral ChannelAgent ingress, the DPAPI edge spool, and the signed Host
ACK boundary.  Results are written as JSON evidence for UI and backend checks.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import uuid
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
from channel_agent.providers import (  # noqa: E402
    ChannelAgentProviderIngress,
    RecordedReplayProvider,
    SyntheticPDDProvider,
)
from channel_agent.security import WindowsDPAPITransientPayloadProtector  # noqa: E402
from channel_engine.provider import NormalizedChannelObservation  # noqa: E402


def _json_ready(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_ready(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_ready(value), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _observations(
    case: str,
    *,
    store_id: str,
    conversation_id: str,
    evidence_root: Path,
) -> tuple[object, tuple[NormalizedChannelObservation, ...], Path | None]:
    now = datetime.now(UTC)
    common = {
        "store_id": store_id,
        "conversation_id": conversation_id,
        "product": {
            "product_id": "PDD-SM-P0002",
            "product_name": "离线验收玩具商品",
            "sku_reference": "PDD-SM-P0002-SKU-01",
            "sku_name": "标准款",
            "attributes": {"适用年龄": "5岁以上", "材质": "ABS"},
        },
        "store_name": "RC5离线验收店铺",
    }
    if case == "synthetic":
        rows = (
            NormalizedChannelObservation.synthetic(
                provider_id="rc5-synthetic-pdd",
                external_message_id=f"synthetic-{conversation_id}-1",
                source_sequence=1,
                content="你好，这款玩具适合几岁的小朋友？",
                timestamp=now,
                **common,
            ),
            NormalizedChannelObservation.synthetic(
                provider_id="rc5-synthetic-pdd",
                external_message_id=f"synthetic-{conversation_id}-2",
                source_sequence=2,
                content="另外请说明一下材质和使用注意事项。",
                timestamp=now + timedelta(milliseconds=50),
                **common,
            ),
        )
        return SyntheticPDDProvider(rows, provider_id="rc5-synthetic-pdd"), rows, None

    row = NormalizedChannelObservation.synthetic(
        provider_id="pdd-recording-v1",
        external_message_id=f"replay-{conversation_id}-1",
        source_sequence=1,
        content="订单显示已发货但物流两天没有更新，能帮我看看应该怎么处理吗？",
        timestamp=now,
        order={
            "order_reference": "PDD-REPLAY-ORDER-0001",
            "order_status": "SHIPPED",
            "logistics_status": "NO_UPDATE_48H",
            "aftersales_status": "NONE",
        },
        **common,
    )
    fixture = evidence_root / case / "recorded-pdd-shaped-input.json"
    _write_json(
        fixture,
        {
            "schema_version": "rc5-recorded-provider-replay.v1",
            "sanitized": True,
            "observations": [row.model_dump(mode="json")],
        },
    )
    return RecordedReplayProvider(fixture, provider_id="rc5-recorded-replay"), (row,), fixture


def _inject(args: argparse.Namespace) -> int:
    config = load_agent_config(args.config)
    evidence_root = args.evidence_root.resolve()
    case_root = evidence_root / args.case
    case_root.mkdir(parents=True, exist_ok=True)
    conversation_id = args.conversation_id or (
        f"rc5-{args.case}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    store_id = args.store_id or config.store_reference
    if not store_id:
        raise RuntimeError("an active store_id is required for validation")

    provider, rows, fixture = _observations(
        args.case,
        store_id=store_id,
        conversation_id=conversation_id,
        evidence_root=evidence_root,
    )
    client = ChannelEngineClient(config)
    spool = DurableEdgeSpool(
        case_root / "edge-spool.sqlite3",
        WindowsDPAPITransientPayloadProtector(),
    )
    forwarder = PersistAckObservationForwarder(client, spool)
    acknowledgements: list[dict[str, Any]] = []
    provider_trace_ids: list[str] = []

    def submit(submission: Any) -> object:
        observation = EdgeObservation(
            observation_id=submission.observation_id,
            agent_id=submission.agent_id,
            device_id=submission.device_id,
            store_id=submission.store_id,
            platform_store_id=(submission.payload.get("platform_store_id") or None),
            conversation_id=submission.conversation_id,
            external_message_id=submission.external_message_id,
            source_cursor=submission.source_cursor,
            source_sequence=submission.source_sequence,
            payload=submission.payload,
            captured_at=submission.captured_at,
            expires_at=submission.captured_at + timedelta(minutes=30),
        )
        acknowledgement = forwarder(observation)
        acknowledgements.append(acknowledgement.model_dump(mode="json"))
        return acknowledgement

    ingress = ChannelAgentProviderIngress(
        provider,
        agent_id=config.agent_id,
        device_id=config.device_id,
        submit=submit,
        provider_read_trace=provider_trace_ids.append,
    )
    started = datetime.now(UTC)
    submitted = ingress.scan_once(limit=100)
    deadline = time.monotonic() + args.timeout_seconds
    snapshot = None
    while time.monotonic() < deadline:
        response = client.fetch_assistant_conversations(limit=100)
        snapshot = next(
            (
                item
                for item in response.conversations
                if item.store_id == store_id
                and item.conversation_id == conversation_id
                and item.reply_content
            ),
            None,
        )
        if snapshot is not None:
            break
        time.sleep(0.5)
    if snapshot is None:
        raise RuntimeError("assistant snapshot did not reach a reply state before timeout")
    if not snapshot.trace_id:
        raise RuntimeError("assistant snapshot does not expose a pipeline trace_id")
    trace = client.fetch_assistant_trace(snapshot.trace_id)
    pending = list(spool.pending())
    result = {
        "schema_version": "rc5-hotstart-case-result.v1",
        "case": args.case,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "agent_id": config.agent_id,
        "device_id": config.device_id,
        "store_id": store_id,
        "conversation_id": conversation_id,
        "provider_class": type(provider).__name__,
        "provider_fixture": str(fixture) if fixture else None,
        "submitted_count": submitted,
        "provider_trace_ids": provider_trace_ids,
        "acknowledgements": acknowledgements,
        "edge_spool_pending_count": len(pending),
        "snapshot": snapshot,
        "host_trace": trace,
        "safety_assertions": {
            "browser_dependency_used": False,
            "pdd_network_requests": 0,
            "real_send": snapshot.safety.real_send,
            "send_count": snapshot.safety.send_count,
            "receipt_count": snapshot.safety.receipt_count,
            "execution_count": snapshot.safety.execution_count,
        },
    }
    output = case_root / "case-result.json"
    _write_json(output, result)
    print(output)
    client.close()
    return 0


def _verify(args: argparse.Namespace) -> int:
    config = load_agent_config(args.config)
    client = ChannelEngineClient(config)
    response = client.fetch_assistant_snapshot(
        store_id=args.store_id,
        conversation_id=args.conversation_id,
    )
    snapshot = response.snapshot
    if snapshot is None:
        raise RuntimeError("assistant snapshot is unavailable")
    trace = client.fetch_assistant_trace(snapshot.trace_id) if snapshot.trace_id else None

    backend_record = None
    if args.host_database:
        with sqlite3.connect(args.host_database) as connection:
            row = connection.execute(
                """
                SELECT preparation_json
                FROM execution_preparations
                WHERE decision_id = ?
                ORDER BY prepared_at DESC LIMIT 1
                """,
                (snapshot.decision_id,),
            ).fetchone()
            if row:
                backend_record = json.loads(row[0])
    passed = (
        snapshot.status == "EXECUTION_PREPARED"
        and snapshot.safety.execution_prepared
        and snapshot.safety.real_send is False
        and snapshot.safety.send_count == 0
        and backend_record is not None
        and backend_record["authorization_kind"] == "HUMAN"
        and backend_record["state"] == "READY"
        and backend_record["real_send_enabled"] is False
        and backend_record["external_side_effect"] is False
    )
    result = {
        "schema_version": "rc5-hotstart-manual-confirm-result.v1",
        "verified_at": datetime.now(UTC).isoformat(),
        "passed": passed,
        "snapshot": snapshot,
        "host_trace": trace,
        "backend_execution_preparation": backend_record,
        "expected_transition": [
            "WAITING_APPROVAL",
            "HUMAN_APPROVAL",
            "EXECUTION_PREPARED",
        ],
    }
    _write_json(args.output, result)
    print(args.output)
    client.close()
    return 0 if passed else 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    inject = sub.add_parser("inject")
    inject.add_argument("--config", type=Path, required=True)
    inject.add_argument("--evidence-root", type=Path, required=True)
    inject.add_argument("--case", choices=("synthetic", "replay"), required=True)
    inject.add_argument("--store-id")
    inject.add_argument("--conversation-id")
    inject.add_argument("--timeout-seconds", type=float, default=90.0)
    inject.set_defaults(handler=_inject)

    verify = sub.add_parser("verify-prepared")
    verify.add_argument("--config", type=Path, required=True)
    verify.add_argument("--store-id", required=True)
    verify.add_argument("--conversation-id", required=True)
    verify.add_argument("--host-database", type=Path)
    verify.add_argument("--output", type=Path, required=True)
    verify.set_defaults(handler=_verify)
    return parser


if __name__ == "__main__":
    namespace = _parser().parse_args()
    raise SystemExit(namespace.handler(namespace))
