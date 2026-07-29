"""Recognition coverage for the six Chinese operations templates."""

import json

import pytest

from app.errors import AppError
from app.knowledge_materials.schemas import KnowledgeMaterialType, KnowledgeTemplateType
from app.knowledge_materials.service import recognize_material


SCOPE = {"store_name": "星芽玩具店", "product_name": "城市消防积木", "sku_name": "豪华版"}


CASES = [
    (
        KnowledgeTemplateType.PRODUCT_KNOWLEDGE,
        KnowledgeMaterialType.PRODUCT_SPEC,
        {
            "店铺名称": "星芽玩具店", "商品名称": "城市消防积木", "商品简介": "消防主题拼装玩具",
            "核心卖点": "机械联动", "适用年龄": "8岁以上", "材质信息": "ABS", "安全提醒": "含小零件",
            "包装内容": "积木和说明书", "使用说明": "按步骤拼装", "玩法介绍": "消防救援游戏",
            "客户常问问题": "适合几岁", "推荐回答方向": "按年龄标识回答", "资料来源": "商品说明书",
            "来源日期": "2026-07-20", "是否人工确认": "是", "备注": "",
        },
    ),
    (
        KnowledgeTemplateType.SKU_DIFFERENCE,
        KnowledgeMaterialType.PRODUCT_SPEC,
        {
            "店铺名称": "星芽玩具店", "商品名称": "城市消防积木", "SKU名称": "豪华版",
            "颜色款式": "红色", "规格区别": "增加灯光组件", "包装区别": "独立彩盒", "数量区别": "多2个人仔",
            "尺寸区别": "已确认无差异", "玩法区别": "支持灯光玩法", "SKU常见问题": "与标准版有什么区别",
            "SKU安全提醒": "电池由成人安装", "资料来源": "SKU包装标识", "来源日期": "2026-07-20",
            "确认状态": "已确认", "备注": "",
        },
    ),
    (
        KnowledgeTemplateType.FAQ,
        KnowledgeMaterialType.FAQ_SOURCE,
        {
            "店铺名称": "星芽玩具店", "商品名称": "城市消防积木", "SKU名称": "豪华版",
            "客户常问问题": "适合几岁", "标准回答": "已确认适合8岁以上儿童", "适用场景": "年龄咨询",
            "是否需要人工确认": "否", "风险等级": "中", "资料来源": "商品说明书", "来源日期": "2026-07-20",
            "事实确认状态": "已确认", "备注": "",
        },
    ),
    (
        KnowledgeTemplateType.SAFETY_RULE,
        KnowledgeMaterialType.SAFETY_INSTRUCTION,
        {
            "店铺名称": "星芽玩具店", "商品名称": "城市消防积木", "适用年龄": "8岁以上",
            "安全主题": "小零件误食", "风险等级": "高", "安全提醒": "含小零件，需成人陪同",
            "禁止承诺内容": "不得承诺绝对安全", "需要人工确认情况": "年龄不明",
            "必须转人工情况": "出现误食或伤害", "资料来源": "包装警示标签", "来源日期": "2026-07-20",
            "事实确认状态": "已确认", "备注": "",
        },
    ),
    (
        KnowledgeTemplateType.AI_FEEDBACK,
        KnowledgeMaterialType.OTHER,
        {
            "问题时间": "2026-07-20T10:00:00", "店铺名称": "星芽玩具店", "商品名称": "城市消防积木",
            "SKU名称": "豪华版", "客户问题": "豪华版有什么区别", "AI回答结果": "未说明灯光组件",
            "客服处理结果": "依据说明书人工补充", "反馈分类": "SKU错误", "问题严重程度": "中",
            "建议补充内容": "补充灯光组件差异", "处理状态": "确认缺口", "是否已去除敏感信息": "已去除",
            "备注": "不含客户身份信息",
        },
    ),
    (
        KnowledgeTemplateType.KNOWLEDGE_GAP,
        KnowledgeMaterialType.OTHER,
        {
            "店铺名称": "星芽玩具店", "商品名称": "城市消防积木", "SKU名称": "豪华版",
            "缺失知识主题": "SKU区别", "缺口说明": "未说明灯光组件", "出现次数": "3",
            "影响客服程度": "中", "风险等级": "中", "复用价值": "高", "优先级": "P1",
            "处理状态": "待确认", "建议补充内容": "补充SKU差异", "补充资料来源": "SKU包装标识",
            "责任角色": "知识运营", "验证结果": "待验证", "备注": "",
        },
    ),
]


@pytest.mark.parametrize(("template_type", "material_type", "row"), CASES)
def test_each_chinese_template_recognizes_real_data_rows(
    template_type: KnowledgeTemplateType,
    material_type: KnowledgeMaterialType,
    row: dict[str, str],
) -> None:
    text, summary = recognize_material(
        filename="运营填写.json",
        content=json.dumps(row, ensure_ascii=False).encode("utf-8"),
        material_type=material_type,
        max_bytes=1024 * 1024,
        template_type=template_type,
        expected_scope=SCOPE,
    )

    assert summary.template_type is template_type
    assert summary.record_count == 1
    assert summary.detected_fields
    assert "数据记录" in text


def test_high_risk_safety_template_requires_a_source() -> None:
    row = dict(CASES[3][2])
    row["资料来源"] = ""

    with pytest.raises(AppError) as captured:
        recognize_material(
            filename="安全规则.json",
            content=json.dumps(row, ensure_ascii=False).encode("utf-8"),
            material_type=KnowledgeMaterialType.SAFETY_INSTRUCTION,
            max_bytes=1024 * 1024,
            template_type=KnowledgeTemplateType.SAFETY_RULE,
            expected_scope=SCOPE,
        )

    assert captured.value.code == "KNOWLEDGE_TEMPLATE_VALIDATION_FAILED"
