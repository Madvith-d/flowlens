"""Security primitives: token encryption at rest, signed session cookies, CSRF.

- GitHub access/refresh tokens are encrypted with a key derived from
  TOKEN_ENCRYPTION_KEY before persistence; they are never logged or returned
  to clients.
- The session cookie stores only a signed session ID (HttpOnly); all session
  state lives server-side in the database.
- CSRF: state-changing, cookie-authenticated requests must carry an Origin
  header matching an allowed origin (see app/core/csrf.py middleware).
"""

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


def _fernet(settings: Settings) -> Fernet:
    digest = hashlib.sha256(settings.token_encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str, settings: Settings) -> str:
    """Encrypt a secret for storage at rest. Returns a token string."""
    return _fernet(settings).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str, settings: Settings) -> str:
    """Decrypt a stored secret. Raises InvalidToken on tampering/wrong key."""
    return _fernet(settings).decrypt(token.encode("ascii")).decode("utf-8")


def sign_value(value: str, settings: Settings) -> str:
    """Return `value.signature` using HMAC-SHA256 with the session signing secret."""
    signature = hmac.new(
        settings.session_signing_secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{value}.{signature}"


def verify_signed(value_with_signature: str, settings: Settings) -> str | None:
    """Verify and return the original value, or None if invalid/tampered."""
    value, separator, signature = value_with_signature.rpartition(".")
    if not separator or not value or not signature:
        return None
    expected = hmac.new(
        settings.session_signing_secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not secrets.compare_digest(expected, signature):
        return None
    return value


__all__ = [
    "encrypt_secret",
    "decrypt_secret",
    "sign_value",
    "verify_signed",
    "InvalidToken",
]
