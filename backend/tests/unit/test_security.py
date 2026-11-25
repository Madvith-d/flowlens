"""Unit tests: crypto helpers (encryption at rest, signed cookies)."""

from cryptography.fernet import InvalidToken

from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    sign_value,
    verify_signed,
)


def test_secret_roundtrip(settings) -> None:
    encrypted = encrypt_secret("gho_super_secret_token", settings)
    assert encrypted != "gho_super_secret_token"
    assert "gho_super_secret" not in encrypted
    assert decrypt_secret(encrypted, settings) == "gho_super_secret_token"


def test_decrypt_rejects_tampered_ciphertext(settings) -> None:
    encrypted = encrypt_secret("gho_token", settings)
    tampered = encrypted[:-8] + ("A" * 8 if encrypted[-8:] != "A" * 8 else "B" * 8)
    try:
        decrypt_secret(tampered, settings)
        raise AssertionError("expected InvalidToken")
    except InvalidToken:
        pass


def test_signed_value_roundtrip(settings) -> None:
    signed = sign_value("session-id-123", settings)
    assert signed.startswith("session-id-123.")
    assert verify_signed(signed, settings) == "session-id-123"


def test_tampered_signature_rejected(settings) -> None:
    signed = sign_value("session-id-123", settings)
    assert verify_signed("session-id-456." + signed.split(".")[-1], settings) is None
    assert verify_signed("no-signature-here", settings) is None


def test_wrong_signing_secret_rejected(settings) -> None:
    signed = sign_value("session-id-123", settings)
    other_settings = settings.model_copy(update={"session_signing_secret": "other"})
    assert verify_signed(signed, other_settings) is None
