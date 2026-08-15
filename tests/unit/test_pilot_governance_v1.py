from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from channel_agent.controlled_auto_runtime import ControlledAutoRuntimeStateV1
from channel_engine.pilot_governance import (
    ActivationValidationResult,
    GateFactsV1,
    LiveProcessSnapshot,
    RagLiveSnapshot,
    RuntimeActivationV1,
    RuntimeCatalogEntryV1,
    RuntimeCatalogV1,
    validate_activation,
)
from scripts.rc5_pilot_governance import (
    _live_process,
    _parse_netstat_listening_ports,
    _rag_live_snapshot,
    evaluate_preflight,
)

NOW = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64


@pytest.mark.parametrize(
    ("pid", "expected_port"),
    [(31376, 8420), (55776, 8422), (36164, 18443)],
)
def test_netstat_port_owner_regression_for_recovered_runtime_pids(
    pid: int,
    expected_port: int,
) -> None:
    output = """
      TCP    127.0.0.1:8420         0.0.0.0:0              LISTENING       31376
      TCP    127.0.0.1:8422         0.0.0.0:0              LISTENING       55776
      TCP    127.0.0.1:18443        0.0.0.0:0              LISTENING       36164
      TCP    127.0.0.1:57632        127.0.0.1:8420         TIME_WAIT       0
    """
    assert _parse_netstat_listening_ports(output, pid) == (expected_port,)


def test_live_process_uses_netstat_owner_instead_of_get_nettcpconnection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(arguments: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(arguments)
        if arguments[0] == "powershell.exe":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "pid": 31376,
                        "path": "C:/Python/python.exe",
                        "started": "2026-08-13T02:03:09.3192778+00:00",
                    }
                ),
            )
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "TCP 127.0.0.1:8420 0.0.0.0:0 LISTENING 31376\n"
            ),
        )

    monkeypatch.setattr("scripts.rc5_pilot_governance.subprocess.run", fake_run)
    live = _live_process(31376)
    assert live is not None
    assert live.listening_ports == (8420,)
    assert calls[1] == ["netstat.exe", "-ano", "-p", "tcp"]


def test_rag_status_reuses_internal_service_token_only_as_request_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activation = RuntimeActivationV1(
        activation_id="activation:rag-auth",
        component="AI_CS_RAG",
        activation_kind="RAG",
        pid=31376,
        executable_path="C:/Python/python.exe",
        manifest_created_at=NOW,
        service_started_at=NOW,
        process_started_at=NOW,
        config_source_path="C:/runtime/ai-cs.ps1",
        config_sha256=SHA_A,
        source_repository_path="C:/src/AI-CS",
        source_revision="c" * 40,
        source_fingerprint=SHA_B,
        rag_identity={
            "model": "qwen3.5:9b",
            "vector_database_path": "C:/runtime/vector_db",
            "active_collection_name": "test_knowledge_v031",
            "ready": True,
            "model_configured": True,
        },
        ports=(8420,),
    )
    token = "existing-internal-service-token-32-bytes"
    observed: dict[str, str | None] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"data": {"ready": True, "model_configured": True}}
            ).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> Response:
        observed["url"] = getattr(request, "full_url")
        observed["token"] = request.get_header("X-ai-cs-service-token")
        observed["timeout"] = str(timeout)
        return Response()

    monkeypatch.setattr(
        "scripts.rc5_pilot_governance.urllib.request.urlopen",
        fake_urlopen,
    )
    snapshot = _rag_live_snapshot(activation, token)
    assert snapshot == RagLiveSnapshot(ready=True, model_configured=True)
    assert observed["token"] == token
    assert token not in str(observed["url"])


