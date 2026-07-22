"""Frozen task-local response schemas for C-T02B read-only integration APIs."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class AnswerAction(StrEnum):
    DIRECT_ANSWER = "DIRECT_ANSWER"
    CONTROLLED_ANSWER = "CONTROLLED_ANSWER"
    ASK_CLARIFY = "ASK_CLARIFY"
    REQUIRE_LOOKUP = "REQUIRE_LOOKUP"
    TRANSFER_HUMAN = "TRANSFER_HUMAN"
    REFUSE = "REFUSE"


class KnowledgeType(StrEnum):
    PRODUCT_FACT = "PRODUCT_FACT"
    SKU_FACT = "SKU_FACT"
    FAQ = "FAQ"
    SAFETY_RULE = "SAFETY_RULE"


class PackageIssue(BaseModel):
    code: str
    message: str


class TestPackagePreflightResponse(BaseModel):
    original_filename: str
    file_sha256: str
    file_size_bytes: int
    package_id: str
    package_name: str
    version: str
    schema_version: str
    tenant_id: str
    platform: str
    store_code: str
    test_data_mode: bool
    production_usable: bool
    response_mode: str
    allow_auto_send: bool
    worksheets: list[str]
    counts: dict[str, int]
    warnings: list[PackageIssue]
    errors: list[PackageIssue]
    can_import: bool


class TestPackageSummary(BaseModel):
    package_id: str
    package_name: str
    version: str
    schema_version: str
    tenant_id: str
    platform: str
    store_code: str
    test_data_mode: bool
    production_usable: bool
    response_mode: str
    allow_auto_send: bool
    import_status: str
    original_filename: str
    zip_sha256: str
    counts: dict[str, int]
    imported_at: datetime


class TestPackageListResponse(BaseModel):
    items: list[TestPackageSummary]
    total: int


class StoreItem(BaseModel):
    tenant_id: str
    platform: str
    store_code: str
    store_name: str
    trial_enabled: bool
    knowledge_scope: str
    response_mode: str
    allow_auto_send: bool
    test_data_mode: bool
    production_usable: bool


class StoreListResponse(BaseModel):
    items: list[StoreItem]
    total: int


class ProductItem(BaseModel):
    product_id: str
    platform: str
    store_code: str
    product_name_official: str
    product_name_display: str
    sales_status: str
    age_min: int | None
    age_max: int | None
    safety_summary: str | None
    review_status: str
    publishable: bool


class ProductListResponse(BaseModel):
    items: list[ProductItem]
    total: int


class SkuItem(BaseModel):
    sku_id: str
    product_id: str
    sku_code: str
    sku_name_official: str
    sku_name_display: str
    relation_type: str
    canonical_sku_id: str | None
    reference_sku_id: str | None
    component_sku_refs: list[str]
    publishable: bool


class SkuListResponse(BaseModel):
    items: list[SkuItem]
    total: int


class RagExportItem(BaseModel):
    knowledge_id: str
    knowledge_type: KnowledgeType
    tenant_id: str
    platform: str
    store_code: str
    product_id: str | None
    sku_id: str | None
    title: str
    content: str
    answer_action: AnswerAction
    risk_level: str
    source_ids: list[str]
    test_data_mode: bool
    production_usable: bool


class PackageMetadataResponse(BaseModel):
    package_id: str
    version: str
    schema_version: str
    tenant_id: str
    platform: str
    store_code: str
    test_data_mode: bool
    production_usable: bool
    response_mode: str
    allow_auto_send: bool


class RagExportResponse(PackageMetadataResponse):
    items: list[RagExportItem]
    total: int


class EvaluationItem(BaseModel):
    case_id: str
    case_type: str
    platform: str
    store_code: str
    product_id: str | None
    sku_id: str | None
    customer_question: str
    conversation_context: str | None
    expected_action: AnswerAction
    expected_key_facts: list[str]
    forbidden_claims: list[str]
    expected_source_ids: list[str]
    expected_required_fields: list[str]
    risk_level: str
    pass_criteria: str
    expected_response_mode: str
    allow_auto_send_expected: bool


class EvaluationResponse(PackageMetadataResponse):
    items: list[EvaluationItem]
    total: int
