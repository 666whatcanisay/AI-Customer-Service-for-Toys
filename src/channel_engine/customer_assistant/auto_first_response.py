from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping

from pydantic import AwareDatetime

from channel_engine.gateway import (
    CONTRACT_VERSION,
    AICSGateway,
    AICSGatewayRequestFailed,
    AICSGatewayTimeout,
    DecisionRequest,
    DecisionResponse,
    GatewayContractViolation,
    GatewayRiskLevel,
    GatewayUnavailable,
)
from channel_engine.gateway.protocol import IdempotencyConflict
from channel_engine.models import DecisionAction

AUTO_ALL_MESSAGES_POLICY = "AUTO_ALL_MESSAGES_V1"
AUTO_FIRST_RESPONSE_REGISTRY_VERSION = "store-approved-first-response.v1"


class StoreApprovedAutoFirstResponseGateway:
    """Turn an unusable AI result into one governed, customer-visible first reply.

    The wrapper runs before the core Decision is persisted, so fallbacks remain
    ordinary Decisions and must pass the existing per-message Grant, Sender and
    Receipt chain.  It never writes to PDD and never creates a second send path.
    """

    version = AUTO_FIRST_RESPONSE_REGISTRY_VERSION

    def __init__(
        self,
        delegate: AICSGateway,
        *,
        clock: Callable[[], AwareDatetime],
    ) -> None:
        self._delegate = delegate
        self._clock = clock

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        try:
            response = self._delegate.decide(request)
        except IdempotencyConflict:
            # A reused message identity with different content is a delivery
            # conflict.  Falling back here could create a second reply.
            raise
        except (
            AICSGatewayRequestFailed,
            AICSGatewayTimeout,
            GatewayContractViolation,
            GatewayUnavailable,
            OSError,
            TimeoutError,
        ):
            return self._fallback(request, failure_kind="AI_CS_UNAVAILABLE")
        if self._eligible(response):
            metadata = dict(response.metadata)
            metadata.setdefault(
                "auto_authorization_basis", "STORE_APPROVED_KNOWLEDGE"
            )
            metadata["auto_policy_mode"] = AUTO_ALL_MESSAGES_POLICY
            return response.model_copy(update={"metadata": metadata})
        return self._fallback(request, failure_kind="AI_CS_RESULT_NOT_AUTO_ELIGIBLE")

    @staticmethod
    def _eligible(response: DecisionResponse) -> bool:
        if response.action is not DecisionAction.SUGGEST_REPLY:
            return False
        metadata = response.metadata
        quality = str(metadata.get("quality_gate_status") or "").upper()
        ai_action = str(metadata.get("ai_cs_action") or "").upper()
        raw_evidence = metadata.get("reply_evidence_bundle")
        evidence_hash = (
            raw_evidence.get("bundle_sha256")
            if isinstance(raw_evidence, Mapping)
            else None
        )
        return (
            quality == "PASS"
            and ai_action in {"DIRECT_ANSWER", "CONTROLLED_ANSWER", "ASK_CLARIFY"}
            and isinstance(evidence_hash, str)
            and len(evidence_hash) == 64
            and all(character in "0123456789abcdef" for character in evidence_hash.lower())
        )

    def _fallback(
        self,
        request: DecisionRequest,
        *,
        failure_kind: str,
    ) -> DecisionResponse:
        template_id, content, action, risk = self._select_template(request)
        evidence_hash = self._evidence_hash(template_id, content)
        decision_hash = hashlib.sha256(
            f"{request.idempotency_key}:{template_id}:{evidence_hash}".encode()
        ).hexdigest()
        return DecisionResponse(
            contract_version=CONTRACT_VERSION,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            correlation_id=request.correlation_id,
            decision_id=f"decision-afr-{decision_hash}",
            action=DecisionAction.SUGGEST_REPLY,
            proposed_content=content,
            requires_approval=True,
            risk_level=risk,
            gateway_version=self.version,
            metadata={
                "ai_cs_action": action,
                "quality_gate_status": "PASS",
                "warnings": [failure_kind],
                "required_fields": (["product"] if template_id == "CLARIFY_PRODUCT" else []),
                "auto_policy_mode": AUTO_ALL_MESSAGES_POLICY,
                "auto_authorization_basis": (
                    "STORE_APPROVED_FALLBACK"
                    if template_id in {"GENERIC_CLARIFY", "AI_UNAVAILABLE"}
                    else "STORE_APPROVED_FIXED_REPLY"
                ),
                "fixed_reply_rule_id": template_id,
                "fixed_reply_registry_version": AUTO_FIRST_RESPONSE_REGISTRY_VERSION,
                "reply_evidence_bundle": {"bundle_sha256": evidence_hash},
                "citations": [
                    {
                        "reference": f"fixed-reply://{AUTO_FIRST_RESPONSE_REGISTRY_VERSION}/{template_id}",
                        "title": "店铺批准的自动首响话术",
                        "source_kind": "STORE_APPROVED_FIXED_REPLY",
                    }
                ],
            },
            decided_at=self._clock(),
        )

    @staticmethod
    def _select_template(
        request: DecisionRequest,
    ) -> tuple[str, str, str, GatewayRiskLevel]:
        question = request.customer_message.casefold()
        compact = "".join(question.split())
        product = request.context.get("product")
        product_reference = (
            product.get("product_reference")
            if isinstance(product, Mapping)
            else None
        )
        product_contact_only = (
            (
                compact.startswith(("http://", "https://"))
                and any(
                    domain in compact
                    for domain in ("yangkeduo.com", "pinduoduo.com")
                )
            )
            or (
                any(
                    marker in compact
                    for marker in ("商品id:", "商品id：", "查看商品规格")
                )
                and not any(
                    marker in compact
                    for marker in (
                        "多少", "多大", "怎么", "什么", "哪", "吗", "呢",
                        "？", "退款", "售后", "订单", "物流",
                    )
                )
            )
        )
        if product_contact_only:
            return (
                "PRODUCT_CONTACT_GREETING",
                "您好，请问需要什么帮助吗？",
                "DIRECT_ANSWER",
                GatewayRiskLevel.LOW,
            )
        if any(marker in question for marker in ("误吞", "吞咽", "吞", "儿童", "小孩", "安全", "有毒")):
            return (
                "SAFETY_SMALL_PARTS",
                "亲，这类积木含小颗粒，建议在成人陪同下使用并远离低龄儿童；如发生误吞或身体不适，请立即停止使用并尽快联系专业医疗机构。",
                "CONTROLLED_ANSWER",
                GatewayRiskLevel.HIGH,
            )
        if any(marker in question for marker in ("退款", "退货", "售后", "破损", "少件", "缺件", "漏发")):
            return (
                "AFTERSALES_STEPS",
                "亲，请在对应订单详情中进入“申请售后”，按页面提示提交退款、退货或补件需求；具体处理结果以平台审核和订单页面为准哦。",
                "CONTROLLED_ANSWER",
                GatewayRiskLevel.MEDIUM,
            )
        if any(marker in question for marker in ("订单", "物流", "快递", "发货", "到货", "到哪", "什么时候到")):
            return (
                "ORDER_LOGISTICS_STATUS",
                "亲，请打开对应订单详情查看当前物流和预计时间；订单状态可能实时变化，以订单页面最新显示为准哦。",
                "CONTROLLED_ANSWER",
                GatewayRiskLevel.MEDIUM,
            )
        if any(marker in question for marker in ("价格", "多少钱", "优惠", "便宜", "库存", "有货", "现货")):
            return (
                "PRICE_STOCK_LIVE_PAGE",
                "亲，价格、优惠和库存会实时变化，请以当前商品页面显示为准哦。",
                "CONTROLLED_ANSWER",
                GatewayRiskLevel.MEDIUM,
            )
        if not isinstance(product_reference, str) or not product_reference.strip():
            return (
                "CLARIFY_PRODUCT",
                "亲，麻烦发送或确认一下您咨询的商品卡，我会按对应商品为您准确解答哦。",
                "ASK_CLARIFY",
                GatewayRiskLevel.MEDIUM,
            )
        return (
            "GENERIC_CLARIFY",
            "亲，我已收到您的问题。为了避免答错，麻烦再具体说明想了解的是尺寸、颗粒数、包装、使用还是售后，我会按当前商品为您解答哦。",
            "ASK_CLARIFY",
            GatewayRiskLevel.MEDIUM,
        )

    @staticmethod
    def _evidence_hash(template_id: str, content: str) -> str:
        canonical = json.dumps(
            {
                "registry_version": AUTO_FIRST_RESPONSE_REGISTRY_VERSION,
                "template_id": template_id,
                "content": content,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


__all__ = [
    "AUTO_ALL_MESSAGES_POLICY",
    "AUTO_FIRST_RESPONSE_REGISTRY_VERSION",
    "StoreApprovedAutoFirstResponseGateway",
]