def _entry(*, lifecycle: str = "ACTIVE") -> RuntimeCatalogEntryV1:
    return RuntimeCatalogEntryV1(
        entry_id="host-db",
        component="CHANNEL_ENGINE_HOST",
        environment_id="RC5_CHANNEL_ENGINE_LOCAL",
        database_role="HOST_CONTROL",
        lifecycle=lifecycle,
        canonical_path="C:/runtime/host.sqlite3",
        database_instance_id="db-instance-1",
        revision="1.0",
        binding_valid=True,
        retention_class="ACTIVE" if lifecycle == "ACTIVE" else "MANUAL",
        classification_reason="TEST",
    )


def _catalog(*entries: RuntimeCatalogEntryV1) -> RuntimeCatalogV1:
    return RuntimeCatalogV1(
        generated_at=NOW,
        expected_active_roles=("RC5_CHANNEL_ENGINE_LOCAL|HOST_CONTROL",),
        entries=entries,
    )


def _activation() -> RuntimeActivationV1:
    return RuntimeActivationV1(
        activation_id="activation:test",
        component="CHANNEL_ENGINE_HOST",
        pid=1234,
        executable_path="C:/Python/python.exe",
        manifest_created_at=NOW,
        service_started_at=NOW,
        process_started_at=NOW,
        config_source_path="C:/runtime/host.config.json",
        config_sha256=SHA_A,
        source_repository_path="C:/src/engine",
        source_revision="f" * 40,
        canonical_database_path="C:/runtime/host.sqlite3",
        binding_sidecar_path="C:/runtime/host.sqlite3.binding.json",
        database_instance_id="db-instance-1",
        environment_id="RC5_CHANNEL_ENGINE_LOCAL",
        database_role="HOST_CONTROL",
        revision="1.0",
        binding_sidecar_sha256=SHA_B,
        ports=(18443,),
        runtime_data_paths={},
    )


def test_gate_facts_reject_read_pass_before_adapter() -> None:
    with pytest.raises(ValidationError, match="REAL_PDD_READ_READY cannot PASS"):
        GateFactsV1(
            gates={
                "RC5_OFFLINE_STABILITY_READY": "PASS",
                "REAL_PDD_ADAPTER_READY": "NOT_VERIFIED",
                "REAL_PDD_READ_READY": "PASS",
                "REAL_PDD_AI_READY": "NOT_VERIFIED",
                "REAL_PDD_CONFIRM_READY": "NOT_VERIFIED",
                "REAL_PDD_SEND_READY": "NOT_VERIFIED",
                "REAL_PDD_AUTO_SEND_READY": "NOT_IN_SCOPE",
            },
        )


def test_gate_facts_accept_and_ignore_legacy_derived_fields() -> None:
    facts = GateFactsV1(
        gates={
            "RC5_OFFLINE_STABILITY_READY": "PASS",
            "REAL_PDD_ADAPTER_READY": "NOT_VERIFIED",
            "REAL_PDD_READ_READY": "NOT_VERIFIED",
            "REAL_PDD_AI_READY": "NOT_VERIFIED",
            "REAL_PDD_CONFIRM_READY": "NOT_VERIFIED",
            "REAL_PDD_SEND_READY": "NOT_VERIFIED",
            "REAL_PDD_AUTO_SEND_READY": "NOT_IN_SCOPE",
        },
        may_enter_read_only_pilot=True,
        ai_cs_production_ready=True,
        real_send_enabled=True,
    )
    assert facts.derived_ai_cs_production_ready() is False
    assert "may_enter_read_only_pilot" not in facts.model_dump()


def test_catalog_requires_exactly_one_active_database() -> None:
    with pytest.raises(ValidationError, match="exactly one ACTIVE"):
        _catalog()
    with pytest.raises(ValidationError, match="exactly one ACTIVE"):
        _catalog(_entry(), _entry())


def test_activation_cross_checks_pid_start_port_config_and_binding() -> None:
    activation = _activation()
    live = LiveProcessSnapshot(
        pid=activation.pid,
        executable_path=activation.executable_path,
        process_started_at=activation.process_started_at,
        listening_ports=(18443,),
    )
    result = validate_activation(
        activation,
        _catalog(_entry()),
        live,
        current_config_sha256=SHA_A,
        current_binding_sha256=SHA_B,
        current_database_instance_id="db-instance-1",
        current_source_revision="f" * 40,
    )
    assert result.status == "PASS"


