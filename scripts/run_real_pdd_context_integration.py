from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from channel_agent.binding import atomic_write_bytes
from channel_agent.browser import ChannelAgentBrowserManager
from channel_agent.client import ChannelEngineClient
from channel_agent.config import load_agent_config
from channel_agent.controlled_auto_runtime import ControlledAutoRuntimeStateStore
from channel_agent.logger import SafeAgentLogger
from channel_agent.pdd_login import EdgePDDTargetResolver
from channel_agent.pdd_workspace import (
    ExistingPDDWorkspaceObserver,
    FixedReadOnlyPDDWorkspaceEvaluator,
    LivePDDContextProvider,
    PDDWorkspaceSelectorContract,
    SQLitePDDWorkspaceCheckpoint,
)
from channel_agent.windows import WindowsStateStore
from channel_engine.browser.cdp_readonly import WebSocketCDPEvaluator
from channel_engine.customer_assistant import (
    AICustomerReplyService,
    CustomerAssistantRuntime,
    CustomerContextCollector,
    CustomerServiceLifecycleProjector,
    SQLiteConversationBuffer,
    render_customer_assistant,
)
from channel_engine.gateway import (
    AICSGatewayRequestFailed,
    GatewayAdapterConfig,
    GatewayEnvironment,
    GatewayHealthStatus,
    GatewayRetryPolicy,
    ProductionGatewayClient,
)
from channel_engine.storage import (
    SqlAlchemyUnitOfWork,
    create_engine_and_session,
    create_schema,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Attach the existing real PDD workspace to the read-only AI-CS assistant."
    )
    parser.add_argument(
        "command",
        choices=(
            "baseline",
            "once",
            "run",
            "status",
            "formal-status",
            "formal-restart",
        ),
    )
    parser.add_argument(
        "--data-root",
        default=".runtime/pdd-login-observation-v1",
    )
    parser.add_argument("--config")
    parser.add_argument(
        "--gateway-base-url",
        default=os.getenv("AI_CS_GATEWAY_BASE_URL", "http://127.0.0.1:8420"),
    )
    parser.add_argument(
        "--gateway-key-reference",
        default=os.getenv("AI_CS_GATEWAY_KEY_REFERENCE"),
    )
    parser.add_argument("--gateway-client-id", default="channel-engine")
    parser.add_argument("--gateway-key-id", default="gateway-key-v1")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--exit-after-reply", action="store_true")
    parser.add_argument(
        "--product-applicable-age",
        default=os.getenv("PDD_PRODUCT_APPLICABLE_AGE"),
        help="Operator-confirmed product fact, for example: 8岁以上",
    )
    parser.add_argument(
        "--requeue-turn-id",
        help="Explicitly requeue a manual-intervention AI turn after context update",
    )
    return parser


