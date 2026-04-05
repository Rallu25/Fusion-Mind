"""Integration tests for API endpoints using FastAPI TestClient."""

import os
import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

# Use test database
TEST_DB = os.path.join("data", "test_api.db")


@pytest.fixture(autouse=True)
def clean_db():
    """Remove test DB before and after each test."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    with patch("database.DB_PATH", TEST_DB):
        import database
        database.DB_PATH = TEST_DB
        database.init_db()
        # Re-import main to pick up the test DB
        import main
        yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


# ── AUTH FLOW ──

class TestAuthFlow:
    def test_register_success(self, client):
        res = client.post("/auth/register", json={
            "email": "new@test.com",
            "password": "pass1234",
            "full_name": "Test User",
            "institution": "MIT",
        })
        data = res.json()
        assert data.get("success") is True
        assert "token" in data
        assert data["email"] == "new@test.com"

    def test_register_duplicate(self, client):
        payload = {"email": "dup@test.com", "password": "pass", "full_name": "A"}
        client.post("/auth/register", json=payload)
        res = client.post("/auth/register", json=payload)
        assert "error" in res.json()

    def test_register_invalid_email(self, client):
        res = client.post("/auth/register", json={
            "email": "nope",
            "password": "pass",
            "full_name": "A",
        })
        assert "error" in res.json()

    def test_register_short_password(self, client):
        res = client.post("/auth/register", json={
            "email": "a@b.com",
            "password": "ab",
            "full_name": "A",
        })
        assert "error" in res.json()

    def test_login_success(self, client):
        client.post("/auth/register", json={
            "email": "login@test.com",
            "password": "secret",
            "full_name": "Login User",
        })
        res = client.post("/auth/login", json={
            "email": "login@test.com",
            "password": "secret",
        })
        data = res.json()
        assert data.get("success") is True
        assert "token" in data

    def test_login_wrong_password(self, client):
        client.post("/auth/register", json={
            "email": "wp@test.com",
            "password": "correct",
            "full_name": "WP",
        })
        res = client.post("/auth/login", json={
            "email": "wp@test.com",
            "password": "wrong",
        })
        assert "error" in res.json()

    def test_login_nonexistent_email(self, client):
        res = client.post("/auth/login", json={
            "email": "ghost@test.com",
            "password": "pass",
        })
        assert "error" in res.json()

    def test_me_authenticated(self, client):
        reg = client.post("/auth/register", json={
            "email": "me@test.com",
            "password": "pass",
            "full_name": "Me User",
            "institution": "UVT",
        })
        token = reg.json()["token"]
        res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        data = res.json()
        assert data["email"] == "me@test.com"
        assert data["full_name"] == "Me User"

    def test_me_unauthenticated(self, client):
        res = client.get("/auth/me")
        assert "error" in res.json()

    def test_update_profile(self, client):
        reg = client.post("/auth/register", json={
            "email": "upd@test.com",
            "password": "pass",
            "full_name": "Old",
        })
        token = reg.json()["token"]
        res = client.post("/auth/update-profile",
            json={"full_name": "New Name", "institution": "Harvard"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.json().get("success") is True

        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["full_name"] == "New Name"


# ── INPUT VALIDATION ──

class TestValidation:
    def _make_pdf(self) -> bytes:
        """Create minimal valid PDF bytes."""
        return b"%PDF-1.4 minimal test content for quiz generation"

    def test_invalid_quiz_type(self, client):
        res = client.post("/generate-quiz", data={
            "n_questions": "5",
            "quiz_type": "banana",
            "difficulty": "medium",
        }, files={"file": ("test.pdf", self._make_pdf(), "application/pdf")})
        assert "error" in res.json()
        assert "quiz_type" in res.json()["error"].lower() or "Invalid" in res.json()["error"]

    def test_invalid_difficulty(self, client):
        res = client.post("/generate-quiz", data={
            "n_questions": "5",
            "quiz_type": "cloze",
            "difficulty": "impossible",
        }, files={"file": ("test.pdf", self._make_pdf(), "application/pdf")})
        assert "error" in res.json()

    def test_n_questions_too_high(self, client):
        res = client.post("/generate-quiz", data={
            "n_questions": "999",
            "quiz_type": "cloze",
            "difficulty": "medium",
        }, files={"file": ("test.pdf", self._make_pdf(), "application/pdf")})
        assert "error" in res.json()

    def test_n_questions_zero(self, client):
        res = client.post("/generate-quiz", data={
            "n_questions": "0",
            "quiz_type": "cloze",
            "difficulty": "medium",
        }, files={"file": ("test.pdf", self._make_pdf(), "application/pdf")})
        assert "error" in res.json()

    def test_not_pdf_extension(self, client):
        res = client.post("/generate-quiz", data={
            "n_questions": "5",
            "quiz_type": "cloze",
            "difficulty": "medium",
        }, files={"file": ("test.txt", b"hello", "text/plain")})
        assert "error" in res.json()

    def test_fake_pdf_extension(self, client):
        res = client.post("/generate-quiz", data={
            "n_questions": "5",
            "quiz_type": "cloze",
            "difficulty": "medium",
        }, files={"file": ("evil.pdf", b"NOT-A-PDF-FILE", "application/pdf")})
        assert "error" in res.json()
        assert "valid PDF" in res.json()["error"]


# ── STUDENT ENDPOINTS ──

class TestStudentEndpoints:
    def test_quiz_not_found(self, client):
        res = client.get("/quiz/nonexistent")
        assert "error" in res.json()

    def test_submit_without_name(self, client):
        res = client.post("/quiz/test123/submit", json={
            "student_name": "",
            "answers": {},
            "score": 0,
            "total": 0,
            "pct": 0,
        })
        data = res.json()
        assert "error" in data

    def test_start_quiz_not_found(self, client):
        res = client.post("/quiz/nonexistent/start")
        assert "error" in res.json()


# ── HTML PAGES ──

class TestHTMLPages:
    def test_home_page(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "FUSION MIND" in res.text

    def test_teacher_page(self, client):
        res = client.get("/teacher")
        assert res.status_code == 200

    def test_student_page(self, client):
        res = client.get("/student/abc123")
        assert res.status_code == 200
        assert "abc123" in res.text
