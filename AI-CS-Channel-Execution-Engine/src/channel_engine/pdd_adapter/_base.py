from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


PDD_ADAPTER_PROTOTYPE_VERSION = "1.0"


class PDDPrototypeModel(BaseModel):
    """Immutable, closed model shared by the offline PDD prototype."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    prototype_version: Literal["1.0"] = PDD_ADAPTER_PROTOTYPE_VERSION


__all__ = ["PDD_ADAPTER_PROTOTYPE_VERSION", "PDDPrototypeModel"]
