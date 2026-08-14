from __future__ import annotations

import hashlib
import json


BASELINE_VERSION = "pdd-common-questions.v1"


def _q(
    question_id: str,
    category: str,
    question: str,
    aliases: list[str],
    risk: str,
    action: str,
    facts: list[str] | None = None,
    *,
    realtime: bool = False,
    prohibited: list[str] | None = None,
) -> dict[str, object]:
    return {
        "question_id": question_id,
        "category": category,
        "canonical_question": question,
        "aliases": aliases,
        "policy_risk_floor": risk,
        "expected_action": action,
        "required_fact_keys": facts or [],
        "requires_realtime_lookup": realtime,
        "prohibited_claims": prohibited or [],
        "mandatory": True,
    }


# Synthetic, de-identified policy questions derived from the supplied category
# counts. No customer utterance, product identifier, source answer or order data
# is stored in this repository.
BASELINE_QUESTIONS: tuple[dict[str, object], ...] = (
    _q("PDD-GREETING", "GREETING", "你好", ["您好", "在吗"], "LOW", "DIRECT_ANSWER"),
    _q("PDD-AFFIRMATION", "AFFIRMATION", "好的", ["行", "可以"], "LOW", "DIRECT_ANSWER"),
    _q("PDD-THANKS", "THANKS", "谢谢", ["感谢", "麻烦了"], "LOW", "DIRECT_ANSWER"),
    _q("PDD-PRODUCT-IMAGES", "PRODUCT_MEDIA", "可以看看商品图片吗", ["有实拍图吗"], "LOW", "DIRECT_ANSWER", ["image_status"]),
    _q("PDD-PRODUCT-VIDEO", "PRODUCT_MEDIA", "有商品视频吗", ["能发视频吗"], "LOW", "DIRECT_ANSWER", ["video_status"]),
    _q("PDD-PARTICLE-COUNT", "PRODUCT_FACT", "这款有多少颗粒", ["颗粒数多少"], "LOW", "DIRECT_ANSWER", ["particle_count"]),
    _q("PDD-FINISHED-SIZE", "PRODUCT_FACT", "拼好后多大", ["成品尺寸多少"], "LOW", "DIRECT_ANSWER", ["finished_size"]),
    _q("PDD-MATERIAL", "PRODUCT_FACT", "是什么材质", ["商品材质"], "LOW", "DIRECT_ANSWER", ["material"]),
    _q("PDD-WEIGHT", "PRODUCT_FACT", "商品多重", ["重量多少"], "LOW", "DIRECT_ANSWER", ["weight"]),
    _q("PDD-INSTALLATION", "PRODUCT_USAGE", "怎么安装", ["怎么拼装"], "MEDIUM", "CONTROLLED_ANSWER", ["installation"]),
    _q("PDD-PACKAGING", "PRODUCT_FACT", "是什么包装", ["包装怎么样"], "LOW", "DIRECT_ANSWER", ["package_contents"]),
    _q("PDD-VARIANT-DIFFERENCE", "SKU_FACT", "几个款式有什么区别", ["版本区别"], "LOW", "DIRECT_ANSWER", ["variant_difference"]),
    _q("PDD-IMAGE-MATCH", "PRODUCT_FACT", "收到的和图片一样吗", ["实物与图片一致吗"], "MEDIUM", "CONTROLLED_ANSWER", ["image_match_policy"], prohibited=["完全一致", "百分百一样"]),
    _q("PDD-INVENTORY", "REALTIME_ORDER", "现在有货吗", ["库存还有吗"], "HIGH", "REQUIRE_LOOKUP", realtime=True),
    _q("PDD-PRICE", "REALTIME_ORDER", "现在多少钱", ["还能便宜吗"], "HIGH", "REQUIRE_LOOKUP", realtime=True, prohibited=["保证最低价"]),
    _q("PDD-GIFT", "PROMOTION", "有赠品吗", ["送东西吗"], "MEDIUM", "REQUIRE_LOOKUP", realtime=True),
    _q("PDD-RECOMMENDATION", "SHOPPING_GUIDE", "推荐哪一款", ["选哪个款式"], "MEDIUM", "ASK_CLARIFY", ["variant_difference"]),
    _q("PDD-COURIER", "FULFILLMENT", "发什么快递", ["可以指定快递吗"], "MEDIUM", "CONTROLLED_ANSWER", ["courier_policy"]),
    _q("PDD-SHIP-ORIGIN", "FULFILLMENT", "从哪里发货", ["发货地在哪"], "LOW", "DIRECT_ANSWER", ["ship_origin"]),
    _q("PDD-DISPATCH-TIME", "REALTIME_ORDER", "什么时候发货", ["今天能发吗"], "HIGH", "REQUIRE_LOOKUP", realtime=True, prohibited=["保证今天发"]),
    _q("PDD-DELIVERY-ETA", "REALTIME_ORDER", "多久能到", ["几天送到"], "HIGH", "REQUIRE_LOOKUP", realtime=True, prohibited=["24小时必到", "48小时必到", "72小时必到"]),
    _q("PDD-LOGISTICS-STALLED", "REALTIME_ORDER", "物流怎么不动了", ["物流没有更新"], "HIGH", "REQUIRE_LOOKUP", realtime=True),
    _q("PDD-URGE-COURIER", "REALTIME_ORDER", "帮我催一下快递", ["催物流"], "HIGH", "TRANSFER_HUMAN", realtime=True),
    _q("PDD-CHANGE-ADDRESS", "REALTIME_ORDER", "可以改地址吗", ["地址填错了"], "HIGH", "TRANSFER_HUMAN", realtime=True),
    _q("PDD-REFUND", "AFTERSALES", "我要退款", ["申请退款"], "HIGH", "TRANSFER_HUMAN", realtime=True),
    _q("PDD-CANCEL-REFUND", "AFTERSALES", "怎么取消退款", ["撤销退款"], "HIGH", "TRANSFER_HUMAN", realtime=True),
    _q("PDD-RETURN", "AFTERSALES", "怎么退货", ["我要退货"], "HIGH", "TRANSFER_HUMAN", realtime=True),
    _q("PDD-MISSING-ITEM", "AFTERSALES", "收到后发现少件", ["缺东西"], "HIGH", "TRANSFER_HUMAN", realtime=True),
    _q("PDD-WRONG-ITEM", "AFTERSALES", "商家发错货了", ["收到的款式不对"], "HIGH", "TRANSFER_HUMAN", realtime=True),
    _q("PDD-QUALITY-ISSUE", "AFTERSALES", "商品有质量问题", ["商品坏了"], "HIGH", "TRANSFER_HUMAN", realtime=True),
    _q("PDD-REPLACEMENT", "AFTERSALES", "可以换货吗", ["怎么换一个"], "HIGH", "TRANSFER_HUMAN", realtime=True),
    _q("PDD-STEALTH-PACKAGING", "FULFILLMENT", "可以隐私发货吗", ["包装能看出商品吗"], "MEDIUM", "CONTROLLED_ANSWER", ["stealth_packaging"]),
    _q("PDD-FREIGHT-INSURANCE", "AFTERSALES", "有运费险吗", ["退货运费谁出"], "HIGH", "REQUIRE_LOOKUP", realtime=True),
    _q("PDD-AUTHENTICITY", "AUTHENTICITY", "是正品吗", ["有品牌授权吗"], "HIGH", "TRANSFER_HUMAN", ["authenticity_evidence"], prohibited=["本店所有产品均为正品", "保证正品"]),
    _q("PDD-CASHBACK", "PROMOTION", "好评返现吗", ["有返现吗"], "HIGH", "TRANSFER_HUMAN", realtime=True),
    _q("PDD-PAYMENT-STATUS", "REALTIME_ORDER", "我已经付款了", ["付款成功了吗"], "HIGH", "REQUIRE_LOOKUP", realtime=True),
)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


BASELINE_FINGERPRINT = hashlib.sha256(
    canonical_json({"version": BASELINE_VERSION, "questions": BASELINE_QUESTIONS}).encode("utf-8")
).hexdigest()
