from __future__ import annotations

import uuid
from datetime import datetime, timezone
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


CONTRACT_VERSION = "1.0"
CONTRACT_SCHEMA_ID = "urn:ai-cs:channel-engine:gateway-contract:v1"
GATEWAY_VERSION = "ai-cs-gateway.v1"
CAPABILITY_VERSION = "decision.ai-cs-scope.v1"
GATEWAY_PREFIX = "/gateway/v1"
DECISION_PATH = f"{GATEWAY_PREFIX}/decisions"
HEALTH_PATH = f"{GATEWAY_PREFIX}/health"
GATEWAY_MEDIA_TYPE = "application/vnd.ai-cs.channel-engine.gateway-v1+json"
GATEWAY_ACCEPTED_MEDIA_TYPES = frozenset({GATEWAY_MEDIA_TYPE, "application/json"})
MAX_DECISION_BODY_BYTES = 64 * 1024

Identifier: TypeAlias = Annotated[
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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GatewayModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
    )


class DecisionAction(StrEnum):
    SUGGEST_REPLY = "SUGGEST_REPLY"
    NO_ACTION = "NO_ACTION"


GatewayDecisionAction = DecisionAction


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
    idempotency_key: Identifier
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
    idempotency_key: Identifier
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
    def validate_action_content(self) -> "DecisionResponse":
        if (
            self.action is DecisionAction.SUGGEST_REPLY
            and self.proposed_content is None
        ):
            raise ValueError("SUGGEST_REPLY requires proposed_content")
        if (
            self.action is DecisionAction.NO_ACTION
            and self.proposed_content is not None
        ):
            raise ValueError("NO_ACTION requires proposed_content to be null")
        return self


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
    def validate_retry_policy(self) -> "GatewayError":
        expected = self.code in RETRYABLE_ERROR_CODES
        if self.retryable is not expected:
            raise ValueError(f"{self.code.value} retryable policy mismatch")
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


class GatewayProblem(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: GatewayErrorCode,
        message: str,
        request_id: str | None = None,
        correlation_id: str | None = None,
        retry_after_seconds: int | None = None,
        details: JsonObject | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.safe_message = message
        self.request_id = request_id
        self.correlation_id = correlation_id
        self.retry_after_seconds = retry_after_seconds
        self.details = details or {}

    def envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(
            contract_version=CONTRACT_VERSION,
            error=GatewayError(
                error_id=f"error-{uuid.uuid4().hex}",
                code=self.code,
                message=self.safe_message,
                retryable=self.code in RETRYABLE_ERROR_CODES,
                retry_after_seconds=self.retry_after_seconds,
                request_id=self.request_id,
                correlation_id=self.correlation_id,
                details=self.details,
                occurred_at=utc_now(),
            ),
        )


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


GatewayArtifact: TypeAlias = (
    DecisionRequest
    | DecisionResponse
    | ErrorEnvelope
    | GatewayHealth
    | AuthenticationMetadata
)


def gateway_contract_schema() -> dict[str, Any]:
    """Return the frozen Production Gateway Contract V1 schema."""
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
