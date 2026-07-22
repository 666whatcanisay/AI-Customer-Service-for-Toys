from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from app.models.chat import FrozenChatContext


class EvaluationValidationError(ValueError):
    pass


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


def parse_evaluations(
    payload: dict[str, Any], expected_package_id: str
) -> list[EvaluationCase]:
    raw = payload
    if raw.get("package_id") != expected_package_id:
        raise EvaluationValidationError("evaluation package_id mismatch")
    if raw.get("schema_version") != "V0.3.1":
        raise EvaluationValidationError("evaluation schema_version must be V0.3.1")
    if raw.get("version") != "V0.3.1":
        raise EvaluationValidationError("evaluation version must be V0.3.1")
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
                        "product_id": raw_case.get("product_id"),
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
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    normalize = lambda value: "".join(str(value).split()).lower()
    for case in cases:
        result = query(case.question, case.context)
        sources = result.get("sources") or []
        source_ids = {
            source_id
            for source in sources
            for source_id in (source.get("source_ids") or [])
        }
        failures: list[str] = []
        if result.get("action") != case.expected_action:
            failures.append("rule")
        if case.expected_source_ids and not set(case.expected_source_ids) <= source_ids:
            failures.append("retrieval")
        answer = str(result.get("answer") or "")
        normalized_answer = normalize(answer)
        if any(normalize(value) not in normalized_answer for value in case.expected_contains):
            failures.append("model")
        if any(normalize(value) in normalized_answer for value in case.forbidden_contains):
            failures.append("rule")
        if tuple(result.get("required_fields") or []) != case.expected_required_fields:
            failures.append("rule")
        if result.get("risk_level") != case.expected_risk_level:
            failures.append("rule")
        if any(
            source.get("product_id") != case.context.product_id
            or (
                source.get("sku_id")
                and source.get("sku_id") != case.context.sku_id
            )
            for source in sources
        ):
            failures.append("retrieval")

        records.append(
            {
                "case_id": case.case_id,
                "question": case.question,
                "context": case.context.model_dump(),
                "top_k": sources,
                "answer": answer,
                "action": result.get("action"),
                "risk": result.get("risk_level"),
                "latency_ms": result.get("latency_ms"),
                "passed": not failures,
                "failure_classes": sorted(set(failures)),
            }
        )
    passed = sum(1 for record in records if record["passed"])
    return {
        "total": len(records),
        "passed": passed,
        "failed": len(records) - passed,
        "pass_rate": round(passed / len(records), 4) if records else 0,
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
        "| Case | Action | Risk | Passed | Failure classes | Latency ms |",
        "|---|---|---|---:|---|---:|",
    ]
    for record in report["records"]:
        lines.append(
            "| {case_id} | {action} | {risk} | {passed} | {failures} | {latency} |".format(
                case_id=record["case_id"],
                action=record.get("action") or "",
                risk=record.get("risk") or "",
                passed="yes" if record["passed"] else "no",
                failures=", ".join(record["failure_classes"]),
                latency=record.get("latency_ms") or 0,
            )
        )
    return "\n".join(lines) + "\n"


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"
