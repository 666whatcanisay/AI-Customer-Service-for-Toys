from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import unquote, urlsplit


class CredentialUnavailable(PermissionError):
    pass


class CredentialProvider(Protocol):
    def acquire(self, reference: str) -> "CredentialMaterial":
        """Resolve an opaque reference without exposing material in logs or config."""


class CredentialMaterial:
    __slots__ = ("reference", "_value")

    def __init__(self, reference: str, value: bytes) -> None:
        if not isinstance(value, bytes) or len(value) < 32:
            raise CredentialUnavailable("gateway credential is unavailable or too short")
        self.reference = reference
        self._value = value

    def __repr__(self) -> str:
        return f"CredentialMaterial(reference={self.reference!r}, value=<redacted>)"

    __str__ = __repr__

    def for_signing(self) -> bytes:
        return self._value


@dataclass(frozen=True, slots=True)
class WindowsCredentialProvider:
    """Read a Generic Credential from Windows Credential Manager."""

    def acquire(self, reference: str) -> CredentialMaterial:
        if os.name != "nt":
            raise CredentialUnavailable("Windows Credential Manager is unavailable")
        target = _target_from_reference(reference)
        blob = _read_generic_credential(target)
        return CredentialMaterial(reference, _decode_material(blob))


def _target_from_reference(reference: str) -> str:
    parsed = urlsplit(reference)
    if parsed.scheme != "wincred" or not parsed.netloc:
        raise CredentialUnavailable("unsupported credential reference")
    target = unquote(parsed.netloc + parsed.path)
    if not target or any(char in target for char in ("\r", "\n", "\x00")):
        raise CredentialUnavailable("credential reference target is invalid")
    return target


def _decode_material(blob: bytes) -> bytes:
    try:
        text = blob.decode("utf-16-le").rstrip("\x00")
        if not text or any(ord(char) < 32 for char in text):
            raise UnicodeError
    except UnicodeError:
        try:
            text = blob.decode("utf-8").strip()
        except UnicodeError:
            return blob
    try:
        if text.startswith("base64:"):
            return base64.b64decode(text[7:], validate=True)
        if text.startswith("hex:"):
            return bytes.fromhex(text[4:])
    except (ValueError, base64.binascii.Error) as exc:
        raise CredentialUnavailable("credential material encoding is invalid") from exc
    return text.encode("utf-8")


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _read_generic_credential(target: str) -> bytes:
    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    credential_pointer = ctypes.POINTER(_CREDENTIALW)()
    cred_read = advapi32.CredReadW
    cred_read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
    ]
    cred_read.restype = wintypes.BOOL
    cred_free = advapi32.CredFree
    cred_free.argtypes = [ctypes.c_void_p]
    cred_free.restype = None
    if not cred_read(target, 1, 0, ctypes.byref(credential_pointer)):
        raise CredentialUnavailable("credential reference could not be resolved")
    try:
        credential = credential_pointer.contents
        if not credential.CredentialBlob or credential.CredentialBlobSize == 0:
            raise CredentialUnavailable("credential reference has no material")
        return ctypes.string_at(
            credential.CredentialBlob, credential.CredentialBlobSize
        )
    finally:
        cred_free(credential_pointer)
