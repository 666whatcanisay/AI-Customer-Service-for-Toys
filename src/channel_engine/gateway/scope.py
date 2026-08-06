from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AICSScope(BaseModel):
    """Compatibility scope required by the real AI-CS Gateway decision path."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    tenant_id: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=40)
    store_code: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=100)
    sku_id: str | None = Field(default=None, max_length=100)

    @field_validator("tenant_id", "platform", "store_code", "product_id")
    @classmethod
    def validate_required_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or "\r" in normalized or "\n" in normalized:
            raise ValueError("AI-CS scope identifiers must be nonblank single lines")
        return normalized

    @field_validator("sku_id")
    @classmethod
    def validate_optional_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if "\r" in normalized or "\n" in normalized:
            raise ValueError("AI-CS sku_id must be a single line")
        return normalized

    def as_gateway_context(self) -> dict[str, object]:
        return {"ai_cs_scope": self.model_dump(mode="json")}


__all__ = ["AICSScope"]
