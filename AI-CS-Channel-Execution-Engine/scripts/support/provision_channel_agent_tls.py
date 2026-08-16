from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from channel_agent.security import WindowsDeviceCredentialStore


def _openssl() -> str:
    candidate = shutil.which("openssl.exe") or shutil.which("openssl")
    if candidate:
        return candidate
    fallback = Path(r"C:\Program Files\Git\usr\bin\openssl.exe")
    if fallback.is_file():
        return str(fallback)
    raise RuntimeError("OpenSSL is unavailable")


def _restrict_private_key(path: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("Windows ACL provisioning is unavailable")
    account = os.environ.get("USERDOMAIN", "") + "\\" + os.environ.get(
        "USERNAME", ""
    )
    account = account.strip("\\")
    if not account:
        raise RuntimeError("Windows runtime account is unavailable")
    completed = subprocess.run(
        [
            "icacls.exe",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{account}:(F)",
            "SYSTEM:(F)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("private-key ACL could not be restricted")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision an encrypted Channel Engine Host Control TLS identity."
    )
    parser.add_argument("--certificate", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--openssl-config", required=True)
    parser.add_argument("--credential-reference", required=True)
    args = parser.parse_args()

    if os.name != "nt":
        raise RuntimeError("Host Control TLS provisioning requires Windows")
    certificate = Path(args.certificate).resolve()
    private_key = Path(args.private_key).resolve()
    openssl_config = Path(args.openssl_config).resolve()
    if not openssl_config.is_file():
        raise RuntimeError("OpenSSL configuration is unavailable")
    certificate.parent.mkdir(parents=True, exist_ok=True)
    private_key.parent.mkdir(parents=True, exist_ok=True)
    temporary_certificate = certificate.with_suffix(certificate.suffix + ".tmp")
    temporary_key = private_key.with_suffix(private_key.suffix + ".tmp")
    passphrase = secrets.token_urlsafe(48).encode("ascii")
    try:
        completed = subprocess.run(
            [
                _openssl(),
                "req",
                "-x509",
                "-newkey",
                "rsa:3072",
                "-sha256",
                "-days",
                "30",
                "-config",
                str(openssl_config),
                "-keyout",
                str(temporary_key),
                "-out",
                str(temporary_certificate),
                "-passout",
                "stdin",
            ],
            input=passphrase + b"\n",
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise RuntimeError("encrypted TLS certificate provisioning failed")
        if b"BEGIN ENCRYPTED PRIVATE KEY" not in temporary_key.read_bytes()[:256]:
            raise RuntimeError("OpenSSL did not produce encrypted PKCS#8")
        _restrict_private_key(temporary_key)
        WindowsDeviceCredentialStore().put(args.credential_reference, passphrase)
        os.replace(temporary_key, private_key)
        os.replace(temporary_certificate, certificate)
        _restrict_private_key(private_key)
    except Exception:
        temporary_key.unlink(missing_ok=True)
        temporary_certificate.unlink(missing_ok=True)
        raise
    finally:
        passphrase = b""
    print("status=PROVISIONED")
    print(f"certificate={certificate}")
    print(f"private_key={private_key}")
    print(f"credential_reference={args.credential_reference}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
