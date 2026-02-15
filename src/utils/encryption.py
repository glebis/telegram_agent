"""
Field-level encryption for sensitive data.

Uses Fernet symmetric encryption (AES-128-CBC with HMAC).
Key is derived from the webhook secret + a fixed salt.
"""

import base64
import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded key
_fernet_instance = None


def _is_production() -> bool:
    """Check if running in production environment."""
    return os.getenv("ENVIRONMENT", "development").lower() == "production"


def _get_fernet():
    """Get or create a Fernet instance using webhook secret as key source."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    try:
        from cryptography.fernet import Fernet
    except ImportError:
        msg = (
            "cryptography package not installed. Field encryption unavailable. "
            "Install with: pip install cryptography"
        )
        if _is_production():
            raise RuntimeError(msg)
        logger.warning(msg)
        return None

    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if not secret:
        msg = "TELEGRAM_WEBHOOK_SECRET not set, encryption unavailable"
        if _is_production():
            raise RuntimeError(msg)
        logger.warning(msg)
        return None

    # Per-instance salt: prefer ENCRYPTION_SALT env var, fall back to a default.
    # Operators SHOULD set ENCRYPTION_SALT to a unique random value per deployment.
    salt_env = os.getenv("ENCRYPTION_SALT", "")
    if salt_env:
        salt = salt_env.encode()
    else:
        salt = b"telegram_agent_field_encryption_v1"
        if _is_production():
            logger.warning(
                "ENCRYPTION_SALT not set — using default salt. "
                "Set ENCRYPTION_SALT to a unique random value for production."
            )

    # Derive a 32-byte key from the secret using PBKDF2
    key_bytes = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, iterations=100_000)
    # Fernet requires url-safe base64 encoded 32-byte key
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    _fernet_instance = Fernet(fernet_key)
    return _fernet_instance


def encrypt_field(plaintext: str) -> Optional[str]:
    """Encrypt a string field. Returns base64-encoded ciphertext or None on failure."""
    if not plaintext:
        return plaintext

    fernet = _get_fernet()
    if fernet is None:
        return plaintext  # Graceful fallback: store unencrypted

    try:
        token = fernet.encrypt(plaintext.encode("utf-8"))
        return base64.urlsafe_b64encode(token).decode("ascii")
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return plaintext


def decrypt_field(ciphertext: str) -> Optional[str]:
    """Decrypt a base64-encoded ciphertext. Returns plaintext or original on failure."""
    if not ciphertext:
        return ciphertext

    fernet = _get_fernet()
    if fernet is None:
        return ciphertext

    try:
        token = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        return fernet.decrypt(token).decode("utf-8")
    except Exception:
        # If decryption fails, the data might be stored unencrypted (pre-migration)
        return ciphertext


def is_encrypted(value: str) -> bool:
    """Check if a value appears to be encrypted (heuristic)."""
    if not value:
        return False
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii"))
        # Fernet tokens start with version byte 0x80
        return len(decoded) > 0 and decoded[0] == 0x80
    except Exception:
        return False
