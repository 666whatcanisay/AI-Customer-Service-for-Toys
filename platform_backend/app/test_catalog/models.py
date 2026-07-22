"""Persistence models for the isolated V0.3.1 test-data tenant."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TestKnowledgePackage(Base):
    __tablename__ = "test_knowledge_packages"

    package_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    package_name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[str] = mapped_column(String(32))
    tenant_id: Mapped[str] = mapped_column(String(96), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    store_code: Mapped[str] = mapped_column(String(96), index=True)
    response_mode: Mapped[str] = mapped_column(String(32))
    test_data_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    production_usable: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_auto_send: Mapped[bool] = mapped_column(Boolean, default=False)
    import_status: Mapped[str] = mapped_column(String(40))
    original_filename: Mapped[str] = mapped_column(String(255))
    zip_sha256: Mapped[str] = mapped_column(String(64), index=True)
    counts_json: Mapped[str] = mapped_column(Text)
    imported_by: Mapped[str] = mapped_column(String(128))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TestStore(Base):
    __tablename__ = "test_catalog_stores"
    __table_args__ = (
        UniqueConstraint("package_id", "store_code", name="uq_test_store_package_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[str] = mapped_column(
        ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(96), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    store_code: Mapped[str] = mapped_column(String(96), index=True)
    store_name: Mapped[str] = mapped_column(String(255))
    trial_enabled: Mapped[bool] = mapped_column(Boolean)
    knowledge_scope: Mapped[str] = mapped_column(String(64))
    response_mode: Mapped[str] = mapped_column(String(32))
    allow_auto_send: Mapped[bool] = mapped_column(Boolean)
    test_data_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    production_usable: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_data_json: Mapped[str] = mapped_column(Text)


class TestProduct(Base):
    __tablename__ = "test_catalog_products"

    product_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(96), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    store_code: Mapped[str] = mapped_column(String(96), index=True)
    product_name_official: Mapped[str] = mapped_column(String(255))
    product_name_display: Mapped[str] = mapped_column(String(255))
    sales_status: Mapped[str] = mapped_column(String(32))
    age_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    safety_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(40))
    publishable: Mapped[bool] = mapped_column(Boolean)
    source_ids_json: Mapped[str] = mapped_column(Text)
    raw_data_json: Mapped[str] = mapped_column(Text)


class TestSku(Base):
    __tablename__ = "test_catalog_skus"

    sku_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("test_catalog_products.product_id", ondelete="CASCADE"), index=True
    )
    sku_code: Mapped[str] = mapped_column(String(128))
    sku_name_official: Mapped[str] = mapped_column(String(255))
    sku_name_display: Mapped[str] = mapped_column(String(255))
    relation_type: Mapped[str] = mapped_column(String(32))
    canonical_sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reference_sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    component_sku_refs_json: Mapped[str] = mapped_column(Text)
    publishable: Mapped[bool] = mapped_column(Boolean)
    source_ids_json: Mapped[str] = mapped_column(Text)
    raw_data_json: Mapped[str] = mapped_column(Text)


class TestSourceEvidence(Base):
    __tablename__ = "test_source_evidence"

    source_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relative_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text)


class TestFaq(Base):
    __tablename__ = "test_faqs"

    faq_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(96), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    store_code: Mapped[str] = mapped_column(String(96), index=True)
    product_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    canonical_question: Mapped[str] = mapped_column(Text)
    recommended_reply: Mapped[str] = mapped_column(Text)
    answer_action: Mapped[str] = mapped_column(String(32))
    risk_level: Mapped[str] = mapped_column(String(16))
    source_ids_json: Mapped[str] = mapped_column(Text)
    raw_data_json: Mapped[str] = mapped_column(Text)


class TestSafetyRule(Base):
    __tablename__ = "test_safety_rules"

    rule_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String(96), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    store_code: Mapped[str] = mapped_column(String(96), index=True)
    scenario: Mapped[str] = mapped_column(String(255))
    rule_type: Mapped[str] = mapped_column(String(64))
    risk_level: Mapped[str] = mapped_column(String(16))
    source_ids_json: Mapped[str] = mapped_column(Text)
    raw_data_json: Mapped[str] = mapped_column(Text)


class TestEvaluationCase(Base):
    __tablename__ = "test_evaluation_cases"

    case_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(32))
    store_code: Mapped[str] = mapped_column(String(96), index=True)
    product_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_data_json: Mapped[str] = mapped_column(Text)


class TestConflictRecord(Base):
    __tablename__ = "test_conflict_records"

    issue_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        ForeignKey("test_knowledge_packages.package_id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(255))
    field_name: Mapped[str] = mapped_column(String(128))
    decision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(64))
    raw_data_json: Mapped[str] = mapped_column(Text)
