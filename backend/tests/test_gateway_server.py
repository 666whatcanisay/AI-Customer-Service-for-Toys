from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from app.config.settings import Settings
from app.gateway.auth import canonical_signing_text
from app.gateway.contract import (
    CONTRACT_VERSION,
    DECISION_PATH,
    GATEWAY_MEDIA_TYPE,
    HEALTH_PATH,
    MAX_DECISION_BODY_BYTES,
)
from app.gateway.lan_proxy import GatewayLanProxyConfig, create_gateway_lan_proxy_app
from app.gateway.service import GatewayRuntimeConfig, GatewayServer
from app.gateway.store import DecisionClaimState, GatewayStateStore
from app.main import create_app
from app.reply_router.contracts import (
    ReplyEvidenceBundleV1,
    canonical_sha256,
    text_sha256,
)
from fastapi.testclient import TestClient

CLIENT_ID = "channel-engine"
KEY_ID = "gateway-key-v1"
SECRET = b"synthetic-gateway-secret-32-bytes-minimum"


def _result(action: str = "DIRECT_ANSWER") -> dict:
    return {
        "answer": "这是仅供客服人工确认的合成测试建议。",
        "action": action,
        "risk_level": "LOW",
        "sources": [{"synthetic": True}],
        "model": "synthetic-model",
        "latency_ms": 1.0,
        "request_id": "ai-request-001",
        "warnings": ["SUGGESTION_ONLY", "AUTO_SEND_DISABLED"],
        "required_fields": ["sku_id"] if action == "ASK_CLARIFY" else [],
    }


def _request_payload(**updates) -> dict:
    payload = {
        "contract_version": CONTRACT_VERSION,
        "request_id": "gateway-request-001",
        "idempotency_key": "decision-message-001",
        "correlation_id": "correlation-001",
        "conversation_id": "conversation-001",
        "message_id": "message-001",
        "customer_message": "这个玩具适合几岁？",
        "context": {
            "channel_name": "synthetic-channel",
            "locale": "zh-CN",
            "ai_cs_scope": {
                "tenant_id": "TENANT-SYNTHETIC",
                "platform": "pdd",
                "store_code": "STORE-SYNTHETIC",
                "product_id": "PRODUCT-SYNTHETIC",
                "sku_id": None,
            },
        },
        "requested_at": "2026-08-04T02:00:00Z",
    }
    payload.update(updates)
    return payload


