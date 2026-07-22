from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

from app.models.chat import FrozenChatContext
from app.service.test_knowledge import EXPECTED_SCHEMA_VERSION, EXPECTED_VERSION


class EvaluationValidationError(ValueError):
    pass


STORE_LEVEL_EVALUATION_PRODUCT_ID = "__STORE_LEVEL_EVALUATION__"


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    question: str
    context: FrozenChatContext
    expected_action: str
    expected_source_ids: tuple[str, ...]
    expected_contains: tuple[str, ...]
    forbidden_contains: tuple[str, ...]
    expected_required_fields: tuple[str, ...]
    expected_risk_level: str
    store_scope: bool

    @property
    def expected_missing_fields(self) -> tuple[str, ...]:
        """Fields still absent before an answer, not fields already in context."""
        if self.expected_action not in {
            "ASK_CLARIFY",
            "REQUIRE_LOOKUP",
            "TRANSFER_HUMAN",
        }:
            return ()
        provided = {"tenant_id", "platform", "store_code"}
        if not self.store_scope:
            provided.add("product_id")
        if self.context.sku_id:
            provided.add("sku_id")
        return tuple(
            field for field in self.expected_required_fields if field not in provided
        )


_TEXT_REPLACEMENTS = {
    "人仔": "人偶",
    "人物": "人偶",
    "小孩": "儿童",
    "孩子": "儿童",
    "款式": "sku",
    "规格": "sku",
    "商品sku页面": "sku页",
    "当前sku页面": "sku页",
    "当前商品页": "sku页",
    "大彩盒包装": "大彩盒",
    "彩盒包装": "彩盒",
    "不可以": "不能",
    "无法": "不能",
    "对应颗粒数为": "为",
    "颗粒数为": "为",
}
_FACT_NOISE = (
    "测试基线",
    "测试口径",
    "测试年龄",
    "测试总数",
    "测试组合",
    "测试材质",
    "运营资料称",
    "运营称",
    "现有资料标注",
    "根据资料",
    "资料显示",
    "明确回答",
    "应引用",
    "来源为",
    "按sku区分",
)


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = text.replace("～", "~").replace("至", "~")
    for source, target in _TEXT_REPLACEMENTS.items():
        text = text.replace(source, target)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff~.+-]+", "", text)


def _material_tokens(value: str) -> set[str]:
    normalized = _normalize_text(value)
    return set(re.findall(r"[a-z]+[a-z0-9+-]*|\d+(?:\.\d+)?", normalized))


def _bigrams(value: str) -> set[str]:
    return {value[index : index + 2] for index in range(max(0, len(value) - 1))}


def _number_unit_pairs(value: str) -> list[tuple[str, str]]:
    normalized = _normalize_text(value)
    return re.findall(
        r"(\d+(?:\.\d+)?)(颗|个人偶|人偶|岁|cm|种|节aaa|节aa|元|天)",
        normalized,
    )


def _fact_matches(expected: str, answer: str) -> bool:
    normalized_expected = _normalize_text(expected)
    normalized_answer = _normalize_text(answer)
    if not normalized_expected:
        return True
    expected_is_negative = any(
        marker in normalized_expected
        for marker in ("不能", "不得", "禁止", "不是", "不含", "无", "未")
    )
    if not expected_is_negative:
        named_tokens = re.findall(r"[a-z]{3,}", normalized_expected)
        for token in named_tokens:
            positions = [
                match.start()
                for match in re.finditer(re.escape(token), normalized_answer)
            ]
            if positions and all(
                any(
                    marker in normalized_answer[max(0, position - 24) : position]
                    for marker in (
                        "未提及",
                        "不能回答",
                        "不能提供",
                        "并非",
                        "不是",
                        "不属于",
                        "未知",
                        "不包含",
                        "不含",
                    )
                )
                for position in positions
            ):
                return False
    if normalized_expected in normalized_answer:
        return True
    expected_tokens = _material_tokens(expected)
    if any(token not in normalized_answer for token in expected_tokens):
        return False
    for number, unit in _number_unit_pairs(expected):
        if not re.search(
            rf"{re.escape(number)}.{{0,3}}{re.escape(unit)}",
            normalized_answer,
        ):
            return False
    reduced = normalized_expected
    for noise in _FACT_NOISE:
        reduced = reduced.replace(_normalize_text(noise), "")
    if reduced and reduced in normalized_answer:
        return True
    grams = _bigrams(reduced or normalized_expected)
    if not grams:
        return False
    coverage = len(grams & _bigrams(normalized_answer)) / len(grams)
    return coverage >= 0.48


