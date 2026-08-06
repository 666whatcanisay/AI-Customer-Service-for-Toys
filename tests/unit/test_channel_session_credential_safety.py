from __future__ import annotations

from channel_engine.channel import FakeChannelAdapter
from channel_engine.session import (
    ChannelInstanceManager,
    ChannelSessionStore,
    CredentialReference,
    FakeCredentialProvider,
    MessageReliabilityService,
)
from channel_engine.storage.orm import ChannelRuntimeSessionRow


def test_credential_reference_only_is_persisted_and_never_logged(
    foundation, caplog
) -> None:
    credential = CredentialReference(
        credential_ref="vault://safe-reference/store-a",
        provider="test-vault",
        version="rotation-3",
    )
    store = ChannelSessionStore(foundation["uow_factory"])
    provider = FakeCredentialProvider((credential,))
    manager = ChannelInstanceManager(
        store,
        provider,
        MessageReliabilityService(foundation["uow_factory"], store),
    )
    adapter = FakeChannelAdapter(channel="fake", store_id="store-a")
    instance = manager.create_instance(
        instance_id="credential-safe-instance",
        platform="fake",
        store_id="store-a",
        adapter_type="FakeChannelAdapter",
        credential_ref=credential,
        adapter=adapter,
    )
    view = manager.start_instance(instance.instance_id)

    with foundation["uow_factory"]() as uow:
        assert uow.session is not None
        row = uow.session.get(ChannelRuntimeSessionRow, view.session.session_id)
        assert row is not None
        persisted = {
            "credential_ref": row.credential_ref,
            "provider": row.credential_provider,
            "version": row.credential_version,
            "lease_ref": row.credential_lease_ref,
        }
    serialized = str(persisted).casefold()
    assert persisted["credential_ref"] == "vault://safe-reference/store-a"
    assert persisted["lease_ref"].startswith("lease-ref://")
    for prohibited in (
        "cookie=",
        "token=",
        "password=",
        "secret=",
        "bearer ",
    ):
        assert prohibited not in serialized
    assert "vault://safe-reference/store-a" not in caplog.text