def _body(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _signed_headers(
    *,
    method: str,
    path: str,
    body: bytes,
    request_id: str,
    correlation_id: str,
    idempotency_key: str,
    secret: bytes = SECRET,
    nonce: str | None = None,
    timestamp: datetime | None = None,
    content_type: str | None = "application/json",
) -> dict[str, str]:
    moment = timestamp or datetime.now(timezone.utc)
    timestamp_text = moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    nonce_value = nonce or f"nonce-{uuid.uuid4().hex}"
    content_sha256 = hashlib.sha256(body).hexdigest()
    signature = base64.urlsafe_b64encode(
        hmac.new(
            secret,
            canonical_signing_text(
                method=method,
                path=path,
                contract_version=CONTRACT_VERSION,
                client_id=CLIENT_ID,
                key_id=KEY_ID,
                timestamp=timestamp_text,
                nonce=nonce_value,
                request_id=request_id,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                content_sha256=content_sha256,
            ),
            hashlib.sha256,
        ).digest()
    ).decode("ascii").rstrip("=")
    headers = {
        "Authorization": (
            f"HMAC-SHA256 Credential={CLIENT_ID}/{KEY_ID},Signature={signature}"
        ),
        "X-AI-CS-Contract-Version": CONTRACT_VERSION,
        "X-AI-CS-Timestamp": timestamp_text,
        "X-AI-CS-Nonce": nonce_value,
        "X-AI-CS-Content-SHA256": content_sha256,
        "X-Request-ID": request_id,
        "X-Correlation-ID": correlation_id,
        "Idempotency-Key": idempotency_key,
    }
    if content_type is not None:
        headers["Content-Type"] = content_type
    return headers


def _post_decision(client, payload: dict, **header_options):
    body = _body(payload)
    headers = _signed_headers(
        method="POST",
        path=DECISION_PATH,
        body=body,
        request_id=payload.get("request_id", "gateway-request-001"),
        correlation_id=payload.get("correlation_id", "correlation-001"),
        idempotency_key=payload.get("idempotency_key", "decision-message-001"),
        **header_options,
    )
    return client.post(DECISION_PATH, content=body, headers=headers)


@pytest.fixture()
def gateway_harness(api_client, tmp_path: Path):
    client, _ = api_client
    active: list[GatewayServer] = []
    state_path = tmp_path / "gateway-state.sqlite3"

    def install(provider=None, *, state: Path | None = None) -> GatewayServer:
        if active:
            active.pop().close()
        server = GatewayServer(
            GatewayRuntimeConfig(
                client_id=CLIENT_ID,
                key_id=KEY_ID,
                hmac_secret=SECRET,
                state_path=state or state_path,
            ),
            decision_provider=provider or (lambda question, context: _result()),
            readiness_provider=lambda: (True, True),
        )
        client.app.state.gateway_server = server
        active.append(server)
        return server

    install()
    yield client, install, state_path
    if active:
        active.pop().close()
    client.app.state.gateway_server = None


def test_gateway_decision_returns_contract_response_and_required_approval(
    gateway_harness,
) -> None:
    client, _, _ = gateway_harness
    response = _post_decision(client, _request_payload())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(GATEWAY_MEDIA_TYPE)
    assert response.headers["x-ai-cs-contract-version"] == CONTRACT_VERSION
    assert response.headers["idempotency-replayed"] == "false"
    payload = response.json()
    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["request_id"] == "gateway-request-001"
    assert payload["idempotency_key"] == "decision-message-001"
    assert payload["action"] == "SUGGEST_REPLY"
    assert payload["requires_approval"] is True
    assert payload["proposed_content"]
    assert payload["metadata"]["source_count"] == 1


@pytest.mark.parametrize(
    "variant",
    [
        "MISSING",
        "TAMPERED",
        "UNKNOWN_VERSION",
        "STRUCTURE_INVALID",
        "CROSS_SCOPE",
    ],
)
def test_gateway_invalid_quality_evidence_fails_closed_to_no_action(
    gateway_harness, variant: str
) -> None:
    client, install, _ = gateway_harness
    result = {
        **_result(),
        "quality_gate_status": "PASS",
    }
    if variant in {"TAMPERED", "UNKNOWN_VERSION", "CROSS_SCOPE"}:
        fixture = (
            Path(__file__).resolve().parents[2]
            / "contracts"
            / "candidates"
            / "reply-router-v1"
            / "fixtures"
            / "reply-evidence-bundle.valid.json"
        )
        evidence = json.loads(fixture.read_text(encoding="utf-8"))
        if variant == "TAMPERED":
            evidence["warnings"] = ["TAMPERED"]
        elif variant == "UNKNOWN_VERSION":
            evidence["schema_version"] = "reply-evidence-bundle.v999"
        else:
            evidence["scope"]["tenant_id"] = "TENANT-OTHER"
            for source in evidence["sources"]:
                source["scope"]["tenant_id"] = "TENANT-OTHER"
            evidence["bundle_sha256"] = canonical_sha256(
                {
                    key: value
                    for key, value in evidence.items()
                    if key != "bundle_sha256"
                }
            )
            response_fixture = fixture.with_name(
                "gateway-decision-response.with-reply-evidence.json"
            )
            result["answer"] = json.loads(
                response_fixture.read_text(encoding="utf-8")
            )["proposed_content"]
        result["reply_evidence_bundle"] = evidence
    elif variant == "STRUCTURE_INVALID":
        result["reply_evidence_bundle"] = {
            "schema_version": "reply-evidence-bundle.v1"
        }
    install(
        lambda question, context: result
    )
    response = _post_decision(client, _request_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "NO_ACTION"
    assert payload["proposed_content"] is None
    assert payload["risk_level"] == "HIGH"
    assert payload["metadata"]["ai_cs_action"] == "TRANSFER_HUMAN"
    assert payload["metadata"]["warnings"] == ["REPLY_EVIDENCE_INVALID"]
    assert "reply_evidence_bundle" not in payload["metadata"]


def test_gateway_validates_bounded_host_context_and_projects_citations(
    gateway_harness,
) -> None:
    client, install, _ = gateway_harness
    captured = []

    def provider(question, context):
        del question
        captured.append(context)
        return {
            **_result("DIRECT_ANSWER"),
            "required_fields": [],
            "sources": [
                {
                    "source_name": "synthetic-product-faq.md",
                    "page": 1,
                    "chunk_id": "chunk-product-001",
                    "distance": 0.1,
                    "product_id": "PRODUCT-SYNTHETIC",
                    "sku_id": "SKU-SYNTHETIC",
                }
            ],
        }

    install(provider)
    request_payload = _request_payload()
    request_payload["context"].update(
        {
            "product": {
                "product_reference": "PRODUCT-SYNTHETIC",
                "product_name": "Synthetic Product",
                "sku_reference": "SKU-SYNTHETIC",
                "sku_name": "Standard",
                "attributes": {"color": "violet"},
            },
            "transaction": {
                "order_reference": "ORDER-SYNTHETIC",
                "order_status": "PAID",
                "logistics_status": "NOT_SHIPPED",
                "aftersales_status": None,
                "payment_data_included": False,
                "address_data_included": False,
            },
            "visible_conversation_history": [
                {
                    "message_id": "message-history-001",
                    "sender": "customer",
                    "content": "Synthetic recent question",
                    "timestamp": "2026-08-11T12:00:00Z",
                }
            ],
        }
    )
    request_payload["context"]["ai_cs_scope"]["sku_id"] = "SKU-SYNTHETIC"

    response = _post_decision(client, request_payload)

    assert response.status_code == 200
    assert len(captured) == 1
    context = captured[0]
    assert context.verified_product.product_name == "Synthetic Product"
    assert context.verified_transaction.order_reference == "ORDER-SYNTHETIC"
    assert context.recent_conversation[0].content == "Synthetic recent question"
    assert response.json()["metadata"]["citations"] == [
        {
            "reference": "chunk-product-001",
            "title": "synthetic-product-faq.md",
            "product_id": "PRODUCT-SYNTHETIC",
            "sku_id": "SKU-SYNTHETIC",
            "source_kind": "RAG_KNOWLEDGE",
        }
    ]


def test_gateway_lan_edge_preserves_hmac_decision_and_idempotency(
    gateway_harness,
) -> None:
    core_client, _, _ = gateway_harness

    def upstream(request: httpx.Request) -> httpx.Response:
        response = core_client.request(
            request.method,
            request.url.path,
            content=request.content,
            headers=dict(request.headers),
        )
        return httpx.Response(
            response.status_code,
            content=response.content,
            headers=dict(response.headers),
        )

    proxy_config = GatewayLanProxyConfig.build(
        bind_address="192.168.1.11",
        port=18080,
        interface_network="192.168.1.0/24",
        allowed_networks=["192.168.1.0/24"],
        upstream_origin="http://127.0.0.1:8000",
    )
    proxy = create_gateway_lan_proxy_app(
        proxy_config,
        transport=httpx.MockTransport(upstream),
        client_host_resolver=lambda _: "192.168.1.50",
    )
    payload = _request_payload()
    body = _body(payload)

    with TestClient(proxy) as lan_client:
        anonymous = lan_client.post(
            DECISION_PATH, content=body, headers={"Content-Type": "application/json"}
        )
        first = lan_client.post(
            DECISION_PATH,
            content=body,
            headers=_signed_headers(
                method="POST",
                path=DECISION_PATH,
                body=body,
                request_id=payload["request_id"],
                correlation_id=payload["correlation_id"],
                idempotency_key=payload["idempotency_key"],
            ),
        )
        replay = lan_client.post(
            DECISION_PATH,
            content=body,
            headers=_signed_headers(
                method="POST",
                path=DECISION_PATH,
                body=body,
                request_id=payload["request_id"],
                correlation_id=payload["correlation_id"],
                idempotency_key=payload["idempotency_key"],
            ),
        )

    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["error_code"] == "AUTHENTICATION_REQUIRED"
    assert first.status_code == 200
    assert first.json()["requires_approval"] is True
    assert replay.status_code == 200
    assert replay.json()["decision_id"] == first.json()["decision_id"]
    assert replay.headers["idempotency-replayed"] == "true"


@pytest.mark.parametrize(
    ("ai_action", "gateway_action", "has_content"),
    [
        ("DIRECT_ANSWER", "SUGGEST_REPLY", True),
        ("CONTROLLED_ANSWER", "SUGGEST_REPLY", True),
        ("ASK_CLARIFY", "SUGGEST_REPLY", True),
        ("REQUIRE_LOOKUP", "NO_ACTION", False),
        ("TRANSFER_HUMAN", "NO_ACTION", False),
        ("REFUSE", "NO_ACTION", False),
    ],
)
def test_gateway_maps_all_existing_ai_actions_without_executing(
    gateway_harness,
    ai_action: str,
    gateway_action: str,
    has_content: bool,
) -> None:
    client, install, _ = gateway_harness
    install(lambda question, context: _result(ai_action))
    payload = _request_payload(
        idempotency_key=f"decision-{ai_action.lower()}",
        request_id=f"request-{ai_action.lower()}",
    )

    response = _post_decision(client, payload)

    assert response.status_code == 200
    assert response.json()["action"] == gateway_action
    assert (response.json()["proposed_content"] is not None) is has_content
    assert response.json()["requires_approval"] is True


@pytest.mark.parametrize(
    ("message", "expected_fragment", "expected_risk"),
    [
        ("这个多少钱，还有库存吗？", "商品页面显示", "MEDIUM"),
        ("我的订单什么时候到？", "订单详情页", "MEDIUM"),
        ("我要退款怎么办？", "发起售后申请", "MEDIUM"),
        ("孩子误吞小颗粒怎么办？", "及时就医", "HIGH"),
        ("这款积木拼好后有多大？", "详情页和所选规格标注", "MEDIUM"),
        ("这款积木一共有多少颗粒？", "标注的颗粒数量", "MEDIUM"),
        ("这个商品主要是什么材质？", "对应规格的材质说明", "MEDIUM"),
        ("这个商品是什么包装？", "所选规格的包装说明", "MEDIUM"),
    ],
)
def test_auto_all_messages_maps_manual_routes_to_governed_fixed_reply(
    gateway_harness,
    message: str,
    expected_fragment: str,
    expected_risk: str,
) -> None:
    client, install, _ = gateway_harness
    install(lambda question, context: _result("REQUIRE_LOOKUP"))
    payload = _request_payload(
        request_id=f"request-auto-{text_sha256(message)[:12]}",
        idempotency_key=f"decision-auto-{text_sha256(message)[:12]}",
        customer_message=message,
    )
    payload["context"]["auto_first_response_policy"] = "AUTO_ALL_MESSAGES_V1"

    response = _post_decision(client, payload)

    assert response.status_code == 200
    decision = response.json()
    assert decision["action"] == "SUGGEST_REPLY"
    assert expected_fragment in decision["proposed_content"]
    assert decision["risk_level"] == expected_risk
    assert decision["metadata"]["ai_cs_action"] == "CONTROLLED_ANSWER"
    assert (
        decision["metadata"]["auto_authorization_basis"]
        == "STORE_APPROVED_FIXED_REPLY"
    )
    evidence = ReplyEvidenceBundleV1.model_validate_json(
        json.dumps(
            decision["metadata"]["reply_evidence_bundle"],
            ensure_ascii=False,
        )
    )
    evidence.validate_proposed_content(decision["proposed_content"])


def test_auto_all_messages_marker_is_required_for_fixed_reply_override(
    gateway_harness,
) -> None:
    client, install, _ = gateway_harness
    install(lambda question, context: _result("REQUIRE_LOOKUP"))

    response = _post_decision(client, _request_payload(customer_message="还有库存吗？"))

    assert response.status_code == 200
    assert response.json()["action"] == "NO_ACTION"
    assert response.json()["proposed_content"] is None


def test_gateway_rejects_anonymous_invalid_signature_stale_timestamp_and_nonce_replay(
    gateway_harness,
) -> None:
    client, _, _ = gateway_harness
    payload = _request_payload()
    body = _body(payload)
    anonymous = client.post(
        DECISION_PATH,
        content=body,
        headers={"Content-Type": "application/json"},
    )
    invalid = _post_decision(client, payload, secret=b"x" * 32)
    stale = _post_decision(
        client,
        payload,
        timestamp=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    nonce = f"nonce-{uuid.uuid4().hex}"
    first = _post_decision(client, payload, nonce=nonce)
    replay = _post_decision(client, payload, nonce=nonce)

    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["error_code"] == "AUTHENTICATION_REQUIRED"
    assert invalid.status_code == 401
    assert invalid.json()["error"]["error_code"] == "AUTHENTICATION_FAILED"
    assert stale.status_code == 401
    assert stale.json()["error"]["error_code"] == "AUTHENTICATION_FAILED"
    assert first.status_code == 200
    assert replay.status_code == 401
    assert replay.json()["error"]["error_code"] == "AUTHENTICATION_FAILED"


def test_gateway_idempotency_replays_same_decision_and_rejects_conflict(
    gateway_harness,
) -> None:
    client, install, _ = gateway_harness
    calls: list[str] = []

    def provider(question, context):
        calls.append(question)
        return _result()

    install(provider)
    original = _request_payload()
    first = _post_decision(client, original)
    replay = _post_decision(client, original)
    conflict_payload = _request_payload(customer_message="不同的合成问题")
    conflict = _post_decision(client, conflict_payload)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.headers["idempotency-replayed"] == "true"
    assert replay.json() == first.json()
    assert calls == [original["customer_message"]]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["error_code"] == "IDEMPOTENCY_CONFLICT"


def test_gateway_idempotency_survives_server_restart(gateway_harness) -> None:
    client, install, state_path = gateway_harness
    calls: list[str] = []

    def provider(question, context):
        calls.append(question)
        return _result()

    install(provider, state=state_path)
    payload = _request_payload()
    first = _post_decision(client, payload)
    install(provider, state=state_path)
    replay = _post_decision(client, payload)

    assert replay.status_code == 200
    assert replay.headers["idempotency-replayed"] == "true"
    assert replay.json() == first.json()
    assert len(calls) == 1


def test_expired_idempotency_lease_cannot_be_overwritten_by_stale_owner(
    tmp_path: Path,
) -> None:
    store = GatewayStateStore(
        tmp_path / "lease-state.sqlite3",
        nonce_ttl_seconds=600,
        decision_retention_seconds=3600,
        decision_lease_seconds=1,
    )
    try:
        first = store.begin_decision(
            client_id=CLIENT_ID,
            idempotency_key="lease-key",
            payload_hash="a" * 64,
            now_epoch=100.0,
        )
        second = store.begin_decision(
            client_id=CLIENT_ID,
            idempotency_key="lease-key",
            payload_hash="a" * 64,
            now_epoch=102.0,
        )
        assert first.claim_token and second.claim_token
        assert first.claim_token != second.claim_token

        store.abandon_decision(
            client_id=CLIENT_ID,
            idempotency_key="lease-key",
            payload_hash="a" * 64,
            claim_token=first.claim_token,
        )
        active = store.begin_decision(
            client_id=CLIENT_ID,
            idempotency_key="lease-key",
            payload_hash="a" * 64,
            now_epoch=102.5,
        )
        assert active.state is DecisionClaimState.IN_PROGRESS

        with pytest.raises(RuntimeError):
            store.complete_decision(
                client_id=CLIENT_ID,
                idempotency_key="lease-key",
                payload_hash="a" * 64,
                claim_token=first.claim_token,
                response_json="{}",
                now_epoch=102.5,
            )
        store.complete_decision(
            client_id=CLIENT_ID,
            idempotency_key="lease-key",
            payload_hash="a" * 64,
            claim_token=second.claim_token,
            response_json="{}",
            now_epoch=102.5,
        )
        replay = store.begin_decision(
            client_id=CLIENT_ID,
            idempotency_key="lease-key",
            payload_hash="a" * 64,
            now_epoch=103.0,
        )
        assert replay.state is DecisionClaimState.REPLAY
    finally:
        store.close()


def test_gateway_validation_and_service_failures_use_error_envelope(
    gateway_harness,
) -> None:
    client, install, _ = gateway_harness
    no_scope = _request_payload(context={"channel_name": "synthetic"})
    scope_error = _post_decision(client, no_scope)

    unknown_field = _request_payload(unexpected="forbidden")
    schema_error = _post_decision(client, unknown_field)

    legacy_names = _request_payload()
    legacy_names["schema_version"] = legacy_names.pop("contract_version")
    legacy_names["message"] = legacy_names.pop("customer_message")
    version_error = _post_decision(client, legacy_names)

    install(
        lambda question, context: {
            **_result("REFUSE"),
            "answer": "服务暂时不可用，请稍后重试。",
            "warnings": ["RAG_RUNTIME_ERROR"],
        }
    )
    unavailable_payload = _request_payload(idempotency_key="decision-unavailable")
    unavailable = _post_decision(client, unavailable_payload)

    assert scope_error.status_code == 422
    assert scope_error.json()["error"]["error_code"] == "SCHEMA_VALIDATION_FAILED"
    assert schema_error.status_code == 422
    assert schema_error.json()["error"]["error_code"] == "SCHEMA_VALIDATION_FAILED"
    assert version_error.status_code == 406
    assert version_error.json()["error"]["error_code"] == "UNSUPPORTED_CONTRACT_VERSION"
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["error_code"] == "SERVICE_UNAVAILABLE"
    assert unavailable.json()["error"]["retryable"] is True


def test_gateway_rejects_unsupported_media_and_oversized_payload(
    gateway_harness,
) -> None:
    client, _, _ = gateway_harness
    unsupported = _post_decision(
        client,
        _request_payload(),
        content_type="text/plain",
    )

    oversized_body = b"{" + (b"x" * MAX_DECISION_BODY_BYTES) + b"}"
    oversized_headers = _signed_headers(
        method="POST",
        path=DECISION_PATH,
        body=oversized_body,
        request_id="oversized-request",
        correlation_id="oversized-correlation",
        idempotency_key="oversized-idempotency",
    )
    oversized = client.post(
        DECISION_PATH,
        content=oversized_body,
        headers=oversized_headers,
    )

    assert unsupported.status_code == 415
    assert unsupported.json()["error"]["error_code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert oversized.status_code == 413
    assert oversized.json()["error"]["error_code"] == "PAYLOAD_TOO_LARGE"


def test_gateway_health_is_authenticated_and_reports_no_production_connection(
    gateway_harness,
) -> None:
    client, _, _ = gateway_harness
    anonymous = client.get(HEALTH_PATH)
    request_id = "health-request-001"
    correlation_id = "health-correlation-001"
    headers = _signed_headers(
        method="GET",
        path=HEALTH_PATH,
        body=b"",
        request_id=request_id,
        correlation_id=correlation_id,
        idempotency_key="health-check-001",
        content_type=None,
    )
    response = client.request("GET", HEALTH_PATH, content=b"", headers=headers)

    assert anonymous.status_code == 401
    assert response.status_code == 200
    assert response.json()["status"] == "HEALTHY"
    assert response.json()["contract_version"] == CONTRACT_VERSION
    assert response.json()["capabilities"] == ["decision.ai-cs-scope.v1"]
    assert response.json()["real_ai_cs_connected"] is True
    assert response.json()["details"]["production_channel_connected"] is False


def test_gateway_does_not_change_legacy_chat_contract(gateway_harness) -> None:
    client, _, _ = gateway_harness
    before = client.post(
        "/api/chat", json={"message": "星云狐狸玩具的指示灯是紫色"}
    )
    gateway = _post_decision(client, _request_payload())
    after = client.post(
        "/api/chat", json={"message": "星云狐狸玩具的指示灯是紫色"}
    )

    assert gateway.status_code == 200
    assert before.status_code == after.status_code == 200
    for response in (before, after):
        assert response.json()["success"] is True
        assert response.json()["data"]["action"] == "ANSWER"
        assert {
            "answer",
            "action",
            "sources",
            "model",
            "latency_ms",
            "request_id",
        } <= response.json()["data"].keys()


def test_unknown_gateway_route_and_method_use_error_envelope(gateway_harness) -> None:
    client, _, _ = gateway_harness
    missing = client.get("/gateway/v1/missing")
    wrong_method = client.put(DECISION_PATH)

    assert missing.status_code == 404
    assert missing.json()["error"]["error_code"] == "RESOURCE_NOT_FOUND"
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["error_code"] == "METHOD_NOT_ALLOWED"


def test_gateway_disabled_state_does_not_change_existing_ai_health(api_client) -> None:
    client, _ = api_client

    gateway = client.get(HEALTH_PATH)
    legacy = client.get("/api/health")

    assert gateway.status_code == 503
    assert gateway.json()["error"]["error_code"] == "SERVICE_UNAVAILABLE"
    assert legacy.status_code == 200
    assert legacy.json()["data"]["status"] == "ok"


def test_enabled_runtime_builds_gateway_without_changing_legacy_routes(
    tmp_path: Path,
) -> None:
    class StubRag:
        model_configured = True

        def __init__(self) -> None:
            self.calls = []

        def warm_up(self) -> None:
            return None

        def query(self, question, context=None):
            self.calls.append((question, context))
            return {
                **_result(),
                "sources": [
                    {
                        "source_name": "synthetic-product-faq.md",
                        "chunk_id": "chunk-product-001",
                        "distance": 0.1,
                        "product_id": "PRODUCT-SYNTHETIC",
                        "sku_id": None,
                        "knowledge_version": "a" * 64,
                        "source_ids": ["SOURCE-SYNTHETIC-001"],
                    }
                ],
            }

        def close(self) -> None:
            return None

    secret_path = tmp_path / "gateway-hmac.secret"
    secret_path.write_text(SECRET.decode("ascii") + "\n", encoding="utf-8")
    internal_secret_path = tmp_path / "internal-service.secret"
    internal_token = "test-internal-service-token-32-bytes-minimum"
    internal_secret_path.write_text(internal_token, encoding="utf-8")
    settings = replace(
        Settings.from_env(),
        backend_root=tmp_path,
        project_root=tmp_path,
        knowledge_base_path=tmp_path / "knowledge",
        vector_db_path=tmp_path / "vectors",
        log_dir=tmp_path / "logs",
        gateway_enabled=True,
        gateway_client_id=CLIENT_ID,
        gateway_key_id=KEY_ID,
        gateway_hmac_secret="",
        gateway_hmac_secret_file=secret_path,
        gateway_state_path=tmp_path / "gateway-state.sqlite3",
        internal_service_secret_file=internal_secret_path,
    )
    stub_rag = StubRag()
    app = create_app(settings=settings, rag_factory=lambda active: stub_rag)

    with TestClient(app, headers={"X-AI-CS-Service-Token": internal_token}) as client:
        missing_turn = _post_decision(client, _request_payload())
        payload = _request_payload(
            request_id="gateway-request-002",
            idempotency_key="decision-message-002",
            correlation_id="correlation-002",
        )
        message = payload["customer_message"]
        payload["context"]["ai_cs_reply_turn"] = {
            "schema_version": "ai-cs-reply-turn.v1",
            "turn_id": "assistant-turn:synthetic-002",
            "aggregate_content_sha256": text_sha256(message),
            "index_unit": "UNICODE_CODE_POINT",
            "aggregation_separator": "\n",
            "messages": [
                {
                    "message_id": "PDD-MSG-SYNTHETIC-002",
                    "content_sha256": text_sha256(message),
                    "range_start": 0,
                    "range_end": len(message),
                }
            ],
        }
        decision = _post_decision(client, payload)
        runtime = client.get("/api/admin/server-runtime")
        legacy = client.post("/api/chat", json={"message": "合成测试问题"})

    assert missing_turn.status_code == 200
    assert missing_turn.json()["action"] == "NO_ACTION"
    assert "REPLY_ROUTER_MANUAL_REQUIRED" in missing_turn.json()["metadata"]["warnings"]
    assert decision.status_code == 200
    assert decision.json()["action"] == "SUGGEST_REPLY"
    assert decision.json()["requires_approval"] is True
    evidence = ReplyEvidenceBundleV1.model_validate_json(
        json.dumps(
            decision.json()["metadata"]["reply_evidence_bundle"],
            ensure_ascii=False,
        )
    )
    evidence.validate_proposed_content(decision.json()["proposed_content"])
    assert len(stub_rag.calls) == 2
    assert stub_rag.calls[0][1].recent_conversation[-1].content == message
    assert stub_rag.calls[1][1] is None
    assert legacy.status_code == 200
    assert legacy.json()["success"] is True
    assert runtime.status_code == 200
    assert runtime.json()["gateway"] == {
        "enabled": True,
        "status": "HEALTHY",
        "version": "ai-cs-gateway.v1",
        "contract_version": "1.0",
        "configuration_state": "CONFIGURED",
    }
