from __future__ import annotations

import pytest

from channel_engine.pdd_adapter import (
    PDDConversation,
    PDDDeduplicationStatus,
    PDDMessageDeduplicator,
    PDDMessageIdentityConflict,
    PDDMessageMapper,
    PDDMessageMappingError,
)

from .helpers import message_envelope, verified_selector_token


def test_pdd_message_maps_to_channel_message_v1_with_sanitized_provenance() -> None:
    token = verified_selector_token()
    envelope = message_envelope(token=token)
    conversation = PDDConversation(
        conversation_id="prototype-conversation-internal-1",
        external_id=envelope.conversation_external_id,
        store_id=envelope.store_id,
    )

    mapped = PDDMessageMapper(token).map(envelope, conversation)

    assert mapped.message.channel == "pdd"
    assert mapped.message.store_id == "synthetic-store-1"
    assert mapped.message.message_id == "synthetic-message-1"
    assert mapped.message.conversation_id == "synthetic-conversation-1"
    assert mapped.message.content == "synthetic customer question"
    assert mapped.source.selector_contract_id == token.contract_id
    assert mapped.source.source_event_ref_digest == (
        envelope.raw_metadata.source_event_ref_digest
    )
    serialized_source = mapped.source.model_dump(mode="json")
    assert "raw_payload" not in serialized_source
    assert "cookie" not in str(serialized_source).casefold()
    assert "token" not in str(serialized_source).casefold()
    assert len(mapped.deduplication_key) == 64


def test_pdd_message_deduplication_is_idempotent_and_conflicts_fail_closed() -> None:
    token = verified_selector_token()
    mapper = PDDMessageMapper(token)
    deduplicator = PDDMessageDeduplicator()
    conversation = PDDConversation(
        conversation_id="prototype-conversation-internal-1",
        external_id="synthetic-conversation-1",
        store_id="synthetic-store-1",
    )
    first = mapper.map(message_envelope(token=token), conversation)
    duplicate = mapper.map(message_envelope(token=token), conversation)
    conflict = mapper.map(
        message_envelope(token=token, content="changed synthetic content"),
        conversation,
    )

    assert deduplicator.accept(first).status is PDDDeduplicationStatus.ACCEPTED
    assert deduplicator.accept(duplicate).status is PDDDeduplicationStatus.DUPLICATE
    with pytest.raises(PDDMessageIdentityConflict):
        deduplicator.accept(conflict)
    assert deduplicator.identity_count == 1


def test_pdd_message_mapping_rejects_store_and_selector_mismatch() -> None:
    token = verified_selector_token()
    mapper = PDDMessageMapper(token)
    envelope = message_envelope(token=token)
    wrong_store = PDDConversation(
        conversation_id="prototype-conversation-internal-1",
        external_id=envelope.conversation_external_id,
        store_id="another-store",
    )
    with pytest.raises(PDDMessageMappingError, match="store mismatch"):
        mapper.map(envelope, wrong_store)

    mismatched_source = envelope.model_copy(
        update={
            "raw_metadata": envelope.raw_metadata.model_copy(
                update={"selector_contract_id": "pdd:merchant_chat:another-v1"}
            )
        }
    )
    conversation = wrong_store.model_copy(update={"store_id": envelope.store_id})
    with pytest.raises(PDDMessageMappingError, match="selector contract mismatch"):
        mapper.map(mismatched_source, conversation)
