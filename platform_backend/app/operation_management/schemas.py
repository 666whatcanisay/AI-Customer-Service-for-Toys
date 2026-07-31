"""Business-facing schemas for C operation management."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StorePlatform(StrEnum):
    PINDUODUO = "pinduoduo"
    TAOBAO = "taobao"
    TMALL = "tmall"
    JD = "jd"
    DOUYIN = "douyin"
    OFFLINE = "offline"
    OTHER = "other"


class StoreOperationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class StoreCreateRequest(BaseModel):
    store_name: str = Field(min_length=2, max_length=255)
    platform: StorePlatform
    remarks: str = Field(default="", max_length=1000)

    @field_validator("store_name", "remarks")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class StoreUpdateRequest(BaseModel):
    store_name: str = Field(min_length=2, max_length=255)
    platform: StorePlatform
    status: StoreOperationStatus
    remarks: str = Field(default="", max_length=1000)

    @field_validator("store_name", "remarks")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class StoreOperationItem(BaseModel):
    store_ref: int
    store_name: str
    platform_name: str
    status: StoreOperationStatus
    status_name: str
    product_count: int
    created_at: datetime
    remarks: str
    data_source: str
    customer_service_status: str
    customer_service_status_updated_at: datetime | None = None
    customer_service_status_updated_by: str | None = None


class StoreOperationListResponse(BaseModel):
    items: list[StoreOperationItem]
    total: int


class ProductCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_name: str = Field(min_length=2, max_length=255)
    product_summary: str = Field(default="", max_length=4000)

    @field_validator("product_name", "product_summary")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ProductOperationItem(BaseModel):
    product_ref: str
    store_ref: int
    store_name: str
    product_name: str
    product_summary: str
    data_status: str
    data_status_name: str
    sku_count: int
    created_at: datetime
    data_source: str
    customer_service_status: str


class ProductBasicInfoUpdateRequest(BaseModel):
    product_display_name: str = Field(min_length=2, max_length=255)
    product_summary: str = Field(default="", max_length=4000)
    store_display_name: str = Field(min_length=2, max_length=255)
    store_remarks: str = Field(default="", max_length=1000)

    @field_validator(
        "product_display_name",
        "product_summary",
        "store_display_name",
        "store_remarks",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()
