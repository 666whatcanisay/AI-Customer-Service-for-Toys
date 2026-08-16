from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from channel_agent.browser import ChannelAgentBrowserManager
from channel_agent.logger import SafeAgentLogger
from channel_agent.pdd_simulator import (
    SYNTHETIC_PDD_CONTRACT_VERSION,
    SYNTHETIC_PDD_URL,
    SimulatorConfirmationPolicy,
    SyntheticPDDAdapter,
    SyntheticPDDCDPClient,
    SyntheticPDDContextProvider,
    SyntheticPDDExecutionAdapter,
    SyntheticPDDTargetResolver,
    simulator_workspace_feed,
)
from channel_agent.pdd_workspace import SQLitePDDWorkspaceCheckpoint
from channel_engine.channel import LedgerExecutionAuthorizationService
from channel_engine.customer_assistant import (
    AICustomerReplyService,
    CustomerAssistantRuntime,
    CustomerContextCollector,
    SQLiteConversationBuffer,
)
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker
from channel_engine.gateway import (
    GatewayAdapterConfig,
    GatewayEnvironment,
    GatewayHealthStatus,
    GatewayRetryPolicy,
    ProductionGatewayClient,
)
from channel_engine.policy import ApprovalPolicy
from channel_engine.storage import SqlAlchemyUnitOfWork, create_engine_and_session, create_schema


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run the synthetic PDD → ChannelAgent → AI-CS → Receipt acceptance flow.")
    result.add_argument("--data-root")
    result.add_argument("--simulator-url", default=SYNTHETIC_PDD_URL)
    result.add_argument("--gateway-base-url", default=os.getenv("AI_CS_GATEWAY_BASE_URL", "http://127.0.0.1:8420"))
    result.add_argument("--gateway-key-reference", default=os.getenv("AI_CS_GATEWAY_KEY_REFERENCE"))
    result.add_argument("--gateway-client-id", default="channel-engine")
    result.add_argument("--gateway-key-id", default="gateway-key-v1")
    result.add_argument(
        "--ai-cs-internal-service-reference",
        default=os.getenv("AI_CS_INTERNAL_SERVICE_REFERENCE"),
        help="File reference for the local AI-CS internal service identity; never the secret value.",
    )
    result.add_argument("--latency-budget-seconds", type=float, default=20.0)
    result.add_argument("--question", default="这款香槟玫瑰积木适合8岁的孩子玩吗？需要家长陪同吗？")
    result.add_argument("--keep-browser-open", action="store_true")
    return result


def atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_event(path: Path, event_type: str, started: float, **metadata: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "event_version": "1.0",
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "metadata": metadata,
        "synthetic_only": True,
        "contains_secret": False,
        "real_platform_connected": False,
        "customer_message_sent": False,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def build_gateway(args: argparse.Namespace) -> ProductionGatewayClient:
    if not args.gateway_key_reference:
        raise RuntimeError("AI_CS_GATEWAY_KEY_REFERENCE is required")
    reference = Path(args.gateway_key_reference).expanduser().resolve()
    secret = reference.read_bytes().strip()
    if len(secret) < 32:
        raise RuntimeError("AI-CS Gateway key reference is invalid")
    return ProductionGatewayClient(
        GatewayAdapterConfig(
            environment=GatewayEnvironment.MOCK,
            base_url=args.gateway_base_url,
            client_id=args.gateway_client_id,
            key_id=args.gateway_key_id,
            production_enabled=False,
            timeout_seconds=18.0,
        ),
        secret,
        retry_policy=GatewayRetryPolicy(max_attempts=1),
    )


def ensure_simulator_knowledge(base_url: str, service_reference: str | None) -> dict[str, object]:
    if base_url.rstrip("/") != "http://127.0.0.1:8420":
        raise RuntimeError("synthetic knowledge publication is restricted to the local AI-CS sandbox")
    if not service_reference:
        raise RuntimeError("AI_CS_INTERNAL_SERVICE_REFERENCE is required")
    service_token = Path(service_reference).expanduser().resolve().read_text(encoding="ascii").strip()
    if len(service_token) < 32:
        raise RuntimeError("AI-CS internal service reference is invalid")
    document = (
        "数据环境：SIMULATOR，仅用于本地链路验收。\n"
        "商品名称：【仿真商品】香槟玫瑰积木花束礼盒\n"
        "商品ID：SIM-PRODUCT-001\n"
        "SKU：SIM-SKU-AGE8-CHAMPAGNE，香槟玫瑰花束礼盒装\n"
        "适用年龄：8岁以上。\n"
        "安全提示：本品属于小颗粒拼搭积木玩具。8岁儿童可按说明书拼搭，"
        "建议家长根据儿童实际动手能力提供指导或陪同，并避免低龄儿童接触小零件。"
    )
    fingerprint = hashlib.sha256(document.encode("utf-8")).hexdigest()
    payload = {
        "schema_version": "ai-product-knowledge-publication.v1",
        "idempotency_key": f"synthetic-pdd-{fingerprint}",
        "tenant_id": "CHANNEL-AGENT-PILOT",
        "platform": "pdd",
        "store_code": "SIM-STORE-001",
        "product_id": "SIM-PRODUCT-001",
        "product_name": "【仿真商品】香槟玫瑰积木花束礼盒",
        "data_source": "TEST",
        "knowledge_fingerprint": fingerprint,
        "document": document,
        "source_ids": ["SYNTHETIC-PDD-CONTRACT-V1"],
        "operator": "synthetic-pdd-e2e",
    }
    with httpx.Client(base_url=base_url, timeout=20.0, trust_env=False) as client:
        response = client.post(
            "/api/admin/ai/knowledge-publications/products",
            json=payload,
            headers={"X-AI-CS-Service-Token": service_token},
        )
    if response.status_code != 200:
        raise RuntimeError(f"synthetic AI-CS knowledge publication failed with HTTP {response.status_code}")
    value = response.json()
    if value.get("status") != "PUBLISHED" or value.get("knowledge_fingerprint") != fingerprint:
        raise RuntimeError("synthetic AI-CS knowledge publication receipt is invalid")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.simulator_url != SYNTHETIC_PDD_URL:
        raise SystemExit("simulator URL is frozen to the loopback Synthetic PDD origin")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    data_root = Path(args.data_root).resolve() if args.data_root else (Path(".runtime") / "synthetic-pdd-e2e" / stamp).resolve()
    runtime_root = data_root / "runtime" / "real-pdd-assistant"
    report_path = data_root / "evidence" / "synthetic-pdd-e2e-report.json"
    event_path = data_root / "evidence" / "synthetic-pdd-e2e-events.jsonl"
    feed_path = runtime_root / "assistant-feed.json"
    status_path = runtime_root / "status.json"
    started = time.perf_counter()
    browser = ChannelAgentBrowserManager(
        agent_id="agent-synthetic-pdd-e2e",
        data_root=data_root,
        enabled=True,
        logger=SafeAgentLogger(data_root / "logs" / "browser.jsonl"),
    )
    gateway: ProductionGatewayClient | None = None
    engine = None
    report: dict[str, object] = {
        "schema_version": "synthetic-pdd-e2e-report.v1",
        "status": "FAILED",
        "contract_version": SYNTHETIC_PDD_CONTRACT_VERSION,
        "environment": "SIMULATOR",
        "safety": {
            "manual_approval_required": True,
            "simulator_auto_confirmation": True,
            "auto_reply_enabled": False,
            "real_send_enabled": False,
            "real_platform_connected": False,
            "customer_message_sent": False,
        },
    }
    try:
        state = browser.open_browser()
        browser.navigate(SYNTHETIC_PDD_URL)
        resolver = SyntheticPDDTargetResolver()
        client = SyntheticPDDCDPClient()
        deadline = time.monotonic() + 12
        while True:
            try:
                resolver.resolve(Path(state.profile_path))
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
        adapter = SyntheticPDDAdapter(
            browser_id=state.browser_id,
            profile_path=state.profile_path,
            profile_reference="agent-data://browser-profiles/agent-synthetic-pdd-e2e",
            resolver=resolver,
            client=client,
        )
        baseline = adapter.capture()
        checkpoint = SQLitePDDWorkspaceCheckpoint(runtime_root / "workspace-checkpoint.sqlite3")
        baselined = checkpoint.baseline(baseline)
        append_event(event_path, "SYNTHETIC_PDD_READY", started, baseline_message_count=baselined)

        database_url = f"sqlite:///{(runtime_root / 'channel-engine.sqlite3').as_posix()}"
        engine, session_factory = create_engine_and_session(database_url)
        create_schema(engine)

        def uow_factory() -> SqlAlchemyUnitOfWork:
            return SqlAlchemyUnitOfWork(session_factory)

        buffer = SQLiteConversationBuffer(
            runtime_root / "conversation-buffer.sqlite3",
            quiet_window=timedelta(milliseconds=800),
            processing_lease=timedelta(minutes=2),
            clock=lambda: datetime.now(UTC),
        )
        provider = SyntheticPDDContextProvider(adapter, buffer)
        collector = CustomerContextCollector(
            provider, provider, provider, provider,
            visible_history_provider=provider,
            clock=lambda: datetime.now(UTC),
        )
        knowledge_receipt = ensure_simulator_knowledge(
            args.gateway_base_url, args.ai_cs_internal_service_reference
        )
        append_event(
            event_path,
            "SYNTHETIC_PRODUCT_KNOWLEDGE_PUBLISHED",
            started,
            publication_receipt_id=knowledge_receipt.get("publication_receipt_id"),
        )
        gateway = build_gateway(args)
        health = gateway.health_check()
        if health.status is not GatewayHealthStatus.HEALTHY or not health.real_ai_cs_connected:
            raise RuntimeError("signed AI-CS Gateway health is not ready")
        runtime = CustomerAssistantRuntime(
            buffer,
            collector,
            AICustomerReplyService(uow_factory, gateway, clock=lambda: datetime.now(UTC)),
            None,
            None,
            uow_factory,
            clock=lambda: datetime.now(UTC),
            real_send_enabled=False,
        )

        message_id = client.push_customer_message(adapter.target(), args.question, baseline.conversation_id)
        injected_at = time.perf_counter()
        append_event(event_path, "SIMULATED_BUYER_MESSAGE_SENT", started, message_id=message_id)
        observed = adapter.capture()
        pending = checkpoint.pending_customer_messages(observed)
        matching = [item for item in pending if item.external_message_id == message_id]
        if len(matching) != 1:
            raise RuntimeError("ChannelAgent did not capture exactly one synthetic buyer message")
        runtime.ingest_redacted(adapter.to_inbound(observed, matching[0]))
        checkpoint.acknowledge(observed, (matching[0],))
        append_event(event_path, "CHANNEL_AGENT_MESSAGE_CAPTURED", started, message_id=message_id)

        time.sleep(0.85)
        package = runtime.generate_ready_reply()
        if package is None or package.action != "SUGGEST_REPLY" or not package.reply_content:
            raise RuntimeError("AI-CS did not produce an actionable reply package")
        append_event(event_path, "AI_CS_REPLY_CREATED", started, request_id=package.request_id, decision_id=package.decision_id)
        before_send_feed_path = runtime_root / "assistant-feed-before-send.json"
        atomic_json(before_send_feed_path, simulator_workspace_feed(observed, package))
        atomic_json(feed_path, simulator_workspace_feed(observed, package))
        append_event(event_path, "DESKTOP_ASSISTANT_UPDATED", started, decision_id=package.decision_id)

        execution_adapter = SyntheticPDDExecutionAdapter(
            authorization_service=LedgerExecutionAuthorizationService(uow_factory),
            adapter=adapter,
            expected_store_id=package.store_id,
            expected_conversation_id=package.conversation_id,
            expected_customer_reference=package.customer_reference,
            expected_content=package.reply_content,
        )
        coordinator = ExecutionCoordinator(uow_factory, ApprovalPolicy())
        worker = ExecutionWorker(uow_factory, execution_adapter, "worker-synthetic-pdd")
        execution_runtime = CustomerAssistantRuntime(
            buffer,
            collector,
            AICustomerReplyService(uow_factory, gateway, clock=lambda: datetime.now(UTC)),
            coordinator,
            worker,
            uow_factory,
            clock=lambda: datetime.now(UTC),
            real_send_enabled=False,
        )
        confirmation = SimulatorConfirmationPolicy.confirmation(package, observed)
        append_event(event_path, "SIMULATOR_CONFIRMATION_GRANTED", started, decision_id=package.decision_id)
        execution = execution_runtime.confirm_and_execute(confirmation)
        final_snapshot = adapter.capture()
        if execution.outcome != "SUCCESS" or not execution.receipt_id:
            raise RuntimeError("synthetic execution did not create a successful immutable receipt")
        if not any(item.sender == "operator" and item.content == package.reply_content for item in final_snapshot.visible_history):
            raise RuntimeError("synthetic workspace did not display the AI-CS reply")
        with uow_factory() as uow:
            receipt = uow.require_repository().get_receipt_for_execution(execution.execution_id)
        if receipt is None or receipt.details.get("customer_message_sent") is not False:
            raise RuntimeError("receipt safety evidence is incomplete")
        atomic_json(feed_path, simulator_workspace_feed(final_snapshot, package, execution))
        elapsed = time.perf_counter() - injected_at
        append_event(event_path, "RECEIPT_CREATED", started, receipt_id=execution.receipt_id, outcome=execution.outcome)
        report.update({
            "status": "PASS",
            "acceptance": "SIMULATED_BUYER_TO_IMMUTABLE_RECEIPT_COMPLETE",
            "latency_seconds": round(elapsed, 3),
            "latency_budget_seconds": args.latency_budget_seconds,
            "latency_budget_met": elapsed <= args.latency_budget_seconds,
            "message_id": message_id,
            "conversation_id": package.conversation_id,
            "customer_context_id": package.context_id,
            "request_id": package.request_id,
            "decision_id": package.decision_id,
            "approval_id": execution.approval_id,
            "execution_id": execution.execution_id,
            "receipt_id": execution.receipt_id,
            "receipt_outcome": execution.outcome,
            "reply_content": package.reply_content,
            "context": {
                "store": {"store_id": final_snapshot.store_id, "store_name": final_snapshot.store_name},
                "product": final_snapshot.product.model_dump(mode="json"),
                "order": final_snapshot.transaction.model_dump(mode="json"),
                "visible_message_count": len(final_snapshot.visible_history),
            },
            "receipt": receipt.model_dump(mode="json"),
            "knowledge_publication": {
                "publication_receipt_id": knowledge_receipt.get("publication_receipt_id"),
                "knowledge_fingerprint": knowledge_receipt.get("knowledge_fingerprint"),
                "chunk_count": knowledge_receipt.get("chunk_count"),
                "embedding_count": knowledge_receipt.get("embedding_count"),
            },
            "artifacts": {
                "feed": str(feed_path),
                "feed_before_send": str(before_send_feed_path),
                "events": str(event_path),
                "report": str(report_path),
            },
        })
        if elapsed > args.latency_budget_seconds:
            report["status"] = "FAILED"
            report["error_code"] = "LATENCY_BUDGET_EXCEEDED"
            atomic_json(report_path, report)
            return 4
        atomic_json(status_path, {
            "phase": "SYNTHETIC_E2E_COMPLETE",
            "manual_approval_required": True,
            "simulator_auto_confirmation": True,
            "auto_reply_enabled": False,
            "real_send_enabled": False,
            "receipt_id": execution.receipt_id,
        })
        atomic_json(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        report["error_code"] = getattr(exc, "error_code", type(exc).__name__.upper())
        report["error_type"] = type(exc).__name__
        report["error_message"] = " ".join(str(exc).split())[:500]
        atomic_json(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 4
    finally:
        if gateway is not None:
            gateway.close()
        if engine is not None:
            engine.dispose()
        if not args.keep_browser_open:
            try:
                browser.close_browser()
            except Exception:
                pass
        browser.close_resources()


if __name__ == "__main__":
    raise SystemExit(main())
