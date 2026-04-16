import hashlib
import hmac
import base64
import time
import os
import uuid

SECRET_KEY = os.getenv("SECRET_KEY", "fusion-mind-secret-key-change-in-production")
TOKEN_EXPIRY = 86400  # 24 hours
SESSION_TOKEN_EXPIRY = 3 * 60 * 60  # 3 hours for a quiz session


def ua_fingerprint(user_agent: str) -> str:
    """Short stable hash of the User-Agent header."""
    return hashlib.sha256((user_agent or "").encode()).hexdigest()[:16]


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


# ── Quiz session tokens (anti-fraud for student submissions) ──

def create_session_token(quiz_id: str, ip: str, ua_fp: str) -> tuple[str, str]:
    """
    Build an HMAC-signed token that binds a quiz attempt to a
    unique nonce, the IP that started the quiz and a UA fingerprint.
    Returns (token, nonce). The nonce must be stored server-side
    and consumed on submit to prevent replay.
    """
    nonce = uuid.uuid4().hex
    issued_at = str(int(time.time()))
    payload = f"v1:{quiz_id}:{nonce}:{ip}:{ua_fp}:{issued_at}"
    signature = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
    token = base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()
    return token, nonce


def verify_session_token(token: str, quiz_id: str, ip: str, ua_fp: str) -> dict | None:
    """
    Verify a session token against the current request context.
    Returns {"nonce": ..., "issued_at": ...} on success, None otherwise.
    Mismatch on signature, quiz_id, IP, UA fingerprint or expiry → None.
    """
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(":")
        if len(parts) != 7 or parts[0] != "v1":
            return None

        _v, tok_quiz, nonce, tok_ip, tok_ua, issued_at_s, signature = parts
        issued_at = int(issued_at_s)

        if time.time() - issued_at > SESSION_TOKEN_EXPIRY:
            return None

        payload = f"v1:{tok_quiz}:{nonce}:{tok_ip}:{tok_ua}:{issued_at_s}"
        expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(signature, expected):
            return None

        if tok_quiz != quiz_id:
            return None
        if tok_ip != ip:
            return None
        if tok_ua != ua_fp:
            return None

        return {"nonce": nonce, "issued_at": issued_at}
    except Exception:
        return None
