"""Tests for auth.py — password hashing and token management."""

import time
from unittest.mock import patch
from auth import hash_password, verify_password, create_token, verify_token


class TestPasswordHashing:
    def test_hash_returns_salt_colon_hash(self):
        result = hash_password("mypassword")
        assert ":" in result
        salt, h = result.split(":")
        assert len(salt) == 32  # 16 bytes hex
        assert len(h) == 64     # sha256 hex

    def test_different_salts_each_time(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # different salts

    def test_verify_correct_password(self):
        pw_hash = hash_password("secret123")
        assert verify_password("secret123", pw_hash) is True

    def test_verify_wrong_password(self):
        pw_hash = hash_password("secret123")
        assert verify_password("wrong", pw_hash) is False

    def test_verify_empty_password(self):
        pw_hash = hash_password("test")
        assert verify_password("", pw_hash) is False

    def test_verify_malformed_hash(self):
        assert verify_password("test", "not-a-valid-hash") is False
        assert verify_password("test", "") is False
        assert verify_password("test", "::::") is False


class TestTokens:
    def test_create_and_verify(self):
        token = create_token(42)
        result = verify_token(token)
        assert result == 42

    def test_verify_different_ids(self):
        for teacher_id in [1, 100, 9999]:
            token = create_token(teacher_id)
            assert verify_token(token) == teacher_id

    def test_expired_token(self):
        token = create_token(1)
        # Simulate time passing beyond expiry (24h + 1s)
        with patch("auth.time") as mock_time:
            mock_time.time.return_value = time.time() + 86401
            # We need to patch in verify_token's scope
        # Alternative: directly test with manipulated token
        # Decode, change timestamp, re-encode
        import base64
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(":")
        # Set timestamp to 2 days ago
        old_timestamp = str(int(time.time()) - 200000)
        # Recreate with old timestamp (signature won't match — that's fine, tests expiry path)
        # Instead, create a token with old timestamp properly signed
        import hashlib, hmac as hmac_mod
        from auth import SECRET_KEY
        payload = f"{parts[0]}:{old_timestamp}"
        sig = hmac_mod.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        old_token = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
        assert verify_token(old_token) is None

    def test_tampered_token(self):
        token = create_token(1)
        # Flip a character in the token
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        assert verify_token(tampered) is None

    def test_invalid_token_formats(self):
        assert verify_token("") is None
        assert verify_token("not-base64-!!!") is None
        assert verify_token("dGVzdA==") is None  # "test" in base64
