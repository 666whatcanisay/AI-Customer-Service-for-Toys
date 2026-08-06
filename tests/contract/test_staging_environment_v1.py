from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from channel_engine.app import create_app
from channel_engine.config import Settings
from channel_engine.environment import (
    AdapterMode,
    CredentialReference,
    EnvironmentProfile,
    EnvironmentProfileError,
    EnvironmentProfileV1,
    ProductionProfileDisabled,
    StagingAction,
    StagingAllowlist,
    StagingDeploymentManifest,
    StagingRuntimeConfigFile,
    StagingSafetyDenied,
    StagingSafetyGuard,
    default_mock_profile,
    load_environment_profile,
)
from channel_engine.execution import FakeExecutor


ROOT = Path(__file__).resolve().parents[2]


def staging_environ() -> dict[str, str]:
    return {
        "CHANNEL_ENGINE_PROFILE": "staging",
        "CHANNEL_ENGINE_GATEWAY_ENDPOINT": "https://ai-cs.staging.invalid",
        "CHANNEL_ENGINE_ADAPTER_MODE": "OBSERVATION_ONLY",
        "CHANNEL_ENGINE_CREDENTIAL_PROVIDER": "secret-manager",
        "CHANNEL_ENGINE_CREDENTIAL_ID": "staging-pdd-observer",
        "CHANNEL_ENGINE_CREDENTIAL_VERSION": "v4",
        "CHANNEL_ENGINE_ACCOUNT_REF": "synthetic-account-1",
        "CHANNEL_ENGINE_POLICY_PROFILE": "staging-observation.v1",
        "CHANNEL_ENGINE_ALLOWED_ACCOUNTS": "synthetic-account-1",
        "CHANNEL_ENGINE_ALLOWED_CONVERSATIONS": "synthetic-conversation-1",
        "CHANNEL_ENGINE_ALLOWED_ACTIONS": (
            "OBSERVE_MESSAGE,REQUEST_DECISION,SIMULATE_SEND_MESSAGE"
        ),
    }


def production_environ() -> dict[str, str]:
    values = staging_environ()
    values.update(
        {
            "CHANNEL_ENGINE_PROFILE": "production",
            "CHANNEL_ENGINE_GATEWAY_ENDPOINT": "https://ai-cs.production.invalid",
            "CHANNEL_ENGINE_ADAPTER_MODE": "PRODUCTION_PREPARATION",
            "CHANNEL_ENGINE_PRODUCTION_ENABLED": "true",
            "CHANNEL_ENGINE_PRODUCTION_CONFIRMATION": (
                "ENABLE_CHANNEL_ENGINE_PRODUCTION"
            ),
        }
    )
    return values


def test_profiles_default_to_mock_and_production_is_default_deny() -> None:
    default = load_environment_profile({})
    assert default == default_mock_profile()
    assert default.profile is EnvironmentProfile.MOCK
    assert default.adapter_mode is AdapterMode.FAKE
    assert default.production_enabled is False
    assert default.automatic_send_enabled is False

    denied = production_environ()
    denied.pop("CHANNEL_ENGINE_PRODUCTION_ENABLED")
    denied.pop("CHANNEL_ENGINE_PRODUCTION_CONFIRMATION")
    with pytest.raises(ProductionProfileDisabled):
        load_environment_profile(denied)

    enabled = load_environment_profile(production_environ())
    assert enabled.profile is EnvironmentProfile.PRODUCTION
    assert enabled.production_enabled is True
    assert enabled.adapter_mode is AdapterMode.PRODUCTION_PREPARATION
    assert enabled.automatic_send_enabled is False
    assert "ENABLE_CHANNEL_ENGINE_PRODUCTION" not in repr(enabled)


def test_staging_profile_requires_https_reference_and_explicit_allowlists() -> None:
    staging = load_environment_profile(staging_environ())
    assert staging.profile_version == "1.0"
    assert staging.profile is EnvironmentProfile.STAGING
    assert staging.gateway_endpoint == "https://ai-cs.staging.invalid"
    assert staging.credential_reference is not None
    assert staging.credential_reference.account_ref == "synthetic-account-1"
    assert staging.allowlist is not None
    assert staging.allowlist.allowed_actions == frozenset(
        {
            StagingAction.OBSERVE_MESSAGE,
            StagingAction.REQUEST_DECISION,
            StagingAction.SIMULATE_SEND_MESSAGE,
        }
    )

    insecure = staging_environ()
    insecure["CHANNEL_ENGINE_GATEWAY_ENDPOINT"] = "http://staging.invalid"
    with pytest.raises(ValidationError, match="require HTTPS"):
        load_environment_profile(insecure)

    empty = staging_environ()
    empty["CHANNEL_ENGINE_ALLOWED_CONVERSATIONS"] = ""
    with pytest.raises(ValidationError):
        load_environment_profile(empty)


