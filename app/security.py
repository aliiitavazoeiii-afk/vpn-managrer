import base64
import hashlib
import hmac
from cryptography.fernet import Fernet
from .config import settings

_key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode("utf-8")).digest())
_fernet = Fernet(_key)

def encrypt_secret(value: str) -> str:
    return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")

def decrypt_secret(value: str) -> str:
    return _fernet.decrypt(value.encode("utf-8")).decode("utf-8")

def check_admin(username: str, password: str) -> bool:
    return hmac.compare_digest(username, settings.admin_username) and hmac.compare_digest(password, settings.admin_password)