def test_activation_rejects_pid_reuse_and_stale_config() -> None:
    activation = _activation()
    reused = LiveProcessSnapshot(
        pid=activation.pid,
        executable_path=activation.executable_path,
        process_started_at=activation.process_started_at + timedelta(minutes=1),
        listening_ports=(18443,),
    )
    result = validate_activation(
        activation,
        _catalog(_entry()),
        reused,
        current_config_sha256="c" * 64,
        current_binding_sha256=SHA_B,
        current_database_instance_id="db-instance-1",
        current_source_revision="e" * 40,
    )
    assert result.status == "BLOCKED"
    assert "ACTIVATION_PROCESS_START_MISMATCH" in result.reason_codes
    assert "ACTIVATION_CONFIG_DIGEST_MISMATCH" in result.reason_codes
    assert "ACTIVATION_SOURCE_REVISION_MISMATCH" in result.reason_codes


def test_rag_activation_validates_source_and_ready_without_transient_metrics() -> None:
    activation = RuntimeActivationV1(
        activation_id="activation:rag",
        component="AI_CS_RAG",
        activation_kind="RAG",
        pid=4321,
        executable_path="C:/Python/python.exe",
        manifest_created_at=NOW,
        service_started_at=NOW,
        process_started_at=NOW,
        config_source_path="C:/runtime/ai-cs.ps1",
        config_sha256=SHA_A,
        source_repository_path="C:/src/AI-CS",
        source_revision="c" * 40,
        source_fingerprint=SHA_B,
        rag_identity={
            "model": "qwen3.5:9b",
            "vector_database_path": "C:/runtime/vector_db",
            "active_collection_name": "test_knowledge_v031",
            "ready": True,
            "model_configured": True,
        },
        ports=(8420,),
        diagnostics={
            "active_collection_chunk_count": 74,
            "chunk_count_is_identity": False,
        },
    )
    result = validate_activation(
        activation,
        _catalog(_entry()),
        LiveProcessSnapshot(
            pid=4321,
            executable_path="C:/Python/python.exe",
            process_started_at=NOW,
            listening_ports=(8420,),
        ),
        current_config_sha256=SHA_A,
        current_source_revision="c" * 40,
        current_source_fingerprint=SHA_B,
        live_rag=RagLiveSnapshot(ready=True, model_configured=True),
    )
    assert result.status == "PASS"


def test_rag_activation_rejects_stale_source_or_unready_runtime() -> None:
    activation = RuntimeActivationV1(
        activation_id="activation:rag",
        component="AI_CS_RAG",
        activation_kind="RAG",
        pid=4321,
        executable_path="C:/Python/python.exe",
        manifest_created_at=NOW,
        service_started_at=NOW,
        process_started_at=NOW,
        config_source_path="C:/runtime/ai-cs.ps1",
        config_sha256=SHA_A,
        source_repository_path="C:/src/AI-CS",
        source_revision="c" * 40,
        source_fingerprint=SHA_B,
        rag_identity={
            "model": "qwen3.5:9b",
            "vector_database_path": "C:/runtime/vector_db",
            "active_collection_name": "test_knowledge_v031",
            "ready": True,
            "model_configured": True,
        },
        ports=(8420,),
    )
    result = validate_activation(
        activation,
        _catalog(_entry()),
        LiveProcessSnapshot(
            pid=4321,
            executable_path="C:/Python/python.exe",
            process_started_at=NOW,
            listening_ports=(8420,),
        ),
        current_config_sha256=SHA_A,
        current_source_revision="d" * 40,
        current_source_fingerprint="e" * 64,
        live_rag=RagLiveSnapshot(ready=False, model_configured=True),
    )
    assert result.status == "BLOCKED"
    assert "ACTIVATION_SOURCE_REVISION_MISMATCH" in result.reason_codes
    assert "ACTIVATION_SOURCE_FINGERPRINT_MISMATCH" in result.reason_codes
    assert "ACTIVATION_RAG_NOT_READY" in result.reason_codes