def _atomic_text(path: Path, value: str) -> None:
    atomic_write_bytes(path, value.encode("utf-8"))


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _append_runtime_event(path: Path, event_type: str, **metadata: object) -> None:
    event = {
        "event_version": "1.0",
        "event_id": f"assistant-event-{os.urandom(16).hex()}",
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "metadata": metadata,
        "contains_secret": False,
        "browser_write_operations": 0,
        "send_count": 0,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _validate_formal_runtime_config(config) -> None:
    """Fail closed unless the installed Agent owns the complete read-only chain."""

    if (
        not config.browser_enabled
        or not config.pdd_login_observation_enabled
        or not config.customer_assistant_enabled
        or not config.message_observation_enabled
        or config.observer_mode != "OBSERVE_ONLY"
        or not config.manual_approval_required
        or config.auto_reply_enabled
        or config.real_send_enabled
        or config.real_platform_activation_allowed
    ):
        raise RuntimeError("formal Windows Agent observation safety is not enabled")


def _formal_scope_reference(store_id: str, conversation_id: str) -> str:
    payload = f"{store_id}\0{conversation_id}".encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _formal_status(data_root: Path, config_path: Path) -> dict[str, object]:
    """Read the installed Agent and signed Host projection without touching PDD."""

    config = load_agent_config(config_path)
    _validate_formal_runtime_config(config)
    state = WindowsStateStore(
        data_root / "runtime" / "channel-agent-state.json"
    ).load()
    if state.agent_id not in {None, config.agent_id}:
        raise RuntimeError("formal Windows Agent state belongs to another agent")
    if state.device_id not in {None, config.device_id}:
        raise RuntimeError("formal Windows Agent state belongs to another device")

    client = ChannelEngineClient(config)
    try:
        response = client.fetch_assistant_conversations(limit=100)
    finally:
        client.close()
    conversations = [
        {
            "scope_reference": _formal_scope_reference(
                item.store_id, item.conversation_id
            ),
            "revision": item.revision,
            "status": item.status,
            "processing_stage": item.processing_stage,
            "quality_status": item.quality_status,
            "policy_mode": item.policy_mode,
        }
        for item in response.conversations
    ]
    return {
        "schema_version": "real-pdd-formal-runtime-status.v1",
        "runtime_owner": "WINDOWS_AGENT",
        "projection_source": "SIGNED_HOST",
        "agent_id": config.agent_id,
        "device_id": config.device_id,
        "identity_status": state.identity_status.value,
        "pdd_login_state": (
            state.pdd_login_state.value if state.pdd_login_state else None
        ),
        "observer_status": state.observer_status,
        "message_observation_enabled": state.message_observation_enabled,
        "assistant_conversation_count": len(conversations),
        "assistant_conversations": conversations,
        "real_send_enabled": False,
        "legacy_runtime_started": False,
    }


def _queue_formal_observer_restart(
    data_root: Path, config_path: Path
) -> dict[str, object]:
    """Queue the existing human-intent request consumed by WindowsAgentHost."""

    config = load_agent_config(config_path)
    _validate_formal_runtime_config(config)
    state = WindowsStateStore(
        data_root / "runtime" / "channel-agent-state.json"
    ).load()
    if state.agent_id != config.agent_id or state.device_id != config.device_id:
        raise RuntimeError("formal Windows Agent runtime identity is unavailable")
    if not state.message_observation_enabled:
        raise RuntimeError("formal Windows Agent message observation is not enabled")
    if state.pdd_login_state is None or state.pdd_login_state.value != "CUSTOMER_SERVICE_READY":
        raise RuntimeError("formal PDD customer service workspace is not ready")
    if state.identity_status.value != "ACTIVE":
        raise RuntimeError("formal Windows Agent identity is not active")

    request_path = data_root / "runtime" / "pdd-observer-restart.request"
    if request_path.exists():
        try:
            existing = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise RuntimeError("existing observer restart request is invalid") from exc
        if (
            not isinstance(existing, dict)
            or existing.get("schema_version")
            != "channel-agent-pdd-observer-restart-request.v1"
            or existing.get("human_intent") is not True
        ):
            raise RuntimeError("existing observer restart request is invalid")
        status = "ALREADY_REQUESTED"
    else:
        _atomic_json(
            request_path,
            {
                "schema_version": "channel-agent-pdd-observer-restart-request.v1",
                "requested_at": datetime.now(UTC).isoformat(),
                "human_intent": True,
            },
        )
        status = "RESTART_REQUESTED"
    return {
        "schema_version": "real-pdd-formal-observer-restart.v1",
        "status": status,
        "runtime_owner": "WINDOWS_AGENT",
        "human_intent": True,
        "real_send_enabled": False,
        "legacy_runtime_started": False,
    }


def _existing_feed_reply(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    reply = value.get("reply") if isinstance(value, dict) else None
    return reply if isinstance(reply, dict) else None


def _workspace_feed(
    snapshot,
    *,
    reply: dict[str, object] | None,
    production_real_send_enabled: bool = False,
    controlled_store_auto_enabled: bool = False,
) -> dict[str, object]:
    customer_messages = [
        item for item in snapshot.visible_history if item.sender == "customer"
    ]
    attributes = snapshot.product.attributes
    return {
        "schemaVersion": "channel-agent-workspace-feed.v1",
        "updatedAt": datetime.now(UTC).isoformat(),
        "safety": {
            "readOnly": True,
            "autoReply": controlled_store_auto_enabled,
            "realSend": production_real_send_enabled,
            "browserWriteOperations": 0,
            "executionCount": 0,
            "receiptCount": 0,
            "sendCount": 0,
        },
        "productContext": {
            "productReference": snapshot.product.product_reference,
            "productName": snapshot.product.product_name,
            "applicableAge": attributes.get("applicable_age", ""),
            "factSource": attributes.get("applicable_age_source", ""),
        },
        "conversations": [
            {
                "conversationId": snapshot.conversation_id,
                "customerLabel": "PDD a***",
                "unreadCount": len(customer_messages),
                "source": "CHANNEL_AGENT",
                "messages": [
                    {
                        "messageId": item.external_message_id,
                        "conversationId": snapshot.conversation_id,
                        "customerLabel": (
                            "PDD a***" if item.sender == "customer" else "客服已回复"
                        ),
                        "content": item.content,
                        "receivedAt": item.timestamp.isoformat(),
                        "source": "CHANNEL_AGENT",
                        "senderRole": (
                            "CUSTOMER" if item.sender == "customer" else "AGENT"
                        ),
                    }
                    for item in snapshot.visible_history
                ],
            }
        ],
        "reply": reply,
    }


def _reply_feed(
    snapshot,
    package,
    *,
    policy_mode: str = "MANUAL_CONFIRM",
) -> dict[str, object]:
    customer_messages = [
        item for item in snapshot.visible_history if item.sender == "customer"
    ]
    message_id = (
        customer_messages[-1].external_message_id
        if customer_messages
        else package.turn_id
    )
    citations = [
        {
            "file": item.title,
            "page": None,
            "chunkId": None,
            "summary": item.reference,
            "distance": None,
            "knowledgeVersion": package.gateway_version,
            "sourceIds": [item.reference],
            "productId": snapshot.product.product_reference,
            "skuId": snapshot.product.sku_reference,
        }
        for item in package.citations
    ]
    if (
        not citations
        and snapshot.product.attributes.get("applicable_age")
        and package.action == "SUGGEST_REPLY"
    ):
        citations = [
            {
                "file": "人工确认商品事实",
                "page": None,
                "chunkId": None,
                "summary": (
                    "适用年龄："
                    + snapshot.product.attributes["applicable_age"]
                ),
                "distance": None,
                "knowledgeVersion": "operator-confirmed-product-fact.v1",
                "sourceIds": ["OPERATOR-CONFIRMED-AGE-2026-08-07"],
                "productId": snapshot.product.product_reference,
                "skuId": snapshot.product.sku_reference,
            }
        ]
    return {
        "conversationId": snapshot.conversation_id,
        "messageId": message_id,
        "answer": package.reply_content,
        "requestId": package.request_id,
        "decisionId": package.decision_id,
        "action": (
            "CONTROLLED_ANSWER"
            if package.action == "SUGGEST_REPLY"
            else "REFUSE"
        ),
        "riskLevel": package.risk_level.value,
        "citations": citations,
        "warnings": list(package.warnings),
        "requiredFields": list(package.required_fields),
        "qualityStatus": package.quality_gate_status,
        "policyMode": policy_mode,
        "evidenceBundleSha256": package.evidence_bundle_sha256,
        "state": package.state,
    }


def _build_observer(
    data_root: Path,
    config_path: Path,
    *,
    product_applicable_age: str | None = None,
):
    config = load_agent_config(config_path)
    if (
        not config.browser_enabled
        or not config.pdd_login_observation_enabled
        or not config.customer_assistant_enabled
        or not config.manual_approval_required
        or config.auto_reply_enabled
        or config.real_send_enabled
    ):
        raise RuntimeError("Channel Agent assistant safety configuration is not enabled")
    manager = ChannelAgentBrowserManager(
        agent_id=config.agent_id,
        data_root=data_root,
        enabled=config.browser_enabled,
        logger=SafeAgentLogger(data_root / "logs" / "real-pdd-browser-attach.jsonl"),
    )
    state = manager.browser_status()
    public = state.public_view(data_root)
    manager.close_resources()
    if state.status.value != "READY" or state.pid is None:
        raise RuntimeError("existing Agent-owned Edge session is not READY")
    evaluator = FixedReadOnlyPDDWorkspaceEvaluator(
        WebSocketCDPEvaluator(timeout_seconds=2.0),
        PDDWorkspaceSelectorContract(),
    )
    observer = ExistingPDDWorkspaceObserver(
        browser_id=state.browser_id,
        profile_path=state.profile_path,
        profile_reference=str(public["profile_reference"]),
        resolver=EdgePDDTargetResolver(timeout_seconds=1.0),
        evaluator=evaluator,
        human_verified_product_attributes=(
            {
                "applicable_age": product_applicable_age.strip(),
                "applicable_age_source": "operator_confirmed",
            }
            if product_applicable_age and product_applicable_age.strip()
            else None
        ),
    )
    return config, state, observer


def _build_gateway(args: argparse.Namespace) -> ProductionGatewayClient:
    if not args.gateway_key_reference:
        raise RuntimeError("AI_CS_GATEWAY_KEY_REFERENCE is required")
    reference = Path(args.gateway_key_reference).expanduser().resolve()
    try:
        secret = reference.read_bytes().strip()
    except OSError as exc:
        raise RuntimeError("AI-CS Gateway key reference is unavailable") from exc
    if len(secret) < 32:
        raise RuntimeError("AI-CS Gateway key reference is invalid")
    config = GatewayAdapterConfig(
        environment=GatewayEnvironment.MOCK,
        base_url=args.gateway_base_url,
        client_id=args.gateway_client_id,
        key_id=args.gateway_key_id,
        production_enabled=False,
        timeout_seconds=15.0,
    )
    return ProductionGatewayClient(
        config,
        secret,
        retry_policy=GatewayRetryPolicy(max_attempts=1),
    )


def _build_assistant(data_root: Path, observer, gateway):
    assistant_root = data_root / "runtime" / "real-pdd-assistant"
    database_url = f"sqlite:///{(assistant_root / 'channel-engine.sqlite3').as_posix()}"
    engine, session_factory = create_engine_and_session(database_url)
    create_schema(engine)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    buffer = SQLiteConversationBuffer(
        assistant_root / "conversation-buffer.sqlite3",
        quiet_window=timedelta(seconds=4),
        processing_lease=timedelta(minutes=2),
        clock=lambda: datetime.now(UTC),
    )
    provider = LivePDDContextProvider(observer, buffer)
    collector = CustomerContextCollector(
        provider,
        provider,
        provider,
        provider,
        visible_history_provider=provider,
        clock=lambda: datetime.now(UTC),
    )
    runtime = CustomerAssistantRuntime(
        buffer,
        collector,
        AICustomerReplyService(
            uow_factory,
            gateway,
            clock=lambda: datetime.now(UTC),
        ),
        None,
        None,
        uow_factory,
        clock=lambda: datetime.now(UTC),
        real_send_enabled=False,
    )
    return assistant_root, engine, buffer, runtime


def _safety_status(
    *,
    phase: str,
    snapshot=None,
    checkpoint: SQLitePDDWorkspaceCheckpoint | None = None,
    error_code: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "status_version": "1.0",
        "phase": phase,
        "observed_at": datetime.now(UTC).isoformat(),
        "manual_approval_required": True,
        "auto_reply_enabled": False,
        "real_send_enabled": False,
        "browser_write_operations": 0,
        "execution_count": 0,
        "receipt_count": 0,
        "send_count": 0,
        "edge_lifecycle_owned": False,
        "edge_will_remain_open": True,
        "error_code": error_code,
    }
    if snapshot is not None:
        value["workspace"] = snapshot.public_view()
    if checkpoint is not None:
        value["checkpoint"] = checkpoint.status()
    return value


def _run_loop(
    args: argparse.Namespace,
    *,
    data_root: Path,
    observer,
    checkpoint: SQLitePDDWorkspaceCheckpoint,
) -> int:
    gateway = _build_gateway(args)
    health = gateway.health_check()
    if health.status is not GatewayHealthStatus.HEALTHY or not health.real_ai_cs_connected:
        gateway.close()
        raise RuntimeError("signed AI-CS Gateway health is not ready")
    assistant_root, engine, buffer, runtime = _build_assistant(
        data_root, observer, gateway
    )
    if args.requeue_turn_id:
        buffer.requeue_manual_intervention(args.requeue_turn_id)
    status_path = assistant_root / "status.json"
    html_path = assistant_root / "assistant.html"
    evidence_path = assistant_root / "first-live-message-evidence.json"
    feed_path = assistant_root / "assistant-feed.json"
    event_path = assistant_root / "assistant-events.jsonl"
    auto_runtime_store = ControlledAutoRuntimeStateStore(
        assistant_root / "controlled-auto-runtime.sqlite3"
    )
    _atomic_json(
        status_path,
        _safety_status(
            phase="READY_TO_RECEIVE_REAL_MESSAGE", checkpoint=checkpoint
        ),
    )
    try:
        while True:
            snapshot = observer.capture()
            auto_state = auto_runtime_store.load()
            pending = checkpoint.pending_customer_messages(snapshot)
            _atomic_json(
                feed_path,
                _workspace_feed(
                    snapshot,
                    reply=(None if pending else _existing_feed_reply(feed_path)),
                    production_real_send_enabled=(
                        auto_state.production_real_send_enabled
                    ),
                    controlled_store_auto_enabled=(
                        auto_state.controlled_store_auto_enabled
                    ),
                ),
            )
            for message in pending:
                runtime.ingest_redacted(observer.to_inbound(snapshot, message))
                _append_runtime_event(
                    event_path,
                    "MESSAGE_RECEIVED",
                    message_id=message.external_message_id,
                    conversation_id=snapshot.conversation_id,
                )
                _append_runtime_event(
                    event_path,
                    "MESSAGE_NORMALIZED",
                    message_id=message.external_message_id,
                    conversation_id=snapshot.conversation_id,
                    privacy_filtered=True,
                )
                checkpoint.acknowledge(snapshot, (message,))
                _append_runtime_event(
                    event_path,
                    "CONVERSATION_BUFFERED",
                    message_id=message.external_message_id,
                    conversation_id=snapshot.conversation_id,
                )
            package = runtime.generate_ready_reply()
            if package is not None:
                reply = _reply_feed(
                    snapshot,
                    package,
                    policy_mode=(
                        "AUTO_LOW_RISK"
                        if (
                            auto_state.controlled_pilot_send_enabled
                            or auto_state.controlled_store_auto_enabled
                        )
                        else "MANUAL_CONFIRM"
                    ),
                )
                _atomic_json(
                    feed_path,
                    _workspace_feed(
                        snapshot,
                        reply=reply,
                        production_real_send_enabled=(
                            auto_state.production_real_send_enabled
                        ),
                        controlled_store_auto_enabled=(
                            auto_state.controlled_store_auto_enabled
                        ),
                    ),
                )
                _append_runtime_event(
                    event_path,
                    "CUSTOMER_CONTEXT_UPDATED",
                    context_id=package.context_id,
                    conversation_id=snapshot.conversation_id,
                )
                _append_runtime_event(
                    event_path,
                    "AI_REPLY_CREATED",
                    decision_id=package.decision_id,
                    request_id=package.request_id,
                    conversation_id=snapshot.conversation_id,
                    state=package.state,
                )
                runtime_state = CustomerServiceLifecycleProjector.project(
                    browser_status="READY",
                    pdd_login_state="CUSTOMER_SERVICE_READY",
                    observation_active=True,
                )
                desktop = runtime.desktop_snapshot(
                    runtime_state=runtime_state,
                    agent_online=True,
                    pdd_status="客服工作台运行中（只读）",
                )
                _atomic_text(html_path, render_customer_assistant(desktop))
                evidence = _safety_status(
                    phase=(
                        "WAITING_HUMAN_CONFIRMATION"
                        if package.state == "WAITING_APPROVAL"
                        else "MANUAL_INTERVENTION_AI_NO_ACTION"
                    ),
                    snapshot=snapshot,
                    checkpoint=checkpoint,
                )
                evidence.update(
                    {
                        "message_id": package.turn_id,
                        "decision_id": package.decision_id,
                        "request_id": package.request_id,
                        "context_id": package.context_id,
                        "reply_package_state": package.state,
                        "reply_action": package.action,
                        "risk_level": package.risk_level.value,
                        "assistant_view_ready": True,
                        "customer_question": package.customer_question,
                        "reply_content": package.reply_content,
                        "citations": [
                            item.model_dump(mode="json") for item in package.citations
                        ],
                    }
                )
                _atomic_json(status_path, evidence)
                _atomic_json(evidence_path, evidence)
                if args.exit_after_reply:
                    return 0
            elif pending:
                _atomic_json(
                    status_path,
                    _safety_status(
                        phase="BUFFERING_REAL_CUSTOMER_MESSAGES",
                        snapshot=snapshot,
                        checkpoint=checkpoint,
                    ),
                )
            if args.command == "once":
                return 0
            time.sleep(max(args.poll_seconds, 0.25))
    finally:
        gateway.close()
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_root = Path(args.data_root).resolve()
    config_path = (
        Path(args.config).resolve()
        if args.config
        else data_root / "config" / "agent.json"
    )
    if args.command in {"formal-status", "formal-restart"}:
        try:
            value = (
                _formal_status(data_root, config_path)
                if args.command == "formal-status"
                else _queue_formal_observer_restart(data_root, config_path)
            )
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            error_code = getattr(exc, "error_code", type(exc).__name__.upper())
            print(
                json.dumps(
                    {"status": "FAILED", "error_code": str(error_code)},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 4
    assistant_root = data_root / "runtime" / "real-pdd-assistant"
    status_path = assistant_root / "status.json"
    checkpoint = SQLitePDDWorkspaceCheckpoint(
        assistant_root / "workspace-checkpoint.sqlite3"
    )
    try:
        _config, _state, observer = _build_observer(
            data_root,
            config_path,
            product_applicable_age=args.product_applicable_age,
        )
        snapshot = observer.capture()
        if args.command == "baseline":
            count = checkpoint.baseline(snapshot)
            value = _safety_status(
                phase="READY_TO_RECEIVE_REAL_MESSAGE",
                snapshot=snapshot,
                checkpoint=checkpoint,
            )
            value["baselined_existing_message_count"] = count
            _atomic_json(status_path, value)
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0
        if args.command == "status":
            value = _safety_status(
                phase="CUSTOMER_SERVICE_RUNNING",
                snapshot=snapshot,
                checkpoint=checkpoint,
            )
            if status_path.exists():
                persisted = json.loads(status_path.read_text(encoding="utf-8"))
                value["assistant_phase"] = persisted.get("phase")
                value["assistant_view_ready"] = persisted.get(
                    "assistant_view_ready", False
                )
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0
        if not checkpoint.status()["baseline_ready"]:
            raise RuntimeError("run baseline before receiving a real message")
        return _run_loop(
            args,
            data_root=data_root,
            observer=observer,
            checkpoint=checkpoint,
        )
    except Exception as exc:
        if isinstance(exc, AICSGatewayRequestFailed):
            error_code = (
                f"AI_CS_{exc.status_code}_{exc.envelope.error.code.value}"
            )
        else:
            error_code = getattr(exc, "error_code", type(exc).__name__.upper())
        _atomic_json(
            status_path,
            _safety_status(phase="MANUAL_INTERVENTION", error_code=str(error_code)),
        )
        print(
            json.dumps(
                {"status": "FAILED", "error_code": str(error_code)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
