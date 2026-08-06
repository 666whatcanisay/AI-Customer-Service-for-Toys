"""Password and opaque-session primitives with no recoverable credential storage."""

import base64
import hashlib
import hmac
import secrets


SCRYPT_VERSION = "v1"
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
        p=SCRYPT_P, dklen=SCRYPT_DKLEN,
    )
    return (
        f"scrypt${SCRYPT_VERSION}$n={SCRYPT_N},r={SCRYPT_R},p={SCRYPT_P}"
        f"${_b64encode(salt)}${_b64encode(digest)}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, version, parameters, salt_value, digest_value = encoded.split("$", 4)
        parsed = dict(item.split("=", 1) for item in parameters.split(","))
        if algorithm != "scrypt" or version != SCRYPT_VERSION:
            return False
        expected = _b64decode(digest_value)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=_b64decode(salt_value),
            n=int(parsed["n"]), r=int(parsed["r"]), p=int(parsed["p"]),
            dklen=len(expected),
        )
    except (KeyError, TypeError, ValueError):
        return False
    return hmac.compare_digest(actual, expected)


def create_session_token() -> str:
    return f"acs_v1_{secrets.token_urlsafe(32)}"


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
