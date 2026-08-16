from __future__ import annotations

from datetime import datetime, timedelta, timezone

from channel_engine.channel import FakeChannelAdapter, store_scoped_conversation_ref
from channel_engine.conversation import ConversationService
from channel_engine.session import (
    ChannelInstanceManager,
    ChannelInstanceStatus,
    ChannelSessionStatus,
    ChannelSessionStore,
    CredentialReference,
    FakeCredentialProvider,
    InboundEnvelope,
    MessageReliabilityService,
)
from channel_engine.channel import ChannelMessageV1


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def credential(store_id: str) -> CredentialReference:
    return CredentialReference(
        credential_ref=f"vault://multi-store/{store_id}",
        provider="test-vault",
        version="v1",
    )


def test_multi_store_start_health_recovery_and_data_isolation(foundation) -> None:
    store = ChannelSessionStore(foundation["uow_factory"])
    ref_a = credential("store-a")
    ref_b = credential("store-b")
    ref_c = credential("store-c")
    provider = FakeCredentialProvider((ref_a, ref_c))
    delivery = MessageReliabilityService(foundation["uow_factory"], store)
    manager = ChannelInstanceManager(store, provider, delivery)
    adapters = {
        store_id: FakeChannelAdapter(channel="fake", store_id=store_id)
        for store_id in ("store-a", "store-b", "store-c")
    }
    instances = {
        store_id: manager.create_instance(
            instance_id=f"instance-{store_id}",
            platform="fake",
            store_id=store_id,
            adapter_type="FakeChannelAdapter",
            credential_ref=ref,
            adapter=adapters[store_id],
        )
        for store_id, ref in {
            "store-a": ref_a,
            "store-b": ref_b,
            "store-c": ref_c,
        }.items()
    }

    manager.start_all()

    assert manager.get_instance(instances["store-a"].instance_id).status is (
        ChannelInstanceStatus.CONNECTED
    )
    assert manager.get_instance(instances["store-b"].instance_id).status is (
        ChannelInstanceStatus.AUTH_REQUIRED
    )
    repeated_auth = manager.start_instance(instances["store-b"].instance_id)
    assert repeated_auth.instance.status is ChannelInstanceStatus.AUTH_REQUIRED
    assert repeated_auth.session.status is ChannelSessionStatus.AUTH_REQUIRED
    assert manager.get_instance(instances["store-c"].instance_id).status is (
        ChannelInstanceStatus.CONNECTED
    )

    adapters["store-c"].simulate_degraded("STORE_C_ADAPTER_FAILURE")
    manager.heartbeat_instance(instances["store-c"].instance_id)
    assert manager.get_instance(instances["store-c"].instance_id).status is (
        ChannelInstanceStatus.DEGRADED
    )
    assert manager.get_instance(instances["store-a"].instance_id).status is (
        ChannelInstanceStatus.CONNECTED
    )
    assert manager.get_instance(instances["store-b"].instance_id).status is (
        ChannelInstanceStatus.AUTH_REQUIRED
    )

    provider.add_reference(ref_b)
    recovered_b = manager.recover_instance(instances["store-b"].instance_id)
    recovered_c = manager.recover_instance(instances["store-c"].instance_id)
    assert recovered_b.instance.status is ChannelInstanceStatus.CONNECTED
    assert recovered_b.session.status is ChannelSessionStatus.CONNECTED
    assert recovered_c.instance.status is ChannelInstanceStatus.CONNECTED
    assert len(store.list_sessions(instances["store-c"].instance_id)) == 2

    for store_id, content in (
        ("store-a", "store A isolated content"),
        ("store-c", "store C isolated content"),
    ):
        instance_id = instances[store_id].instance_id
        delivery.persist(
            instance_id,
            (
                InboundEnvelope(
                    message=ChannelMessageV1(
                        message_id="same-platform-message-id",
                        channel="fake",
                        store_id=store_id,
                        conversation_id="same-conversation-id",
                        sender="synthetic-customer",
                        content=content,
                        timestamp=NOW,
                    ),
                    source_cursor="source:1",
                    source_sequence=1,
                ),
            ),
        )
    a_delivery = delivery.receive_pending(instances["store-a"].instance_id)[0]
    c_delivery = delivery.receive_pending(instances["store-c"].instance_id)[0]
    assert a_delivery.message.content == "store A isolated content"
    assert c_delivery.message.content == "store C isolated content"
    assert a_delivery.delivery_id != c_delivery.delivery_id