def test_staging_guard_limits_account_conversation_and_action() -> None:
    profile = load_environment_profile(staging_environ())
    guard = StagingSafetyGuard(profile)
    allowed = guard.assert_allowed(
        account_ref="synthetic-account-1",
        conversation_id="synthetic-conversation-1",
        action=StagingAction.OBSERVE_MESSAGE,
    )
    assert allowed.allowed is True

    cases = [
        ("other-account", "synthetic-conversation-1", StagingAction.OBSERVE_MESSAGE),
        ("synthetic-account-1", "other-conversation", StagingAction.OBSERVE_MESSAGE),
        ("synthetic-account-1", "synthetic-conversation-1", StagingAction.REFUND),
        (
            "synthetic-account-1",
            "synthetic-conversation-1",
            StagingAction.MODIFY_ORDER,
        ),
        ("synthetic-account-1", "synthetic-conversation-1", StagingAction.PAYMENT),
        (
            "synthetic-account-1",
            "synthetic-conversation-1",
            StagingAction.SEND_MESSAGE,
        ),
    ]
    for account, conversation, action in cases:
        with pytest.raises(StagingSafetyDenied):
            guard.assert_allowed(
                account_ref=account,
                conversation_id=conversation,
                action=action,
            )


def test_configuration_accepts_references_only_and_rejects_secret_fields() -> None:
    reference = CredentialReference(
        provider="secret-manager",
        credential_id="staging-observer",
        version="v1",
        account_ref="synthetic-account-1",
    )
    serialized = reference.model_dump(mode="json")
    assert set(serialized) == {
        "provider",
        "credential_id",
        "version",
        "account_ref",
    }
    with pytest.raises(ValidationError, match="Extra inputs"):
        CredentialReference.model_validate(
            {**serialized, "secret_value": "prohibited-value"}
        )
    with pytest.raises(EnvironmentProfileError, match="secret values are prohibited"):
        load_environment_profile(
            {
                **staging_environ(),
                "CHANNEL_ENGINE_CREDENTIAL_SECRET": "prohibited-value",
            }
        )
    with pytest.raises(ValueError, match="cannot enable a real channel"):
        Settings(environment_profile=load_environment_profile(staging_environ()), real_channel_enabled=True)


def test_deployment_manifests_are_valid_ordered_and_secretless() -> None:
    runtime_path = ROOT / "deploy" / "staging" / "runtime-config.json"
    deployment_path = ROOT / "deploy" / "staging" / "deployment-manifest.json"
    runtime_payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    deployment_payload = json.loads(deployment_path.read_text(encoding="utf-8"))

    runtime = StagingRuntimeConfigFile.model_validate_json(
        runtime_path.read_text(encoding="utf-8")
    )
    deployment = StagingDeploymentManifest.model_validate_json(
        deployment_path.read_text(encoding="utf-8")
    )
    assert runtime.runtime.profile is EnvironmentProfile.STAGING
    assert deployment.health.liveness == "/health"
    assert deployment.health.aggregate_readiness == "/control/v1/health"
    assert deployment.startup_order[0] == "runtime-store"
    assert deployment.shutdown_order == tuple(reversed(deployment.startup_order))
    assert deployment.production_deployment_enabled is False
    assert deployment.real_channel_enabled is False
    assert deployment.automatic_send_enabled is False

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for item in value.values() for key in keys(item)}
        if isinstance(value, list):
            return {key for item in value for key in keys(item)}
        return set()

    all_keys = {key.casefold() for key in keys([runtime_payload, deployment_payload])}
    assert not all_keys & {
        "secret",
        "secret_value",
        "token",
        "password",
        "cookie",
        "private_key",
    }


def test_staging_app_enforces_allowlist_before_mock_runtime(tmp_path) -> None:
    profile = load_environment_profile(staging_environ())
    executor = FakeExecutor()
    application = create_app(
        settings=Settings(
            database_url=f"sqlite:///{(tmp_path / 'staging-app.sqlite3').as_posix()}",
            environment_profile=profile,
        ),
        executor=executor,
    )
    with TestClient(application) as client:
        denied = client.post(
            "/v1/fake-channel/messages",
            json={
                "conversation_external_ref": "not-allowlisted",
                "external_message_id": "denied-staging-message",
                "text": "synthetic staging message",
            },
        )
        allowed = client.post(
            "/v1/fake-channel/messages",
            json={
                "conversation_external_ref": "synthetic-conversation-1",
                "external_message_id": "allowed-staging-message",
                "text": "synthetic staging message",
            },
        )
        health = client.get("/health")

        assert denied.status_code == 403
        assert denied.json()["detail"] == "STAGING_CONVERSATION_NOT_ALLOWLISTED"
        assert allowed.status_code == 200
        assert health.json()["environment"] == "staging"
        assert health.json()["adapter_mode"] == "OBSERVATION_ONLY"
        approval = client.post(
            f"/v1/decisions/{allowed.json()['decision_id']}/approve",
            json={"operator": "staging-human-operator"},
        )
        assert approval.status_code == 202
        assert executor.call_count == 0
        worker_result = application.state.execution_worker.run_once()
        assert worker_result is not None
        assert executor.call_count == 1
        assert application.state.fake_pdd_adapter.send_call_count == 0
