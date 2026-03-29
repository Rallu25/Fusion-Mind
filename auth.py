import hashlib
import hmac
import base64
import time
import os

SECRET_KEY = os.getenv("SECRET_KEY", "fusion-mind-secret-key-change-in-production")
TOKEN_EXPIRY = 86400  # 24 hours


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}:{h}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, h = password_hash.split(":")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
        return hmac.compare_digest(h, check)
    except Exception:
        return False


def create_token(teacher_id: int) -> str:
    timestamp = str(int(time.time()))
    payload = f"{teacher_id}:{timestamp}"
    signature = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    token = base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()
    return token


def verify_token(token: str) -> int | None:
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(":")
        if len(parts) != 3:
            return None

        teacher_id, timestamp, signature = int(parts[0]), int(parts[1]), parts[2]

        # Check expiry
        if time.time() - timestamp > TOKEN_EXPIRY:
            return None

        # Check signature
        payload = f"{teacher_id}:{timestamp}"
        expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(signature, expected):
            return None

        return teacher_id
    except Exception:
        return None