def test_same_platform_conversation_id_is_store_qualified(foundation) -> None:
    service = ConversationService(
        foundation["uow_factory"], foundation["gateway"]
    )
    messages = tuple(
        ChannelMessageV1(
            message_id="same-external-message",
            channel="fake",
            store_id=store_id,
            conversation_id="same-external-conversation",
            sender="synthetic-customer",
            content=f"isolated message for {store_id}",
            timestamp=NOW,
        )
        for store_id in ("store-a", "store-b")
    )

    first = service.receive(messages[0].to_runtime_message())
    second = service.receive(messages[1].to_runtime_message())

    assert first.conversation_id != second.conversation_id
    assert "store_id" not in messages[0].to_runtime_message().model_dump()
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        for store_id in ("store-a", "store-b"):
            scoped_ref = store_scoped_conversation_ref(
                store_id,
                "same-external-conversation",
            )
            assert repo.find_conversation("fake", scoped_ref) is not None


def test_adapter_restart_resumes_persisted_source_cursor(foundation) -> None:
    store = ChannelSessionStore(foundation["uow_factory"])
    ref = credential("restart-store")
    provider = FakeCredentialProvider((ref,))
    delivery = MessageReliabilityService(foundation["uow_factory"], store)
    first_manager = ChannelInstanceManager(store, provider, delivery)
    first_adapter = FakeChannelAdapter(channel="fake", store_id="restart-store")
    instance = first_manager.create_instance(
        instance_id="instance-restart-store",
        platform="fake",
        store_id="restart-store",
        adapter_type="FakeChannelAdapter",
        credential_ref=ref,
        adapter=first_adapter,
    )
    first_manager.start_instance(instance.instance_id)
    from channel_engine.channel import FakeChannelInbound

    first_adapter.enqueue_message(
        FakeChannelInbound(
            message_id="restart-message-1",
            conversation_id="restart-conversation",
            sender="synthetic-customer",
            content="first persisted message",
            timestamp=NOW,
        )
    )
    first_delivery = first_manager.poll_messages(instance.instance_id)[0]
    assert delivery.get_cursor(instance.instance_id).last_sequence == 1

    replacement_manager = ChannelInstanceManager(store, provider, delivery)
    replacement_adapter = FakeChannelAdapter(
        channel="fake", store_id="restart-store"
    )
    replacement_manager.attach_adapter(instance.instance_id, replacement_adapter)
    replacement_manager.start_instance(instance.instance_id)
    replacement_adapter.enqueue_message(
        FakeChannelInbound(
            message_id="restart-message-2",
            conversation_id="restart-conversation",
            sender="synthetic-customer",
            content="second persisted message",
            timestamp=NOW,
        )
    )

    deliveries = replacement_manager.poll_messages(instance.instance_id)
    assert [item.source_sequence for item in deliveries] == [1, 2]
    assert deliveries[0].delivery_id == first_delivery.delivery_id
    assert delivery.get_cursor(instance.instance_id).last_sequence == 2


class MutableClock:
    def __init__(self) -> None:
        self.current = NOW

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def test_expired_session_creates_new_recoverable_session(foundation) -> None:
    clock = MutableClock()
    store = ChannelSessionStore(foundation["uow_factory"])
    ref = credential("expiring-store")
    provider = FakeCredentialProvider(
        (ref,), lease_ttl=timedelta(seconds=1), clock=clock
    )
    delivery = MessageReliabilityService(
        foundation["uow_factory"], store, clock=clock
    )
    manager = ChannelInstanceManager(
        store, provider, delivery, clock=clock
    )
    adapter = FakeChannelAdapter(
        channel="fake", store_id="expiring-store", clock=clock
    )
    instance = manager.create_instance(
        instance_id="instance-expiring-store",
        platform="fake",
        store_id="expiring-store",
        adapter_type="FakeChannelAdapter",
        credential_ref=ref,
        adapter=adapter,
    )
    first = manager.start_instance(instance.instance_id)
    first_session_id = first.session.session_id

    clock.advance(timedelta(seconds=2))
    expired = manager.heartbeat_instance(instance.instance_id)
    assert expired.instance.status is ChannelInstanceStatus.AUTH_REQUIRED
    assert expired.session.status is ChannelSessionStatus.EXPIRED

    recovered = manager.recover_instance(instance.instance_id)
    assert recovered.instance.status is ChannelInstanceStatus.CONNECTED
    assert recovered.session.status is ChannelSessionStatus.CONNECTED
    assert recovered.session.session_id != first_session_id
    assert len(store.list_sessions(instance.instance_id)) == 2
