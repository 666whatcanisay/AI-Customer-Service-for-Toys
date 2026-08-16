from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, unquote, urlsplit


class DeviceCredentialUnavailable(PermissionError):
    pass


class DeviceCredentialMaterial:
    __slots__ = ("reference", "_value")

    def __init__(self, reference: str, value: bytes) -> None:
        if not isinstance(value, bytes) or len(value) < 32:
            raise DeviceCredentialUnavailable("device credential is unavailable")
        self.reference = reference
        self._value = value

    def __repr__(self) -> str:
        return f"DeviceCredentialMaterial(reference={self.reference!r}, value=<redacted>)"

    __str__ = __repr__

    def for_signing(self) -> bytes:
        return self._value


class DeviceCredentialStore(Protocol):
    def put(self, reference: str, material: bytes) -> None: ...

    def acquire(self, reference: str) -> DeviceCredentialMaterial: ...

    def delete(self, reference: str) -> None: ...


class TransientPayloadProtector(Protocol):
    def protect(self, value: bytes) -> bytes: ...

    def unprotect(self, value: bytes) -> bytes: ...


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


@dataclass(frozen=True, slots=True)
class WindowsDPAPITransientPayloadProtector:
    """Protect short-lived business payloads for the current Windows user."""

    entropy: bytes = b"AI-CS ChannelAgent transient edge spool v2.1"

    def protect(self, value: bytes) -> bytes:
        return self._crypt(value, decrypt=False)

    def unprotect(self, value: bytes) -> bytes:
        return self._crypt(value, decrypt=True)

    def _crypt(self, value: bytes, *, decrypt: bool) -> bytes:
        if os.name != "nt":
            raise DeviceCredentialUnavailable("Windows DPAPI is unavailable")
        if not value:
            raise DeviceCredentialUnavailable("transient payload is empty")
        input_buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
        entropy_buffer = (ctypes.c_ubyte * len(self.entropy)).from_buffer_copy(
            self.entropy
        )
        input_blob = _DATA_BLOB(
            len(value), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte))
        )
        entropy_blob = _DATA_BLOB(
            len(self.entropy),
            ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        output_blob = _DATA_BLOB()
        crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
        if decrypt:
            function = crypt32.CryptUnprotectData
            arguments = (
                ctypes.byref(input_blob),
                None,
                ctypes.byref(entropy_blob),
                None,
                None,
                1,
                ctypes.byref(output_blob),
            )
        else:
            function = crypt32.CryptProtectData
            arguments = (
                ctypes.byref(input_blob),
                "AI-CS ChannelAgent transient payload",
                ctypes.byref(entropy_blob),
                None,
                None,
                1,
                ctypes.byref(output_blob),
            )
        if not function(*arguments):
            raise DeviceCredentialUnavailable("transient payload protection failed")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)


class InMemoryDeviceCredentialStore:
    def __init__(self) -> None:
        self._values: dict[str, bytes] = {}

    def put(self, reference: str, material: bytes) -> None:
        _target_from_reference(reference)
        if len(material) < 32:
            raise DeviceCredentialUnavailable("device credential is unavailable")
        self._values[reference] = bytes(material)

    def acquire(self, reference: str) -> DeviceCredentialMaterial:
        try:
            value = self._values[reference]
        except KeyError as exc:
            raise DeviceCredentialUnavailable(
                "device credential reference could not be resolved"
            ) from exc
        return DeviceCredentialMaterial(reference, value)

    def delete(self, reference: str) -> None:
        self._values.pop(reference, None)


@dataclass(frozen=True, slots=True)
class WindowsDeviceCredentialStore:
    """Read and write Agent device keys in Windows Credential Manager."""

    def put(self, reference: str, material: bytes) -> None:
        if os.name != "nt":
            raise DeviceCredentialUnavailable("Windows Credential Manager is unavailable")
        if len(material) < 32 or len(material) > 1024:
            raise DeviceCredentialUnavailable("device credential has an invalid size")
        _write_generic_credential(_target_from_reference(reference), material)

    def acquire(self, reference: str) -> DeviceCredentialMaterial:
        if os.name != "nt":
            raise DeviceCredentialUnavailable("Windows Credential Manager is unavailable")
        return DeviceCredentialMaterial(
            reference,
            _read_generic_credential(_target_from_reference(reference)),
        )

    def delete(self, reference: str) -> None:
        if os.name != "nt":
            raise DeviceCredentialUnavailable("Windows Credential Manager is unavailable")
        _delete_generic_credential(_target_from_reference(reference))


def device_credential_reference(host_id: str, device_id: str) -> str:
    for value in (host_id, device_id):
        if not value or any(character in value for character in "\r\n\x00"):
            raise ValueError("credential reference identifier is invalid")
    target = f"AI-CS/ChannelAgent/{host_id}/{device_id}"
    return "wincred://" + quote(target, safe="/-._")


def _target_from_reference(reference: str) -> str:
    parsed = urlsplit(reference)
    if (
        parsed.scheme != "wincred"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise DeviceCredentialUnavailable("unsupported device credential reference")
    target = unquote(parsed.netloc + parsed.path)
    if not target or any(character in target for character in "\r\n\x00"):
        raise DeviceCredentialUnavailable("device credential reference is invalid")
    return target


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


def _advapi32():  # type: ignore[no-untyped-def]
    return ctypes.WinDLL("Advapi32.dll", use_last_error=True)


def _write_generic_credential(target: str, material: bytes) -> None:
    buffer = (ctypes.c_ubyte * len(material)).from_buffer_copy(material)
    credential = _CREDENTIALW()
    credential.Type = 1  # CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.CredentialBlobSize = len(material)
    credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = "AI-CS Channel Agent"
    function = _advapi32().CredWriteW
    function.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(credential), 0):
        raise DeviceCredentialUnavailable("device credential could not be stored")


def _read_generic_credential(target: str) -> bytes:
    library = _advapi32()
    pointer = ctypes.POINTER(_CREDENTIALW)()
    read = library.CredReadW
    read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
    ]
    read.restype = wintypes.BOOL
    free = library.CredFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = None
    if not read(target, 1, 0, ctypes.byref(pointer)):
        raise DeviceCredentialUnavailable("device credential could not be resolved")
    try:
        credential = pointer.contents
        if not credential.CredentialBlob or credential.CredentialBlobSize < 32:
            raise DeviceCredentialUnavailable("device credential is unavailable")
        return ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
    finally:
        free(pointer)


def _delete_generic_credential(target: str) -> None:
    function = _advapi32().CredDeleteW
    function.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    function.restype = wintypes.BOOL
    if not function(target, 1, 0):
        error = ctypes.get_last_error()
        if error != 1168:  # ERROR_NOT_FOUND
            raise DeviceCredentialUnavailable("device credential could not be deleted")


__all__ = [
    "DeviceCredentialMaterial",
    "DeviceCredentialStore",
    "DeviceCredentialUnavailable",
    "InMemoryDeviceCredentialStore",
    "WindowsDeviceCredentialStore",
    "TransientPayloadProtector",
    "WindowsDPAPITransientPayloadProtector",
    "device_credential_reference",
]
