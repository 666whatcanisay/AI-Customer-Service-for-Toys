from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from channel_engine.pilot_governance import load_gate_facts


def main() -> int:
    engine_root = Path(__file__).resolve().parents[1]
    ai_root = engine_root.parent / "AI-CS"
    facts_path = (
        engine_root
        / "docs"
        / "production"
        / "rc5-final"
        / "RC5-Offline-Stability-Version-Matrix.json"
    )
    payload = json.loads(facts_path.read_text(encoding="utf-8"))
    load_gate_facts(facts_path)
    errors: list[str] = []

    expected_head = "0019_runtime_database_identity_v1"
    if payload["database_and_startup"]["platform_migration_head"] != expected_head:
        errors.append("canonical Platform migration head is not 0019")
    migration = ai_root / "platform_backend" / "migrations" / "versions" / f"{expected_head}.py"
    if not migration.is_file():
        errors.append(f"migration file missing: {migration}")
    else:
        source = migration.read_text(encoding="utf-8")
        if not re.search(rf"revision\s*=\s*[\"']{re.escape(expected_head)}[\"']", source):
            errors.append("0019 migration revision declaration is inconsistent")

    expected_gates = {
        "RC5_OFFLINE_STABILITY_READY": "PASS",
        "REAL_PDD_ADAPTER_READY": "NOT_VERIFIED",
        "REAL_PDD_READ_READY": "NOT_VERIFIED",
        "REAL_PDD_AI_READY": "NOT_VERIFIED",
        "REAL_PDD_CONFIRM_READY": "NOT_VERIFIED",
        "REAL_PDD_SEND_READY": "NOT_VERIFIED",
        "REAL_PDD_AUTO_SEND_READY": "NOT_IN_SCOPE",
    }
    if payload.get("gates") != expected_gates:
        errors.append("canonical Gate values drifted")
    dependencies = payload.get("gate_contract", {}).get("dependencies", [])
    expected_dependencies = [
        "REAL_PDD_ADAPTER_READY->REAL_PDD_READ_READY",
        "REAL_PDD_READ_READY->REAL_PDD_AI_READY",
        "REAL_PDD_AI_READY->REAL_PDD_CONFIRM_READY",
        "REAL_PDD_CONFIRM_READY->REAL_PDD_SEND_READY",
    ]
    if dependencies != expected_dependencies:
        errors.append("PDD Gate dependency order drifted")

    current_docs = (
        engine_root / "README.md",
        engine_root / "docs" / "production" / "rc5-final" / "README.md",
        ai_root / "README.md",
        ai_root / "docs" / "platform" / "01_当前发展状态.md",
    )
    for path in current_docs:
        text = path.read_text(encoding="utf-8-sig")
        if "RC5_OFFLINE_STABILITY_READY" not in text or "NOT_VERIFIED" not in text:
            errors.append(f"current Gate facts missing from {path}")
    ai_readme_lead = (ai_root / "README.md").read_text(encoding="utf-8-sig")[:1600]
    if expected_head not in ai_readme_lead or "VALIDATE_ONLY" not in ai_readme_lead:
        errors.append("AI-CS README lead does not state current DB/startup truth")

    ordinary_start = (
        ai_root / "scripts" / "windows" / "start_ai_customer_service.ps1"
    ).read_text(encoding="utf-8-sig")
    forbidden = ("alembic upgrade", "AutoImportTestData", "AutoSyncTestKnowledge")
    for token in forbidden:
        if token.casefold() in ordinary_start.casefold():
            errors.append(f"ordinary startup contains forbidden behavior: {token}")

    result = {
        "schema": "rc5-current-facts-verification.v1",
        "status": "PASS" if not errors else "BLOCKED",
        "canonical_facts": str(facts_path),
        "platform_migration_head": expected_head,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
