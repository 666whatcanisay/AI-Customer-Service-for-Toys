"""C-internal schemas for trial-store setup and aggregate status."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PilotStoreCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_code: str = Field(min_length=1, max_length=96)
    store_name: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=32)

    @field_validator("store_code", "store_name", "platform")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class PilotStoreItem(BaseModel):
    store_code: str
    store_name: str
    platform: str
    created_at: datetime
    setup_status: str
    catalog_product_count: int
    catalog_sku_count: int
    staged_product_count: int
    staged_sku_count: int
    faq_count: int
    safety_rule_count: int
    experience_case_count: int
    ai_feedback_count: int
    latest_product_imported_at: datetime | None
    test_data_mode: bool = True
    production_usable: bool = False


class PilotStoreListResponse(BaseModel):
    items: list[PilotStoreItem]
    total: int
