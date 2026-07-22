from datetime import datetime

from app.ingestion.hashing import stable_row_hash
from app.ingestion.normalizers.product_sku import normalize_product_sku
from app.ingestion.schemas import ErrorCode
from app.ingestion.validators.product_sku import validate_product_sku
from conftest import valid_row


def issue_codes(row: dict[str, object]) -> set[ErrorCode]:
    normalized = normalize_product_sku(row)
    return {
        issue.error_code
        for issue in validate_product_sku(
            normalized, row_number=3, formula_fields=[]
        )
    }


def test_normalization_is_deterministic_and_does_not_invent_values() -> None:
    row = valid_row()
    row.update(
        platform=" OFFLINE ",
        product_name="  虚构   商品  ",
        applicable_age_min="06",
        effective_from=datetime(2026, 7, 1, 8, 30),
        specifications='{ "pieces": 120, "color": "blue" }',
        material="   ",
    )

    normalized = normalize_product_sku(row)

    assert normalized["platform"] == "offline"
    assert normalized["product_name"] == "虚构 商品"
    assert normalized["applicable_age_min"] == 6
    assert normalized["effective_from"] == "2026-07-01"
    assert normalized["specifications"] == '{"color":"blue","pieces":120}'
    assert normalized["material"] is None
    assert normalized["platform_product_id"] is None


def test_stable_hash_ignores_dictionary_insertion_order() -> None:
    normalized = normalize_product_sku(valid_row())
    reversed_items = dict(reversed(list(normalized.items())))

    assert stable_row_hash(normalized) == stable_row_hash(reversed_items)


def test_required_fields_and_both_identifier_pairs_are_enforced() -> None:
    row = valid_row()
    row.update(
        product_name=None,
        sku_name=None,
        product_code=None,
        platform_product_id=None,
        sku_code=None,
        platform_sku_id=None,
    )

    codes = issue_codes(row)

    assert ErrorCode.REQUIRED_FIELD_MISSING in codes
    assert ErrorCode.PRODUCT_IDENTIFIER_MISSING in codes
    assert ErrorCode.SKU_IDENTIFIER_MISSING in codes


def test_platform_integer_age_and_date_rules_have_stable_codes() -> None:
    row = valid_row()
    row.update(
        platform="unknown",
        applicable_age_min="six",
        applicable_age_max=-1,
        effective_from="07/01/2026",
    )

    codes = issue_codes(row)

    assert ErrorCode.INVALID_PLATFORM in codes
    assert ErrorCode.INVALID_INTEGER in codes
    assert ErrorCode.INVALID_DATE in codes


def test_age_and_effective_ranges_are_validated() -> None:
    row = valid_row()
    row.update(
        applicable_age_min=12,
        applicable_age_max=6,
        effective_from="2027-01-01",
        effective_to="2026-12-31",
    )

    codes = issue_codes(row)

    assert ErrorCode.AGE_RANGE_INVALID in codes
    assert ErrorCode.EFFECTIVE_RANGE_INVALID in codes


def test_length_and_formula_checks_reject_untrusted_values() -> None:
    row = normalize_product_sku(valid_row())
    row["notes"] = "X" * 2001

    issues = validate_product_sku(row, row_number=8, formula_fields=["product_name"])

    assert {issue.error_code for issue in issues} == {
        ErrorCode.INVALID_TEMPLATE,
        ErrorCode.FORMULA_NOT_ALLOWED,
    }
    assert all(issue.row_number == 8 and issue.suggestion for issue in issues)
