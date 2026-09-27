"""Security primitives for the API gateway."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("arcas.security")


# Password hashing

try:  # Prefer passlib/bcrypt when present.
    from passlib.context import CryptContext  # type: ignore

    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    _HAS_PASSLIB = True
except Exception:  # noqa: BLE001
    _pwd_context = None
    _HAS_PASSLIB = False


_PBKDF2_ROUNDS = 200_000


def hash_password(password: str) -> str:
    if _HAS_PASSLIB:
        return _pwd_context.hash(password)

    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS
    )
    return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(
        digest
    ).decode()


def verify_password(password: str, hashed: str) -> bool:
    if hashed.startswith("pbkdf2$"):
        try:
            _, salt_b64, digest_b64 = hashed.split("$")
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(digest_b64)
            candidate = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS
            )
            return hmac.compare_digest(candidate, expected)
        except Exception:  # noqa: BLE001
            return False

    if _HAS_PASSLIB:
        try:
            return _pwd_context.verify(password, hashed)
        except Exception:  # noqa: BLE001
            return False

    return False


# JWT

try:  # Prefer PyJWT when present.
    import jwt as _pyjwt  # type: ignore

    _HAS_PYJWT = True
except Exception:  # noqa: BLE001
    _pyjwt = None
    _HAS_PYJWT = False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(
    subject: str,
    expires_minutes: Optional[int] = None,
) -> str:
    """Create a signed HS256 access token for subject (username)."""
    expires_minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_minutes * 60,
    }

    if _HAS_PYJWT:
        return _pyjwt.encode(
            payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
        )

    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    )
    signature = hmac.new(
        settings.JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return signing_input + "." + _b64url_encode(signature)


def decode_access_token(token: str) -> Optional[dict]:
    """Validate a token's signature and expiry; return the payload or None."""
    if not token:
        return None

    if _HAS_PYJWT:
        try:
            return _pyjwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("JWT validation failed: %s", exc)
            return None

    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signing_input = header_b64 + "." + payload_b64
        expected = hmac.new(
            settings.JWT_SECRET.encode(),
            signing_input.encode(),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception as exc:  # noqa: BLE001
        logger.debug("Token validation failed: %s", exc)
        return None