def _facts() -> GateFactsV1:
    return GateFactsV1(
        gates={
            "RC5_OFFLINE_STABILITY_READY": "PASS",
            "REAL_PDD_ADAPTER_READY": "NOT_VERIFIED",
            "REAL_PDD_READ_READY": "NOT_VERIFIED",
            "REAL_PDD_AI_READY": "NOT_VERIFIED",
            "REAL_PDD_CONFIRM_READY": "NOT_VERIFIED",
            "REAL_PDD_SEND_READY": "NOT_VERIFIED",
            "REAL_PDD_AUTO_SEND_READY": "NOT_IN_SCOPE",
        }
    )


def _activation_results() -> dict[str, ActivationValidationResult]:
    passed = ActivationValidationResult(status="PASS", reason_codes=("CURRENT",))
    return {
        "CHANNEL_ENGINE_HOST": passed,
        "AI_CS_PLATFORM": passed,
        "AI_CS_RAG": passed,
    }


@pytest.mark.parametrize("failed_storage", ["buffer", "offline_control", "agent_spool"])
def test_preflight_blocks_storage_failure_without_misreporting_runtime(
    failed_storage: str,
) -> None:
    storage = {
        "host": "PASS",
        "buffer": "PASS",
        "offline_control": "PASS",
        "agent_spool": "PASS",
    }
    storage[failed_storage] = "BLOCKED"
    result = evaluate_preflight(
        activation_results=_activation_results(),
        source_identity={
            "channel_engine": {"working_tree": "CLEAN"},
            "ai_cs": {"working_tree": "CLEAN"},
        },
        storage_statuses=storage,
        gate_facts=_facts(),
        host_real_send_enabled=False,
        agent_real_send_enabled=False,
        real_execution_attempts=0,
        real_sends=0,
        real_receipts=0,
    )
    assert result["runtime_health"]["status"] == "PASS"
    assert result["storage_health"]["status"] == "BLOCKED"
    assert result["pilot_governance_preflight"]["status"] == "BLOCKED"


def test_preflight_blocks_missing_rag_activation() -> None:
    activations = _activation_results()
    del activations["AI_CS_RAG"]
    result = evaluate_preflight(
        activation_results=activations,
        source_identity={
            "channel_engine": {"working_tree": "CLEAN"},
            "ai_cs": {"working_tree": "CLEAN"},
        },
        storage_statuses={
            "host": "PASS",
            "buffer": "PASS",
            "offline_control": "PASS",
            "agent_spool": "PASS",
        },
        gate_facts=_facts(),
        host_real_send_enabled=False,
        agent_real_send_enabled=False,
        real_execution_attempts=0,
        real_sends=0,
        real_receipts=0,
    )
    assert result["runtime_health"]["status"] == "BLOCKED"
    assert any("AI_CS_RAG" in item for item in result["runtime_health"]["reason_codes"])


def test_preflight_blocks_dirty_source_only_in_source_freeze() -> None:
    result = evaluate_preflight(
        activation_results=_activation_results(),
        source_identity={
            "channel_engine": {"working_tree": "DIRTY"},
            "ai_cs": {"working_tree": "CLEAN"},
        },
        storage_statuses={
            "host": "PASS",
            "buffer": "PASS",
            "offline_control": "PASS",
            "agent_spool": "PASS",
        },
        gate_facts=_facts(),
        host_real_send_enabled=False,
        agent_real_send_enabled=False,
        real_execution_attempts=0,
        real_sends=0,
        real_receipts=0,
    )
    assert result["runtime_health"]["status"] == "PASS"
    assert result["source_freeze"]["status"] == "BLOCKED"
    assert result["pilot_governance_preflight"]["status"] == "BLOCKED"


