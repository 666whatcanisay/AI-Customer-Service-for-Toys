from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from threading import RLock

from channel_engine.channel.adapter_foundation import ChannelMessageV1
from channel_engine.pdd_adapter._base import PDDPrototypeModel
from channel_engine.pdd_adapter.message import (
    PDDConversation,
    PDDMessageEnvelope,
    PDDMessageSourceRecord,
)
from channel_engine.pdd_adapter.selector import (
    PDD_REQUIRED_MESSAGE_PURPOSES,
    PDDVerifiedSelectorToken,
)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class PDDMessageMappingError(ValueError):
    pass


class PDDMessageIdentityConflict(PDDMessageMappingError):
    pass


class PDDDeduplicationStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"


class PDDMappedMessage(PDDPrototypeModel):
    message: ChannelMessageV1
    source: PDDMessageSourceRecord
    deduplication_key: str
    normalized_fingerprint: str


class PDDDeduplicationResult(PDDPrototypeModel):
    status: PDDDeduplicationStatus
    mapped: PDDMappedMessage


class PDDMessageMapper:
    mapping_contract_id = "pdd:merchant_chat:message:v1"

    def __init__(self, selector_token: PDDVerifiedSelectorToken) -> None:
        if not selector_token.synthetic_test_data:
            raise PDDMessageMappingError(
                "prototype mapping accepts verified synthetic selectors only"
            )
        if not PDD_REQUIRED_MESSAGE_PURPOSES.issubset(selector_token.purposes):
            raise PDDMessageMappingError(
                "verified selector token lacks message observation purposes"
            )
        self._selector_token = selector_token

    def map(
        self,
        envelope: PDDMessageEnvelope,
        conversation: PDDConversation,
    ) -> PDDMappedMessage:
        if envelope.store_id != conversation.store_id:
            raise PDDMessageMappingError("message and conversation store mismatch")
        if envelope.conversation_external_id != conversation.external_id:
            raise PDDMessageMappingError("message and conversation identity mismatch")
        if envelope.raw_metadata.selector_contract_id != self._selector_token.contract_id:
            raise PDDMessageMappingError("message source selector contract mismatch")
        if envelope.raw_metadata.mapping_contract_id != self.mapping_contract_id:
            raise PDDMessageMappingError("message mapping contract mismatch")

        message = ChannelMessageV1(
            message_id=envelope.external_message_id,
            channel="pdd",
            store_id=envelope.store_id,
            conversation_id=conversation.external_id,
            sender=envelope.sender,
            content=envelope.content,
            timestamp=envelope.timestamp,
        )
        source = PDDMessageSourceRecord(
            external_message_id_digest=_digest(envelope.external_message_id),
            conversation_id_digest=_digest(conversation.external_id),
            source_event_ref_digest=envelope.raw_metadata.source_event_ref_digest,
            payload_digest=envelope.raw_metadata.payload_digest,
            cursor_digest=envelope.raw_metadata.cursor_digest,
            source_sequence=envelope.raw_metadata.source_sequence,
            selector_contract_id=envelope.raw_metadata.selector_contract_id,
            mapping_contract_id=envelope.raw_metadata.mapping_contract_id,
            source_kind=envelope.raw_metadata.source_kind,
            observed_at=envelope.raw_metadata.observed_at,
        )
        return PDDMappedMessage(
            message=message,
            source=source,
            deduplication_key=_digest(
                [envelope.store_id, conversation.external_id, envelope.external_message_id]
            ),
            normalized_fingerprint=_digest(message.model_dump(mode="json")),
        )


class PDDMessageDeduplicator:
    """Keeps identity and payload digests only; conflicting duplicates fail closed."""

    def __init__(self) -> None:
        self._fingerprints: dict[str, str] = {}
        self._lock = RLock()

    def accept(self, mapped: PDDMappedMessage) -> PDDDeduplicationResult:
        with self._lock:
            previous = self._fingerprints.get(mapped.deduplication_key)
            if previous is None:
                self._fingerprints[mapped.deduplication_key] = (
                    mapped.normalized_fingerprint
                )
                status = PDDDeduplicationStatus.ACCEPTED
            elif previous == mapped.normalized_fingerprint:
                status = PDDDeduplicationStatus.DUPLICATE
            else:
                raise PDDMessageIdentityConflict(
                    "external message identity was reused with different content"
                )
        return PDDDeduplicationResult(status=status, mapped=mapped)

    @property
    def identity_count(self) -> int:
        with self._lock:
            return len(self._fingerprints)


__all__ = [
    "PDDDeduplicationResult",
    "PDDDeduplicationStatus",
    "PDDMappedMessage",
    "PDDMessageDeduplicator",
    "PDDMessageIdentityConflict",
    "PDDMessageMapper",
    "PDDMessageMappingError",
]
