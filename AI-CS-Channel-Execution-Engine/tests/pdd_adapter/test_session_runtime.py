from __future__ import annotations

from channel_engine.pdd_adapter import PDDPrototypeSessionRuntime, PDDSessionStatus
from channel_engine.session import (
    ChannelInstanceManager,
    ChannelSessionStore,
    CredentialReference,
    FakeCredentialProvider,
    MessageReliabilityService,
)


def build_runtime(foundation, *, credential_available: bool = True):
    store = ChannelSessionStore(foundation["uow_factory"])
    reference = CredentialReference(
        credential_ref="vault://offline-pdd-prototype/store-1",
        provider="offline-vault",
        version="v1",
    )
    provider = FakeCredentialProvider((reference,) if credential_available else ())
    delivery = MessageReliabilityService(foundation["uow_factory"], store)
    manager = ChannelInstanceManager(store, provider, delivery)
    return PDDPrototypeSessionRuntime(manager), reference


def test_pdd_session_lifecycle_uses_durable_channel_session_runtime(foundation) -> None:
    runtime, reference = build_runtime(foundation)
    created = runtime.create(
        store_id="synthetic-store-1",
        credential_ref=reference,
        instance_id="pdd-prototype-instance-1",
    )
    assert created.status is PDDSessionStatus.CREATED

    connected = runtime.start(created.instance_id)
    assert connected.status is PDDSessionStatus.CONNECTED
    assert connected.store_id == "synthetic-store-1"
    assert runtime.heartbeat(created.instance_id).status is PDDSessionStatus.CONNECTED

    degraded = runtime.simulate_adapter_degraded(created.instance_id)
    assert degraded.status is PDDSessionStatus.DEGRADED
    recovered = runtime.recover(created.instance_id)
    assert recovered.status is PDDSessionStatus.CONNECTED
    assert recovered.session_id != degraded.session_id

    stopped = runtime.stop(created.instance_id)
    assert stopped.status is PDDSessionStatus.EXPIRED
    assert runtime.get(created.instance_id) == stopped


def test_missing_credential_reference_enters_auth_required_without_secret(foundation) -> None:
    runtime, reference = build_runtime(foundation, credential_available=False)
    created = runtime.create(
        store_id="synthetic-store-1",
        credential_ref=reference,
        instance_id="pdd-prototype-auth-required",
    )
    blocked = runtime.start(created.instance_id)

    assert blocked.status is PDDSessionStatus.AUTH_REQUIRED
    assert blocked.failure_code == "CREDENTIAL_REFERENCE_UNAVAILABLE"
    serialized = blocked.model_dump_json().casefold()
    assert "cookie=" not in serialized
    assert "password=" not in serialized
    assert "token=" not in serialized
