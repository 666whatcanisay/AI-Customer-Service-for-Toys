from __future__ import annotations

from pathlib import Path

import pytest

from channel_engine.agent import tls as tls_module
from channel_engine.agent.tls import (
    HostTLSConfiguration,
    HostTLSConfigurationError,
    is_loopback_bind_address,
)


def test_non_loopback_tls_requires_encrypted_pkcs8_and_wincred_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    certificate = tmp_path / "host.pem"
    certificate.write_text("-----BEGIN CERTIFICATE-----\nTEST\n", encoding="ascii")
    private_key = tmp_path / "host-key.pem"
    private_key.write_text(
        "-----BEGIN ENCRYPTED PRIVATE KEY-----\nTEST\n", encoding="ascii"
    )
    monkeypatch.setattr(tls_module, "_assert_restricted_windows_acl", lambda _path: None)
    monkeypatch.setenv("CHANNEL_ENGINE_TLS_CERTIFICATE", str(certificate))
    monkeypatch.setenv("CHANNEL_ENGINE_TLS_PRIVATE_KEY", str(private_key))
    monkeypatch.setenv(
        "CHANNEL_ENGINE_TLS_PRIVATE_KEY_CREDENTIAL_REFERENCE",
        "wincred://AI-CS/ChannelEngine/host/TLSKeyPassword",
    )

    loaded = HostTLSConfiguration.from_environment()
    assert loaded.private_key_path == private_key

    private_key.write_text("-----BEGIN PRIVATE KEY-----\nTEST\n", encoding="ascii")
    with pytest.raises(HostTLSConfigurationError, match="encrypted PKCS#8"):
        HostTLSConfiguration.from_environment()


def test_bind_address_classification_is_fail_closed() -> None:
    assert is_loopback_bind_address("127.0.0.1") is True
    assert is_loopback_bind_address("::1") is True
    assert is_loopback_bind_address("0.0.0.0") is False
    assert is_loopback_bind_address("192.168.1.10") is False
