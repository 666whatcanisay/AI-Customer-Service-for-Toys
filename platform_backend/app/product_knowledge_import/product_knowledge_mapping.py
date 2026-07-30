"""Frozen field mapping for 商品知识采集模板 V1.

The mapping is deliberately code-owned.  The workbook's 字段说明 sheet is
validated as evidence, but never used to infer or execute arbitrary mappings.
"""

from dataclasses import dataclass


TEMPLATE_TYPE = "PRODUCT_KNOWLEDGE"
TEMPLATE_VERSION = "1.0"
PARSER_VERSION = "product-knowledge-parser.v1.1"
EXPECTED_SHEETS = ("填写说明", "数据填写", "示例数据", "字段说明")
EXPECTED_SHEET_TITLES = {
    "填写说明": "商品知识采集模板 V1",
    "数据填写": "商品知识采集模板 V1｜数据填写",
    "示例数据": "商品知识采集模板 V1｜示例数据",
    "字段说明": "商品知识采集模板 V1｜字段说明",
}
DATA_SHEET = "数据填写"
EXAMPLE_SHEET = "示例数据"
FIELD_DESCRIPTION_SHEET = "字段说明"
HEADER_SCAN_MAX_ROWS = 100

EXPECTED_HEADERS = (
    "店铺名称",
    "商品名称",
    "商品简介",
    "核心卖点",
    "适用年龄",
    "材质信息",
    "安全提醒",
    "包装内容",
    "使用说明",
    "玩法介绍",
    "客户常问问题",
    "推荐回答方向",
    "资料来源",
    "来源日期",
    "是否人工确认",
    "备注",
)

REQUIRED_HEADERS = (
    "店铺名称",
    "商品名称",
    "商品简介",
    "核心卖点",
    "资料来源",
)

CONFIRMATION_VALUES = {"已确认", "待确认"}


@dataclass(frozen=True, slots=True)
class ProductKnowledgeFieldMapping:
    excel_header: str
    field_key: str
    field_label: str
    storage: str
    display_order: int


PRODUCT_FIELD_MAPPINGS = (
    ProductKnowledgeFieldMapping("商品名称", "product.name", "商品名称", "name", 10),
    ProductKnowledgeFieldMapping(
        "商品简介", "product_knowledge.product_summary", "商品简介", "raw", 20
    ),
    ProductKnowledgeFieldMapping(
        "核心卖点", "product_knowledge.main_selling_points", "核心卖点", "raw", 30
    ),
    ProductKnowledgeFieldMapping(
        "适用年龄", "product_knowledge.recommended_age", "适用年龄", "age", 40
    ),
    ProductKnowledgeFieldMapping(
        "材质信息", "product_knowledge.material", "材质信息", "raw", 50
    ),
    ProductKnowledgeFieldMapping(
        "安全提醒", "product_knowledge.safety_summary", "安全提醒", "safety", 60
    ),
    ProductKnowledgeFieldMapping(
        "包装内容", "product_knowledge.package_contents", "包装内容", "raw", 70
    ),
    ProductKnowledgeFieldMapping(
        "使用说明", "product_knowledge.usage_instructions", "使用说明", "raw", 80
    ),
    ProductKnowledgeFieldMapping(
        "玩法介绍", "product_knowledge.play_method", "玩法介绍", "raw", 90
    ),
    ProductKnowledgeFieldMapping(
        "客户常问问题",
        "product_knowledge.common_customer_questions",
        "客户常问问题",
        "raw",
        100,
    ),
    ProductKnowledgeFieldMapping(
        "推荐回答方向",
        "product_knowledge.recommended_answer_direction",
        "推荐回答方向",
        "raw",
        110,
    ),
)

MAPPING_BY_HEADER = {item.excel_header: item for item in PRODUCT_FIELD_MAPPINGS}
MAPPING_BY_KEY = {item.field_key: item for item in PRODUCT_FIELD_MAPPINGS}
