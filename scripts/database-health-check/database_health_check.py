"""Read-only SQLite health and AI-CS business-data consistency checks.

The checker deliberately opens SQLite with ``mode=ro`` and never attempts repair.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote


def _readonly_uri(database_path: Path) -> str:
    normalized = database_path.resolve().as_posix()
    return f"file:{quote(normalized, safe='/:')}?mode=ro"


def _scalar(connection: sqlite3.Connection, query: str) -> int:
    return int(connection.execute(query).fetchone()[0])


def _finding(code: str, severity: str, count: int, message: str) -> dict[str, object]:
    return {
        "code": code,
        "severity": severity,
        "status": "PASS" if count == 0 else ("WARN" if severity == "P2" else "FAIL"),
        "count": count,
        "message": message,
    }


def inspect_database(database_path: Path, expected_revision: str | None = None) -> dict[str, object]:
    if not database_path.is_file():
        raise FileNotFoundError(f"database does not exist: {database_path}")

    with sqlite3.connect(_readonly_uri(database_path), uri=True) as connection:
        connection.row_factory = sqlite3.Row
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        integrity_rows = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        foreign_key_rows = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]

        findings = [
            _finding(
                "DB_INTEGRITY",
                "P0",
                0 if integrity_rows == ["ok"] else len(integrity_rows),
                "SQLite integrity_check must return exactly 'ok'.",
            ),
            _finding(
                "DB_FOREIGN_KEYS",
                "P1",
                len(foreign_key_rows),
                "SQLite foreign_key_check must return no rows.",
            ),
            _finding(
                "PRODUCT_ORPHAN_STORE",
                "P1",
                _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM test_catalog_products p
                    LEFT JOIN test_catalog_stores s
                      ON s.package_id=p.package_id AND s.store_code=p.store_code
                    WHERE s.id IS NULL
                    """,
                ),
                "Every product must resolve to one store within the same package.",
            ),
            _finding(
                "SKU_ORPHAN_PRODUCT",
                "P1",
                _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM test_catalog_skus s
                    LEFT JOIN test_catalog_products p ON p.product_id=s.product_id
                    WHERE p.product_id IS NULL
                    """,
                ),
                "Every SKU must resolve to a product.",
            ),
            _finding(
                "FAQ_ORPHAN_PRODUCT",
                "P1",
                _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM test_faqs f
                    LEFT JOIN test_catalog_products p ON p.product_id=f.product_id
                    WHERE f.product_id IS NOT NULL AND p.product_id IS NULL
                    """,
                ),
                "Product-scoped FAQs must resolve to a product.",
            ),
            _finding(
                "FAQ_ORPHAN_SKU",
                "P1",
                _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM test_faqs f
                    LEFT JOIN test_catalog_skus s ON s.sku_id=f.sku_id
                    WHERE f.sku_id IS NOT NULL AND s.sku_id IS NULL
                    """,
                ),
                "SKU-scoped FAQs must resolve to a SKU.",
            ),
            _finding(
                "KNOWLEDGE_ORPHAN_PRODUCT",
                "P1",
                _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM knowledge_materials k
                    LEFT JOIN test_catalog_products p ON p.product_id=k.product_id
                    WHERE k.product_id IS NOT NULL AND p.product_id IS NULL
                    """,
                ),
                "Product-scoped knowledge materials must resolve to a product.",
            ),
            _finding(
                "KNOWLEDGE_ORPHAN_SKU",
                "P1",
                _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM knowledge_materials k
                    LEFT JOIN test_catalog_skus s ON s.sku_id=k.sku_id
                    WHERE k.sku_id IS NOT NULL AND s.sku_id IS NULL
                    """,
                ),
                "SKU-scoped knowledge materials must resolve to a SKU.",
            ),
            _finding(
                "STORE_CUSTOMER_STATUS_DOMAIN",
                "P1",
                _scalar(
                    connection,
                    "SELECT COUNT(*) FROM test_catalog_stores WHERE customer_service_status NOT IN ('ENABLED','DISABLED')",
                ),
                "Store customer-service status must use the frozen R006 domain.",
            ),
            _finding(
                "PRODUCT_CUSTOMER_STATUS_DOMAIN",
                "P1",
                _scalar(
                    connection,
                    "SELECT COUNT(*) FROM test_catalog_products WHERE customer_service_status NOT IN ('ENABLED','DISABLED')",
                ),
                "Product customer-service status must use the frozen R006 domain.",
            ),
            _finding(
                "ENABLED_PRODUCT_NOT_APPROVED",
                "P1",
                _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM test_catalog_products
                    WHERE customer_service_status='ENABLED'
                      AND review_status NOT IN ('APPROVED','TEST_CONFIRMED')
                    """,
                ),
                "Only approved or formally initialized products may enter the customer catalog.",
            ),
            _finding(
                "ACTIVATION_RECEIPT_ORPHAN",
                "P1",
                _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM catalog_activation_receipts r
                    LEFT JOIN test_catalog_products p
                      ON r.entity_type='PRODUCT' AND p.product_id=r.entity_ref
                    LEFT JOIN test_catalog_stores s
                      ON r.entity_type='STORE' AND CAST(s.id AS TEXT)=r.entity_ref
                    WHERE (r.entity_type='PRODUCT' AND p.product_id IS NULL)
                       OR (r.entity_type='STORE' AND s.id IS NULL)
                       OR r.entity_type NOT IN ('STORE','PRODUCT')
                    """,
                ),
                "Every activation receipt must reference a live Store or Product.",
            ),
            _finding(
                "ACTIVATION_LATEST_STATUS_MISMATCH",
                "P1",
                _scalar(
                    connection,
                    """
                    WITH ranked AS (
                      SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY entity_type, entity_ref
                        ORDER BY confirmed_at DESC, activation_receipt_id DESC
                      ) AS rn
                      FROM catalog_activation_receipts
                    )
                    SELECT COUNT(*) FROM ranked r
                    LEFT JOIN test_catalog_products p
                      ON r.entity_type='PRODUCT' AND p.product_id=r.entity_ref
                    LEFT JOIN test_catalog_stores s
                      ON r.entity_type='STORE' AND CAST(s.id AS TEXT)=r.entity_ref
                    WHERE r.rn=1 AND (
                      (r.entity_type='PRODUCT' AND p.customer_service_status<>r.customer_service_status)
                      OR (r.entity_type='STORE' AND s.customer_service_status<>r.customer_service_status)
                    )
                    """,
                ),
                "The latest activation receipt must match the entity's current status.",
            ),
            _finding(
                "PUBLICATION_STATUS_DOMAIN",
                "P1",
                _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM product_knowledge_publications
                    WHERE status NOT IN ('NOT_GENERATED','GENERATING','PUBLISHED','SYNC_FAILED','NEED_RESYNC')
                    """,
                ),
                "AI publication status must use the frozen R006.1 domain.",
            ),
            _finding(
                "PUBLISHED_KNOWLEDGE_INCOMPLETE",
                "P1",
                _scalar(
                    connection,
                    """
                    SELECT COUNT(*) FROM product_knowledge_publications p
                    LEFT JOIN product_knowledge_publication_receipts r
                      ON r.publication_receipt_id=p.publication_receipt_id
                    WHERE p.status='PUBLISHED' AND (
                      p.chunk_count<=0 OR p.embedding_count<=0
                      OR p.current_fingerprint IS NULL
                      OR p.current_fingerprint<>p.indexed_fingerprint
                      OR r.publication_receipt_id IS NULL
                      OR r.status<>'PUBLISHED'
                      OR r.product_id<>p.product_id
                      OR r.chunk_count<>p.chunk_count
                      OR r.embedding_count<>p.embedding_count
                      OR r.active_collection<>p.active_collection
                    )
                    """,
                ),
                "Published knowledge needs matching fingerprints, positive chunks/embeddings and a receipt.",
            ),
        ]

        if expected_revision is not None:
            findings.append(
                _finding(
                    "ALEMBIC_REVISION",
                    "P1",
                    0 if revision == expected_revision else 1,
                    f"Expected Alembic revision {expected_revision}; observed {revision}.",
                )
            )

        gated_enabled_products = _scalar(
            connection,
            """
            SELECT COUNT(*) FROM test_catalog_products p
            JOIN test_catalog_stores s
              ON s.package_id=p.package_id AND s.store_code=p.store_code
            WHERE p.customer_service_status='ENABLED'
              AND s.customer_service_status='DISABLED'
            """,
        )
        counts = {
            "business_tables": len(table_names - {"alembic_version"}),
            "stores": _scalar(connection, "SELECT COUNT(*) FROM test_catalog_stores"),
            "products": _scalar(connection, "SELECT COUNT(*) FROM test_catalog_products"),
            "skus": _scalar(connection, "SELECT COUNT(*) FROM test_catalog_skus"),
            "faqs": _scalar(connection, "SELECT COUNT(*) FROM test_faqs"),
            "knowledge_materials": _scalar(connection, "SELECT COUNT(*) FROM knowledge_materials"),
            "activation_receipts": _scalar(connection, "SELECT COUNT(*) FROM catalog_activation_receipts"),
            "publication_receipts": _scalar(
                connection, "SELECT COUNT(*) FROM product_knowledge_publication_receipts"
            ),
            "store_gated_enabled_products": gated_enabled_products,
        }

    return {
        "checker": "AI-CS Database Health Check V1",
        "mode": "READ_ONLY",
        "database": str(database_path.resolve()),
        "revision": revision,
        "counts": counts,
        "findings": findings,
        "summary": {
            "p0": sum(item["count"] for item in findings if item["severity"] == "P0"),
            "p1": sum(item["count"] for item in findings if item["severity"] == "P1"),
            "p2": sum(item["count"] for item in findings if item["severity"] == "P2"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="Path to the SQLite database")
    parser.add_argument("--expected-revision")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    try:
        report = inspect_database(args.database, args.expected_revision)
    except (FileNotFoundError, sqlite3.Error) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=None if args.compact else 2))
    return 0 if report["summary"]["p0"] == 0 and report["summary"]["p1"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
