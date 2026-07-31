from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


CHECKER_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "database-health-check"
    / "database_health_check.py"
)
SPEC = importlib.util.spec_from_file_location("database_health_check", CHECKER_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


SCHEMA = """
CREATE TABLE alembic_version(version_num TEXT NOT NULL);
INSERT INTO alembic_version VALUES ('0012_internal_production_finalization_v1');
CREATE TABLE test_catalog_stores(
  id INTEGER PRIMARY KEY, package_id TEXT, store_code TEXT,
  customer_service_status TEXT
);
CREATE TABLE test_catalog_products(
  product_id TEXT PRIMARY KEY, package_id TEXT, store_code TEXT,
  review_status TEXT, customer_service_status TEXT
);
CREATE TABLE test_catalog_skus(sku_id TEXT PRIMARY KEY, product_id TEXT);
CREATE TABLE test_faqs(faq_id TEXT PRIMARY KEY, product_id TEXT, sku_id TEXT);
CREATE TABLE knowledge_materials(id INTEGER PRIMARY KEY, product_id TEXT, sku_id TEXT);
CREATE TABLE catalog_activation_receipts(
  activation_receipt_id TEXT PRIMARY KEY, entity_type TEXT, entity_ref TEXT,
  customer_service_status TEXT, confirmed_at TEXT
);
CREATE TABLE product_knowledge_publications(
  product_id TEXT PRIMARY KEY, status TEXT, current_fingerprint TEXT,
  indexed_fingerprint TEXT, active_collection TEXT, chunk_count INTEGER,
  embedding_count INTEGER, publication_receipt_id TEXT
);
CREATE TABLE product_knowledge_publication_receipts(
  publication_receipt_id TEXT PRIMARY KEY, product_id TEXT, status TEXT,
  chunk_count INTEGER, embedding_count INTEGER, active_collection TEXT
);
"""


def build_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        connection.executescript(
            """
            INSERT INTO test_catalog_stores VALUES (1,'pkg','store','ENABLED');
            INSERT INTO test_catalog_products VALUES ('p1','pkg','store','APPROVED','ENABLED');
            INSERT INTO test_catalog_skus VALUES ('s1','p1');
            INSERT INTO test_faqs VALUES ('f1','p1','s1');
            INSERT INTO knowledge_materials VALUES (1,'p1',NULL);
            INSERT INTO catalog_activation_receipts VALUES ('a1','STORE','1','ENABLED','2026-01-01');
            INSERT INTO catalog_activation_receipts VALUES ('a2','PRODUCT','p1','ENABLED','2026-01-01');
            INSERT INTO product_knowledge_publications
              VALUES ('p1','PUBLISHED','fp','fp','collection',1,1,'r1');
            INSERT INTO product_knowledge_publication_receipts
              VALUES ('r1','p1','PUBLISHED',1,1,'collection');
            """
        )


def test_clean_database_passes_without_writing(tmp_path: Path) -> None:
    database = tmp_path / "health.sqlite3"
    build_database(database)
    before = database.read_bytes()

    report = MODULE.inspect_database(database, "0012_internal_production_finalization_v1")

    assert report["mode"] == "READ_ONLY"
    assert report["summary"] == {"p0": 0, "p1": 0, "p2": 0}
    assert database.read_bytes() == before


def test_orphans_and_publication_mismatch_are_reported(tmp_path: Path) -> None:
    database = tmp_path / "broken.sqlite3"
    build_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO test_catalog_skus VALUES ('orphan','missing')")
        connection.execute("UPDATE product_knowledge_publications SET chunk_count=0 WHERE product_id='p1'")

    report = MODULE.inspect_database(database)
    findings = {item["code"]: item for item in report["findings"]}

    assert findings["SKU_ORPHAN_PRODUCT"]["count"] == 1
    assert findings["PUBLISHED_KNOWLEDGE_INCOMPLETE"]["count"] == 1
    assert report["summary"]["p1"] >= 2
