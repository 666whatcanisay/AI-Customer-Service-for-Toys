"""Synchronous, review-gated product-knowledge import orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import PurePosixPath
import re
import unicodedata
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.errors import AppError
from app.ingestion.models import (
    ImportBatch,
    ImportChangeSet,
    ImportFieldChange,
    ImportReviewRecord,
    ImportRow,
    utc_now,
)
from app.ingestion.schemas import BatchStatus, RowStatus
from app.product_knowledge_import.parser import ProductKnowledgeTemplateParser
from app.product_knowledge_import.product_knowledge_mapping import (
    MAPPING_BY_KEY,
    PARSER_VERSION,
    PRODUCT_FIELD_MAPPINGS,
    TEMPLATE_TYPE,
    TEMPLATE_VERSION,
)
from app.product_knowledge_import.schemas import (
    ChangeSetOperation,
    ChangeSetStatus,
    ChangeType,
    ImportAcceptedResponse,
    MergeFieldPreview,
    MergePreviewItem,
    MergePreviewResponse,
    MergeProductPreview,
    ProductKnowledgePreflightResponse,
    ProductMatchType,
    ReviewDecision,
    ReviewOutcome,
    ReviewReceipt,
    ReviewRequest,
    ReviewResponse,
)
from app.test_catalog.models import (
    TestKnowledgePackage,
    TestProduct,
    TestSourceEvidence,
    TestStore,
)


ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
}
ACTIVE_BATCH_STATUSES = {
    BatchStatus.IDENTIFIED_PENDING_REVIEW,
    BatchStatus.PARTIALLY_REVIEWED,
}
TERMINAL_CHANGE_SET_STATUSES = {
    ChangeSetStatus.APPROVED_APPLIED,
    ChangeSetStatus.REJECTED,
}


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_load(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return fallback
    return result


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_hash(value: Any) -> str:
    return _sha256_bytes(_json_dump(value).encode("utf-8"))


def _identity_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _product_identity_key(store_ref: int, product_name: str) -> str:
    return _stable_hash({"store_ref": store_ref, "product_name": _identity_text(product_name)})


def _clean_operator(value: str) -> str:
    result = value.strip()
    if not result:
        raise AppError("PRODUCT_KNOWLEDGE_IMPORT_OPERATOR_REQUIRED", "operator 不能为空。", status_code=422)
    return result[:128]


def _safe_filename(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).name[:255] or "upload.xlsx"


class ProductKnowledgeImportService:
    def __init__(self, session: Session, *, max_upload_bytes: int, max_rows: int) -> None:
        self.session = session
        self.max_upload_bytes = max_upload_bytes
        self.max_rows = max_rows
        self.parser = ProductKnowledgeTemplateParser()

    def upload(
        self,
        *,
        store_ref: int,
        template_type: str,
        filename: str,
        content_type: str | None,
        content: bytes,
        operator: str,
        idempotency_key: str,
    ) -> tuple[ImportAcceptedResponse, bool]:
        operator = _clean_operator(operator)
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 255:
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_IDEMPOTENCY_KEY_INVALID",
                "Idempotency-Key 必须存在且不超过 255 个字符。",
                status_code=422,
            )
        if template_type != TEMPLATE_TYPE:
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_NOT_AVAILABLE",
                "该模板导入功能暂未开放",
                status_code=422,
            )
        safe_filename = _safe_filename(filename)
        self._validate_file(safe_filename, content_type, content)
        file_sha256 = _sha256_bytes(content)
        request_fingerprint = _stable_hash(
            {
                "store_ref": store_ref,
                "template_type": template_type,
                "file_sha256": file_sha256,
            }
        )
        existing = self.session.scalar(
            select(ImportBatch).where(
                ImportBatch.import_type == TEMPLATE_TYPE,
                ImportBatch.created_by == operator,
                ImportBatch.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                raise AppError(
                    "PRODUCT_KNOWLEDGE_IMPORT_IDEMPOTENCY_CONFLICT",
                    "同一 Idempotency-Key 对应了不同上传请求。",
                    status_code=409,
                )
            return ImportAcceptedResponse(batch_id=existing.id, status=existing.status), True

        duplicate = self.session.scalar(
            select(ImportBatch).where(
                ImportBatch.import_type == TEMPLATE_TYPE,
                ImportBatch.store_ref == str(store_ref),
                ImportBatch.template_type == template_type,
                ImportBatch.file_sha256 == file_sha256,
                ImportBatch.status.in_(ACTIVE_BATCH_STATUSES),
            )
        )
        if duplicate is not None:
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_DUPLICATE_ACTIVE_BATCH",
                f"相同文件已有待审核批次：{duplicate.id}。",
                status_code=409,
            )

        store = self.session.get(TestStore, store_ref)
        if store is None:
            raise AppError("PRODUCT_KNOWLEDGE_IMPORT_STORE_NOT_FOUND", "未找到所选店铺。", status_code=404)
        if not store.trial_enabled:
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_STORE_INACTIVE",
                "停用店铺不能创建商品知识导入批次。",
                status_code=409,
            )

        batch = ImportBatch(
            tenant_id=store.tenant_id,
            import_type=TEMPLATE_TYPE,
            original_filename=safe_filename,
            file_sha256=file_sha256,
            status=BatchStatus.PARSING,
            created_by=operator,
            store_ref=str(store_ref),
            store_code_snapshot=store.store_code,
            store_name_snapshot=store.store_name,
            platform_snapshot=store.platform,
            file_size_bytes=len(content),
            template_type=TEMPLATE_TYPE,
            template_version=TEMPLATE_VERSION,
            parser_version=PARSER_VERSION,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            template_evidence_json="{}",
            version=1,
            updated_at=utc_now(),
        )
        self.session.add(batch)
        self.session.commit()

        try:
            result = self.parser.parse(content, max_rows=self.max_rows)
            store_issues = self._store_scope_issues(result.products, store)
            field_result = dict(result.field_validation_result)
            issues = list(field_result.get("issues", [])) + store_issues
            field_result["issues"] = issues
            field_result["blocking_issue_count"] = int(
                field_result.get("blocking_issue_count", 0)
            ) + len(store_issues)
            field_result["valid"] = field_result["blocking_issue_count"] == 0

            rows = self._save_rows(batch, result.products, issues)
            identification = self._identify_products(batch, store, result.products, rows)
            blocking = not field_result["valid"] or identification["conflict_count"] > 0
            if blocking:
                batch.status = BatchStatus.PREFLIGHT_FAILED
            else:
                self._save_change_sets(batch, store, result.products, rows, identification)
                pending = self._count_change_sets(batch.id, ChangeSetStatus.IDENTIFIED_PENDING_REVIEW)
                batch.status = (
                    BatchStatus.IDENTIFIED_PENDING_REVIEW if pending else BatchStatus.NO_CHANGE
                )
                if not pending:
                    batch.completed_at = utc_now()
            batch.total_rows = len(result.products)
            batch.valid_rows = sum(row.validation_status == RowStatus.VALID for row in rows)
            batch.invalid_rows = sum(row.validation_status == RowStatus.INVALID for row in rows)
            batch.duplicate_rows = 0
            batch.updated_at = utc_now()
            batch.template_evidence_json = _json_dump(
                {
                    "file_result": {
                        "filename": safe_filename,
                        "file_size_bytes": len(content),
                        "file_sha256": file_sha256,
                        "valid": not blocking,
                    },
                    "sheet_results": result.sheet_results,
                    "template_metadata": result.template_metadata,
                    "field_validation_result": field_result,
                    "product_identification_result": identification,
                }
            )
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            batch = self.session.get(ImportBatch, batch.id)
            if batch is not None:
                batch.status = BatchStatus.FAILED
                batch.error_message = "PRODUCT_KNOWLEDGE_IMPORT_INTERNAL_ERROR"
                batch.completed_at = utc_now()
                batch.updated_at = utc_now()
                self.session.commit()
            if isinstance(exc, AppError):
                raise
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_INTERNAL_ERROR",
                "商品知识导入处理失败。",
                status_code=500,
            ) from exc

        return ImportAcceptedResponse(batch_id=batch.id, status=batch.status), False

    def preflight(self, batch_id: str) -> ProductKnowledgePreflightResponse:
        batch = self._get_product_batch(batch_id)
        evidence = _json_load(batch.template_evidence_json, {})
        pending = self._count_change_sets(batch.id, ChangeSetStatus.IDENTIFIED_PENDING_REVIEW)
        return ProductKnowledgePreflightResponse(
            batch_id=batch.id,
            status=batch.status,
            can_review=pending > 0,
            file_result=evidence.get("file_result", {}),
            sheet_results=evidence.get("sheet_results", []),
            field_validation_result=evidence.get("field_validation_result", {}),
            product_identification_result=evidence.get("product_identification_result", {}),
        )

    def merge_preview(
        self,
        batch_id: str,
        *,
        page: int,
        page_size: int,
    ) -> MergePreviewResponse:
        batch = self._get_product_batch(batch_id)
        total = int(
            self.session.scalar(
                select(func.count()).select_from(ImportChangeSet).where(
                    ImportChangeSet.batch_id == batch.id
                )
            )
            or 0
        )
        change_sets = list(
            self.session.scalars(
                select(ImportChangeSet)
                .options(selectinload(ImportChangeSet.field_changes))
                .where(ImportChangeSet.batch_id == batch.id)
                .order_by(ImportChangeSet.created_at, ImportChangeSet.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        items = [
            MergePreviewItem(
                product=MergeProductPreview(
                    change_set_id=item.id,
                    product_name=item.product_name,
                    target_product_id=item.target_product_id,
                    operation=item.operation,
                    status=item.status,
                    base_snapshot_hash=item.base_snapshot_hash,
                    version=item.version,
                ),
                fields=[
                    MergeFieldPreview(
                        field_key=field.field_key,
                        field_label=field.field_label,
                        old_value=_json_load(field.old_value_json, None),
                        incoming_value=_json_load(field.incoming_value_json, None),
                        merged_value=_json_load(field.merged_value_json, None),
                        change_type=field.change_type,
                    )
                    for field in sorted(item.field_changes, key=lambda value: value.display_order)
                ],
            )
            for item in change_sets
        ]
        return MergePreviewResponse(
            batch_id=batch.id,
            status=batch.status,
            items=items,
            page=page,
            page_size=page_size,
            total=total,
        )

    def review(
        self,
        *,
        batch_id: str,
        change_set_id: str,
        request: ReviewRequest,
        idempotency_key: str,
    ) -> tuple[ReviewResponse, bool]:
        batch = self._get_product_batch(batch_id)
        change_set = self.session.scalar(
            select(ImportChangeSet)
            .options(selectinload(ImportChangeSet.field_changes))
            .where(
                ImportChangeSet.id == change_set_id,
                ImportChangeSet.batch_id == batch.id,
            )
        )
        if change_set is None:
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_CHANGE_SET_NOT_FOUND",
                "未找到待审核商品变更。",
                status_code=404,
            )
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 255:
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_IDEMPOTENCY_KEY_INVALID",
                "Idempotency-Key 必须存在且不超过 255 个字符。",
                status_code=422,
            )
        fingerprint = _stable_hash(request.model_dump(mode="json"))
        replay = self.session.scalar(
            select(ImportReviewRecord).where(
                ImportReviewRecord.change_set_id == change_set.id,
                ImportReviewRecord.reviewed_by == request.operator,
                ImportReviewRecord.idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            if replay.request_fingerprint != fingerprint:
                raise AppError(
                    "PRODUCT_KNOWLEDGE_IMPORT_REVIEW_IDEMPOTENCY_CONFLICT",
                    "同一 Idempotency-Key 对应了不同审核请求。",
                    status_code=409,
                )
            return ReviewResponse(review_receipt=self._receipt(replay)), True

        if change_set.status in TERMINAL_CHANGE_SET_STATUSES:
            prior = self.session.scalar(
                select(ImportReviewRecord)
                .where(ImportReviewRecord.change_set_id == change_set.id)
                .order_by(ImportReviewRecord.created_at.desc())
            )
            if prior is not None and prior.decision == request.decision:
                return ReviewResponse(review_receipt=self._receipt(prior)), True
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_REVIEW_CONFLICT",
                "该商品变更已经完成相反的审核决定。",
                status_code=409,
            )
        if change_set.status != ChangeSetStatus.IDENTIFIED_PENDING_REVIEW:
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_CHANGE_SET_NOT_REVIEWABLE",
                "当前商品变更状态不可审核。",
                status_code=409,
            )

        if request.decision == ReviewDecision.REJECT:
            record = self._create_review_record(
                batch=batch,
                change_set=change_set,
                request=request,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                outcome=ReviewOutcome.REJECTED,
                observed_hash=change_set.base_snapshot_hash,
                before_hash=change_set.base_snapshot_hash,
                after_hash=change_set.base_snapshot_hash,
            )
            change_set.status = ChangeSetStatus.REJECTED
            change_set.version += 1
            change_set.updated_at = utc_now()
            self._refresh_batch_status(batch)
            self.session.commit()
            return ReviewResponse(review_receipt=self._receipt(record)), False

        observed_hash = self._observed_snapshot_hash(batch, change_set)
        stale = (
            request.expected_base_snapshot_hash != change_set.base_snapshot_hash
            or request.expected_change_set_version != change_set.version
            or observed_hash != change_set.base_snapshot_hash
        )
        if stale:
            record = self._create_review_record(
                batch=batch,
                change_set=change_set,
                request=request,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                outcome=ReviewOutcome.STALE_REVIEW_REQUIRED,
                observed_hash=observed_hash,
                before_hash=observed_hash,
                after_hash=None,
                error_code="BASE_SNAPSHOT_CHANGED",
            )
            change_set.status = ChangeSetStatus.STALE_REVIEW_REQUIRED
            change_set.version += 1
            change_set.updated_at = utc_now()
            self._refresh_batch_status(batch)
            self.session.commit()
            return ReviewResponse(review_receipt=self._receipt(record)), False

        try:
            product, applied_count = self._apply_change_set(batch, change_set, request)
            after_hash = _stable_hash(self._product_snapshot(product))
            record = self._create_review_record(
                batch=batch,
                change_set=change_set,
                request=request,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                outcome=ReviewOutcome.APPLIED,
                observed_hash=observed_hash,
                before_hash=observed_hash,
                after_hash=after_hash,
                applied_product_id=product.product_id,
                applied_field_count=applied_count,
            )
            change_set.status = ChangeSetStatus.APPROVED_APPLIED
            change_set.applied_product_id = product.product_id
            change_set.applied_at = utc_now()
            change_set.version += 1
            change_set.updated_at = utc_now()
            self._refresh_batch_status(batch)
            self.session.commit()
        except AppError as exc:
            self.session.rollback()
            if exc.code != "PRODUCT_KNOWLEDGE_IMPORT_STALE_REVIEW":
                raise
            batch = self._get_product_batch(batch_id)
            change_set = self.session.get(ImportChangeSet, change_set_id)
            if change_set is None:
                raise
            observed_hash = self._observed_snapshot_hash(batch, change_set)
            record = self._create_review_record(
                batch=batch,
                change_set=change_set,
                request=request,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                outcome=ReviewOutcome.STALE_REVIEW_REQUIRED,
                observed_hash=observed_hash,
                before_hash=observed_hash,
                after_hash=None,
                error_code=exc.code,
            )
            change_set.status = ChangeSetStatus.STALE_REVIEW_REQUIRED
            change_set.version += 1
            change_set.updated_at = utc_now()
            self._refresh_batch_status(batch)
            self.session.commit()
            return ReviewResponse(review_receipt=self._receipt(record)), False
        except Exception:
            self.session.rollback()
            batch = self._get_product_batch(batch_id)
            change_set = self.session.get(ImportChangeSet, change_set_id)
            if change_set is None:
                raise AppError(
                    "PRODUCT_KNOWLEDGE_IMPORT_APPLY_FAILED",
                    "审核通过后的商品知识写入失败，正式数据未提交。",
                    status_code=500,
                )
            record = self._create_review_record(
                batch=batch,
                change_set=change_set,
                request=request,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                outcome=ReviewOutcome.APPLY_FAILED,
                observed_hash=observed_hash,
                before_hash=observed_hash,
                after_hash=None,
                error_code="PRODUCT_KNOWLEDGE_IMPORT_APPLY_FAILED",
            )
            change_set.status = ChangeSetStatus.APPLY_FAILED
            change_set.version += 1
            change_set.updated_at = utc_now()
            self._refresh_batch_status(batch)
            self.session.commit()
            return ReviewResponse(review_receipt=self._receipt(record)), False
        return ReviewResponse(review_receipt=self._receipt(record)), False

    def _validate_file(self, filename: str, content_type: str | None, content: bytes) -> None:
        if not filename.lower().endswith(".xlsx"):
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_UNSUPPORTED_FILE_TYPE",
                "只支持 .xlsx 文件。",
                status_code=415,
            )
        if content_type not in ALLOWED_MIME_TYPES:
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_UNSUPPORTED_FILE_TYPE",
                "上传文件不是受支持的 XLSX 类型。",
                status_code=415,
            )
        if len(content) > self.max_upload_bytes:
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_FILE_TOO_LARGE",
                f"文件超过 {self.max_upload_bytes} 字节限制。",
                status_code=413,
            )

    @staticmethod
    def _store_scope_issues(products, store: TestStore) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for product in products:
            if _identity_text(product.store_name) != _identity_text(store.store_name):
                issues.append(
                    {
                        "code": "STORE_SCOPE_MISMATCH",
                        "sheet": "数据填写",
                        "row": product.source_row_number,
                        "field": "店铺名称",
                        "message": (
                            f"当前选择店铺：{store.store_name}；"
                            f"Excel 数据所属店铺：{product.store_name}。请确认后重新上传。"
                        ),
                    }
                )
        return issues

    def _save_rows(self, batch, products, issues) -> list[ImportRow]:
        issue_rows = {item.get("row") for item in issues if item.get("row") is not None}
        rows: list[ImportRow] = []
        for product in products:
            raw = {
                "店铺名称": product.store_name,
                "商品名称": product.product_name,
                **product.fields,
                "资料来源": product.source_name,
                "来源日期": product.source_date,
                "是否人工确认": product.human_confirmation,
                "备注": product.remark,
            }
            normalized = product.model_dump(mode="json")
            row_issues = [item for item in issues if item.get("row") == product.source_row_number]
            row = ImportRow(
                batch_id=batch.id,
                source_row_number=product.source_row_number,
                raw_data_json=_json_dump(raw),
                normalized_data_json=_json_dump(normalized),
                row_hash=_stable_hash(normalized),
                validation_status=(
                    RowStatus.INVALID
                    if product.source_row_number in issue_rows
                    else RowStatus.VALID
                ),
                error_codes_json=_json_dump(row_issues),
                warning_codes_json="[]",
                sheet_name="数据填写",
                product_identity_key=_product_identity_key(int(batch.store_ref), product.product_name),
            )
            self.session.add(row)
            rows.append(row)
        self.session.flush()
        return rows

    def _identify_products(self, batch, store, products, rows) -> dict[str, Any]:
        existing_products = list(
            self.session.scalars(
                select(TestProduct).where(
                    TestProduct.package_id == store.package_id,
                    TestProduct.store_code == store.store_code,
                )
            )
        )
        by_name: dict[str, list[TestProduct]] = {}
        for product in existing_products:
            for name in {product.product_name_display, product.product_name_official}:
                by_name.setdefault(_identity_text(name), []).append(product)
        product_items: list[dict[str, Any]] = []
        new_count = existing_count = conflict_count = 0
        for parsed, row in zip(products, rows, strict=True):
            matches = {item.product_id: item for item in by_name.get(_identity_text(parsed.product_name), [])}
            if len(matches) == 0:
                match_type = ProductMatchType.NEW
                target = None
                new_count += 1
            elif len(matches) == 1:
                match_type = ProductMatchType.EXISTING
                target = next(iter(matches.values()))
                existing_count += 1
            else:
                match_type = ProductMatchType.CONFLICT
                target = None
                conflict_count += 1
                row.validation_status = RowStatus.CONFLICT
            row.product_match_type = match_type
            row.target_product_id = target.product_id if target else None
            product_items.append(
                {
                    "source_row_number": parsed.source_row_number,
                    "product_name": parsed.product_name,
                    "match_type": match_type,
                    "target_product_id": target.product_id if target else None,
                }
            )
        self.session.flush()
        return {
            "total_products": len(products),
            "new_count": new_count,
            "existing_count": existing_count,
            "conflict_count": conflict_count,
            "products": product_items,
        }

    def _save_change_sets(self, batch, store, products, rows, identification) -> None:
        identification_by_row = {
            item["source_row_number"]: item
            for item in identification["products"]
        }
        for parsed, row in zip(products, rows, strict=True):
            identified = identification_by_row[parsed.source_row_number]
            target = (
                self.session.get(TestProduct, identified["target_product_id"])
                if identified["target_product_id"]
                else None
            )
            old_snapshot = (
                self._product_snapshot(target)
                if target is not None
                else self._missing_product_snapshot(store.id, parsed.product_name)
            )
            incoming_fields = dict(parsed.fields)
            merged_fields: dict[str, Any] = {}
            field_changes: list[ImportFieldChange] = []
            material_changes = 0
            for mapping in PRODUCT_FIELD_MAPPINGS:
                old_value = old_snapshot.get(mapping.field_key)
                incoming_value = incoming_fields.get(mapping.field_key)
                if incoming_value in {None, ""}:
                    merged_value = old_value
                    change_type = ChangeType.KEEP
                elif target is None:
                    merged_value = incoming_value
                    change_type = ChangeType.ADD
                    material_changes += 1
                elif old_value in {None, ""}:
                    merged_value = incoming_value
                    change_type = ChangeType.ADD
                    material_changes += 1
                elif old_value == incoming_value:
                    merged_value = old_value
                    change_type = ChangeType.NO_CHANGE
                else:
                    merged_value = incoming_value
                    change_type = ChangeType.UPDATE
                    material_changes += 1
                merged_fields[mapping.field_key] = merged_value
                field_changes.append(
                    ImportFieldChange(
                        field_key=mapping.field_key,
                        field_label=mapping.field_label,
                        display_order=mapping.display_order,
                        old_value_json=_json_dump(old_value),
                        incoming_value_json=_json_dump(incoming_value),
                        merged_value_json=_json_dump(merged_value),
                        change_type=change_type,
                    )
                )
            operation = (
                ChangeSetOperation.CREATE
                if target is None
                else ChangeSetOperation.UPDATE
                if material_changes
                else ChangeSetOperation.NO_CHANGE
            )
            status = (
                ChangeSetStatus.NO_CHANGE
                if operation == ChangeSetOperation.NO_CHANGE
                else ChangeSetStatus.IDENTIFIED_PENDING_REVIEW
            )
            incoming_snapshot = {
                "fields": incoming_fields,
                "evidence": {
                    "source_name": parsed.source_name,
                    "source_date": parsed.source_date,
                    "human_confirmation": parsed.human_confirmation,
                    "remark": parsed.remark,
                    "source_row_number": parsed.source_row_number,
                },
            }
            change_set = ImportChangeSet(
                batch_id=batch.id,
                source_row_ids_json=_json_dump([row.id]),
                product_identity_key=row.product_identity_key,
                product_name=parsed.product_name,
                target_product_id=target.product_id if target else None,
                operation=operation,
                status=status,
                base_snapshot_hash=_stable_hash(old_snapshot),
                old_snapshot_json=_json_dump(old_snapshot),
                incoming_snapshot_json=_json_dump(incoming_snapshot),
                merged_snapshot_json=_json_dump(merged_fields),
                error_codes_json="[]",
                warning_codes_json="[]",
                version=1,
            )
            change_set.field_changes = field_changes
            self.session.add(change_set)
        self.session.flush()

    def _get_product_batch(self, batch_id: str) -> ImportBatch:
        batch = self.session.get(ImportBatch, batch_id)
        if batch is None or batch.import_type != TEMPLATE_TYPE:
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_BATCH_NOT_FOUND",
                "未找到商品知识导入批次。",
                status_code=404,
            )
        return batch

    def _count_change_sets(self, batch_id: str, status: ChangeSetStatus) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(ImportChangeSet).where(
                    ImportChangeSet.batch_id == batch_id,
                    ImportChangeSet.status == status,
                )
            )
            or 0
        )

    def _observed_snapshot_hash(self, batch: ImportBatch, change_set: ImportChangeSet) -> str:
        if change_set.operation == ChangeSetOperation.CREATE:
            store = self.session.get(TestStore, int(batch.store_ref))
            if store is None:
                return _stable_hash({"store_ref": batch.store_ref, "missing_store": True})
            existing = self._find_product(store, change_set.product_name)
            if existing is not None:
                return _stable_hash(self._product_snapshot(existing))
            return _stable_hash(self._missing_product_snapshot(store.id, change_set.product_name))
        product = (
            self.session.get(TestProduct, change_set.target_product_id)
            if change_set.target_product_id
            else None
        )
        if product is None:
            return _stable_hash({"product_id": change_set.target_product_id, "missing": True})
        return _stable_hash(self._product_snapshot(product))

    def _apply_change_set(
        self,
        batch: ImportBatch,
        change_set: ImportChangeSet,
        request: ReviewRequest,
    ) -> tuple[TestProduct, int]:
        store = self.session.get(TestStore, int(batch.store_ref))
        if store is None:
            raise AppError("PRODUCT_KNOWLEDGE_IMPORT_STORE_NOT_FOUND", "未找到所选店铺。", status_code=409)
        package = self.session.get(TestKnowledgePackage, store.package_id)
        if package is None:
            raise AppError(
                "PRODUCT_KNOWLEDGE_IMPORT_STORE_SCOPE_INVALID",
                "店铺业务范围不完整。",
                status_code=409,
            )
        incoming = _json_load(change_set.incoming_snapshot_json, {})
        incoming_fields = incoming.get("fields", {})
        evidence = incoming.get("evidence", {})
        if change_set.operation == ChangeSetOperation.CREATE:
            if self._find_product(store, change_set.product_name) is not None:
                raise AppError(
                    "PRODUCT_KNOWLEDGE_IMPORT_STALE_REVIEW",
                    "同名商品已创建，请重新上传并审核。",
                    status_code=409,
                )
            product = TestProduct(
                product_id=f"C-PRODUCT-{uuid4().hex}",
                package_id=store.package_id,
                tenant_id=store.tenant_id,
                platform=store.platform,
                store_code=store.store_code,
                product_name_official=change_set.product_name,
                product_name_display=change_set.product_name,
                sales_status="OFF_SALE",
                age_min=None,
                age_max=None,
                safety_summary=None,
                review_status="REVIEWING",
                publishable=False,
                source_ids_json="[]",
                raw_data_json="{}",
            )
            self.session.add(product)
            self.session.flush()
        else:
            product = self.session.get(TestProduct, change_set.target_product_id)
            if product is None:
                raise AppError(
                    "PRODUCT_KNOWLEDGE_IMPORT_STALE_REVIEW",
                    "目标商品已不存在，请重新上传并审核。",
                    status_code=409,
                )

        raw = _json_load(product.raw_data_json, {})
        if not isinstance(raw, dict):
            raw = {}
        applied_count = 0
        for field in change_set.field_changes:
            if field.change_type not in {ChangeType.ADD, ChangeType.UPDATE}:
                continue
            value = incoming_fields.get(field.field_key)
            mapping = MAPPING_BY_KEY[field.field_key]
            if mapping.storage == "name":
                product.product_name_display = str(value)
                if change_set.operation == ChangeSetOperation.CREATE:
                    product.product_name_official = str(value)
            elif mapping.storage == "age":
                product.age_min, product.age_max = self._parse_age(str(value))
                raw["recommended_age_text"] = value
            elif mapping.storage == "safety":
                product.safety_summary = str(value)
            else:
                raw[field.field_key.rsplit(".", 1)[-1]] = value
            applied_count += 1

        history = raw.get("_product_knowledge_import_history")
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "batch_id": batch.id,
                "change_set_id": change_set.id,
                "reviewed_by": request.operator,
                "reviewed_at": utc_now().isoformat(),
            }
        )
        raw["_product_knowledge_import_history"] = history[-50:]
        product.raw_data_json = _json_dump(raw)
        product.review_status = (
            "APPROVED" if evidence.get("human_confirmation") == "已确认" else "REVIEWING"
        )
        product.publishable = False

        source = TestSourceEvidence(
            source_id=f"PKI-{uuid4().hex}",
            package_id=product.package_id,
            product_id=product.product_id,
            sku_id=None,
            source_type="PRODUCT_KNOWLEDGE_IMPORT",
            file_name=batch.original_filename,
            relative_path=None,
            file_sha256=batch.file_sha256,
            metadata_json=_json_dump(
                {
                    **evidence,
                    "batch_id": batch.id,
                    "change_set_id": change_set.id,
                    "reviewed_by": request.operator,
                    "review_note": request.review_note,
                    "template_type": batch.template_type,
                    "template_version": batch.template_version,
                }
            ),
        )
        self.session.add(source)
        source_ids = _json_load(product.source_ids_json, [])
        if not isinstance(source_ids, list):
            source_ids = []
        source_ids.append(source.source_id)
        product.source_ids_json = _json_dump(source_ids)

        if change_set.operation == ChangeSetOperation.CREATE:
            counts = _json_load(package.counts_json, {})
            if not isinstance(counts, dict):
                counts = {}
            counts["products"] = int(
                self.session.scalar(
                    select(func.count(TestProduct.product_id)).where(
                        TestProduct.package_id == store.package_id
                    )
                )
                or 0
            )
            package.counts_json = _json_dump(counts)
        self.session.flush()
        return product, applied_count

    def _create_review_record(
        self,
        *,
        batch,
        change_set,
        request,
        idempotency_key,
        fingerprint,
        outcome,
        observed_hash,
        before_hash,
        after_hash,
        applied_product_id=None,
        applied_field_count=0,
        error_code=None,
    ) -> ImportReviewRecord:
        record = ImportReviewRecord(
            batch_id=batch.id,
            change_set_id=change_set.id,
            decision=request.decision,
            outcome=outcome,
            reviewed_by=request.operator,
            review_note=request.review_note,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            expected_base_snapshot_hash=request.expected_base_snapshot_hash,
            observed_base_snapshot_hash=observed_hash,
            expected_change_set_version=request.expected_change_set_version,
            applied_product_id=applied_product_id,
            applied_field_count=applied_field_count,
            before_snapshot_hash=before_hash,
            after_snapshot_hash=after_hash,
            error_code=error_code,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def _refresh_batch_status(self, batch: ImportBatch) -> None:
        pending = self._count_change_sets(batch.id, ChangeSetStatus.IDENTIFIED_PENDING_REVIEW)
        if pending:
            batch.status = BatchStatus.PARTIALLY_REVIEWED
        else:
            batch.status = BatchStatus.COMPLETED
            batch.completed_at = utc_now()
        batch.version += 1
        batch.updated_at = utc_now()

    @staticmethod
    def _receipt(record: ImportReviewRecord) -> ReviewReceipt:
        created_at = record.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return ReviewReceipt(
            receipt_id=record.id,
            batch_id=record.batch_id,
            change_set_id=record.change_set_id,
            decision=record.decision,
            outcome=record.outcome,
            reviewed_by=record.reviewed_by,
            reviewed_at=created_at.isoformat(),
            applied_product_id=record.applied_product_id,
            applied_field_count=record.applied_field_count,
            before_snapshot_hash=record.before_snapshot_hash,
            after_snapshot_hash=record.after_snapshot_hash,
        )

    @staticmethod
    def _missing_product_snapshot(store_ref: int, product_name: str) -> dict[str, Any]:
        return {
            "_missing": True,
            "store_ref": store_ref,
            "product_identity": _identity_text(product_name),
            **{mapping.field_key: None for mapping in PRODUCT_FIELD_MAPPINGS},
        }

    @staticmethod
    def _product_snapshot(product: TestProduct) -> dict[str, Any]:
        raw = _json_load(product.raw_data_json, {})
        if not isinstance(raw, dict):
            raw = {}
        result: dict[str, Any] = {
            "_missing": False,
            "product_id": product.product_id,
            "product.name": product.product_name_display,
            "product_knowledge.product_summary": raw.get("product_summary"),
            "product_knowledge.main_selling_points": raw.get("main_selling_points"),
            "product_knowledge.recommended_age": raw.get("recommended_age_text")
            or ProductKnowledgeImportService._format_age(product.age_min, product.age_max),
            "product_knowledge.material": raw.get("material"),
            "product_knowledge.safety_summary": product.safety_summary,
            "product_knowledge.package_contents": raw.get("package_contents"),
            "product_knowledge.usage_instructions": raw.get("usage_instructions"),
            "product_knowledge.play_method": raw.get("play_method"),
            "product_knowledge.common_customer_questions": raw.get(
                "common_customer_questions"
            ),
            "product_knowledge.recommended_answer_direction": raw.get(
                "recommended_answer_direction"
            ),
        }
        return result

    @staticmethod
    def _format_age(age_min: int | None, age_max: int | None) -> str | None:
        if age_min is None and age_max is None:
            return None
        if age_min is not None and age_max is not None:
            return f"{age_min}-{age_max}岁"
        if age_min is not None:
            return f"{age_min}岁+"
        return f"不超过{age_max}岁"

    @staticmethod
    def _parse_age(value: str) -> tuple[int | None, int | None]:
        numbers = [int(item) for item in re.findall(r"\d+", value)]
        if len(numbers) >= 2:
            return min(numbers[0], numbers[1]), max(numbers[0], numbers[1])
        if len(numbers) == 1:
            if any(marker in value for marker in ("以下", "以内", "不超过")):
                return None, numbers[0]
            return numbers[0], None
        return None, None

    def _find_product(self, store: TestStore, product_name: str) -> TestProduct | None:
        candidates = list(
            self.session.scalars(
                select(TestProduct).where(
                    TestProduct.package_id == store.package_id,
                    TestProduct.store_code == store.store_code,
                )
            )
        )
        matches = [
            product
            for product in candidates
            if _identity_text(product.product_name_display) == _identity_text(product_name)
            or _identity_text(product.product_name_official) == _identity_text(product_name)
        ]
        return matches[0] if len(matches) == 1 else None
