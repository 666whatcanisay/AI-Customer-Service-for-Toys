from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.gateway.auth import GatewayAuthenticator, GatewayIdentity
from app.gateway.contract import (
    CAPABILITY_VERSION,
    CONTRACT_VERSION,
    GATEWAY_VERSION,
    DecisionRequest,
    DecisionResponse,
    GatewayDecisionAction,
    GatewayErrorCode,
    GatewayHealth,
    GatewayHealthStatus,
    GatewayProblem,
    GatewayRiskLevel,
    utc_now,
)
from app.gateway.store import DecisionClaimState, GatewayStateStore
from app.models.chat import (
    FrozenChatContext,
    VerifiedConversationEntry,
    VerifiedProductContext,
    VerifiedTransactionContext,
)
from app.service.rag_service import (
    LLM_REQUEST_FAILED_MESSAGE,
    MODEL_NOT_CONFIGURED_MESSAGE,
    RAG_RUNTIME_ERROR_MESSAGE,
)


DecisionProvider = Callable[[str, FrozenChatContext], dict[str, Any]]
ReadinessProvider = Callable[[], tuple[bool, bool]]


@dataclass(frozen=True, slots=True)
class GatewayRuntimeConfig:
    client_id: str
    key_id: str
    hmac_secret: bytes = field(repr=False)
    state_path: Path
    clock_skew_seconds: int = 300
    nonce_ttl_seconds: int = 600
    decision_retention_seconds: int = 7 * 24 * 60 * 60
    decision_lease_seconds: int = 30

    def __post_init__(self) -> None:
        if not self.client_id or not self.key_id:
            raise ValueError("gateway credential identifiers must be configured")
        if len(self.hmac_secret) < 32:
            raise ValueError("gateway HMAC secret must contain at least 32 bytes")