def _forbidden_claim_present(rule: str, answer: str) -> bool:
    normalized_answer = _normalize_text(answer)
    core = re.sub(
        r"^(不得|禁止)",
        "",
        _normalize_text(rule),
    )
    if not core:
        return False
    position = normalized_answer.find(core)
    if position < 0:
        return False
    prefix = normalized_answer[max(0, position - 10) : position]
    return not any(
        marker in prefix
        for marker in ("不", "不能", "不得", "禁止", "未", "不会", "不能", "需核实")
    )


def parse_evaluations(
    payload: dict[str, Any], expected_package_id: str
) -> list[EvaluationCase]:
    raw = payload
    if raw.get("package_id") != expected_package_id:
        raise EvaluationValidationError("evaluation package_id mismatch")
    if raw.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise EvaluationValidationError(
            f"evaluation schema_version must be {EXPECTED_SCHEMA_VERSION}"
        )
    if raw.get("version") != EXPECTED_VERSION:
        raise EvaluationValidationError(
            f"evaluation version must be {EXPECTED_VERSION}"
        )
    if raw.get("test_data_mode") is not True:
        raise EvaluationValidationError("evaluation test_data_mode must be true")
    if raw.get("production_usable") is not False:
        raise EvaluationValidationError("production_usable must be false")
    if raw.get("response_mode") != "SUGGESTION_ONLY":
        raise EvaluationValidationError("response_mode must be SUGGESTION_ONLY")
    if raw.get("allow_auto_send") is not False:
        raise EvaluationValidationError("allow_auto_send must be false")
    if raw.get("tenant_id") != "TENANT-PDD-SM-TEST":
        raise EvaluationValidationError("tenant_id mismatch")
    if raw.get("platform") != "pdd" or raw.get("store_code") != "PDD-SM":
        raise EvaluationValidationError("platform/store_code mismatch")
    cases = raw.get("items")
    if not isinstance(cases, list) or len(cases) != 28:
        raise EvaluationValidationError("evaluations must contain exactly 28 cases")
    if raw.get("total") != 28:
        raise EvaluationValidationError("evaluation total must be 28")

    parsed: list[EvaluationCase] = []
    seen: set[str] = set()
    for raw_case in cases:
        if not isinstance(raw_case, dict):
            raise EvaluationValidationError("evaluation case must be an object")
        case_id = str(raw_case.get("case_id") or "").strip()
        if not case_id or case_id in seen:
            raise EvaluationValidationError("case_id must be unique and non-empty")
        seen.add(case_id)
        for list_field in (
            "expected_key_facts",
            "forbidden_claims",
            "expected_source_ids",
            "expected_required_fields",
        ):
            if not isinstance(raw_case.get(list_field), list):
                raise EvaluationValidationError(f"{list_field} must be an array")
            if any(not isinstance(value, str) for value in raw_case[list_field]):
                raise EvaluationValidationError(
                    f"{list_field} must contain only strings"
                )
        if raw_case.get("expected_response_mode") != "SUGGESTION_ONLY":
            raise EvaluationValidationError(
                "case expected_response_mode must be SUGGESTION_ONLY"
            )
        if raw_case.get("allow_auto_send_expected") is not False:
            raise EvaluationValidationError(
                "case allow_auto_send_expected must be false"
            )
        parsed.append(
            EvaluationCase(
                case_id=case_id,
                question=str(raw_case.get("customer_question") or "").strip(),
                context=FrozenChatContext.model_validate(
                    {
                        "tenant_id": raw["tenant_id"],
                        "platform": raw_case.get("platform"),
                        "store_code": raw_case.get("store_code"),
                        "product_id": (
                            raw_case.get("product_id")
                            or STORE_LEVEL_EVALUATION_PRODUCT_ID
                        ),
                        "sku_id": raw_case.get("sku_id") or None,
                    }
                ),
                expected_action=str(raw_case.get("expected_action") or "").strip(),
                expected_source_ids=tuple(raw_case.get("expected_source_ids") or []),
                expected_contains=tuple(raw_case.get("expected_key_facts") or []),
                forbidden_contains=tuple(raw_case.get("forbidden_claims") or []),
                expected_required_fields=tuple(
                    raw_case.get("expected_required_fields") or []
                ),
                expected_risk_level=str(raw_case.get("risk_level") or ""),
                store_scope=not bool(raw_case.get("product_id")),
            )
        )
        if not parsed[-1].question or not parsed[-1].expected_action:
            raise EvaluationValidationError(
                "question and expected_action are required"
            )
    return parsed


