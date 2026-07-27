"""C-internal multi-store pilot setup and aggregate visibility checks."""

from datetime import datetime, timezone
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.test_catalog.models import (
    TestFaq as CatalogFaq,
    TestKnowledgePackage as CatalogKnowledgePackage,
    TestSafetyRule as CatalogSafetyRule,
)
from conftest import valid_row, workbook_bytes


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PILOT_STORE_URL = "/api/v1/admin/pilot-stores"
IMPORT_URL = "/api/v1/import-batches/product-sku"
PREFLIGHT_URL = f"{IMPORT_URL}/preflight"
STORE_CODE = "PILOT-ONE"


def _create_store(client: TestClient) -> dict[str, object]:
    response = client.post(
        PILOT_STORE_URL,
        json={"store_code": STORE_CODE, "store_name": "Pilot One", "platform": "pdd"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _workbook(store_code: str) -> bytes:
    row = valid_row()
    row["store_code"] = store_code
    return workbook_bytes([row])


def _seed_store_knowledge(session: Session) -> None:
    now = datetime.now(timezone.utc)
    session.add(
        CatalogKnowledgePackage(
            package_id="PILOT-PACKAGE",
            package_name="Synthetic pilot package",
            version="V0.3.1",
            schema_version="0.3.1-test",
            tenant_id="TEST-TENANT",
            platform="pdd",
            store_code=STORE_CODE,
            response_mode="SUGGESTION_ONLY",
            test_data_mode=True,
            production_usable=False,
            allow_auto_send=False,
            import_status="IMPORTED_TEST_ONLY",
            original_filename="pilot-governance.zip",
            zip_sha256="a" * 64,
            counts_json="{}",
            imported_by="pytest",
            imported_at=now,
        )
    )
    session.add_all(
        [
            CatalogFaq(
                faq_id="PILOT-FAQ",
                package_id="PILOT-PACKAGE",
                tenant_id="TEST-TENANT",
                platform="pdd",
                store_code=STORE_CODE,
                product_id=None,
                sku_id=None,
                canonical_question="Synthetic FAQ",
                recommended_reply="Synthetic controlled reply",
                answer_action="CONTROLLED_ANSWER",
                risk_level="LOW",
                source_ids_json="[]",
                raw_data_json="{}",
            ),
            CatalogSafetyRule(
                rule_id="PILOT-RULE",
                package_id="PILOT-PACKAGE",
                tenant_id="TEST-TENANT",
                platform="pdd",
                store_code=STORE_CODE,
                scenario="Synthetic scenario",
                rule_type="SAFETY",
                risk_level="LOW",
                source_ids_json="[]",
                raw_data_json="{}",
            ),
        ]
    )
    session.commit()


def test_pilot_store_requires_real_setup_data_and_returns_aggregates_only(
    client: TestClient, session: Session
) -> None:
    created = _create_store(client)

    assert created["setup_status"] == "NEEDS_PRODUCT_IMPORT"
    assert created["test_data_mode"] is True
    assert created["production_usable"] is False
    duplicate = client.post(
        PILOT_STORE_URL,
        json={"store_code": STORE_CODE, "store_name": "Duplicate", "platform": "pdd"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "PILOT_STORE_ALREADY_EXISTS"

    missing_target = client.post(
        IMPORT_URL,
        files={"file": ("pilot.xlsx", _workbook(STORE_CODE), XLSX_MIME)},
        data={"target_store_code": "MISSING-STORE"},
    )
    assert missing_target.status_code == 404
    assert missing_target.json()["error"]["code"] == "PILOT_STORE_NOT_FOUND"

    mismatch = client.post(
        PREFLIGHT_URL,
        files={"file": ("mismatch.xlsx", _workbook("OTHER-STORE"), XLSX_MIME)},
        data={"target_store_code": STORE_CODE},
    )
    assert mismatch.status_code == 200, mismatch.text
    assert mismatch.json()["can_import"] is False
    assert {item["code"] for item in mismatch.json()["error_summary"]} == {"STORE_CODE_MISMATCH"}

    imported = client.post(
        IMPORT_URL,
        files={"file": ("pilot.xlsx", _workbook(STORE_CODE), XLSX_MIME)},
        data={"created_by": "pilot-admin", "target_store_code": STORE_CODE},
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["target_store_code"] == STORE_CODE
    assert imported.json()["status"] == "READY_FOR_REVIEW"

    after_import = client.get(PILOT_STORE_URL).json()["items"][0]
    assert after_import["setup_status"] == "NEEDS_KNOWLEDGE"
    assert after_import["staged_product_count"] == 1
    assert after_import["staged_sku_count"] == 1
    assert after_import["latest_product_imported_at"] is not None

    _seed_store_knowledge(session)
    case = client.post(
        "/api/v1/customer-experience-cases",
        json={
            "store_code": STORE_CODE,
            "product_id": None,
            "sku_id": None,
            "question": "Synthetic customer question",
            "ai_answer": "Synthetic AI response",
            "final_answer": "Synthetic support response",
            "feedback_type": "EDITED_ADOPTED",
            "created_by": "agent-pilot",
        },
    )
    assert case.status_code == 201, case.text
    feedback = client.post(
        "/api/v1/ai-response-feedback",
        headers={"Idempotency-Key": "pilot-feedback-1"},
        json={
            "store_code": STORE_CODE,
            "product_id": None,
            "sku_id": None,
            "question": "Synthetic customer question",
            "ai_answer": "Synthetic AI response",
            "final_answer": "Synthetic support response",
            "feedback_type": "MISSING_INFO",
            "created_by": "agent-pilot",
            "context": {"store_code": STORE_CODE, "product_id": None, "sku_id": None},
        },
    )
    assert feedback.status_code == 201, feedback.text

    listing = client.get(PILOT_STORE_URL)
    assert listing.status_code == 200, listing.text
    item = listing.json()["items"][0]
    assert item["setup_status"] == "OBSERVABLE"
    assert item["faq_count"] == 1
    assert item["safety_rule_count"] == 1
    assert item["experience_case_count"] == 1
    assert item["ai_feedback_count"] == 1
    aggregate_payload = json.dumps(item)
    assert "Synthetic customer question" not in aggregate_payload
    assert "agent-pilot" not in aggregate_payload
