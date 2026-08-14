from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.reply_router.contracts import (
    ENGINE_AUTOREPLY_V2_REQUIRED_CHECKS,
    EngineAutoreplyV2AcceptanceV1,
)
from scripts import verify_engine_autoreply_v2_readiness as verifier
from scripts.export_reply_router_contract_candidates import (
    reply_router_candidate_fixtures,
)


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ROOT = ROOT / "contracts" / "candidates" / "reply-router-v1"
GATEWAY_SCHEMA = (
    ROOT / "contracts" / "schemas" / "channel-engine-gateway-server.v1.schema.json"
)
ENGINE_COMMIT = "d" * 40


def _fake_engine(tmp_path: Path, *, mode: str = "PASS") -> Path:
    engine_root = tmp_path / "engine"
    schema = engine_root / verifier.ENGINE_GATEWAY_SCHEMA
    schema.parent.mkdir(parents=True)
    schema.write_bytes(GATEWAY_SCHEMA.read_bytes())
    adapter = engine_root / verifier.ENGINE_ACCEPTANCE_ADAPTER
    adapter.parent.mkdir(parents=True)
    required = json.dumps(list(ENGINE_AUTOREPLY_V2_REQUIRED_CHECKS))
    adapter.write_text(
        f"""from __future__ import annotations
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
for name in (
    'candidate-root', 'candidate-manifest-sha256', 'gateway-schema',
    'gateway-raw-sha256', 'gateway-canonical-sha256', 'engine-commit', 'output'
):
    parser.add_argument('--' + name, required=True)
parser.add_argument('--offline-only', action='store_true')
args = parser.parse_args()
assert args.offline_only
assert __import__('os').environ['AI_CS_AUTOREPLY_ACCEPTANCE_OFFLINE_ONLY'] == '1'
checks = {{
    name: {{'status': 'PASS', 'evidence_codes': [name.upper() + '_PASS']}}
    for name in {required}
}}
payload = {{
    'schema_version': 'engine-autoreply-v2-acceptance.v1',
    'engine_commit': args.engine_commit,
    'candidate_manifest_sha256': (
        {'"0" * 64' if mode == 'BAD_MANIFEST' else 'args.candidate_manifest_sha256'}
    ),
    'gateway_wire': '1.0',
    'gateway_raw_sha256': args.gateway_raw_sha256,
    'gateway_canonical_sha256': args.gateway_canonical_sha256,
    'contract_status': 'UNCOORDINATED_CANDIDATE',
    'checks': checks,
    'side_effects': {{
        'engine_source_modified': False,
        'runtime_started': False,
        'pdd_connected': False,
        'real_send_attempted': False,
    }},
    'contains_secret_material': False,
    'contains_customer_data': False,
    'final_status': 'PASS',
}}
Path(args.output).write_text(json.dumps(payload), encoding='utf-8')
""",
        encoding="utf-8",
    )
    return engine_root


def test_engine_acceptance_candidate_fixture_is_strict() -> None:
    fixture = reply_router_candidate_fixtures()[
        "engine-autoreply-v2-acceptance.valid.json"
    ]
    parsed = EngineAutoreplyV2AcceptanceV1.model_validate_json(json.dumps(fixture))
    assert set(parsed.checks) == set(ENGINE_AUTOREPLY_V2_REQUIRED_CHECKS)
    assert parsed.final_status.value == "PASS"

    missing = json.loads(json.dumps(fixture))
    missing["checks"].pop(ENGINE_AUTOREPLY_V2_REQUIRED_CHECKS[0])
    with pytest.raises(ValidationError):
        EngineAutoreplyV2AcceptanceV1.model_validate_json(json.dumps(missing))

    unsafe = json.loads(json.dumps(fixture))
    unsafe["side_effects"]["pdd_connected"] = True
    with pytest.raises(ValidationError):
        EngineAutoreplyV2AcceptanceV1.model_validate_json(json.dumps(unsafe))


def test_readiness_verifier_passes_only_exact_engine_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine_root = _fake_engine(tmp_path)
    monkeypatch.setattr(verifier, "resolve_engine_commit", lambda _root: ENGINE_COMMIT)
    monkeypatch.setattr(
        verifier, "engine_worktree_fingerprint", lambda _root: "e" * 64
    )

    report = verifier.audit_engine_readiness(
        engine_root,
        engine_python=Path(sys.executable),
    )

    assert report["final_status"] == "PASS"
    assert report["blocker_codes"] == []
    assert report["adapter_final_status"] == "PASS"
    assert not any(report["side_effect_attestation"].values())


def test_readiness_verifier_fails_when_engine_adapter_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine_root = _fake_engine(tmp_path)
    (engine_root / verifier.ENGINE_ACCEPTANCE_ADAPTER).unlink()
    monkeypatch.setattr(verifier, "resolve_engine_commit", lambda _root: ENGINE_COMMIT)
    monkeypatch.setattr(
        verifier, "engine_worktree_fingerprint", lambda _root: "e" * 64
    )

    report = verifier.audit_engine_readiness(
        engine_root,
        engine_python=Path(sys.executable),
    )

    assert report["final_status"] == "FAIL"
    assert "ENGINE_ACCEPTANCE_ADAPTER_MISSING" in report["blocker_codes"]
    assert report["adapter_final_status"] is None


def test_readiness_verifier_rejects_mismatched_candidate_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine_root = _fake_engine(tmp_path, mode="BAD_MANIFEST")
    monkeypatch.setattr(verifier, "resolve_engine_commit", lambda _root: ENGINE_COMMIT)
    monkeypatch.setattr(
        verifier, "engine_worktree_fingerprint", lambda _root: "e" * 64
    )

    report = verifier.audit_engine_readiness(
        engine_root,
        engine_python=Path(sys.executable),
    )

    assert report["final_status"] == "FAIL"
    assert "ENGINE_ACCEPTANCE_EVIDENCE_INVALID" in report["blocker_codes"]
    assert report["adapter_final_status"] is None
