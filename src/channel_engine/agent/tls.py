from __future__ import annotations

import ipaddress
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from channel_agent.security import (
    DeviceCredentialUnavailable,
    WindowsDeviceCredentialStore,
)


class HostTLSConfigurationError(RuntimeError):
    """The production host TLS boundary is incomplete or unsafe."""


@dataclass(frozen=True, slots=True)
class HostTLSConfiguration:
    certificate_path: Path
    private_key_path: Path
    private_key_credential_reference: str

    @classmethod
    def from_environment(cls) -> "HostTLSConfiguration":
        certificate = os.getenv("CHANNEL_ENGINE_TLS_CERTIFICATE", "").strip()
        private_key = os.getenv("CHANNEL_ENGINE_TLS_PRIVATE_KEY", "").strip()
        reference = os.getenv(
            "CHANNEL_ENGINE_TLS_PRIVATE_KEY_CREDENTIAL_REFERENCE", ""
        ).strip()
        if not certificate or not private_key or not reference:
            raise HostTLSConfigurationError(
                "non-loopback Host Control requires certificate, encrypted private "
                "key and Windows credential reference"
            )
        value = cls(Path(certificate), Path(private_key), reference)
        value.validate()
        return value

    def validate(self) -> None:
        if not self.certificate_path.is_file():
            raise HostTLSConfigurationError("Host Control certificate is unavailable")
        if not self.private_key_path.is_file():
            raise HostTLSConfigurationError("Host Control private key is unavailable")
        if not self.private_key_credential_reference.startswith("wincred://"):
            raise HostTLSConfigurationError(
                "Host Control private-key password must use Windows Credential Manager"
            )
        first_bytes = self.private_key_path.read_bytes()[:256]
        if b"BEGIN ENCRYPTED PRIVATE KEY" not in first_bytes:
            raise HostTLSConfigurationError(
                "Host Control private key must be encrypted PKCS#8"
            )
        if os.name == "nt":
            _assert_restricted_windows_acl(self.private_key_path)

    def password(self) -> str:
        try:
            raw = WindowsDeviceCredentialStore().acquire(
                self.private_key_credential_reference
            ).for_signing()
            value = raw.decode("ascii")
        except (DeviceCredentialUnavailable, UnicodeDecodeError) as exc:
            raise HostTLSConfigurationError(
                "Host Control private-key password cannot be resolved"
            ) from exc
        if len(value) < 32 or any(character.isspace() for character in value):
            raise HostTLSConfigurationError(
                "Host Control private-key password is invalid"
            )
        return value


def is_loopback_bind_address(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"localhost"}:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _assert_restricted_windows_acl(path: Path) -> None:
    completed = subprocess.run(
        ["icacls.exe", str(path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise HostTLSConfigurationError("Host Control private-key ACL cannot be read")
    lowered = completed.stdout.casefold()
    broad_identities = (
        "everyone:",
        "authenticated users:",
        "builtin\\users:",
        "everyone:(",
        "authenticated users:(",
        "builtin\\users:(",
    )
    if any(identity in lowered for identity in broad_identities):
        raise HostTLSConfigurationError(
            "Host Control private-key ACL grants access to a broad Windows group"
        )


__all__ = [
    "HostTLSConfiguration",
    "HostTLSConfigurationError",
    "is_loopback_bind_address",
]
