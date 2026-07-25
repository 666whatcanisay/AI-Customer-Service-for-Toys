"""Response models for read-only administration data."""

from datetime import datetime

from pydantic import BaseModel


class AdminPage(BaseModel):
    page: int
    size: int
    total: int


class StoreItem(BaseModel):
    store_code: str
    store_name: str
    platform: str
    test_data_mode: bool
    product_count: int


class StoreListResponse(AdminPage):
    items: list[StoreItem]


class ProductItem(BaseModel):
    product_id: str
    store_code: str
    platform: str
    product_name_official: str
    product_name_display: str
    sales_status: str
    age_min: int | None
    age_max: int | None
    safety_summary: str | None
    review_status: str
    publishable: bool
    source_ids: list[str]
    test_data_mode: bool = True
    production_usable: bool = False


class ProductDetailResponse(ProductItem):
    sku_count: int


class ProductListResponse(AdminPage):
    items: list[ProductItem]


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
    source_ids: list[str]
    test_data_mode: bool = True
    production_usable: bool = False


class SkuListResponse(AdminPage):
    items: list[SkuItem]


class FaqItem(BaseModel):
    faq_id: str
    store_code: str
    product_id: str | None
    sku_id: str | None
    question: str
    recommended_reply: str
    answer_action: str
    risk_level: str
    source_ids: list[str]
    test_data_mode: bool = True
    production_usable: bool = False


class FaqListResponse(AdminPage):
    items: list[FaqItem]


class SafetyRuleItem(BaseModel):
    rule_id: str
    store_code: str
    scenario: str
    risk_level: str
    action: str | None
    forbidden_claim: str | None
    source_ids: list[str]
    test_data_mode: bool = True
    production_usable: bool = False


class SafetyRuleListResponse(AdminPage):
    items: list[SafetyRuleItem]


class SourceItem(BaseModel):
    source_id: str
    source_type: str
    file_name: str | None
    file_sha256: str | None
    relative_path: str | None
    product_id: str | None
    sku_id: str | None
    test_data_mode: bool = True
    production_usable: bool = False


class SourceListResponse(AdminPage):
    items: list[SourceItem]


class ConflictItem(BaseModel):
    issue_id: str
    entity_type: str
    entity_id: str
    field_name: str
    value_a: str | None
    value_b: str | None
    source_ids: list[str]
    status: str
    decision: str | None
    test_data_mode: bool = True
    production_usable: bool = False


class ConflictListResponse(AdminPage):
    items: list[ConflictItem]


class AdminImportBatchItem(BaseModel):
    id: str
    import_type: str
    original_filename: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    test_data_mode: bool


class AdminImportBatchListResponse(AdminPage):
    items: list[AdminImportBatchItem]


class SuggestionStatusCounts(BaseModel):
    submitted: int
    reviewing: int
    planned: int
    done: int
    rejected: int


class OverviewCounts(BaseModel):
    stores: int
    products: int
    skus: int
    faqs: int
    safety_rules: int
    sources: int
    conflicts: int
    import_batches: int
    suggestions: SuggestionStatusCounts


class AdminOverviewResponse(BaseModel):
    counts: OverviewCounts
    recent_imported_at: datetime | None
    test_data_mode: bool
    production_usable: bool
