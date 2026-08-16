from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import (
    AliasChoices,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    model_validator,
)

from channel_engine.models.enums import DecisionAction, EventType, ReceiptOutcome


CONTRACT_VERSION = "1.0"
CONTRACT_SCHEMA_ID = "urn:ai-cs:channel-engine:gateway-contract:v1"

Identifier: TypeAlias = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
]
IdempotencyKey: TypeAlias = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
]
MessageText: TypeAlias = Annotated[
    str,
    Field(min_length=1, max_length=8_000, pattern=r"^[\s\S]*\S[\s\S]*$"),
]
ShortText: TypeAlias = Annotated[
    str,
    Field(min_length=1, max_length=512, pattern=r"^[\s\S]*\S[\s\S]*$"),
]
JsonObject: TypeAlias = dict[str, JsonValue]


class GatewayModel(BaseModel):
    """Strict, immutable base for every V1 wire-contract object."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
    )


class GatewayAggregateType(StrEnum):
    CONVERSATION = "Conversation"
    MESSAGE = "Message"
    DECISION = "Decision"
    EXECUTION = "Execution"
    RECEIPT = "Receipt"


class GatewayRiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class GatewayErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    UNSUPPORTED_CONTRACT_VERSION = "UNSUPPORTED_CONTRACT_VERSION"
    IDEMPOTENCY_IN_PROGRESS = "IDEMPOTENCY_IN_PROGRESS"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"


RETRYABLE_ERROR_CODES = frozenset(
    {
        GatewayErrorCode.IDEMPOTENCY_IN_PROGRESS,
        GatewayErrorCode.RATE_LIMITED,
        GatewayErrorCode.INTERNAL_ERROR,
        GatewayErrorCode.SERVICE_UNAVAILABLE,
        GatewayErrorCode.DEADLINE_EXCEEDED,
    }
)


class DecisionRequest(GatewayModel):
    contract_version: Literal[CONTRACT_VERSION]
    request_id: Identifier
    idempotency_key: IdempotencyKey
    correlation_id: Identifier
    conversation_id: Identifier
    message_id: Identifier
    customer_message: MessageText
    context: JsonObject = Field(default_factory=dict)
    requested_at: AwareDatetime


class DecisionResponse(GatewayModel):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"action": {"const": "SUGGEST_REPLY"}},
                        "required": ["action"],
                    },
                    "then": {
                        "properties": {
                            "proposed_content": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 8_000,
                                "pattern": r"^[\s\S]*\S[\s\S]*$",
                            }
                        }
                    },
                },
                {
                    "if": {
                        "properties": {"action": {"const": "NO_ACTION"}},
                        "required": ["action"],
                    },
                    "then": {"properties": {"proposed_content": {"type": "null"}}},
                },
            ]
        }
    )

    contract_version: Literal[CONTRACT_VERSION]
    request_id: Identifier
    idempotency_key: IdempotencyKey
    correlation_id: Identifier
    decision_id: Identifier
    action: DecisionAction
    proposed_content: MessageText | None
    requires_approval: Literal[True]
    risk_level: GatewayRiskLevel
    gateway_version: Annotated[str, Field(min_length=1, max_length=64)]
    metadata: JsonObject = Field(default_factory=dict)
    decided_at: AwareDatetime

    @model_validator(mode="after")
    def validate_action_content(self) -> DecisionResponse:
        if self.action is DecisionAction.SUGGEST_REPLY and self.proposed_content is None:
            raise ValueError("SUGGEST_REPLY requires proposed_content")
        if self.action is DecisionAction.NO_ACTION and self.proposed_content is not None:
            raise ValueError("NO_ACTION requires proposed_content to be null")
        return self


class GatewayHealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"


class GatewayHealth(GatewayModel):
    status: GatewayHealthStatus
    service: Annotated[str, Field(min_length=1, max_length=64)]
    contract_version: Literal[CONTRACT_VERSION]
    version: Annotated[str, Field(min_length=1, max_length=64)] | None
    capabilities: tuple[
        Annotated[str, Field(min_length=1, max_length=128)], ...
    ]
    reachable: bool
    real_ai_cs_connected: bool
    timestamp: AwareDatetime
    details: dict[str, str | int | bool]

    @property
    def gateway_version(self) -> str | None:
        """Compatibility accessor for pre-freeze local callers."""
        return self.version

    @property
    def capability_version(self) -> str | None:
        """Compatibility accessor for the former singular capability field."""
        return self.capabilities[0] if self.capabilities else None

    @property
    def checked_at(self) -> datetime:
        """Compatibility accessor; wire responses use ``timestamp``."""
        return self.timestamp


class ReceiptError(GatewayModel):
    code: Annotated[
        str,
        Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]{0,63}$"),
    ]
    message: ShortText
    retryable: bool


class ExecutionReceipt(GatewayModel):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"outcome": {"const": "SUCCESS"}},
                        "required": ["outcome"],
                    },
                    "then": {
                        "properties": {
                            "error": {"type": "null"},
                            "reconciliation_required": {"const": False},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {"outcome": {"const": "FAILED"}},
                        "required": ["outcome"],
                    },
                    "then": {
                        "properties": {
                            "error": {"not": {"type": "null"}},
                            "reconciliation_required": {"const": False},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {"outcome": {"const": "UNKNOWN"}},
                        "required": ["outcome"],
                    },
                    "then": {
                        "properties": {
                            "error": {"not": {"type": "null"}},
                            "reconciliation_required": {"const": True},
                        }
                    },
                },
            ]
        }
    )

    contract_version: Literal[CONTRACT_VERSION]
    receipt_id: Identifier
    idempotency_key: IdempotencyKey
    correlation_id: Identifier
    execution_id: Identifier
    decision_id: Identifier
    attempt: int = Field(ge=1)
    outcome: ReceiptOutcome
    external_reference: Annotated[str, Field(min_length=1, max_length=256)] | None
    error: ReceiptError | None
    reconciliation_required: bool
    details: JsonObject = Field(default_factory=dict)
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def validate_outcome(self) -> ExecutionReceipt:
        if self.idempotency_key != self.receipt_id:
            raise ValueError("ExecutionReceipt idempotency_key must equal receipt_id")
        if self.outcome is ReceiptOutcome.SUCCESS:
            if self.error is not None or self.reconciliation_required:
                raise ValueError(
                    "SUCCESS requires error=null and reconciliation_required=false"
                )
        elif self.outcome is ReceiptOutcome.FAILED:
            if self.error is None or self.reconciliation_required:
                raise ValueError(
                    "FAILED requires error and reconciliation_required=false"
                )
        elif self.error is None or not self.reconciliation_required:
            raise ValueError(
                "UNKNOWN requires error and reconciliation_required=true"
            )
        return self


class Event(GatewayModel):
    contract_version: Literal[CONTRACT_VERSION]
    event_id: Identifier
    correlation_id: Identifier
    causation_id: Identifier | None
    source: Literal["CHANNEL_ENGINE"]
    event_type: EventType
    aggregate_type: GatewayAggregateType
    aggregate_id: Identifier
    payload: JsonObject = Field(default_factory=dict)
    occurred_at: AwareDatetime


class AuthenticationMetadata(GatewayModel):
    """Normalized representation of the frozen HMAC request headers."""

    contract_version: Literal[CONTRACT_VERSION]
    scheme: Literal["HMAC-SHA256"]
    client_id: Identifier
    key_id: Identifier
    timestamp: AwareDatetime
    nonce: Annotated[
        str,
        Field(min_length=22, max_length=86, pattern=r"^[A-Za-z0-9_-]+$"),
    ]
    content_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    signature: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{43}$")]


class GatewayError(GatewayModel):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "error_code": {
                                "enum": sorted(
                                    code.value for code in RETRYABLE_ERROR_CODES
                                )
                            }
                        },
                        "required": ["error_code"],
                    },
                    "then": {"properties": {"retryable": {"const": True}}},
                    "else": {"properties": {"retryable": {"const": False}}},
                },
                {
                    "if": {
                        "properties": {"retryable": {"const": False}},
                        "required": ["retryable"],
                    },
                    "then": {
                        "properties": {"retry_after_seconds": {"type": "null"}}
                    },
                },
                {
                    "if": {
                        "properties": {"error_code": {"const": "RATE_LIMITED"}},
                        "required": ["error_code"],
                    },
                    "then": {
                        "required": ["retry_after_seconds"],
                        "properties": {
                            "retry_after_seconds": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 3_600,
                            }
                        },
                    },
                },
            ]
        }
    )

    error_id: Identifier
    error_code: GatewayErrorCode = Field(
        validation_alias=AliasChoices("error_code", "code")
    )
    message: ShortText
    retryable: bool
    retry_after_seconds: int | None = Field(default=None, ge=1, le=3_600)
    request_id: Identifier | None
    correlation_id: Identifier | None
    details: JsonObject = Field(default_factory=dict)
    occurred_at: AwareDatetime

    @property
    def code(self) -> GatewayErrorCode:
        """Compatibility accessor; wire responses use ``error_code``."""
        return self.error_code

    @model_validator(mode="after")
    def validate_retry_policy(self) -> GatewayError:
        expected_retryable = self.code in RETRYABLE_ERROR_CODES
        if self.retryable is not expected_retryable:
            raise ValueError(
                f"{self.code.value} requires retryable={str(expected_retryable).lower()}"
            )
        if not self.retryable and self.retry_after_seconds is not None:
            raise ValueError("non-retryable errors cannot set retry_after_seconds")
        if (
            self.code is GatewayErrorCode.RATE_LIMITED
            and self.retry_after_seconds is None
        ):
            raise ValueError("RATE_LIMITED requires retry_after_seconds")
        return self


class ErrorEnvelope(GatewayModel):
    contract_version: Literal[CONTRACT_VERSION]
    error: GatewayError


GatewayArtifact: TypeAlias = (
    DecisionRequest
    | DecisionResponse
    | ErrorEnvelope
    | GatewayHealth
    | AuthenticationMetadata
)


def build_gateway_contract_schema() -> dict[str, Any]:
    """Build the frozen Production Gateway Contract V1 schema bundle."""

    generated = TypeAdapter(GatewayArtifact).json_schema(
        ref_template="#/$defs/{model}"
    )
    generated["oneOf"] = generated.pop("anyOf")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": CONTRACT_SCHEMA_ID,
        "title": "AI-CS Channel Engine Gateway Contract V1",
        "description": (
            "Production Gateway Contract V1 for DecisionRequest, "
            "DecisionResponse, ErrorEnvelope, authenticated GatewayHealth "
            "and normalized HMAC metadata."
        ),
        **generated,
    }
