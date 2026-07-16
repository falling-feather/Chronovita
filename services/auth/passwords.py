from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


_SCHEME = "scrypt"
_VERSION = "1"
_N = 1 << 14
_R = 8
_P = 1
_DKLEN = 32
_MAX_PASSWORD_BYTES = 256


class PasswordFormatError(ValueError):
    pass


def validate_password(password: str) -> None:
    try:
        encoded = password.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("password contains invalid Unicode") from exc
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError("password is too long")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt, n=_N, r=_R, p=_P)
    return "$".join(
        (
            _SCHEME,
            _VERSION,
            str(_N),
            str(_R),
            str(_P),
            _encode(salt),
            _encode(digest),
        )
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        scheme, version, raw_n, raw_r, raw_p, raw_salt, raw_digest = encoded_hash.split("$")
        if scheme != _SCHEME or version != _VERSION:
            return False
        n, r, p = int(raw_n), int(raw_r), int(raw_p)
        if (n, r, p) != (_N, _R, _P):
            return False
        salt = _decode(raw_salt)
        expected = _decode(raw_digest)
        if len(salt) != 16 or len(expected) != _DKLEN:
            return False
        actual = _derive(password, salt, n=n, r=r, p=p)
    except (UnicodeError, ValueError, PasswordFormatError):
        return False
    return hmac.compare_digest(actual, expected)


def _derive(password: str, salt: bytes, *, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=_DKLEN,
        maxmem=64 * 1024 * 1024,
    )


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    try:
        return base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except Exception as exc:
        raise PasswordFormatError("invalid password hash encoding") from exc


_DUMMY_SALT = b"chronovita-auth!"
_DUMMY_DIGEST = _derive("not-a-valid-password", _DUMMY_SALT, n=_N, r=_R, p=_P)
DUMMY_PASSWORD_HASH = "$".join(
    (
        _SCHEME,
        _VERSION,
        str(_N),
        str(_R),
        str(_P),
        _encode(_DUMMY_SALT),
        _encode(_DUMMY_DIGEST),
    )
)
