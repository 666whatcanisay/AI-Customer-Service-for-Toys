"""Evidence-only diagnosis for the newest saved live RAG evaluation.

This service is deliberately deterministic: it classifies the evaluator's
recorded failure signals and never asks a model to reinterpret them.  That
keeps a quality investigation from becoming an untraceable prompt change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.quality_baseline import (
    CauseFinding,
    FailedCaseDiagnosis,
    QualityBaselineSnapshot,
    QualityBaselineSummary,
    QualityCheckSummary,
    QualityRecommendation,
)


CHECK_ORDER = (
    "action",
    "source_ids",
    "key_facts",
    "forbidden_claims",
    "required_fields",
    "risk_level",
    "scope",
)
FAILURE_CLASS_ORDER = (
    "metadata_loss",
    "retrieval_miss",
    "model_expression_error",
    "structured_decision_error",
)
CAUSE_ORDER = (
    "DATA_PROBLEM",
    "KNOWLEDGE_PROBLEM",
    "RETRIEVAL_PROBLEM",
    "PROMPT_OR_MODEL_PROBLEM",
    "RULE_DECISION_PROBLEM",
)


def _as_non_negative_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _latest_live_evaluation(evaluations_root: Path) -> tuple[Path, dict[str, Any]] | None:
    candidates: list[tuple[float, Path, dict[str, Any]]] = []
    if evaluations_root.exists():
        for path in evaluations_root.glob("*/a-t03-evaluation.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("evidence_mode") == "live_c_api":
                candidates.append((path.stat().st_mtime, path, payload))
    if not candidates:
        return None
    _, path, payload = max(candidates, key=lambda candidate: candidate[0])
    return path, payload


def _list_length(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _failure_classes(record: dict[str, Any]) -> list[str]:
    values = record.get("failure_classes")
    found = set(values) if isinstance(values, list) else set()
    return [name for name in FAILURE_CLASS_ORDER if name in found]


def _failed_checks(record: dict[str, Any]) -> list[str]:
    checks = record.get("checks")
    if not isinstance(checks, dict):
        return []
    return [name for name in CHECK_ORDER if checks.get(name) is False]


def _categories(failure_classes: list[str], failed_checks: list[str]) -> list[str]:
    categories: set[str] = set()
    if "metadata_loss" in failure_classes:
        categories.add("DATA_PROBLEM")
    if "retrieval_miss" in failure_classes:
        categories.add("RETRIEVAL_PROBLEM")
    if "model_expression_error" in failure_classes:
        categories.add("PROMPT_OR_MODEL_PROBLEM")
    if "structured_decision_error" in failure_classes:
        categories.add("RULE_DECISION_PROBLEM")
    if "key_facts" in failed_checks:
        categories.add("KNOWLEDGE_PROBLEM")
    if "source_ids" in failed_checks and not categories:
        categories.add("RETRIEVAL_PROBLEM")
    if not categories:
        categories.add("DATA_PROBLEM")
    return [category for category in CAUSE_ORDER if category in categories]


def _suggested_verifications(categories: list[str]) -> list[str]:
    suggestions: list[str] = []
    if "DATA_PROBLEM" in categories:
        suggestions.append(
            "Verify the governed C export, source catalog, and expected provenance before changing index settings."
        )
    if "KNOWLEDGE_PROBLEM" in categories:
        suggestions.append(
            "Verify the frozen expected fact against governed knowledge content; do not synthesize a missing fact."
        )
    if "RETRIEVAL_PROBLEM" in categories:
        suggestions.append(
            "After data verification, replay the same scoped retrieval to distinguish indexing from ranking."
        )
    if "RULE_DECISION_PROBLEM" in categories:
        suggestions.append(
            "Review the expected and actual structured action or risk policy with the governed metadata owner."
        )
    if "PROMPT_OR_MODEL_PROBLEM" in categories:
        suggestions.append(
            "Only after grounded evidence is available, compare the model expression; do not change Prompt automatically."
        )
    return suggestions


def _cause_findings(failed_cases: list[FailedCaseDiagnosis]) -> list[CauseFinding]:
    counts = {
        category: sum(category in case.categories for case in failed_cases)
        for category in CAUSE_ORDER
    }
    details = {
        "DATA_PROBLEM": (
            "metadata_loss is an evaluator signal that expected source metadata or governed provenance is unavailable or incompatible.",
            "Validate C export/source-catalog ownership and scope before changing retrieval or Prompt.",
        ),
        "KNOWLEDGE_PROBLEM": (
            "key_facts mismatches mean the recorded answer was not grounded in the evaluation's expected fact.",
            "Reconcile the frozen expected fact with governed source content; do not add or publish knowledge automatically.",
        ),
        "RETRIEVAL_PROBLEM": (
            "retrieval_miss is emitted only when the evaluator records a retrieval failure rather than metadata loss.",
            "Replay scoped retrieval after data validation and inspect index/ranking evidence before changing thresholds.",
        ),
        "PROMPT_OR_MODEL_PROBLEM": (
            "model_expression_error is emitted only when evidence is available but the answer expression misses the expected fact.",
            "Keep Prompt frozen unless a grounded replay reproduces this signal; then review a proposed change manually.",
        ),
        "RULE_DECISION_PROBLEM": (
            "structured_decision_error covers action, required-field, forbidden-claim, or risk-level mismatches.",
            "Review governed decision metadata and expected policy; do not alter rules or Prompt automatically.",
        ),
    }
    return [
        CauseFinding(
            category=category,
            affected_case_count=counts[category],
            evidence=(
                "DIRECT_EVALUATOR_SIGNAL"
                if counts[category]
                else "NO_SIGNAL_IN_CURRENT_REPORT"
            ),
            conclusion=details[category][0],
            recommended_verification=details[category][1],
        )
        for category in CAUSE_ORDER
    ]


def _recommendations(failed_cases: list[FailedCaseDiagnosis]) -> list[QualityRecommendation]:
    counts = {
        category: sum(category in case.categories for case in failed_cases)
        for category in CAUSE_ORDER
    }
    recommendations = [
        QualityRecommendation(
            priority="P0",
            category="DATA_PROBLEM",
            recommendation="Validate missing or incompatible source provenance in the governed export and catalog.",
            rationale=f"The report has {counts['DATA_PROBLEM']} case(s) with metadata_loss evidence.",
        ),
        QualityRecommendation(
            priority="P0",
            category="KNOWLEDGE_PROBLEM",
            recommendation="Reconcile expected facts with governed knowledge before any retrieval or Prompt experiment.",
            rationale=f"The report has {counts['KNOWLEDGE_PROBLEM']} case(s) with key_facts mismatches.",
        ),
    ]
    if counts["RULE_DECISION_PROBLEM"]:
        recommendations.append(
            QualityRecommendation(
                priority="P1",
                category="RULE_DECISION_PROBLEM",
                recommendation="Review the affected action/risk decision against governed metadata after data reconciliation.",
                rationale=f"The report has {counts['RULE_DECISION_PROBLEM']} case(s) with structured decision evidence.",
            )
        )
    recommendations.extend(
        [
            QualityRecommendation(
                priority="P2",
                category="RETRIEVAL_PROBLEM",
                recommendation="Run a scoped retrieval replay only after provenance validation; do not tune thresholds blindly.",
                rationale=(
                    "The current report has "
                    f"{counts['RETRIEVAL_PROBLEM']} direct retrieval_miss signal(s)."
                ),
            ),
            QualityRecommendation(
                priority="P2",
                category="PROMPT_OR_MODEL_PROBLEM",
                recommendation="Keep the Prompt unchanged unless a grounded replay produces a model_expression_error signal.",
                rationale=(
                    "The current report has "
                    f"{counts['PROMPT_OR_MODEL_PROBLEM']} direct model-expression signal(s)."
                ),
            ),
        ]
    )
    return recommendations


def latest_quality_baseline(evaluations_root: Path) -> QualityBaselineSnapshot:
    """Return a safe diagnosis of the newest saved ``live_c_api`` report."""

    selected = _latest_live_evaluation(evaluations_root)
    if selected is None:
        no_signal_findings = _cause_findings([])
        return QualityBaselineSnapshot(
            status="NOT_AVAILABLE",
            cause_findings=no_signal_findings,
            recommendations=[
                QualityRecommendation(
                    priority="P2",
                    category="DATA_PROBLEM",
                    recommendation="Run an explicit approved evaluation before diagnosing quality changes.",
                    rationale="No saved live_c_api evaluation report is available.",
                )
            ],
        )

    path, payload = selected
    records = payload.get("records")
    records = records if isinstance(records, list) else []
    failed_cases: list[FailedCaseDiagnosis] = []
    for record in records:
        if not isinstance(record, dict) or record.get("passed") is not False:
            continue
        failure_classes = _failure_classes(record)
        failed_checks = _failed_checks(record)
        categories = _categories(failure_classes, failed_checks)
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            case_id = "UNIDENTIFIED_EVALUATION_CASE"
        failed_cases.append(
            FailedCaseDiagnosis(
                case_id=case_id[:160],
                categories=categories,
                evaluator_failure_classes=failure_classes,
                failed_checks=failed_checks,
                expected_source_count=_list_length(record.get("expected_source_ids")),
                missing_expected_source_count=_list_length(record.get("missing_source_ids")),
                expected_fact_count=_list_length(record.get("expected_key_facts")),
                suggested_verifications=_suggested_verifications(categories),
            )
        )

    total_cases = _as_non_negative_int(payload.get("total"))
    passed_cases = _as_non_negative_int(payload.get("passed"))
    check_counts = payload.get("check_pass_counts")
    check_counts = check_counts if isinstance(check_counts, dict) else {}
    summary = QualityBaselineSummary(
        evaluation_id=path.parent.name,
        executed_at=(
            payload.get("executed_at")
            if isinstance(payload.get("executed_at"), str)
            else "NOT_AVAILABLE"
        ),
        dataset_version=(
            payload.get("dataset_version")
            if isinstance(payload.get("dataset_version"), str)
            else "NOT_AVAILABLE"
        ),
        total_case_count=total_cases,
        passed_case_count=passed_cases,
        failed_case_count=len(failed_cases),
        pass_rate_percent=(round((passed_cases / total_cases) * 100, 2) if total_cases else 0),
        checks=[
            QualityCheckSummary(
                check=check,
                passed_case_count=(
                    value if isinstance(value := check_counts.get(check), int) else None
                ),
            )
            for check in CHECK_ORDER
        ],
    )
    return QualityBaselineSnapshot(
        status="AVAILABLE",
        summary=summary,
        failed_cases=failed_cases,
        cause_findings=_cause_findings(failed_cases),
        recommendations=_recommendations(failed_cases),
    )
