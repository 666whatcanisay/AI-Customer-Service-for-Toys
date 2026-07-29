"""Safe, deterministic recognition helpers for controlled material intake.

Recognition intentionally does not call an AI model and does not publish any
material.  It extracts a bounded text snapshot so human review can decide
whether the revision may be exported to A for a later, explicit analysis.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from openpyxl import load_workbook

from app.errors import AppError
from app.knowledge_materials.schemas import (
    KnowledgeMaterialType,
    KnowledgeTemplateRecognitionSummary,
    KnowledgeTemplateType,
)


ALLOWED_SUFFIXES = {".txt", ".md", ".csv", ".json", ".xlsx"}
MAX_ANALYSIS_TEXT_CHARS = 24_000
_PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_ID_PATTERN = re.compile(r"(?<!\d)\d{17}[\dXx](?![\dXx])")

_EXPECTED_FIELDS: dict[KnowledgeMaterialType, list[str]] = {
    KnowledgeMaterialType.PRODUCT_SPEC: ["适用年龄", "安全提示", "包装清单"],
    KnowledgeMaterialType.SAFETY_INSTRUCTION: ["安全提示", "适用年龄"],
    KnowledgeMaterialType.ASSEMBLY_GUIDE: ["安装步骤", "安全提示"],
    KnowledgeMaterialType.FAQ_SOURCE: ["问题", "答案"],
    KnowledgeMaterialType.OTHER: [],
}
_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "适用年龄": ("适用年龄", "年龄", "岁"),
    "安全提示": ("安全", "警告", "成人陪同", "不适合"),
    "包装清单": ("包装", "清单", "配件", "包含"),
    "安装步骤": ("安装", "拼装", "步骤", "说明书"),
    "问题": ("问题", "问：", "q:"),
    "答案": ("答案", "答：", "a:"),
}

_FORBIDDEN_TEMPLATE_HEADERS = {
    "product_name", "sku_code", "tenant_id", "product_id", "external_id", "revision", "hash"
}
_TEMPLATE_DEFINITIONS: dict[KnowledgeTemplateType, dict[str, object]] = {
    KnowledgeTemplateType.PRODUCT_KNOWLEDGE: {
        "name": "商品知识采集模板",
        "fields": [
            "店铺名称", "商品名称", "商品简介", "核心卖点", "适用年龄", "材质信息", "安全提醒",
            "包装内容", "使用说明", "玩法介绍", "客户常问问题", "推荐回答方向", "资料来源",
            "来源日期", "是否人工确认", "备注",
        ],
        "required": ["店铺名称", "商品名称", "资料来源", "是否人工确认"],
        "knowledge_fields": [
            "商品简介", "核心卖点", "适用年龄", "材质信息", "安全提醒", "包装内容",
            "使用说明", "玩法介绍", "客户常问问题",
        ],
    },
    KnowledgeTemplateType.SKU_DIFFERENCE: {
        "name": "SKU差异知识采集模板",
        "fields": [
            "店铺名称", "商品名称", "SKU名称", "颜色款式", "规格区别", "包装区别", "数量区别",
            "尺寸区别", "玩法区别", "SKU常见问题", "SKU安全提醒", "资料来源", "来源日期",
            "确认状态", "备注",
        ],
        "required": [
            "店铺名称", "商品名称", "SKU名称", "颜色款式", "规格区别", "包装区别", "数量区别",
            "尺寸区别", "玩法区别", "资料来源", "确认状态",
        ],
        "knowledge_fields": [
            "颜色款式", "规格区别", "包装区别", "数量区别", "尺寸区别", "玩法区别",
            "SKU常见问题", "SKU安全提醒",
        ],
    },
    KnowledgeTemplateType.FAQ: {
        "name": "客服FAQ知识采集模板",
        "fields": [
            "店铺名称", "商品名称", "SKU名称", "客户常问问题", "标准回答", "适用场景",
            "是否需要人工确认", "风险等级", "资料来源", "来源日期", "事实确认状态", "备注",
        ],
        "required": ["店铺名称", "商品名称", "客户常问问题", "标准回答", "风险等级", "资料来源", "事实确认状态"],
        "knowledge_fields": ["客户常问问题", "标准回答", "适用场景"],
    },
    KnowledgeTemplateType.SAFETY_RULE: {
        "name": "商品安全规则采集模板",
        "fields": [
            "店铺名称", "商品名称", "适用年龄", "安全主题", "风险等级", "安全提醒", "禁止承诺内容",
            "需要人工确认情况", "必须转人工情况", "资料来源", "来源日期", "事实确认状态", "备注",
        ],
        "required": [
            "店铺名称", "商品名称", "安全主题", "风险等级", "安全提醒", "禁止承诺内容",
            "必须转人工情况", "资料来源", "事实确认状态",
        ],
        "knowledge_fields": [
            "适用年龄", "安全主题", "安全提醒", "禁止承诺内容", "需要人工确认情况", "必须转人工情况",
        ],
    },
    KnowledgeTemplateType.AI_FEEDBACK: {
        "name": "客服AI问题反馈模板",
        "fields": [
            "问题时间", "店铺名称", "商品名称", "SKU名称", "客户问题", "AI回答结果", "客服处理结果",
            "反馈分类", "问题严重程度", "建议补充内容", "处理状态", "是否已去除敏感信息", "备注",
        ],
        "required": [
            "问题时间", "店铺名称", "商品名称", "客户问题", "AI回答结果", "客服处理结果",
            "反馈分类", "问题严重程度", "处理状态", "是否已去除敏感信息",
        ],
        "knowledge_fields": ["客户问题", "AI回答结果", "客服处理结果", "建议补充内容"],
    },
    KnowledgeTemplateType.KNOWLEDGE_GAP: {
        "name": "AI知识缺口管理模板",
        "fields": [
            "店铺名称", "商品名称", "SKU名称", "缺失知识主题", "缺口说明", "出现次数", "影响客服程度",
            "风险等级", "复用价值", "优先级", "处理状态", "建议补充内容", "补充资料来源",
            "责任角色", "验证结果", "备注",
        ],
        "required": [
            "店铺名称", "商品名称", "缺失知识主题", "缺口说明", "出现次数", "影响客服程度",
            "风险等级", "复用价值", "优先级", "处理状态", "建议补充内容",
        ],
        "knowledge_fields": ["缺失知识主题", "缺口说明", "建议补充内容", "补充资料来源", "验证结果"],
    },
}


def safe_filename(filename: str) -> str:
    return PurePosixPath(filename.replace("\\", "/")).name


def content_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def fingerprint_upload(values: dict[str, str | None], content: bytes) -> str:
    canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical + b'\x00' + content).hexdigest()}"


def recognize_material(
    *,
    filename: str,
    content: bytes,
    material_type: KnowledgeMaterialType,
    max_bytes: int,
    template_type: KnowledgeTemplateType | None = None,
    expected_scope: dict[str, str | None] | None = None,
) -> tuple[str, KnowledgeTemplateRecognitionSummary]:
    safe_name = safe_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    if not safe_name or suffix not in ALLOWED_SUFFIXES:
        raise AppError(
            "KNOWLEDGE_MATERIAL_UNSUPPORTED_FILE",
            "仅支持 .txt、.md、.csv、.json 或 .xlsx 商品资料文件。",
            status_code=422,
        )
    if not content or len(content) > max_bytes:
        raise AppError(
            "KNOWLEDGE_MATERIAL_VALIDATION_FAILED",
            "资料文件为空或超过当前受控上传大小限制。",
            status_code=422,
        )

    try:
        if template_type is not None:
            records = _extract_template_records(suffix, content, template_type)
            warnings, high_risk_source_confirmed = _validate_template_records(
                records, template_type, expected_scope or {}
            )
            definition = _TEMPLATE_DEFINITIONS[template_type]
            fields = list(definition["fields"])
            knowledge_fields = list(definition["knowledge_fields"])
            detected = [
                field for field in fields
                if any(_has_value(record.get(field)) for record in records)
            ]
            missing = [field for field in knowledge_fields if field not in detected]
            text = json.dumps(
                {"模板类型": definition["name"], "数据记录": records},
                ensure_ascii=False,
                indent=2,
            )
        else:
            text = _extract_text(suffix, content)
            warnings = []
            high_risk_source_confirmed = None
            records = []
    except AppError:
        raise
    except (UnicodeDecodeError, ValueError, csv.Error) as exc:
        raise AppError(
            "KNOWLEDGE_MATERIAL_VALIDATION_FAILED",
            "无法识别资料内容；请使用可读取、无密码保护的受支持文件。",
            status_code=422,
        ) from exc
    except Exception as exc:  # openpyxl parse errors are not stable public messages
        raise AppError(
            "KNOWLEDGE_MATERIAL_VALIDATION_FAILED",
            "无法识别资料内容；请检查文件格式后重试。",
            status_code=422,
        ) from exc
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()
    if not text:
        raise AppError(
            "KNOWLEDGE_MATERIAL_VALIDATION_FAILED",
            "资料中没有可识别的文字内容。",
            status_code=422,
        )
    if _PHONE_PATTERN.search(text) or _ID_PATTERN.search(text):
        raise AppError(
            "KNOWLEDGE_MATERIAL_VALIDATION_FAILED",
            "资料疑似包含手机号或证件号。请人工去标识化后再上传。",
            status_code=422,
        )
    bounded = text[:MAX_ANALYSIS_TEXT_CHARS]
    if template_type is None:
        detected = [
            field for field, keywords in _FIELD_KEYWORDS.items()
            if any(keyword.lower() in bounded.lower() for keyword in keywords)
        ]
        expected = _EXPECTED_FIELDS[material_type]
        missing = [field for field in expected if field not in detected]
    return bounded, KnowledgeTemplateRecognitionSummary(
        readable=True,
        file_extension=suffix,
        detected_fields=detected,
        missing_expected_fields=missing,
        privacy_reminder="请确认资料不包含客户会话、手机号、地址、订单或支付信息；系统不会自动脱敏。",
        template_type=template_type,
        template_name=str(_TEMPLATE_DEFINITIONS[template_type]["name"]) if template_type else None,
        record_count=len(records),
        warnings=warnings,
        high_risk_source_confirmed=high_risk_source_confirmed,
    )


def _has_value(value: object) -> bool:
    return value is not None and bool(str(value).strip())


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _extract_template_records(
    suffix: str, content: bytes, template_type: KnowledgeTemplateType
) -> list[dict[str, str]]:
    definition = _TEMPLATE_DEFINITIONS[template_type]
    fields = list(definition["fields"])
    if suffix == ".json":
        value: Any = json.loads(content.decode("utf-8-sig"))
        if isinstance(value, dict) and isinstance(value.get("数据记录"), list):
            value = value["数据记录"]
        elif isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("template JSON must contain an object or list")
        records = [
            {field: _cell_text(row.get(field)) for field in fields}
            for row in value if isinstance(row, dict)
        ]
    elif suffix == ".xlsx":
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        try:
            if "数据填写" not in workbook.sheetnames:
                raise ValueError("missing 数据填写 worksheet")
            worksheet = workbook["数据填写"]
            rows = list(worksheet.iter_rows(values_only=True))
            header_index = -1
            header_values: list[str] = []
            for index, row in enumerate(rows[:30]):
                values = [_cell_text(value) for value in row]
                if set(fields).issubset(set(values)):
                    header_index = index
                    header_values = values
                    break
            if header_index < 0:
                raise ValueError("template headers do not match")
            lowered = {value.lower() for value in header_values if value}
            if lowered & _FORBIDDEN_TEMPLATE_HEADERS:
                raise ValueError("technical headers are not allowed")
            column_by_field = {field: header_values.index(field) for field in fields}
            records = []
            for row in rows[header_index + 1:]:
                record = {
                    field: _cell_text(row[column]) if column < len(row) else ""
                    for field, column in column_by_field.items()
                }
                if any(_has_value(value) for value in record.values()):
                    records.append(record)
        finally:
            workbook.close()
    else:
        raise ValueError("structured templates only accept xlsx or json")
    if not records:
        raise ValueError("template has no data rows")
    return records


def _validate_template_records(
    records: list[dict[str, str]],
    template_type: KnowledgeTemplateType,
    expected_scope: dict[str, str | None],
) -> tuple[list[str], bool | None]:
    definition = _TEMPLATE_DEFINITIONS[template_type]
    required = list(definition["required"])
    warnings: list[str] = []
    for index, record in enumerate(records, start=1):
        missing = [field for field in required if not _has_value(record.get(field))]
        if missing:
            raise AppError(
                "KNOWLEDGE_TEMPLATE_VALIDATION_FAILED",
                f"数据填写第 {index} 条缺少必填项：{'、'.join(missing)}。",
                status_code=422,
            )
        for field, scope_key in (("店铺名称", "store_name"), ("商品名称", "product_name")):
            expected = expected_scope.get(scope_key)
            if expected and record.get(field) != expected:
                raise AppError(
                    "KNOWLEDGE_TEMPLATE_SCOPE_MISMATCH",
                    f"数据填写第 {index} 条的{field}与页面所选范围不一致。",
                    status_code=422,
                )
        selected_sku = expected_scope.get("sku_name")
        row_sku = record.get("SKU名称", "")
        if "SKU名称" in definition["fields"] and selected_sku and row_sku not in {
            selected_sku, "全部SKU", "全部 SKU"
        }:
            raise AppError(
                "KNOWLEDGE_TEMPLATE_SCOPE_MISMATCH",
                f"数据填写第 {index} 条的SKU名称与页面所选范围不一致。",
                status_code=422,
            )
    if template_type is KnowledgeTemplateType.PRODUCT_KNOWLEDGE:
        for index, record in enumerate(records, start=1):
            if not any(_has_value(record.get(field)) for field in definition["knowledge_fields"]):
                raise AppError(
                    "KNOWLEDGE_TEMPLATE_VALIDATION_FAILED",
                    f"数据填写第 {index} 条至少需要填写一项商品知识。",
                    status_code=422,
                )
            if record.get("是否人工确认") not in {"是", "已确认"}:
                warnings.append(f"第 {index} 条尚未完成人工确认。")
    if template_type is KnowledgeTemplateType.SKU_DIFFERENCE:
        difference_fields = ["颜色款式", "规格区别", "包装区别", "数量区别", "尺寸区别", "玩法区别"]
        for index, record in enumerate(records, start=1):
            for field in difference_fields:
                if not _has_value(record.get(field)):
                    raise AppError(
                        "KNOWLEDGE_TEMPLATE_VALIDATION_FAILED",
                        f"数据填写第 {index} 条的{field}必须填写实际差异或“已确认无差异”。",
                        status_code=422,
                    )
            if record.get("确认状态") not in {"已确认", "确认"}:
                warnings.append(f"第 {index} 条SKU差异尚未确认。")
    if template_type is KnowledgeTemplateType.AI_FEEDBACK:
        for index, record in enumerate(records, start=1):
            if record.get("是否已去除敏感信息") not in {"已去除", "是"}:
                raise AppError(
                    "KNOWLEDGE_TEMPLATE_PRIVACY_REVIEW_REQUIRED",
                    f"数据填写第 {index} 条必须先确认已去除敏感信息。",
                    status_code=422,
                )
    high_risk_source_confirmed: bool | None = None
    if template_type in {KnowledgeTemplateType.SAFETY_RULE, KnowledgeTemplateType.FAQ}:
        high_risk_rows = [record for record in records if record.get("风险等级") in {"高", "高风险", "P0"}]
        high_risk_source_confirmed = all(_has_value(record.get("资料来源")) for record in high_risk_rows)
        if not high_risk_source_confirmed:
            raise AppError(
                "KNOWLEDGE_TEMPLATE_HIGH_RISK_SOURCE_REQUIRED",
                "高风险安全或FAQ资料必须填写可追溯来源。",
                status_code=422,
            )
    return list(dict.fromkeys(warnings)), high_risk_source_confirmed


def write_controlled_upload(*, storage_root: str, material_id: str, revision: int, filename: str, content: bytes) -> str:
    """Store raw bytes only under a runtime path excluded from Git."""
    suffix = Path(safe_filename(filename)).suffix.lower()
    target = Path(storage_root).resolve() / material_id / str(revision) / f"source{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return str(target)


def remove_controlled_upload(storage_path: str) -> None:
    path = Path(storage_path)
    if path.exists():
        path.unlink()
    for parent in (path.parent, path.parent.parent):
        try:
            parent.rmdir()
        except OSError:
            break


def _extract_text(suffix: str, content: bytes) -> str:
    if suffix in {".txt", ".md", ".csv"}:
        return content.decode("utf-8-sig")
    if suffix == ".json":
        value: Any = json.loads(content.decode("utf-8-sig"))
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    values: list[str] = []
    for worksheet in workbook.worksheets:
        if worksheet.sheet_state != "visible":
            continue
        values.append(f"工作表：{worksheet.title}")
        for row in worksheet.iter_rows(values_only=True):
            row_values = [str(value).strip() for value in row if value is not None and str(value).strip()]
            if row_values:
                values.append(" | ".join(row_values))
    workbook.close()
    return "\n".join(values)