def test_preflight_derives_technical_readiness_but_not_pdd_authorization() -> None:
    result = evaluate_preflight(
        activation_results=_activation_results(),
        source_identity={
            "channel_engine": {"working_tree": "CLEAN"},
            "ai_cs": {"working_tree": "CLEAN"},
        },
        storage_statuses={
            "host": "PASS",
            "buffer": "PASS",
            "offline_control": "PASS",
            "agent_spool": "PASS",
        },
        gate_facts=_facts(),
        host_real_send_enabled=False,
        agent_real_send_enabled=False,
        real_execution_attempts=0,
        real_sends=0,
        real_receipts=0,
    )
    assert result["pilot_governance_preflight"]["status"] == "PASS"
    assert result["derived"]["may_enter_read_only_pilot"] is True
    assert result["derived"]["real_pdd_operation_authorized"] is False


@pytest.mark.parametrize(
    ("host_send", "agent_send", "attempts", "sends", "receipts"),
    [
        (True, False, 0, 0, 0),
        (False, True, 0, 0, 0),
        (False, False, 1, 0, 0),
        (False, False, 0, 1, 0),
        (False, False, 0, 0, 1),
    ],
)
def test_preflight_blocks_any_real_send_safety_violation(
    host_send: bool,
    agent_send: bool,
    attempts: int,
    sends: int,
    receipts: int,
) -> None:
    result = evaluate_preflight(
        activation_results=_activation_results(),
        source_identity={
            "channel_engine": {"working_tree": "CLEAN"},
            "ai_cs": {"working_tree": "CLEAN"},
        },
        storage_statuses={
            "host": "PASS",
            "buffer": "PASS",
            "offline_control": "PASS",
            "agent_spool": "PASS",
        },
        gate_facts=_facts(),
        host_real_send_enabled=host_send,
        agent_real_send_enabled=agent_send,
        real_execution_attempts=attempts,
        real_sends=sends,
        real_receipts=receipts,
    )
    assert result["send_safety"]["status"] == "BLOCKED"
    assert result["pilot_governance_preflight"]["status"] == "BLOCKED"


def test_preflight_accepts_mode_consistent_production_auto_and_blocks_no_grant() -> None:
    state = ControlledAutoRuntimeStateV1(
        revision=2,
        runtime_mode="PRODUCTION_AUTO",
        production_real_send_enabled=True,
        controlled_pilot_send_enabled=False,
        controlled_store_auto_enabled=True,
        ai_cs_store_id="c-store-6639df2982014226",
        platform_store_id="328616090",
        policy_mode="AUTO_LOW_RISK",
        policy_revision=4,
        whitelist_revision="single-store-v1",
        kill_switch_enabled=False,
        changed_by="operator",
        changed_at=NOW,
        reason="explicit activation",
    )
    base = dict(
        activation_results=_activation_results(),
        source_identity={
            "channel_engine": {"working_tree": "CLEAN"},
            "ai_cs": {"working_tree": "CLEAN"},
        },
        storage_statuses={
            "host": "PASS",
            "buffer": "PASS",
            "offline_control": "PASS",
            "agent_spool": "PASS",
        },
        gate_facts=_facts(),
        host_real_send_enabled=True,
        agent_real_send_enabled=False,
        real_execution_attempts=1,
        real_sends=1,
        real_receipts=1,
        send_runtime_state=state,
        observed_ai_cs_store_id=state.ai_cs_store_id,
        observed_platform_store_id=state.platform_store_id,
    )
    result = evaluate_preflight(**base)
    assert result["send_safety"]["status"] == "PASS"
    assert result["derived"]["real_send_enabled"] is True

    blocked = evaluate_preflight(
        **base,
        concrete_send_requested=True,
        concrete_send_has_valid_grant=False,
    )
    assert blocked["send_safety"]["status"] == "BLOCKED"
    assert "CONCRETE_SEND_GRANT_MISSING" in blocked["send_safety"]["reason_codes"]
