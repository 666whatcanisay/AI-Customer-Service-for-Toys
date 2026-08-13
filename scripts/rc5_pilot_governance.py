from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from channel_engine.pilot_governance import (
    ActivationValidationResult,
    GateFactsV1,
    LiveProcessSnapshot,
    RagLiveSnapshot,
    RuntimeActivationV1,
    RuntimeCatalogEntryV1,
    RuntimeCatalogV1,
    RuntimeLifecycle,
    classify_runtime_path,
    load_gate_facts,
    sha256_file,
    validate_activation,
)


DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
REQUIRED_ACTIVATION_COMPONENTS = {
    "CHANNEL_ENGINE_HOST",
    "AI_CS_PLATFORM",
    "AI_CS_RAG",
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _binding(path: Path, database_path: Path) -> tuple[dict[str, Any], bool, str]:
    if not database_path.is_file() or database_path.stat().st_size <= 16:
        return {}, False, "DATABASE_MISSING_OR_EMPTY"
    if not path.is_file():
        return {}, False, "BINDING_SIDECAR_MISSING"
    try:
        value = _read_json(path)
    except Exception:
        return {}, False, "BINDING_SIDECAR_INVALID"
    required = ("database_instance_id", "database_role", "environment_id", "canonical_path")
    if any(not str(value.get(name, "")).strip() for name in required):
        return value, False, "BINDING_REQUIRED_FIELD_MISSING"
    expected = str(database_path.resolve(strict=False)).casefold()
    actual = str(Path(str(value["canonical_path"])).resolve(strict=False)).casefold()
    if expected != actual:
        return value, False, "BINDING_CANONICAL_PATH_MISMATCH"
    try:
        uri = f"file:{database_path.resolve(strict=True).as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=3.0) as connection:
            rows = connection.execute(
                "SELECT database_role,database_instance_id,environment_id,"
                "identity_revision,schema_fingerprint,restore_generation,"
                "restored_from_backup_epoch FROM runtime_database_identity"
            ).fetchall()
            if len(rows) != 1:
                return value, False, "DATABASE_INTERNAL_IDENTITY_NOT_UNIQUE"
            internal = rows[0]
            comparisons = (
                (str(internal[0]), str(value["database_role"])),
                (str(internal[1]), str(value["database_instance_id"])),
                (str(internal[2]), str(value["environment_id"])),
                (str(internal[3]), str(value.get("identity_revision", ""))),
                (str(internal[4]), str(value.get("schema_fingerprint", ""))),
                (str(internal[5]), str(value.get("restore_generation", ""))),
                (str(internal[6] or ""), str(value.get("restored_from_backup_epoch") or "")),
            )
            if any(left != right for left, right in comparisons):
                return value, False, "DATABASE_INTERNAL_IDENTITY_MISMATCH"
            if value.get("expected_revision"):
                revision = connection.execute(
                    "SELECT version_num FROM alembic_version"
                ).fetchone()
                if not revision or str(revision[0]) != str(value["expected_revision"]):
                    return value, False, "DATABASE_INTERNAL_REVISION_MISMATCH"
            elif value.get("runtime_storage_version"):
                revision = connection.execute(
                    "SELECT runtime_storage_version FROM runtime_storage_metadata "
                    "WHERE singleton_id='channel-engine-runtime'"
                ).fetchone()
                if not revision or str(revision[0]) != str(value["runtime_storage_version"]):
                    return value, False, "DATABASE_INTERNAL_REVISION_MISMATCH"
    except (OSError, sqlite3.Error):
        return value, False, "DATABASE_INTERNAL_IDENTITY_UNREADABLE"
    return value, True, "BINDING_VALID"


def build_catalog(
    roots: list[Path], active_specs: list[Path], expected_roles: list[str]
) -> RuntimeCatalogV1:
    active_by_path: dict[str, dict[str, Any]] = {}
    for spec_path in active_specs:
        spec = _read_json(spec_path)
        database_path = Path(str(spec["database_path"])).resolve(strict=False)
        key = str(database_path).casefold()
        if key in active_by_path:
            raise ValueError(f"database declared ACTIVE more than once: {database_path}")
        active_by_path[key] = spec

    discovered: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for value in root.rglob("*"):
            if value.is_file() and value.suffix.casefold() in DATABASE_SUFFIXES:
                resolved = value.resolve(strict=False)
                discovered[str(resolved).casefold()] = resolved
    for key, spec in active_by_path.items():
        discovered[key] = Path(str(spec["database_path"])).resolve(strict=False)

    entries: list[RuntimeCatalogEntryV1] = []
    for key, database_path in sorted(discovered.items()):
        spec = active_by_path.get(key)
        binding_path = (
            Path(str(spec["binding_path"])).resolve(strict=False)
            if spec
            else Path(str(database_path) + ".binding.json")
        )
        binding, binding_valid, binding_reason = _binding(binding_path, database_path)
        if spec:
            lifecycle = RuntimeLifecycle.ACTIVE
            retention = "ACTIVE"
            reason = "EXPLICIT_ACTIVE_AND_" + binding_reason
            component = str(spec["component"])
        else:
            lifecycle, retention, reason = classify_runtime_path(database_path)
            component = str(binding.get("database_role") or "UNASSIGNED")
            if lifecycle is RuntimeLifecycle.UNCLASSIFIED and binding_valid:
                reason = "VALID_IDENTITY_BUT_NOT_ACTIVE_OR_ARCHIVED"
        environment_id = str(binding.get("environment_id") or "UNASSIGNED")
        database_role = str(binding.get("database_role") or "UNASSIGNED")
        revision = binding.get("expected_revision") or binding.get("runtime_storage_version")
        entries.append(
            RuntimeCatalogEntryV1(
                entry_id=f"runtime-db:{len(entries) + 1:04d}",
                component=component,
                environment_id=environment_id,
                database_role=database_role,
                lifecycle=lifecycle,
                canonical_path=str(database_path),
                database_instance_id=(
                    str(binding["database_instance_id"])
                    if binding.get("database_instance_id")
                    else None
                ),
                revision=str(revision) if revision else None,
                binding_valid=binding_valid,
                retention_class=retention,
                classification_reason=reason,
            )
        )
    return RuntimeCatalogV1(
        generated_at=datetime.now(UTC),
        expected_active_roles=tuple(expected_roles),
        entries=tuple(entries),
    )


def _live_process(pid: int) -> LiveProcessSnapshot | None:
    if os.name != "nt":
        return None
    command = (
        "$p=Get-Process -Id %d -ErrorAction SilentlyContinue;"
        "if($null -eq $p){exit 3};"
        "$ports=@(Get-NetTCPConnection -State Listen -OwningProcess %d "
        "-ErrorAction SilentlyContinue|Select-Object -ExpandProperty LocalPort -Unique);"
        "[pscustomobject]@{pid=[int]$p.Id;path=[string]$p.Path;"
        "started=$p.StartTime.ToUniversalTime().ToString('o');ports=$ports}"
        "|ConvertTo-Json -Compress"
    ) % (pid, pid)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    value = json.loads(result.stdout)
    ports = value.get("ports", [])
    if isinstance(ports, int):
        ports = [ports]
    return LiveProcessSnapshot(
        pid=int(value["pid"]),
        executable_path=str(value["path"]),
        process_started_at=datetime.fromisoformat(str(value["started"])),
        listening_ports=tuple(sorted(int(item) for item in ports)),
    )


def _query_counts(path: Path, queries: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {"database_path": str(path), "status": "UNKNOWN"}
    if not path.is_file() or path.stat().st_size <= 16:
        result["reason"] = "DATABASE_MISSING_OR_EMPTY"
        return result
    try:
        uri = f"file:{path.resolve(strict=True).as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=3.0) as connection:
            result["integrity"] = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            for name, query in queries.items():
                result[name] = connection.execute(query).fetchall()
        result["status"] = "PASS" if result["integrity"] == "ok" else "BLOCKED"
    except Exception as exc:
        result["reason"] = f"READ_ONLY_QUERY_FAILED:{type(exc).__name__}"
    return result


def _source_identity(repository: Path) -> dict[str, str]:
    def run(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=True,
        )
        return result.stdout.strip()

    head = run("rev-parse", "HEAD")
    porcelain = run("status", "--porcelain=v1", "--untracked-files=all")
    diff = run("-c", "core.safecrlf=false", "diff", "--no-ext-diff", "--binary", "HEAD")
    untracked = sorted(
        item for item in run("ls-files", "--others", "--exclude-standard").splitlines()
        if item
    )
    fingerprint_parts = [
        f"head={head.lower()}",
        f"status={porcelain}",
        f"diff={diff}",
    ]
    for relative_path in untracked:
        candidate = (repository / relative_path).resolve(strict=True)
        candidate.relative_to(repository.resolve(strict=True))
        fingerprint_parts.append(f"untracked={relative_path}:{sha256_file(candidate)}")
    return {
        "repository": str(repository.resolve(strict=True)),
        "head": head,
        "working_tree": "DIRTY" if porcelain else "CLEAN",
        "source_fingerprint": hashlib.sha256(
            "\n".join(fingerprint_parts).encode("utf-8")
        ).hexdigest(),
    }


def _rag_live_snapshot(activation: RuntimeActivationV1) -> RagLiveSnapshot | None:
    if activation.component != "AI_CS_RAG" or len(activation.ports) != 1:
        return None
    url = f"http://127.0.0.1:{activation.ports[0]}/api/status"
    try:
        with urllib.request.urlopen(url, timeout=3.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return None
    return RagLiveSnapshot(
        ready=bool(data.get("ready")),
        model_configured=bool(data.get("model_configured")),
    )


def _read_agent_send_enabled(path: Path) -> bool | None:
    try:
        payload = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    value = payload.get("real_send_enabled")
    return value if isinstance(value, bool) else None


def _check(status: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "reason_codes": reasons or ["CURRENT"],
    }


def evaluate_preflight(
    *,
    activation_results: dict[str, ActivationValidationResult],
    source_identity: dict[str, dict[str, str]],
    storage_statuses: dict[str, str],
    gate_facts: GateFactsV1,
    host_real_send_enabled: bool | None,
    agent_real_send_enabled: bool | None,
    real_execution_attempts: int,
    real_sends: int,
    real_receipts: int,
) -> dict[str, Any]:
    runtime_reasons = [
        f"{component}:{reason}"
        for component in sorted(REQUIRED_ACTIVATION_COMPONENTS)
        for reason in (
            activation_results.get(component).reason_codes
            if component in activation_results
            and activation_results[component].status != "PASS"
            else (() if component in activation_results else ("ACTIVATION_MISSING",))
        )
    ]
    runtime_health = _check("BLOCKED" if runtime_reasons else "PASS", runtime_reasons)

    source_reasons = [
        f"{name}:SOURCE_NOT_FROZEN"
        for name, identity in source_identity.items()
        if identity.get("working_tree") != "CLEAN"
    ]
    source_freeze = _check("BLOCKED" if source_reasons else "PASS", source_reasons)

    storage_reasons = [
        f"{name}:STORAGE_NOT_READY"
        for name, status in storage_statuses.items()
        if status != "PASS"
    ]
    storage_health = _check("BLOCKED" if storage_reasons else "PASS", storage_reasons)

    send_reasons: list[str] = []
    if host_real_send_enabled is not False:
        send_reasons.append("HOST_REAL_SEND_NOT_PROVEN_DISABLED")
    if agent_real_send_enabled is not False:
        send_reasons.append("AGENT_REAL_SEND_NOT_PROVEN_DISABLED")
    if real_execution_attempts != 0:
        send_reasons.append("REAL_EXECUTION_ATTEMPT_NONZERO")
    if real_sends != 0:
        send_reasons.append("REAL_SEND_NONZERO")
    if real_receipts != 0:
        send_reasons.append("REAL_RECEIPT_NONZERO")
    send_safety = _check("BLOCKED" if send_reasons else "PASS", send_reasons)

    gate_facts_validity = _check("PASS", ["GATE_FACTS_VALID"])
    checks = {
        "runtime_health": runtime_health,
        "source_freeze": source_freeze,
        "storage_health": storage_health,
        "send_safety": send_safety,
        "gate_facts_validity": gate_facts_validity,
    }
    preflight_reasons = [
        f"{name.upper()}_BLOCKED"
        for name, check in checks.items()
        if check["status"] != "PASS"
    ]
    preflight = _check(
        "BLOCKED" if preflight_reasons else "PASS", preflight_reasons
    )
    production_ready = (
        preflight["status"] == "PASS"
        and gate_facts.derived_ai_cs_production_ready()
    )
    return {
        **checks,
        "pilot_governance_preflight": preflight,
        "derived": {
            "may_enter_read_only_pilot": preflight["status"] == "PASS",
            "ai_cs_production_ready": production_ready,
            "real_send_enabled": False
            if send_safety["status"] == "PASS"
            else None,
            "real_pdd_operation_authorized": False,
            "real_pdd_operation_authorization_reason": (
                "CURRENT_GREEN_UI_HUMAN_ACCEPTANCE_PASS_AND_MANUAL_TRIGGER_REQUIRED"
            ),
        },
    }


def build_status(
    facts_path: Path,
    catalog_path: Path,
    activation_paths: list[Path],
    agent_config_path: Path,
) -> dict[str, Any]:
    facts = load_gate_facts(facts_path)
    catalog = RuntimeCatalogV1.model_validate(_read_json(catalog_path))
    activations: list[dict[str, Any]] = []
    activation_models: list[RuntimeActivationV1] = []
    activation_results: dict[str, ActivationValidationResult] = {}
    runtime_data: dict[str, Path] = {}
    source_identity = {
        "channel_engine": _source_identity(Path(__file__).resolve().parents[1]),
        "ai_cs": _source_identity(Path(__file__).resolve().parents[2] / "AI-CS"),
    }
    for path in activation_paths:
        activation = RuntimeActivationV1.model_validate(_read_json(path))
        activation_models.append(activation)
        live = _live_process(activation.pid)
        if activation.activation_kind == "DATABASE":
            binding = _read_json(Path(str(activation.binding_sidecar_path)))
            current_source = (
                _source_identity(Path(activation.source_repository_path))
                if activation.source_repository_path
                else None
            )
            validation = validate_activation(
                activation,
                catalog,
                live,
                current_config_sha256=sha256_file(activation.config_source_path),
                current_binding_sha256=sha256_file(
                    str(activation.binding_sidecar_path)
                ),
                current_database_instance_id=str(
                    binding.get("database_instance_id", "")
                ),
                current_source_revision=(
                    current_source["head"] if current_source else None
                ),
                current_source_fingerprint=(
                    current_source["source_fingerprint"]
                    if current_source
                    else None
                ),
            )
        else:
            repository = Path(str(activation.source_repository_path))
            current_source = _source_identity(repository)
            validation = validate_activation(
                activation,
                catalog,
                live,
                current_config_sha256=sha256_file(activation.config_source_path),
                current_source_revision=current_source["head"],
                current_source_fingerprint=current_source["source_fingerprint"],
                live_rag=_rag_live_snapshot(activation),
            )
        if activation.component in activation_results:
            validation = ActivationValidationResult(
                status="BLOCKED",
                reason_codes=("DUPLICATE_COMPONENT_ACTIVATION",),
            )
        activation_results[activation.component] = validation
        activations.append(
            {
                "component": activation.component,
                "activation_kind": activation.activation_kind,
                "pid": activation.pid,
                "database_path": activation.canonical_database_path,
                "database_instance_id": activation.database_instance_id,
                "revision": activation.revision,
                "rag_identity": (
                    activation.rag_identity.model_dump(mode="json")
                    if activation.rag_identity
                    else None
                ),
                "diagnostics": activation.diagnostics,
                "validation": validation.model_dump(mode="json"),
            }
        )
        runtime_data.update(
            {name: Path(value) for name, value in activation.runtime_data_paths.items()}
        )
        if activation.activation_kind == "DATABASE":
            runtime_data.setdefault(
                str(activation.database_role),
                Path(str(activation.canonical_database_path)),
            )

    host = _query_counts(
        runtime_data.get("HOST_CONTROL", Path("__missing__")),
        {
            "observations": (
                "SELECT COUNT(*),SUM(CASE WHEN forwarded_at IS NOT NULL "
                "THEN 1 ELSE 0 END) FROM channel_agent_observations"
            ),
            "assistant_events": (
                "SELECT event_type,status,COUNT(*) "
                "FROM channel_agent_assistant_events GROUP BY event_type,status"
            ),
            "decisions": "SELECT state,COUNT(*) FROM decisions GROUP BY state",
            "approvals": "SELECT COUNT(*) FROM approvals",
            "execution_states": "SELECT state,COUNT(*) FROM executions GROUP BY state",
            "real_execution_attempts": (
                "SELECT COUNT(*) FROM pdd_pilot_execution_reservations"
            ),
            "real_send_receipts": (
                "SELECT outcome,COUNT(*) FROM pdd_send_transport_receipts "
                "GROUP BY outcome"
            ),
        },
    )
    buffer = _query_counts(
        runtime_data.get("CONVERSATION_BUFFER", Path("__missing__")),
        {
            "message_states": (
                "SELECT state,COUNT(*) FROM assistant_buffer_messages GROUP BY state"
            ),
            "turn_states": (
                "SELECT state,COUNT(*) FROM assistant_buffer_turns GROUP BY state"
            ),
        },
    )
    offline = _query_counts(
        runtime_data.get("OFFLINE_CONTROL", Path("__missing__")),
        {
            "decision_quality": (
                "SELECT quality_status,COUNT(*) FROM offline_reply_decisions "
                "GROUP BY quality_status"
            ),
            "preparation_states": (
                "SELECT state,COUNT(*) FROM execution_preparations GROUP BY state"
            ),
            "trace_stages": (
                "SELECT stage,state,COUNT(*) FROM pipeline_trace_steps "
                "GROUP BY stage,state"
            ),
            "offline_receipts": (
                "SELECT receipt_kind,outcome,COUNT(*) FROM offline_receipts "
                "GROUP BY receipt_kind,outcome"
            ),
        },
    )
    spool = _query_counts(
        runtime_data.get("AGENT_SPOOL", Path("__missing__")),
        {
            "ack_state": (
                "SELECT CASE WHEN acked_at IS NULL THEN 'PENDING' ELSE 'ACKED' END,"
                "COUNT(*) FROM edge_observations GROUP BY 1"
            ),
            "cursor_count": "SELECT COUNT(*) FROM edge_cursors",
        },
    )
    trace_rows = {
        (str(row[0]), str(row[1])): int(row[2])
        for row in offline.get("trace_stages", [])
    }
    observation_row = (host.get("observations") or [[0, 0]])[0]
    real_attempt_row = (host.get("real_execution_attempts") or [[0]])[0]
    real_receipt_count = sum(
        int(row[1]) for row in host.get("real_send_receipts", [])
    )
    preparation_states = {
        str(row[0]): int(row[1]) for row in offline.get("preparation_states", [])
    }
    real_execution_attempts = int(real_attempt_row[0] or 0)
    real_sends = real_receipt_count
    real_receipts = real_receipt_count
    pipeline_summary = {
        "observation_received": int(observation_row[0] or 0),
        "host_persisted": int(observation_row[0] or 0),
        "host_forwarded": int(observation_row[1] or 0),
        "ack_cursor": spool.get("ack_state", []),
        "buffer_message_states": buffer.get("message_states", []),
        "ai_requested": sum(
            count
            for (stage, _state), count in trace_rows.items()
            if stage == "AI_GENERATING"
        ),
        "ai_completed": trace_rows.get(("AI_GENERATING", "SUCCEEDED"), 0),
        "ai_failed": trace_rows.get(("AI_GENERATING", "FAILED"), 0),
        "decision_states": host.get("decisions", []),
        "approval_count": int((host.get("approvals") or [[0]])[0][0]),
        "execution_prepared": preparation_states.get("READY", 0),
        "real_execution_attempt": real_execution_attempts,
        "real_send": real_sends,
        "real_receipt": real_receipts,
    }
    host_activation = next(
        (
            activation
            for activation in activation_models
            if activation.component == "CHANNEL_ENGINE_HOST"
        ),
        None,
    )
    host_real_send_enabled = (
        host_activation.safety_flags.get("real_send_enabled")
        if host_activation
        else None
    )
    evaluation = evaluate_preflight(
        activation_results=activation_results,
        source_identity=source_identity,
        storage_statuses={
            "host": str(host["status"]),
            "buffer": str(buffer["status"]),
            "offline_control": str(offline["status"]),
            "agent_spool": str(spool["status"]),
        },
        gate_facts=facts,
        host_real_send_enabled=host_real_send_enabled,
        agent_real_send_enabled=_read_agent_send_enabled(agent_config_path),
        real_execution_attempts=real_execution_attempts,
        real_sends=real_sends,
        real_receipts=real_receipts,
    )
    overall = evaluation["pilot_governance_preflight"]["status"]
    return {
        "schema": "rc5-pilot-status.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": overall,
        "source_identity": source_identity,
        "gate_facts": {
            **facts.model_dump(mode="json", by_alias=True),
            "legacy_derived_fields": "DEPRECATED_IGNORED",
        },
        "governance": evaluation,
        "runtime_catalog": {
            "path": str(catalog_path),
            "active_count": sum(
                item.lifecycle is RuntimeLifecycle.ACTIVE for item in catalog.entries
            ),
            "unclassified_count": sum(
                item.lifecycle is RuntimeLifecycle.UNCLASSIFIED for item in catalog.entries
            ),
        },
        "activations": activations,
        "pipeline": {
            "summary": pipeline_summary,
            "host": host,
            "buffer": buffer,
            "offline_control": offline,
            "agent_spool": spool,
            "real_send_interpretation": (
                "RealExecutionAttempt/RealSend/RealReceipt are PDD-specific; "
                "offline EXECUTION_PREPARED may increase normally."
            ),
        },
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="RC5 Pilot governance catalog/status")
    sub = parser.add_subparsers(dest="command", required=True)
    catalog_parser = sub.add_parser("catalog")
    catalog_parser.add_argument("--scan-root", action="append", default=[])
    catalog_parser.add_argument("--active-spec", action="append", default=[])
    catalog_parser.add_argument("--expected-active-role", action="append", default=[])
    catalog_parser.add_argument("--output", required=True)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--facts", required=True)
    status_parser.add_argument("--catalog", required=True)
    status_parser.add_argument("--activation", action="append", default=[])
    status_parser.add_argument("--agent-config", required=True)
    status_parser.add_argument("--output")
    args = parser.parse_args()
    if args.command == "catalog":
        value = build_catalog(
            [Path(item).resolve(strict=False) for item in args.scan_root],
            [Path(item).resolve(strict=True) for item in args.active_spec],
            list(args.expected_active_role),
        )
        _write_json(Path(args.output).resolve(strict=False), value.model_dump(mode="json"))
        print(value.model_dump_json())
        return 0
    value = build_status(
        Path(args.facts).resolve(strict=True),
        Path(args.catalog).resolve(strict=True),
        [Path(item).resolve(strict=True) for item in args.activation],
        Path(args.agent_config).resolve(strict=True),
    )
    if args.output:
        _write_json(Path(args.output).resolve(strict=False), value)
    print(json.dumps(value, ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from exc