class GatewayServer:
    def __init__(
        self,
        config: GatewayRuntimeConfig,
        *,
        decision_provider: DecisionProvider,
        readiness_provider: ReadinessProvider,
    ) -> None:
        self.config = config
        self._decision_provider = decision_provider
        self._readiness_provider = readiness_provider
        self.state_store = GatewayStateStore(
            config.state_path,
            nonce_ttl_seconds=config.nonce_ttl_seconds,
            decision_retention_seconds=config.decision_retention_seconds,
            decision_lease_seconds=config.decision_lease_seconds,
        )
        self.authenticator = GatewayAuthenticator(
            credentials={(config.client_id, config.key_id): config.hmac_secret},
            state_store=self.state_store,
            allowed_clock_skew_seconds=config.clock_skew_seconds,
        )

    def health(self) -> GatewayHealth:
        ai_ready, model_configured = self._readiness_provider()
        healthy = ai_ready and model_configured
        return GatewayHealth(
            status=(
                GatewayHealthStatus.HEALTHY
                if healthy
                else GatewayHealthStatus.UNHEALTHY
            ),
            service="ai-cs-gateway",
            contract_version=CONTRACT_VERSION,
            version=GATEWAY_VERSION,
            capabilities=(CAPABILITY_VERSION,),
            reachable=True,
            real_ai_cs_connected=True,
            timestamp=utc_now(),
            details={
                "gateway_configured": True,
                "ai_ready": ai_ready,
                "model_configured": model_configured,
                "production_channel_connected": False,
            },
        )

    def decide(
        self,
        identity: GatewayIdentity,
        request: DecisionRequest,
    ) -> tuple[DecisionResponse, bool]:
        canonical = json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        payload_hash = hashlib.sha256(canonical).hexdigest()
        now_epoch = utc_now().astimezone(timezone.utc).timestamp()
        claim = self.state_store.begin_decision(
            client_id=identity.client_id,
            idempotency_key=request.idempotency_key,
            payload_hash=payload_hash,
            now_epoch=now_epoch,
        )
        if claim.state is DecisionClaimState.REPLAY:
            try:
                return DecisionResponse.model_validate_json(claim.response_json), True
            except ValidationError as exc:
                raise GatewayProblem(
                    status_code=500,
                    code=GatewayErrorCode.INTERNAL_ERROR,
                    message="Stored Gateway decision is unavailable.",
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                ) from exc
        if claim.state is DecisionClaimState.CONFLICT:
            raise GatewayProblem(
                status_code=409,
                code=GatewayErrorCode.IDEMPOTENCY_CONFLICT,
                message="Idempotency key is bound to another request.",
                request_id=request.request_id,
                correlation_id=request.correlation_id,
            )
        if claim.state is DecisionClaimState.IN_PROGRESS:
            raise GatewayProblem(
                status_code=409,
                code=GatewayErrorCode.IDEMPOTENCY_IN_PROGRESS,
                message="Gateway decision is still in progress.",
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                retry_after_seconds=1,
            )
        if claim.claim_token is None:
            raise GatewayProblem(
                status_code=500,
                code=GatewayErrorCode.INTERNAL_ERROR,
                message="Gateway idempotency claim is unavailable.",
                request_id=request.request_id,
                correlation_id=request.correlation_id,
            )

        try:
            scope = self._scope_from(request)
            result = self._decision_provider(request.customer_message, scope)
            response = self._map_response(request, result)
            response_json = response.model_dump_json()
            self.state_store.complete_decision(
                client_id=identity.client_id,
                idempotency_key=request.idempotency_key,
                payload_hash=payload_hash,
                claim_token=claim.claim_token,
                response_json=response_json,
                now_epoch=utc_now().astimezone(timezone.utc).timestamp(),
            )
            return response, False
        except GatewayProblem:
            self.state_store.abandon_decision(
                client_id=identity.client_id,
                idempotency_key=request.idempotency_key,
                payload_hash=payload_hash,
                claim_token=claim.claim_token,
            )
            raise
        except Exception as exc:
            self.state_store.abandon_decision(
                client_id=identity.client_id,
                idempotency_key=request.idempotency_key,
                payload_hash=payload_hash,
                claim_token=claim.claim_token,
            )
            raise GatewayProblem(
                status_code=500,
                code=GatewayErrorCode.INTERNAL_ERROR,
                message="Gateway decision could not be created.",
                request_id=request.request_id,
                correlation_id=request.correlation_id,
            ) from exc

    @staticmethod
    def _scope_from(request: DecisionRequest) -> FrozenChatContext:
        raw_scope = request.context.get("ai_cs_scope")
        if not isinstance(raw_scope, dict):
            raise GatewayProblem(
                status_code=422,
                code=GatewayErrorCode.SCHEMA_VALIDATION_FAILED,
                message="context.ai_cs_scope is required for AI-CS decisions.",
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                details={"field": "context.ai_cs_scope"},
            )
        try:
            product = request.context.get("product")
            transaction = request.context.get("transaction")
            raw_history = request.context.get("visible_conversation_history")
            if not isinstance(raw_history, list) or not raw_history:
                raw_history = request.context.get("conversation_history")
            if not isinstance(raw_history, list):
                raw_history = []
            verified_history = tuple(
                VerifiedConversationEntry.model_validate(
                    GatewayServer._bounded_history_item(item)
                )
                for item in raw_history[-20:]
                if isinstance(item, dict)
            )
            enriched_scope = dict(raw_scope)
            if isinstance(product, dict):
                enriched_scope["verified_product"] = VerifiedProductContext.model_validate(
                    product
                ).model_dump()
            if isinstance(transaction, dict):
                enriched_scope["verified_transaction"] = (
                    VerifiedTransactionContext.model_validate(transaction).model_dump()
                )
            enriched_scope["recent_conversation"] = verified_history
            return FrozenChatContext.model_validate(enriched_scope, strict=True)
        except ValidationError as exc:
            raise GatewayProblem(
                status_code=422,
                code=GatewayErrorCode.SCHEMA_VALIDATION_FAILED,
                message="context.ai_cs_scope is invalid.",
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                details={"field": "context.ai_cs_scope"},
            ) from exc

    @staticmethod
    def _bounded_history_item(item: dict[object, object]) -> dict[object, object]:
        """Bound already-redacted context without weakening its strict schema."""

        value = dict(item)
        limits = {"message_id": 255, "sender": 32, "content": 2_000, "timestamp": 64}
        for field, maximum in limits.items():
            candidate = value.get(field)
            if isinstance(candidate, str):
                value[field] = candidate[:maximum]
        return value

    @staticmethod
    def _map_response(
        request: DecisionRequest,
        result: dict[str, Any],
    ) -> DecisionResponse:
        warnings = result.get("warnings")
        if not isinstance(warnings, list) or not all(
            isinstance(item, str) for item in warnings
        ):
            warnings = []
        answer = result.get("answer")
        if (
            "RAG_RUNTIME_ERROR" in warnings
            or answer in {
                MODEL_NOT_CONFIGURED_MESSAGE,
                LLM_REQUEST_FAILED_MESSAGE,
                RAG_RUNTIME_ERROR_MESSAGE,
            }
        ):
            raise GatewayProblem(
                status_code=503,
                code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                message="AI decision capability is unavailable.",
                request_id=request.request_id,
                correlation_id=request.correlation_id,
            )

        ai_action = result.get("action")
        suggest_actions = {"DIRECT_ANSWER", "CONTROLLED_ANSWER", "ASK_CLARIFY"}
        no_action_actions = {"REQUIRE_LOOKUP", "TRANSFER_HUMAN", "REFUSE"}
        if ai_action not in suggest_actions | no_action_actions:
            raise GatewayProblem(
                status_code=500,
                code=GatewayErrorCode.INTERNAL_ERROR,
                message="AI decision action is not supported by Gateway V1.",
                request_id=request.request_id,
                correlation_id=request.correlation_id,
            )
        action = (
            GatewayDecisionAction.SUGGEST_REPLY
            if ai_action in suggest_actions
            else GatewayDecisionAction.NO_ACTION
        )
        proposed_content: str | None = None
        if action is GatewayDecisionAction.SUGGEST_REPLY:
            if not isinstance(answer, str) or not answer.strip() or len(answer) > 8_000:
                raise GatewayProblem(
                    status_code=500,
                    code=GatewayErrorCode.INTERNAL_ERROR,
                    message="AI decision content is invalid.",
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                )
            proposed_content = answer.strip()

        required_fields = result.get("required_fields")
        if not isinstance(required_fields, list) or not all(
            isinstance(item, str) for item in required_fields
        ):
            required_fields = []
        sources = result.get("sources")
        source_count = len(sources) if isinstance(sources, list) else 0
        raw_risk_level = result.get("risk_level")
        risk_level = (
            GatewayRiskLevel(raw_risk_level)
            if raw_risk_level in {item.value for item in GatewayRiskLevel}
            else GatewayRiskLevel.HIGH
        )
        metadata: dict[str, Any] = {
            "ai_cs_action": ai_action,
            "risk_level": risk_level.value,
            "warnings": warnings,
            "required_fields": required_fields,
            "source_count": source_count,
            "citations": GatewayServer._citation_descriptors(sources),
        }
        ai_request_id = result.get("request_id")
        if isinstance(ai_request_id, str) and ai_request_id:
            metadata["ai_request_id"] = ai_request_id[:128]

        return DecisionResponse(
            contract_version=CONTRACT_VERSION,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            correlation_id=request.correlation_id,
            decision_id=f"decision-{uuid.uuid4().hex}",
            action=action,
            proposed_content=proposed_content,
            requires_approval=True,
            risk_level=risk_level,
            gateway_version=GATEWAY_VERSION,
            metadata=metadata,
            decided_at=utc_now(),
        )

    @staticmethod
    def _citation_descriptors(sources: Any) -> list[dict[str, Any]]:
        if not isinstance(sources, list):
            return []
        citations: list[dict[str, Any]] = []
        for item in sources[:32]:
            if not isinstance(item, dict):
                continue
            chunk_id = item.get("chunk_id")
            source_name = item.get("source_name")
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                continue
            title = (
                source_name.strip()
                if isinstance(source_name, str) and source_name.strip()
                else "AI-CS knowledge"
            )
            if title.casefold().startswith("product-knowledge:"):
                title = "商品知识"
            excerpt = item.get("excerpt")
            descriptor = {
                    "reference": chunk_id.strip()[:512],
                    "title": title[:256],
                    "product_id": (
                        str(item["product_id"])[:160]
                        if item.get("product_id") is not None
                        else None
                    ),
                    "sku_id": (
                        str(item["sku_id"])[:160]
                        if item.get("sku_id") is not None
                        else None
                    ),
                    "source_kind": "RAG_KNOWLEDGE",
                }
            if isinstance(excerpt, str) and excerpt.strip():
                descriptor["excerpt"] = excerpt.strip()[:1000]
            citations.append(descriptor)
        return citations

    def close(self) -> None:
        self.state_store.close()
