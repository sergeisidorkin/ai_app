import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class SMTPSecretError(RuntimeError):
    """Raised when an SMTP secret cannot be encrypted or decrypted."""


def _build_fernet() -> Fernet:
    raw_key = getattr(settings, "SMTP_APP_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    digest = hashlib.sha256(str(raw_key).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    clean_value = str(value or "")
    if not clean_value:
        return ""
    return _build_fernet().encrypt(clean_value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    clean_value = str(value or "")
    if not clean_value:
        return ""
    try:
        return _build_fernet().decrypt(clean_value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SMTPSecretError("Не удалось расшифровать SMTP-секрет.") from exc
