"""Persistence-only operations for import batches and review staging."""

import json
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.models import ImportBatch, ImportRow, StagedProductSku, utc_now
from app.ingestion.schemas import BatchStatus, ProcessedRow, ReviewStatus, RowStatus


class IngestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_batch(
        self,
        *,
        original_filename: str,
        file_sha256: str,
        created_by: str,
        target_store_code: str | None = None,
    ) -> ImportBatch:
        batch = ImportBatch(
            tenant_id="UNRESOLVED",
            target_store_code=target_store_code,
            import_type="PRODUCT_SKU",
            original_filename=original_filename,
            file_sha256=file_sha256,
            status=BatchStatus.RECEIVED,
            created_by=created_by,
        )
        self.session.add(batch)
        self.session.commit()
        self.session.refresh(batch)
        return batch

    def set_status(
        self,
        batch: ImportBatch,
        status: BatchStatus,
        *,
        error_message: str | None = None,
        completed: bool = False,
    ) -> None:
        batch.status = status
        batch.error_message = error_message
        if completed:
            batch.completed_at = utc_now()
        self.session.commit()

    def save_processed_rows(
        self,
        batch: ImportBatch,
        rows: list[ProcessedRow],
    ) -> None:
        tenant_ids = sorted(
            {str(row.normalized_data["tenant_id"]) for row in rows if row.normalized_data.get("tenant_id")}
        )
        batch.tenant_id = tenant_ids[0] if len(tenant_ids) == 1 else "MULTIPLE"
        for row in rows:
            self.session.add(
                ImportRow(
                    batch_id=batch.id,
                    source_row_number=row.source_row_number,
                    raw_data_json=json.dumps(row.raw_data, ensure_ascii=False, default=str),
                    normalized_data_json=json.dumps(
                        row.normalized_data, ensure_ascii=False, default=str
                    ),
                    row_hash=row.row_hash,
                    validation_status=row.validation_status,
                    error_codes_json=json.dumps(
                        [issue.model_dump(mode="json") for issue in row.errors],
                        ensure_ascii=False,
                    ),
                    warning_codes_json=json.dumps(
                        [issue.model_dump(mode="json") for issue in row.warnings],
                        ensure_ascii=False,
                    ),
                )
            )
            if row.validation_status == RowStatus.VALID:
                data = row.normalized_data
                self.session.add(
                    StagedProductSku(
                        tenant_id=data["tenant_id"],
                        batch_id=batch.id,
                        platform=data["platform"],
                        store_code=data["store_code"],
                        product_code=data.get("product_code"),
                        platform_product_id=data.get("platform_product_id"),
                        product_name=data["product_name"],
                        sku_code=data.get("sku_code"),
                        platform_sku_id=data.get("platform_sku_id"),
                        sku_name=data["sku_name"],
                        specifications=data.get("specifications"),
                        applicable_age_min=data.get("applicable_age_min"),
                        applicable_age_max=data.get("applicable_age_max"),
                        material=data.get("material"),
                        package_contents=data.get("package_contents"),
                        source_name=data["source_name"],
                        effective_from=_as_date(data.get("effective_from")),
                        effective_to=_as_date(data.get("effective_to")),
                        row_hash=row.row_hash,
                        review_status=ReviewStatus.PENDING_REVIEW,
                        external_system="MANUAL_EXCEL",
                    )
                )
        batch.total_rows = len(rows)
        batch.valid_rows = sum(row.validation_status == RowStatus.VALID for row in rows)
        batch.invalid_rows = sum(
            row.validation_status in {RowStatus.INVALID, RowStatus.CONFLICT} for row in rows
        )
        batch.duplicate_rows = sum(
            row.validation_status == RowStatus.DUPLICATE for row in rows
        )
        self.session.commit()

    def get_batch(self, batch_id: str) -> ImportBatch | None:
        return self.session.get(ImportBatch, batch_id)

    def list_batches(self, *, page: int, page_size: int) -> tuple[list[ImportBatch], int]:
        total = self.session.scalar(select(func.count()).select_from(ImportBatch)) or 0
        items = list(
            self.session.scalars(
                select(ImportBatch)
                .order_by(ImportBatch.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    def list_rows(
        self,
        batch_id: str,
        *,
        status: RowStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ImportRow], int]:
        query = select(ImportRow).where(ImportRow.batch_id == batch_id)
        count_query = select(func.count()).select_from(ImportRow).where(
            ImportRow.batch_id == batch_id
        )
        if status is not None:
            query = query.where(ImportRow.validation_status == status)
            count_query = count_query.where(ImportRow.validation_status == status)
        total = self.session.scalar(count_query) or 0
        items = list(
            self.session.scalars(
                query.order_by(ImportRow.source_row_number)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    def count_staged(self, batch_id: str) -> int:
        return (
            self.session.scalar(
                select(func.count()).select_from(StagedProductSku).where(
                    StagedProductSku.batch_id == batch_id
                )
            )
            or 0
        )


def _as_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
