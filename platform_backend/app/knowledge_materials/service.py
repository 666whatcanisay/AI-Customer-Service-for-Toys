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
from pathlib import Path, PurePosixPath
from typing import Any

from openpyxl import load_workbook

from app.errors import AppError
from app.knowledge_materials.schemas import KnowledgeMaterialType, RecognitionSummary


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


def safe_filename(filename: str) -> str:
    return PurePosixPath(filename.replace("\\", "/")).name


def content_hash(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def fingerprint_upload(values: dict[str, str | None], content: bytes) -> str:
    canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical + b'\x00' + content).hexdigest()}"


def recognize_material(
    *, filename: str, content: bytes, material_type: KnowledgeMaterialType, max_bytes: int
) -> tuple[str, RecognitionSummary]:
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
        text = _extract_text(suffix, content)
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
    detected = [
        field for field, keywords in _FIELD_KEYWORDS.items()
        if any(keyword.lower() in bounded.lower() for keyword in keywords)
    ]
    expected = _EXPECTED_FIELDS[material_type]
    missing = [field for field in expected if field not in detected]
    return bounded, RecognitionSummary(
        readable=True,
        file_extension=suffix,
        detected_fields=detected,
        missing_expected_fields=missing,
        privacy_reminder="请确认资料不包含客户会话、手机号、地址、订单或支付信息；系统不会自动脱敏。",
    )


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
