"""Safe ZIP and governance-workbook parser for the V0.3.1 test package."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import PurePosixPath
import re
import stat
from typing import Any
from zipfile import BadZipFile, ZipFile, ZipInfo

from openpyxl import load_workbook

from app.errors import AppError

EXPECTED_VERSION = "V0.3.1"
EXPECTED_SCHEMA_VERSION = "0.3.1-test"
EXPECTED_PACKAGE_ID = "PDD-SM-2026-001-TEST"
EXPECTED_PACKAGE_NAME = "汕明_AI客服双版本数据包_V0.3.1_测试基线版"
EXPECTED_TENANT_ID = "TENANT-PDD-SM-TEST"
EXPECTED_PLATFORM = "pdd"
EXPECTED_STORE_CODE = "PDD-SM"
EXPECTED_RESPONSE_MODE = "SUGGESTION_ONLY"
EXPECTED_SHEET_NAMES = [
    "00_版本与试点范围",
    "01_店铺与数据范围",
    "02_商品主表",
    "03_SKU与款式主表",
    "04_附件与证据索引",
    "05_FAQ与回答策略",
    "06_客服安全与权限边界",
    "07_AI评测集",
    "08_冲突与待确认事项",
]
EXPECTED_COUNTS = {
    "products": 5,
    "skus_and_bundles": 18,
    "image_evidence": 35,
    "source_records_total": 37,
    "faqs": 16,
    "safety_rules": 8,
    "evaluation_cases": 28,
    "issues": 13,
}

SHEET_HEADERS: dict[str, list[str]] = {
    "00_版本与试点范围": [
        "data_package_id", "version", "tenant_id", "platform", "store_code",
        "store_name", "trial_scope", "data_owner", "reviewer", "created_at",
        "updated_at", "package_status", "notes", "schema_version",
        "response_mode_default", "allow_auto_send_default",
    ],
    "01_店铺与数据范围": [
        "platform", "store_code", "store_name", "platform_store_id", "store_owner",
        "trial_enabled", "shared_product_group", "shared_after_sales_rules",
        "shared_customer_service_team", "knowledge_scope", "remarks",
        "response_mode_default", "allow_auto_send",
    ],
    "02_商品主表": [
        "product_id", "platform", "store_code", "platform_product_id",
        "product_name_official", "product_name_display", "product_url", "source_url_raw",
        "sales_status", "high_frequency", "age_min", "age_max", "material",
        "particle_type", "compatibility", "assembled_size", "package_size",
        "main_selling_points", "play_method", "assembly_summary", "safety_summary",
        "source_ids", "review_status", "effective_from", "effective_to", "reviewer",
        "notes", "candidate_fields", "blocked_fields", "publishable",
    ],
    "03_SKU与款式主表": [
        "sku_id", "product_id", "platform_sku_id", "sku_code", "sku_name_official",
        "sku_name_display", "color", "model_type", "package_type", "particle_count",
        "small_model_count", "large_model_count", "minifigure_count", "light_type",
        "remote_included", "light_color", "light_modes", "battery_model",
        "battery_included", "manual_included", "sticker_included", "tool_included",
        "assembled_size", "package_size", "difference_summary", "source_ids",
        "review_status", "effective_from", "effective_to", "notes", "relation_type",
        "canonical_sku_id", "reference_sku_id", "component_sku_refs",
        "bundle_specific_notes", "publishable",
    ],
    "04_附件与证据索引": [
        "source_id", "product_id", "sku_id", "source_type", "file_name", "relative_path",
        "source_origin", "platform_url", "page_or_image_number", "provided_by",
        "provided_at", "file_sha256", "supported_field_keys", "observed_values",
        "evidence_description", "review_status", "notes",
    ],
    "05_FAQ与回答策略": [
        "faq_id", "platform", "store_code", "product_id", "sku_id", "question_category",
        "canonical_question", "similar_questions", "fact_answer", "recommended_reply",
        "answer_action", "risk_level", "required_fields", "requires_realtime_lookup",
        "transfer_condition", "forbidden_claims", "source_ids", "review_status",
        "effective_from", "effective_to", "notes", "response_mode", "allow_auto_send",
        "publishable",
    ],
    "06_客服安全与权限边界": [
        "rule_id", "platform", "store_code", "scenario", "rule_type", "risk_level",
        "allowed_action", "requires_confirmation", "requires_supervisor",
        "required_information", "fixed_instruction", "forbidden_claim", "source_id",
        "review_status", "effective_from", "effective_to", "notes", "response_mode",
        "allow_auto_send", "publishable",
    ],
    "07_AI评测集": [
        "case_id", "case_type", "platform", "store_code", "product_id", "sku_id",
        "customer_question", "conversation_context", "expected_action", "expected_key_facts",
        "forbidden_claims", "expected_source_ids", "expected_required_fields", "risk_level",
        "pass_criteria", "review_status", "notes", "expected_response_mode",
        "allow_auto_send_expected",
    ],
    "08_冲突与待确认事项": [
        "issue_id", "entity_type", "entity_id", "field_name", "candidate_value",
        "candidate_source_ids", "candidate_source_description", "conflicting_value",
        "conflicting_source_ids", "conflicting_source_description", "field_review_status",
        "confirmed_value", "risk_level", "decision_owner", "decision", "status",
        "created_at", "resolved_at", "notes",
    ],
}

SHEET_KEYS = {
    "00_版本与试点范围": ("data_package_id", "version", "tenant_id"),
    "01_店铺与数据范围": ("platform",),
    "02_商品主表": ("product_id",),
    "03_SKU与款式主表": ("sku_id",),
    "04_附件与证据索引": ("source_id",),
    "05_FAQ与回答策略": ("faq_id",),
    "06_客服安全与权限边界": ("rule_id",),
    "07_AI评测集": ("case_id",),
    "08_冲突与待确认事项": ("issue_id",),
}


@dataclass(frozen=True, slots=True)
class ParsedTestPackage:
    manifest: dict[str, Any]
    file_sha256: str
    file_size_bytes: int
    worksheets: list[str]
    rows: dict[str, list[dict[str, Any]]]

    @property
    def package_id(self) -> str:
        return str(self.manifest["data_package_id"])

    @property
    def counts(self) -> dict[str, int]:
        return {key: int(value) for key, value in self.manifest["counts"].items()}


def split_array(value: Any, *, pipe_only: bool = False) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    pattern = r"\|" if pipe_only else r"[,，;；|]"
    return [part.strip() for part in re.split(pattern, text) if part.strip()]


def parse_test_package_zip(
    content: bytes,
    *,
    max_entries: int,
    max_uncompressed_bytes: int,
    max_single_file_bytes: int,
) -> ParsedTestPackage:
    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile as exc:
        raise AppError("INVALID_ZIP", "The uploaded file is not a valid ZIP archive") from exc

    with archive:
        physical_files = _validate_zip_entries(
            archive.infolist(),
            max_entries=max_entries,
            max_uncompressed_bytes=max_uncompressed_bytes,
            max_single_file_bytes=max_single_file_bytes,
        )
        files = _resolve_logical_root(physical_files, archive.infolist())
        manifest_info = files.get("manifest.json")
        if manifest_info is None:
            raise AppError("MANIFEST_MISSING", "manifest.json must exist at the logical ZIP root")
        if manifest_info.file_size > 1024 * 1024:
            raise AppError("MANIFEST_TOO_LARGE", "manifest.json exceeds the 1 MB limit")
        try:
            manifest = json.loads(archive.read(manifest_info).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AppError("MANIFEST_INVALID", "manifest.json must be valid UTF-8 JSON") from exc

        manifest_files = _validate_manifest(manifest, files, archive)
        company_workbook_path = _manifest_workbook_path(manifest, "company")
        workbook_path = _manifest_workbook_path(manifest, "middle")
        if company_workbook_path not in manifest_files or workbook_path not in manifest_files:
            raise AppError(
                "WORKBOOK_NOT_LISTED",
                "Both package workbooks must be listed in manifest files",
            )
        workbook_rows = _parse_governance_workbook(archive.read(files[workbook_path]))
        _validate_workbook_data(manifest, workbook_rows, manifest_files)

    return ParsedTestPackage(
        manifest=manifest,
        file_sha256=sha256(content).hexdigest(),
        file_size_bytes=len(content),
        worksheets=list(EXPECTED_SHEET_NAMES),
        rows=workbook_rows,
    )


def _validate_zip_entries(
    infos: list[ZipInfo],
    *,
    max_entries: int,
    max_uncompressed_bytes: int,
    max_single_file_bytes: int,
) -> dict[str, ZipInfo]:
    file_infos = [info for info in infos if not info.is_dir()]
    if len(file_infos) > max_entries:
        raise AppError("ZIP_TOO_MANY_ENTRIES", "ZIP contains too many files")
    total = 0
    normalized: dict[str, ZipInfo] = {}
    for info in infos:
        path = _safe_archive_path(info.filename)
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise AppError("ZIP_SYMLINK_REJECTED", f"ZIP symlink is not allowed: {path}")
        if info.flag_bits & 0x1:
            raise AppError("ZIP_ENCRYPTED_ENTRY", f"Encrypted ZIP entry is not allowed: {path}")
        if info.is_dir():
            continue
        if path in normalized:
            raise AppError("ZIP_DUPLICATE_PATH", f"Duplicate ZIP path: {path}")
        if info.file_size > max_single_file_bytes:
            raise AppError("ZIP_ENTRY_TOO_LARGE", f"ZIP entry exceeds the file limit: {path}")
        total += info.file_size
        if total > max_uncompressed_bytes:
            raise AppError("ZIP_EXPANDED_TOO_LARGE", "ZIP expanded size exceeds the limit")
        if info.file_size and info.compress_size == 0:
            raise AppError("ZIP_INVALID_SIZE", f"ZIP entry has an invalid compressed size: {path}")
        if info.compress_size and info.file_size / info.compress_size > 200:
            raise AppError("ZIP_SUSPICIOUS_RATIO", f"ZIP entry compression ratio is unsafe: {path}")
        normalized[path] = info
    return normalized


def _safe_archive_path(raw_path: str) -> str:
    if not raw_path or "\x00" in raw_path or "\\" in raw_path:
        raise AppError("ZIP_PATH_TRAVERSAL", "ZIP contains an unsafe path")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AppError("ZIP_PATH_TRAVERSAL", f"ZIP contains an unsafe path: {raw_path}")
    if path.parts and re.match(r"^[A-Za-z]:", path.parts[0]):
        raise AppError("ZIP_PATH_TRAVERSAL", f"ZIP contains an unsafe path: {raw_path}")
    return path.as_posix()


def _resolve_logical_root(
    files: dict[str, ZipInfo], infos: list[ZipInfo]
) -> dict[str, ZipInfo]:
    """Return a safe in-memory logical root for a root or singly-wrapped package."""
    if "manifest.json" in files:
        if any(path.endswith("/manifest.json") for path in files):
            raise AppError(
                "MANIFEST_FILE_SET_MISMATCH",
                "ZIP cannot contain both a root manifest and a wrapped manifest",
            )
        return files

    top_level_names = {
        PurePosixPath(_safe_archive_path(info.filename)).parts[0]
        for info in infos
    }
    if len(top_level_names) != 1:
        raise AppError(
            "MANIFEST_MISSING",
            "manifest.json must be at the ZIP root or in one wrapped directory",
        )

    logical_files: dict[str, ZipInfo] = {}
    for physical_path, info in files.items():
        physical_parts = PurePosixPath(physical_path).parts
        if len(physical_parts) < 2:
            raise AppError(
                "MANIFEST_MISSING",
                "manifest.json must be at the ZIP root or in one wrapped directory",
            )
        logical_path = PurePosixPath(*physical_parts[1:]).as_posix()
        if logical_path in logical_files:
            raise AppError(
                "ZIP_DUPLICATE_PATH",
                f"Duplicate logical ZIP path: {logical_path}",
            )
        logical_files[logical_path] = info

    if "manifest.json" not in logical_files:
        raise AppError(
            "MANIFEST_MISSING",
            "manifest.json must be at the ZIP root or in one wrapped directory",
        )
    return logical_files


def _validate_manifest(
    manifest: Any,
    files: dict[str, ZipInfo],
    archive: ZipFile,
) -> dict[str, dict[str, Any]]:
    if not isinstance(manifest, dict):
        raise AppError("MANIFEST_INVALID", "manifest.json must contain an object")
    if manifest.get("data_package_id") != EXPECTED_PACKAGE_ID:
        raise AppError("PACKAGE_ID_INVALID", f"data_package_id must be {EXPECTED_PACKAGE_ID}")
    if manifest.get("package_name") != EXPECTED_PACKAGE_NAME:
        raise AppError("PACKAGE_NAME_INVALID", "package_name is not the V0.3.1 test baseline")
    if manifest.get("version") != EXPECTED_VERSION:
        raise AppError("PACKAGE_VERSION_UNSUPPORTED", "Only V0.3.1 test packages are accepted")
    if manifest.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise AppError("PACKAGE_SCHEMA_UNSUPPORTED", "Only schema 0.3.1-test is accepted")
    if manifest.get("test_data_mode") is not True:
        raise AppError("TEST_DATA_MODE_REQUIRED", "test_data_mode must be true")
    if manifest.get("production_usable") is not False:
        raise AppError("PRODUCTION_PACKAGE_REJECTED", "production_usable must be false")
    if manifest.get("allow_auto_send") is not False:
        raise AppError("AUTO_SEND_REJECTED", "allow_auto_send must be false")
    if manifest.get("tenant_id") != EXPECTED_TENANT_ID:
        raise AppError("TEST_TENANT_REQUIRED", f"tenant_id must be {EXPECTED_TENANT_ID}")
    if manifest.get("response_mode") != EXPECTED_RESPONSE_MODE:
        raise AppError("RESPONSE_MODE_INVALID", f"response_mode must be {EXPECTED_RESPONSE_MODE}")
    expected_gates = {
        "package_status": "TEST_READY_FOR_IMPORT",
        "overall_status": "PASS",
        "data_gate": "PASS",
        "import_gate": "PASS_FOR_TEST_ENVIRONMENT",
    }
    for field, expected in expected_gates.items():
        if manifest.get(field) != expected:
            raise AppError("PACKAGE_GATE_INVALID", f"manifest {field} must be {expected}")
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        raise AppError("MANIFEST_COUNTS_INVALID", "manifest counts must be an object")
    for key, expected in EXPECTED_COUNTS.items():
        if counts.get(key) != expected:
            raise AppError(
                "MANIFEST_COUNT_MISMATCH",
                f"manifest count {key} must be {expected}",
            )
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise AppError("MANIFEST_FILES_INVALID", "manifest files must be an array")
    if manifest.get("file_count_excluding_manifest") != len(entries):
        raise AppError("MANIFEST_FILE_COUNT_MISMATCH", "manifest file count is inconsistent")
    listed: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise AppError("MANIFEST_FILES_INVALID", "manifest file entry must be an object")
        path = _safe_archive_path(str(entry.get("relative_path", "")))
        if path == "manifest.json" or path in listed:
            raise AppError("MANIFEST_DUPLICATE_PATH", f"Invalid manifest path: {path}")
        info = files.get(path)
        if info is None:
            raise AppError("MANIFEST_FILE_MISSING", f"Manifest file is missing from ZIP: {path}")
        if entry.get("size_bytes") != info.file_size:
            raise AppError("MANIFEST_SIZE_MISMATCH", f"File size mismatch: {path}")
        digest = sha256(archive.read(info)).hexdigest()
        if str(entry.get("sha256", "")).lower() != digest:
            raise AppError("MANIFEST_SHA256_MISMATCH", f"SHA-256 mismatch: {path}")
        listed[path] = entry
    actual = set(files) - {"manifest.json"}
    if actual != set(listed):
        raise AppError("MANIFEST_FILE_SET_MISMATCH", "ZIP files do not exactly match manifest")
    return listed


def _manifest_workbook_path(manifest: dict[str, Any], key: str) -> str:
    workbooks = manifest.get("workbooks")
    if not isinstance(workbooks, dict) or not workbooks.get(key):
        raise AppError("WORKBOOK_PATH_MISSING", f"Manifest workbook path is missing: {key}")
    return _safe_archive_path(str(workbooks[key]))


def _parse_governance_workbook(content: bytes) -> dict[str, list[dict[str, Any]]]:
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=False, keep_links=False)
    except Exception as exc:
        raise AppError("WORKBOOK_INVALID", "The C governance workbook cannot be opened") from exc
    try:
        if workbook.sheetnames != EXPECTED_SHEET_NAMES:
            raise AppError("WORKBOOK_SHEETS_INVALID", "Workbook must contain exactly sheets 00 through 08")
        parsed: dict[str, list[dict[str, Any]]] = {}
        for sheet_name in EXPECTED_SHEET_NAMES:
            sheet = workbook[sheet_name]
            if sheet.sheet_state != "visible":
                raise AppError("WORKBOOK_HIDDEN_SHEET", f"Workbook sheet must be visible: {sheet_name}")
            rows = list(sheet.iter_rows())
            if not rows:
                raise AppError("WORKBOOK_HEADER_INVALID", f"Workbook sheet is empty: {sheet_name}")
            headers = [_cell_value(cell.value) for cell in rows[0]]
            while headers and headers[-1] is None:
                headers.pop()
            expected = SHEET_HEADERS[sheet_name]
            if headers != expected:
                raise AppError("WORKBOOK_HEADER_INVALID", f"Workbook headers changed: {sheet_name}")
            items: list[dict[str, Any]] = []
            keys = SHEET_KEYS[sheet_name]
            for row in rows[1:]:
                if any(cell.data_type == "f" for cell in row):
                    raise AppError("WORKBOOK_FORMULA_REJECTED", f"Formula cell found: {sheet_name}")
                values = [_cell_value(cell.value) for cell in row[: len(expected)]]
                values.extend([None] * (len(expected) - len(values)))
                item = dict(zip(expected, values, strict=True))
                if any(item.get(key) in {None, ""} for key in keys):
                    continue
                items.append(item)
            parsed[sheet_name] = items
        return parsed
    finally:
        workbook.close()


def _cell_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return value


def _validate_workbook_data(
    manifest: dict[str, Any],
    rows: dict[str, list[dict[str, Any]]],
    manifest_files: dict[str, dict[str, Any]],
) -> None:
    metadata = _single(rows["00_版本与试点范围"], "version metadata")
    stores = rows["01_店铺与数据范围"]
    products = rows["02_商品主表"]
    skus = rows["03_SKU与款式主表"]
    evidence = rows["04_附件与证据索引"]
    faqs = rows["05_FAQ与回答策略"]
    rules = rows["06_客服安全与权限边界"]
    evaluations = rows["07_AI评测集"]
    conflicts = rows["08_冲突与待确认事项"]
    store = _single(stores, "store scope")

    fixed_pairs = {
        "data_package_id": manifest["data_package_id"],
        "version": EXPECTED_VERSION,
        "tenant_id": EXPECTED_TENANT_ID,
        "platform": EXPECTED_PLATFORM,
        "store_code": EXPECTED_STORE_CODE,
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "response_mode_default": EXPECTED_RESPONSE_MODE,
        "allow_auto_send_default": False,
    }
    for field, expected in fixed_pairs.items():
        if metadata.get(field) != expected:
            raise AppError("WORKBOOK_METADATA_MISMATCH", f"Workbook metadata mismatch: {field}")
    if (
        store.get("platform") != EXPECTED_PLATFORM
        or store.get("store_code") != EXPECTED_STORE_CODE
        or store.get("trial_enabled") is not True
        or store.get("response_mode_default") != EXPECTED_RESPONSE_MODE
        or store.get("allow_auto_send") is not False
    ):
        raise AppError("WORKBOOK_STORE_INVALID", "Workbook store scope violates test-only rules")

    actual_counts = {
        "products": len(products),
        "skus_and_bundles": len(skus),
        "image_evidence": sum(_is_image_evidence(item.get("relative_path")) for item in evidence),
        "source_records_total": len(evidence),
        "faqs": len(faqs),
        "safety_rules": len(rules),
        "evaluation_cases": len(evaluations),
        "issues": len(conflicts),
    }
    for key, expected in EXPECTED_COUNTS.items():
        if actual_counts[key] != expected or manifest["counts"].get(key) != actual_counts[key]:
            raise AppError("WORKBOOK_COUNT_MISMATCH", f"Workbook count mismatch: {key}")

    product_ids = _unique_ids(products, "product_id", "product")
    sku_ids = _unique_ids(skus, "sku_id", "SKU")
    source_ids = _unique_ids(evidence, "source_id", "source")
    _unique_ids(faqs, "faq_id", "FAQ")
    _unique_ids(rules, "rule_id", "safety rule")
    _unique_ids(evaluations, "case_id", "evaluation")
    _unique_ids(conflicts, "issue_id", "conflict")

    for product in products:
        _validate_scope(product)
        _require_sources(product.get("source_ids"), source_ids)
    for sku in skus:
        if sku.get("product_id") not in product_ids:
            raise AppError("SKU_PRODUCT_MISSING", f"SKU product is missing: {sku.get('sku_id')}")
        _require_sources(sku.get("source_ids"), source_ids)
    for sku in skus:
        relation = sku.get("relation_type")
        if relation not in {"INDEPENDENT", "REFERENCE", "BUNDLE"}:
            raise AppError("SKU_RELATION_INVALID", f"Unknown SKU relation: {relation}")
        if relation == "REFERENCE" and sku.get("reference_sku_id") not in sku_ids:
            raise AppError("SKU_REFERENCE_MISSING", f"Referenced SKU is missing: {sku.get('sku_id')}")
        if relation == "BUNDLE":
            components = split_array(sku.get("component_sku_refs"), pipe_only=True)
            if not components or any(component not in sku_ids for component in components):
                raise AppError("SKU_BUNDLE_INVALID", f"Bundle components are invalid: {sku.get('sku_id')}")

    for item in evidence:
        path = item.get("relative_path")
        if not path:
            continue
        safe_path = _safe_archive_path(str(path))
        entry = manifest_files.get(safe_path)
        if entry is None or str(item.get("file_sha256", "")).lower() != str(entry["sha256"]).lower():
            raise AppError("EVIDENCE_FILE_MISMATCH", f"Evidence file metadata mismatch: {safe_path}")
    allowed_actions = {
        "DIRECT_ANSWER", "CONTROLLED_ANSWER", "ASK_CLARIFY",
        "REQUIRE_LOOKUP", "TRANSFER_HUMAN", "REFUSE",
    }
    for item in faqs:
        _validate_scope(item)
        if item.get("answer_action") not in allowed_actions:
            raise AppError("ANSWER_ACTION_INVALID", f"FAQ action is invalid: {item.get('faq_id')}")
        _validate_test_response_flags(item, "response_mode", "allow_auto_send")
        _require_sources(item.get("source_ids"), source_ids)
    for item in rules:
        _validate_scope(item)
        _validate_test_response_flags(item, "response_mode", "allow_auto_send")
        _require_sources(item.get("source_id"), source_ids)
    for item in evaluations:
        _validate_scope(item)
        if item.get("expected_action") not in allowed_actions:
            raise AppError("ANSWER_ACTION_INVALID", f"Evaluation action is invalid: {item.get('case_id')}")
        _validate_test_response_flags(
            item, "expected_response_mode", "allow_auto_send_expected"
        )
        _require_sources(item.get("expected_source_ids"), source_ids)


def _single(items: list[dict[str, Any]], name: str) -> dict[str, Any]:
    if len(items) != 1:
        raise AppError("WORKBOOK_RECORD_COUNT_INVALID", f"Workbook must contain one {name} row")
    return items[0]


def _unique_ids(items: list[dict[str, Any]], field: str, label: str) -> set[str]:
    values = [str(item.get(field) or "") for item in items]
    if any(not value for value in values) or len(set(values)) != len(values):
        raise AppError("WORKBOOK_DUPLICATE_ID", f"Workbook contains invalid {label} IDs")
    return set(values)


def _validate_scope(item: dict[str, Any]) -> None:
    if item.get("platform") != EXPECTED_PLATFORM or item.get("store_code") != EXPECTED_STORE_CODE:
        raise AppError("WORKBOOK_SCOPE_INVALID", "Workbook row is outside the frozen test scope")


def _validate_test_response_flags(
    item: dict[str, Any], response_field: str, auto_send_field: str
) -> None:
    if item.get(response_field) != EXPECTED_RESPONSE_MODE or item.get(auto_send_field) is not False:
        raise AppError("WORKBOOK_RESPONSE_MODE_INVALID", "Workbook row violates suggestion-only mode")


def _require_sources(value: Any, source_ids: set[str]) -> None:
    missing = [source_id for source_id in split_array(value) if source_id not in source_ids]
    if missing:
        raise AppError("SOURCE_REFERENCE_MISSING", f"Unknown source reference: {missing[0]}")


def _is_image_evidence(value: Any) -> bool:
    if not value:
        return False
    return PurePosixPath(str(value)).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
