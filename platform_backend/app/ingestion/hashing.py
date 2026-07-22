"""Stable hashes used for file identity, exact duplicates, and conflicts."""

import hashlib
import json
from typing import Any


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def stable_row_hash(normalized_data: dict[str, Any]) -> str:
    canonical = json.dumps(
        normalized_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def stable_identity_key(normalized_data: dict[str, Any]) -> str:
    identity = {
        "tenant_id": normalized_data.get("tenant_id"),
        "platform": normalized_data.get("platform"),
        "store_code": normalized_data.get("store_code"),
        "product": normalized_data.get("product_code")
        or normalized_data.get("platform_product_id"),
        "sku": normalized_data.get("sku_code") or normalized_data.get("platform_sku_id"),
    }
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