def run_evaluations(
    cases: list[EvaluationCase],
    query: Callable[[str, FrozenChatContext], dict[str, Any]],
    available_source_ids: set[str] | None = None,
    source_catalog: dict[str, list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for case in cases:
        result = query(case.question, case.context)
        sources = result.get("sources") or []
        source_ids = {
            source_id
            for source in sources
            for source_id in (source.get("source_ids") or [])
        }
        failures: list[str] = []
        def source_scope_compatible(source: dict[str, Any]) -> bool:
            if case.store_scope:
                return not source.get("product_id") and not source.get("sku_id")
            if source.get("product_id") != case.context.product_id:
                return False
            return (
                not case.context.sku_id
                or source.get("sku_id") in ("", case.context.sku_id)
            )

        compatible_source_ids = {
            source_id
            for source in sources
            if source_scope_compatible(source)
            for source_id in (source.get("source_ids") or [])
        }
        checks = {
            "action": result.get("action") == case.expected_action,
            "source_ids": (
                not case.expected_source_ids
                or set(case.expected_source_ids) <= compatible_source_ids
            ),
        }
        diagnostic_categories: set[str] = set()
        if not checks["action"]:
            failures.append("structured_decision_error")
            diagnostic_categories.add("structured_decision_error")
        missing_source_ids = (
            set(case.expected_source_ids) - compatible_source_ids
        )
        if not checks["source_ids"]:
            catalog_gap = False
            if source_catalog is not None:
                for source_id in missing_source_ids:
                    entries = source_catalog.get(source_id, [])
                    compatible = any(
                        (
                            case.store_scope
                            and not entry.get("product_id")
                        )
                        or (
                            not case.store_scope
                            and entry.get("product_id") == case.context.product_id
                            and (
                                not case.context.sku_id
                                or entry.get("sku_id") in ("", case.context.sku_id)
                            )
                        )
                        for entry in entries
                    )
                    if not compatible:
                        catalog_gap = True
                        break
            if catalog_gap or (
                available_source_ids is not None
                and not missing_source_ids <= available_source_ids
            ):
                failures.append("metadata_loss")
                diagnostic_categories.add("metadata_loss")
            else:
                failures.append("retrieval_miss")
                diagnostic_categories.add("retrieval_miss")
        answer = str(result.get("answer") or "")
        checks["key_facts"] = all(
            _fact_matches(value, answer) for value in case.expected_contains
        )
        legacy_key_facts = all(
            _normalize_text(value) in _normalize_text(answer)
            for value in case.expected_contains
        )
        if checks["key_facts"] and not legacy_key_facts:
            diagnostic_categories.add("evaluator_semantic_error_corrected")
        checks["forbidden_claims"] = all(
            not _forbidden_claim_present(value, answer)
            for value in case.forbidden_contains
        )
        expected_missing_fields = case.expected_missing_fields
        actual_required_fields = tuple(result.get("required_fields") or [])
        checks["required_fields"] = (
            actual_required_fields == expected_missing_fields
        )
        checks["risk_level"] = (
            result.get("risk_level") == case.expected_risk_level
        )
        if not checks["key_facts"]:
            evidence_text = " ".join(
                str(source.get("excerpt") or "") for source in sources
            )
            evidence_has_expected_facts = all(
                _fact_matches(value, evidence_text)
                for value in case.expected_contains
            )
            if (
                "metadata_loss" in diagnostic_categories
                or (sources and not evidence_has_expected_facts)
            ):
                failures.append("metadata_loss")
                diagnostic_categories.add("metadata_loss")
            elif not sources:
                failures.append("retrieval_miss")
                diagnostic_categories.add("retrieval_miss")
            else:
                failures.append("model_expression_error")
                diagnostic_categories.add("model_expression_error")
        if not checks["forbidden_claims"]:
            failures.append("structured_decision_error")
            diagnostic_categories.add("structured_decision_error")
        if not checks["required_fields"]:
            failures.append("structured_decision_error")
            diagnostic_categories.add("structured_decision_error")
        if not checks["risk_level"]:
            failures.append("structured_decision_error")
            diagnostic_categories.add("structured_decision_error")
        checks["scope"] = not any(
            (
                case.store_scope
                and (bool(source.get("product_id")) or bool(source.get("sku_id")))
            )
            or (
                not case.store_scope
                and source.get("product_id") not in ("", case.context.product_id)
            )
            or (
                not case.store_scope
                and bool(case.context.sku_id)
                and bool(source.get("sku_id"))
                and source.get("sku_id") != case.context.sku_id
            )
            for source in sources
        )
        if not checks["scope"]:
            failures.append("retrieval_miss")
            diagnostic_categories.add("retrieval_miss")

        failure_reason = "; ".join(
            [
                f"{name} mismatch"
                for name, passed in checks.items()
                if not passed
            ]
        ) or "none"

        records.append(
            {
                "case_id": case.case_id,
                "question": case.question,
                "context": case.context.model_dump(),
                "scope_mode": "store" if case.store_scope else "product",
                "top_k": sources,
                "answer": answer,
                "actual_answer": answer,
                "action": result.get("action"),
                "expected_action": case.expected_action,
                "actual_action": result.get("action"),
                "risk": result.get("risk_level"),
                "expected_risk": case.expected_risk_level,
                "actual_risk": result.get("risk_level"),
                "declared_expected_required_fields": list(
                    case.expected_required_fields
                ),
                "expected_required_fields": list(expected_missing_fields),
                "actual_required_fields": list(actual_required_fields),
                "expected_source_ids": list(case.expected_source_ids),
                "retrieved_source_ids": sorted(source_ids),
                "returned_source_ids": sorted(source_ids),
                "missing_source_ids": sorted(missing_source_ids),
                "expected_key_facts": list(case.expected_contains),
                "latency_ms": result.get("latency_ms"),
                "passed": not failures,
                "failure_classes": sorted(set(failures)),
                "diagnostic_categories": sorted(diagnostic_categories),
                "failure_reason": failure_reason,
                "checks": checks,
            }
        )
    passed = sum(1 for record in records if record["passed"])
    return {
        "total": len(records),
        "passed": passed,
        "failed": len(records) - passed,
        "pass_rate": round(passed / len(records), 4) if records else 0,
        "check_pass_counts": {
            name: sum(record["checks"][name] for record in records)
            for name in (
                "action",
                "source_ids",
                "key_facts",
                "forbidden_claims",
                "required_fields",
                "risk_level",
                "scope",
            )
        },
        "records": records,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# A-T03 RAG evaluation report",
        "",
        f"- Total: {report['total']}",
        f"- Passed: {report['passed']}",
        f"- Failed: {report['failed']}",
        f"- Pass rate: {report['pass_rate']:.2%}",
        f"- Evidence mode: {report.get('evidence_mode', 'unknown')}",
        f"- Production usable: {str(report.get('production_usable', False)).lower()}",
        "",
        "## Check pass counts",
        "",
        *[
            f"- {name}: {count}/{report['total']}"
            for name, count in report.get("check_pass_counts", {}).items()
        ],
        "",
        "| Case | Scope | Expected / actual action | Expected / actual risk | Required expected / actual | Source expected / returned | Key facts | Actual answer | Failure reason |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    def cell(value: Any, limit: int = 180) -> str:
        rendered = str(value).replace("|", "\\|").replace("\n", " ")
        return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"

    for record in report["records"]:
        lines.append(
            "| {case_id} | {scope} | {action} | {risk} | {required} | {sources} | {facts} | {answer} | {failure} |".format(
                case_id=record["case_id"],
                scope=record.get("scope_mode") or "",
                action=cell(
                    f"{record.get('expected_action')} / {record.get('actual_action')}"
                ),
                risk=cell(
                    f"{record.get('expected_risk')} / {record.get('actual_risk')}"
                ),
                required=cell(
                    f"{record.get('expected_required_fields')} / {record.get('actual_required_fields')}"
                ),
                sources=cell(
                    f"{record.get('expected_source_ids')} / {record.get('returned_source_ids')}"
                ),
                facts=cell(record.get("expected_key_facts")),
                answer=cell(record.get("actual_answer")),
                failure=cell(record.get("failure_reason")),
            )
        )
    return "\n".join(lines) + "\n"


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"
