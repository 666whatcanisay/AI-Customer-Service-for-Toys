from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from channel_engine.pdd_adapter._base import PDDPrototypeModel


class PDDMessageSourceKind(StrEnum):
    BROWSER_OBSERVATION = "BROWSER_OBSERVATION"
    NETWORK_OBSERVATION = "NETWORK_OBSERVATION"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"


class PDDRawMetadata(PDDPrototypeModel):
    """Allowlisted metadata only; the platform payload is never retained."""

    source_kind: PDDMessageSourceKind
    source_event_ref_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    cursor_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_sequence: int | None = Field(default=None, ge=1)
    selector_contract_id: str = Field(min_length=1, max_length=160)
    mapping_contract_id: Literal["pdd:merchant_chat:message:v1"] = (
        "pdd:merchant_chat:message:v1"
    )
    observed_at: AwareDatetime
    synthetic_test_data: Literal[True] = True
    secret_material_captured: Literal[False] = False
    raw_payload_retained: Literal[False] = False


class PDDConversation(PDDPrototypeModel):
    conversation_id: str = Field(min_length=1, max_length=255)
    external_id: str = Field(min_length=1, max_length=255)
    store_id: str = Field(min_length=1, max_length=128)


class PDDMessageEnvelope(PDDPrototypeModel):
    external_message_id: str = Field(min_length=1, max_length=255)
    sender: Literal["customer"] = "customer"
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
        repr=False,
    )
    timestamp: AwareDatetime
    raw_metadata: PDDRawMetadata
    store_id: str = Field(min_length=1, max_length=128)
    conversation_external_id: str = Field(min_length=1, max_length=255)

    @field_validator("external_message_id", "store_id", "conversation_external_id")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise ValueError("PDD identifier contains control characters")
        return value


class PDDMessageSourceRecord(PDDPrototypeModel):
    """Non-sensitive provenance retained alongside the normalized message."""

    external_message_id_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    conversation_id_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_event_ref_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    cursor_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_sequence: int | None = Field(default=None, ge=1)
    selector_contract_id: str = Field(min_length=1, max_length=160)
    mapping_contract_id: Literal["pdd:merchant_chat:message:v1"] = (
        "pdd:merchant_chat:message:v1"
    )
    source_kind: PDDMessageSourceKind
    observed_at: AwareDatetime
    synthetic_test_data: Literal[True] = True


__all__ = [
    "PDDConversation",
    "PDDMessageEnvelope",
    "PDDMessageSourceKind",
    "PDDMessageSourceRecord",
    "PDDRawMetadata",
]
