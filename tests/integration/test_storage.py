from __future__ import annotations

from channel_engine.models import Conversation, Event, EventType


def test_event_and_outbox_are_committed_together(foundation) -> None:
    conversation = Conversation(channel_name="fake", external_ref="conversation-storage")
    event = Event(
        aggregate_type="Conversation",
        aggregate_id=conversation.conversation_id,
        event_type=EventType.MESSAGE_RECEIVED,
        payload={"test": True},
        correlation_id="correlation-storage",
    )

    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        repo.save_conversation(conversation)
        repo.append_event(event)

    with foundation["uow_factory"]() as uow:
        pending = uow.require_repository().list_pending_outbox()

    assert len(pending) == 1
    assert pending[0].event_id == event.event_id
    assert pending[0].topic == EventType.MESSAGE_RECEIVED.value


def test_unit_of_work_rolls_back_event_and_outbox_together(foundation) -> None:
    event = Event(
        aggregate_type="Conversation",
        aggregate_id="conv-rollback",
        event_type=EventType.MESSAGE_RECEIVED,
        correlation_id="correlation-rollback",
    )

    try:
        with foundation["uow_factory"]() as uow:
            uow.require_repository().append_event(event)
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    with foundation["uow_factory"]() as uow:
        assert uow.require_repository().list_pending_outbox() == []
