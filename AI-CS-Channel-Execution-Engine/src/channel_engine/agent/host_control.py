from __future__ import annotations

import os
import socket
from datetime import datetime
from pathlib import Path

from channel_agent.control_v2 import (
    DeviceRequestVerifier,
    LANHostCandidate,
    ReplayNonceStore,
    ServiceRequestVerifier,
    certificate_sha256,
    decode_pairing_credential,
    encode_pairing_credential,
)
from channel_agent.security import WindowsDeviceCredentialStore

from .control_v2 import DeviceCredentialIndex, HostPairingService


def build_agent_control_v2_from_env(
    *,
    server_version: str,
    nonce_store: ReplayNonceStore | None = None,
) -> tuple[HostPairingService, DeviceRequestVerifier] | None:
    """Build the signed device control plane without importing the dev application.

    The production host and the compatibility application share this factory so the
    security-sensitive pairing/index construction cannot drift between entrypoints.
    """

    if os.getenv("CHANNEL_ENGINE_AGENT_CONTROL_V2_ENABLED", "").casefold() != "true":
        return None
    required = {
        "host_id": os.getenv("CHANNEL_ENGINE_AGENT_HOST_ID", "").strip(),
        "server_url": os.getenv("CHANNEL_ENGINE_AGENT_PUBLIC_URL", "").strip(),
        "ca_path": os.getenv("CHANNEL_ENGINE_AGENT_CA_CERTIFICATE", "").strip(),
        "index_path": os.getenv("CHANNEL_ENGINE_DEVICE_CREDENTIAL_INDEX", "").strip(),
    }
    if any(not value for value in required.values()):
        raise ValueError("Agent Control V2 environment is incomplete")

    credential_store = WindowsDeviceCredentialStore()
    pairing_reference = os.getenv(
        "CHANNEL_ENGINE_AGENT_PAIRING_CREDENTIAL_REFERENCE", ""
    ).strip()
    legacy_pairing_code = os.getenv(
        "CHANNEL_ENGINE_AGENT_PAIRING_CODE", ""
    ).strip()
    pairing_expires_at = None
    rotation_sink = None
    if pairing_reference:
        credential = decode_pairing_credential(
            credential_store.acquire(pairing_reference).for_signing()
        )
        pairing_code = credential.pairing_code
        pairing_expires_at = credential.expires_at

        def publish_pairing_code(code: str, expires_at: datetime) -> None:
            credential_store.put(
                pairing_reference,
                encode_pairing_credential(code, expires_at),
            )

        rotation_sink = publish_pairing_code
    elif legacy_pairing_code:
        pairing_code = legacy_pairing_code
    else:
        raise ValueError("Agent Control V2 pairing credential is unavailable")

    ca_path = Path(required["ca_path"])
    ca_pem = ca_path.read_text(encoding="utf-8")
    candidate = LANHostCandidate(
        host_id=required["host_id"],
        host_name=socket.gethostname(),
        environment=os.getenv(
            "CHANNEL_ENGINE_AGENT_ENVIRONMENT", "STAGING"
        ).upper(),
        server_url=required["server_url"],
        server_version=server_version,
        certificate_sha256=certificate_sha256(ca_pem),
        ca_certificate_pem=ca_pem,
    )
    index = DeviceCredentialIndex(
        required["index_path"],
        credential_store,
    )
    pairing = HostPairingService(
        candidate,
        pairing_code,
        index,
        expires_at=pairing_expires_at,
        rotation_sink=rotation_sink,
    )
    return pairing, DeviceRequestVerifier(index.resolve, nonce_store=nonce_store)


def build_ai_cs_service_verifier_from_env(
    *,
    nonce_store: ReplayNonceStore | None = None,
) -> ServiceRequestVerifier | None:
    if os.getenv("CHANNEL_ENGINE_AI_CS_SERVICE_CONTROL_ENABLED", "").casefold() != "true":
        return None
    service_id = os.getenv("CHANNEL_ENGINE_AI_CS_SERVICE_ID", "").strip()
    key_id = os.getenv("CHANNEL_ENGINE_AI_CS_SERVICE_KEY_ID", "").strip()
    credential_reference = os.getenv(
        "CHANNEL_ENGINE_AI_CS_SERVICE_CREDENTIAL_REFERENCE", ""
    ).strip()
    if not service_id or not key_id or not credential_reference:
        raise ValueError("AI-CS service control identity is incomplete")
    credential_store = WindowsDeviceCredentialStore()

    def resolve(candidate_service_id: str, candidate_key_id: str) -> bytes:
        if candidate_service_id != service_id or candidate_key_id != key_id:
            raise PermissionError("AI-CS service identity is not authorized")
        return credential_store.acquire(credential_reference).for_signing()

    return ServiceRequestVerifier(resolve, nonce_store=nonce_store)


__all__ = [
    "build_agent_control_v2_from_env",
    "build_ai_cs_service_verifier_from_env",
]
