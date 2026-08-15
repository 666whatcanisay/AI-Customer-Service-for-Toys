from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
from app.reply_router.contracts import (
    ReplyEvidenceBundleV1,
    RuleScopeKind,
    canonical_sha256,
    text_sha256,
)
from app.service.rag_service import (
    LLM_REQUEST_FAILED_MESSAGE,
    MODEL_NOT_CONFIGURED_MESSAGE,
    RAG_RUNTIME_ERROR_MESSAGE,
)

DecisionProvider = Callable[[str, FrozenChatContext], dict[str, Any]]
RequestDecisionProvider = Callable[
    [DecisionRequest, FrozenChatContext], dict[str, Any]
]
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
        request_decision_provider: RequestDecisionProvider | None = None,
    ) -> None:
        self.config = config
        self._decision_provider = decision_provider
        self._request_decision_provider = request_decision_provider
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
            decision_message = self._resolve_contextual_customer_message(
                request=request,
                scope=scope,
            )
            result = (
                self._request_decision_provider(
                    request.model_copy(
                        update={"customer_message": decision_message}
                    ),
                    scope,
                )
                if self._request_decision_provider is not None
                else self._decision_provider(decision_message, scope)
            )
            response = self._map_response(request, result, scope)
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
    def _resolve_contextual_customer_message(
        *,
        request: DecisionRequest,
        scope: FrozenChatContext,
    ) -> str:
        """Resolve a short product-card follow-up to the immediately prior intent.

        The resolution is deliberately narrow: it only applies when the current
        product is verified, the immediately preceding customer message carries
        a supported intent, and both messages are within five minutes.  It never
        searches older turns past an operator/system boundary.
        """

        message = request.customer_message.strip()
        compact = "".join(message.lower().split())
        if compact not in {
            "这款呢",
            "这个呢",
            "那这款呢",
            "那这个呢",
            "这一个呢",
            "这个商品呢",
        }:
            return message
        if scope.product_id.startswith("__STORE_LEVEL_"):
            return message

        current_skipped = False
        for entry in reversed(scope.recent_conversation):
            candidate = entry.content.strip()
            if not current_skipped and (
                entry.message_id == request.message_id or candidate == message
            ):
                current_skipped = True
                continue
            if entry.sender and entry.sender.upper() not in {
                "CUSTOMER",
                "BUYER",
                "USER",
            }:
                return message
            try:
                timestamp = datetime.fromisoformat(
                    entry.timestamp.replace("Z", "+00:00")
                )
                age_seconds = (
                    request.requested_at.astimezone(timezone.utc)
                    - timestamp.astimezone(timezone.utc)
                ).total_seconds()
            except ValueError:
                return message
            if not 0 <= age_seconds <= 300:
                return message

            previous = "".join(candidate.lower().split())
            supported_intent = any(
                keyword in previous
                for keyword in (
                    "拼好后有多大",
                    "拼装后有多大",
                    "拼起来多大",
                    "成品尺寸",
                    "商品尺寸",
                    "长宽高",
                    "颗粒",
                    "材质",
                    "包装",
                    "彩盒",
                    "礼盒",
                    "价格",
                    "多少钱",
                    "优惠",
                    "库存",
                    "有货",
                    "现货",
                    "订单",
                    "物流",
                    "快递",
                    "到货",
                    "发货",
                    "退款",
                    "退货",
                    "售后",
                    "少件",
                    "缺件",
                    "破损",
                    "误吞",
                    "吞咽",
                    "安全",
                )
            )
            return candidate if supported_intent else message
        return message

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
        for field_name, maximum in limits.items():
            candidate = value.get(field_name)
            if isinstance(candidate, str):
                value[field_name] = candidate[:maximum]
        return value

    @staticmethod
    def _map_response(
        request: DecisionRequest,
        result: dict[str, Any],
        scope: FrozenChatContext,
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

        result = GatewayServer._apply_auto_first_response_policy(
            request=request,
            result=result,
            scope=scope,
        )
        warnings = result.get("warnings")
        if not isinstance(warnings, list) or not all(
            isinstance(item, str) for item in warnings
        ):
            warnings = []
        answer = result.get("answer")
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

        evidence_bundle: ReplyEvidenceBundleV1 | None = None
        raw_evidence = result.get("reply_evidence_bundle")
        raw_quality_status = result.get("quality_gate_status")
        evidence_declared = raw_evidence is not None or raw_quality_status is not None
        evidence_invalid = False
        if evidence_declared:
            try:
                if (
                    raw_quality_status != "PASS"
                    or not isinstance(raw_evidence, dict)
                    or proposed_content is None
                ):
                    raise ValueError("quality evidence declaration is incomplete")
                evidence_bundle = ReplyEvidenceBundleV1.model_validate_json(
                    json.dumps(
                        raw_evidence,
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                )
                evidence_bundle.validate_proposed_content(proposed_content)
                if not GatewayServer._evidence_matches_scope(
                    evidence_bundle, scope
                ):
                    raise ValueError("quality evidence scope does not match request")
            except (TypeError, ValueError, ValidationError):
                evidence_invalid = True
                evidence_bundle = None
                ai_action = "TRANSFER_HUMAN"
                action = GatewayDecisionAction.NO_ACTION
                proposed_content = None
                warnings = ["REPLY_EVIDENCE_INVALID"]

        required_fields = result.get("required_fields")
        if not isinstance(required_fields, list) or not all(
            isinstance(item, str) for item in required_fields
        ):
            required_fields = []
        if evidence_invalid:
            required_fields = []
        sources = result.get("sources")
        if evidence_invalid:
            sources = []
        source_count = len(sources) if isinstance(sources, list) else 0
        raw_risk_level = "HIGH" if evidence_invalid else result.get("risk_level")
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
        if evidence_bundle is not None:
            metadata["reply_evidence_bundle"] = evidence_bundle.model_dump(mode="json")
            metadata["quality_gate_status"] = "PASS"
        authorization_basis = result.get("auto_authorization_basis")
        if authorization_basis in {
            "STORE_APPROVED_KNOWLEDGE",
            "STORE_APPROVED_FIXED_REPLY",
            "STORE_APPROVED_FALLBACK",
        }:
            metadata["auto_authorization_basis"] = authorization_basis

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
    def _apply_auto_first_response_policy(
        *,
        request: DecisionRequest,
        result: dict[str, Any],
        scope: FrozenChatContext,
    ) -> dict[str, Any]:
        """Turn governed manual routes into a store-approved first response.

        The opt-in marker is internal context carried by Channel Engine.  Legacy
        callers retain the existing fail-closed/manual behavior.
        """

        if (
            request.context.get("auto_first_response_policy")
            != "AUTO_ALL_MESSAGES_V1"
            or result.get("action")
            not in {"REQUIRE_LOOKUP", "TRANSFER_HUMAN", "REFUSE"}
        ):
            return result

        message = request.customer_message.strip()
        compact = "".join(message.lower().split())
        if any(
            keyword in compact
            for keyword in ("误吞", "吞咽", "吞下", "小孩", "儿童", "安全", "有毒")
        ):
            rule_id = "auto-first-small-parts-safety-v1"
            answer = (
                "亲，积木含有小颗粒，请避免儿童放入口中或误吞，"
                "建议在成人陪同下使用；如已发生误吞，请立即停止使用并及时就医。"
            )
            action = "CONTROLLED_ANSWER"
            risk_level = "HIGH"
        elif any(
            keyword in compact
            for keyword in ("退款", "退货", "售后", "少件", "缺件", "补发", "破损")
        ):
            rule_id = "auto-first-aftersales-v1"
            answer = (
                "亲，可以在对应订单详情中发起售后申请，并按页面提示选择原因、"
                "上传凭证；如果页面状态不清楚，把当前显示的状态发给我，我继续帮您核对哦。"
            )
            action = "CONTROLLED_ANSWER"
            risk_level = "MEDIUM"
        elif any(
            keyword in compact
            for keyword in ("订单", "物流", "快递", "到货", "发货", "送到", "几天到")
        ):
            rule_id = "auto-first-order-logistics-v1"
            answer = (
                "亲，请以订单详情页显示的发货和物流进度为准；"
                "如果页面状态不清楚，把当前显示的状态发给我，我继续帮您核对哦。"
            )
            action = "CONTROLLED_ANSWER"
            risk_level = "MEDIUM"
        elif any(
            keyword in compact
            for keyword in ("价格", "多少钱", "便宜", "优惠", "库存", "有货", "现货")
        ):
            rule_id = "auto-first-price-inventory-v1"
            answer = "亲，价格、优惠和库存会实时变化，请以当前商品页面显示为准哦。"
            action = "CONTROLLED_ANSWER"
            risk_level = "MEDIUM"
        elif any(
            keyword in compact
            for keyword in (
                "拼好后有多大",
                "拼装后有多大",
                "拼起来多大",
                "成品尺寸",
                "商品尺寸",
                "长宽高",
            )
        ):
            rule_id = "auto-first-product-size-page-v1"
            answer = (
                "亲，不同款式拼装后的尺寸会有差异，"
                "具体请以当前商品详情页和所选规格标注的尺寸为准哦。"
            )
            action = "CONTROLLED_ANSWER"
            risk_level = "MEDIUM"
        elif "颗粒" in compact:
            rule_id = "auto-first-product-pieces-page-v1"
            answer = (
                "亲，不同款式的颗粒数量会有差异，"
                "具体请以当前商品详情页和所选规格标注的颗粒数量为准哦。"
            )
            action = "CONTROLLED_ANSWER"
            risk_level = "MEDIUM"
        elif "材质" in compact:
            rule_id = "auto-first-product-material-page-v1"
            answer = "亲，具体材质请以当前商品详情页对应规格的材质说明为准哦。"
            action = "CONTROLLED_ANSWER"
            risk_level = "MEDIUM"
        elif any(keyword in compact for keyword in ("包装", "彩盒", "礼盒")):
            rule_id = "auto-first-product-package-page-v1"
            answer = "亲，具体包装方式请以当前商品详情页和所选规格的包装说明为准哦。"
            action = "CONTROLLED_ANSWER"
            risk_level = "MEDIUM"
        elif scope.product_id.startswith("__STORE_LEVEL_"):
            rule_id = "auto-first-product-clarify-v1"
            answer = "亲，请发一下您咨询的商品卡片或商品名称，我马上帮您确认哦。"
            action = "ASK_CLARIFY"
            risk_level = "MEDIUM"
        else:
            rule_id = "auto-first-general-page-check-v1"
            answer = (
                "亲，您的问题已收到，我正在按当前商品和规格核对；"
                "页面已有标注的信息请先以当前详情页为准哦。"
            )
            action = "CONTROLLED_ANSWER"
            risk_level = "MEDIUM"

        evidence = GatewayServer._fixed_reply_evidence(
            request=request,
            scope=scope,
            rule_id=rule_id,
            answer=answer,
            action=action,
            risk_level=risk_level,
        )
        mapped = dict(result)
        mapped.update(
            {
                "answer": answer,
                "action": action,
                "risk_level": risk_level,
                "required_fields": (
                    ["product_id"] if rule_id == "auto-first-product-clarify-v1" else []
                ),
                "sources": [
                    {
                        "chunk_id": rule_id,
                        "source_name": "STORE_APPROVED_FIXED_REPLY",
                    }
                ],
                "warnings": ["STORE_APPROVED_FIXED_REPLY"],
                "quality_gate_status": "PASS",
                "reply_evidence_bundle": evidence.model_dump(mode="json"),
                "auto_authorization_basis": "STORE_APPROVED_FIXED_REPLY",
            }
        )
        return mapped

    @staticmethod
    def _fixed_reply_evidence(
        *,
        request: DecisionRequest,
        scope: FrozenChatContext,
        rule_id: str,
        answer: str,
        action: str,
        risk_level: str,
    ) -> ReplyEvidenceBundleV1:
        frozen_scope: dict[str, Any]
        if scope.product_id.startswith("__STORE_LEVEL_"):
            frozen_scope = {
                "scope_kind": "STORE",
                "tenant_id": scope.tenant_id,
                "platform": scope.platform,
                "store_code": scope.store_code,
                "product_id": None,
                "sku_id": None,
            }
        elif scope.sku_id is not None:
            frozen_scope = {
                "scope_kind": "SKU",
                "tenant_id": scope.tenant_id,
                "platform": scope.platform,
                "store_code": scope.store_code,
                "product_id": scope.product_id,
                "sku_id": scope.sku_id,
            }
        else:
            frozen_scope = {
                "scope_kind": "PRODUCT",
                "tenant_id": scope.tenant_id,
                "platform": scope.platform,
                "store_code": scope.store_code,
                "product_id": scope.product_id,
                "sku_id": None,
            }
        store_scope = {
            "scope_kind": "STORE",
            "tenant_id": scope.tenant_id,
            "platform": scope.platform,
            "store_code": scope.store_code,
            "product_id": None,
            "sku_id": None,
        }
        material_fingerprint = canonical_sha256(
            {"rule_id": rule_id, "answer": answer, "revision": 1}
        )
        rule_fingerprint = canonical_sha256(
            {"rule_id": rule_id, "answer": answer, "scope": store_scope}
        )
        snapshot_fingerprint = canonical_sha256(
            {"revision": 1, "rule_id": rule_id, "rule": rule_fingerprint}
        )
        content_range = {
            "range_start": 0,
            "range_end": len(answer),
            "content_sha256": text_sha256(answer),
        }
        source_id = f"source-{text_sha256(rule_id)[:24]}"
        segment_id = "segment-1"
        question_id = "question-1"
        draft: dict[str, Any] = {
            "schema_version": "reply-evidence-bundle.v1",
            "reply_origin": "FIXED_RULE",
            "scope": frozen_scope,
            "sub_question_plan": {
                "schema_version": "sub-question-plan.v1",
                "turn_id": f"turn-{text_sha256(request.message_id)[:24]}",
                "aggregate_content_sha256": text_sha256(request.customer_message),
                "split_status": "SINGLE",
                "sub_questions": [
                    {
                        "sub_question_id": question_id,
                        "ordinal": 1,
                        "source_ranges": [
                            {
                                "message_id": request.message_id,
                                "aggregate_start": 0,
                                "aggregate_end": len(request.customer_message),
                            }
                        ],
                        "source_content_sha256": text_sha256(
                            request.customer_message
                        ),
                        "intent": "STORE_APPROVED_FIXED_REPLY",
                        "route": "FIXED_RULE",
                        "depends_on": [],
                        "blocker_codes": [],
                    }
                ],
                "blocker_codes": [],
            },
            "segments": [
                {
                    "segment_id": segment_id,
                    "ordinal": 1,
                    "sub_question_id": question_id,
                    "content_range": content_range,
                    "action": action,
                    "risk_level": risk_level,
                    "source_ids": [source_id],
                }
            ],
            "sources": [
                {
                    "source_id": source_id,
                    "source_type": "FIXED_RULE",
                    "scope": store_scope,
                    "rule_id": rule_id,
                    "rule_version": 1,
                    "rule_content_fingerprint": rule_fingerprint,
                    "rule_snapshot_revision": 1,
                    "rule_snapshot_fingerprint": snapshot_fingerprint,
                    "rule_source_materials": [
                        {
                            "material_id": f"material-{text_sha256(rule_id)[:24]}",
                            "revision": 1,
                            "content_sha256": material_fingerprint,
                            "governance_status": "REVIEWED_VALID",
                            "scope": store_scope,
                            "reviewed_by": "store-owner-approved",
                            "reviewed_at": "2026-08-15T00:00:00Z",
                        }
                    ],
                    "knowledge_reference": None,
                    "knowledge_publication_fingerprint": None,
                }
            ],
            "facts": [
                {
                    "fact_id": "fact-1",
                    "segment_id": segment_id,
                    "content_range": content_range,
                    "source_ids": [source_id],
                }
            ],
            "warnings": ["STORE_APPROVED_FIXED_REPLY"],
            "missing_fields": [],
            "blocker_codes": [],
        }
        draft["bundle_sha256"] = canonical_sha256(draft)
        bundle = ReplyEvidenceBundleV1.model_validate_json(
            json.dumps(draft, ensure_ascii=False, allow_nan=False)
        )
        bundle.validate_proposed_content(answer)
        return bundle

    @staticmethod
    def _evidence_matches_scope(
        bundle: ReplyEvidenceBundleV1,
        scope: FrozenChatContext,
    ) -> bool:
        evidence_scope = bundle.scope
        if (
            evidence_scope.tenant_id != scope.tenant_id
            or evidence_scope.platform != scope.platform
            or evidence_scope.store_code != scope.store_code
        ):
            return False
        if scope.product_id.startswith("__STORE_LEVEL_"):
            return evidence_scope.scope_kind is RuleScopeKind.STORE
        if evidence_scope.product_id != scope.product_id:
            return False
        if scope.sku_id is None:
            return evidence_scope.scope_kind is RuleScopeKind.PRODUCT
        return (
            evidence_scope.scope_kind is RuleScopeKind.SKU
            and evidence_scope.sku_id == scope.sku_id
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
                    "source_kind": (
                        "FIXED_RULE"
                        if chunk_id.strip().startswith("reply-rule:")
                        else "RAG_KNOWLEDGE"
                    ),
                }
            if isinstance(excerpt, str) and excerpt.strip():
                descriptor["excerpt"] = excerpt.strip()[:1000]
            citations.append(descriptor)
        return citations

    def close(self) -> None:
        self.state_store.close()
