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
        main._rate_buckets.clear()
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


class TestSessionTokenAntiFraud:
    """End-to-end checks for the anti-fraud session token wired into /start and /submit."""

    def _seed_quiz(self):
        import database
        conn = database.get_db()
        conn.execute(
            "INSERT INTO teachers (email, password_hash) VALUES (?, ?)",
            ("fraud@test.com", "x"),
        )
        conn.execute(
            "INSERT INTO shared_quizzes (id, teacher_id, title, quiz_type, questions_json) "
            "VALUES (?, ?, ?, ?, ?)",
            ("fraudq", 1, "t", "cloze", "[]"),
        )
        conn.commit()
        conn.close()

    def test_start_issues_session_token(self, client):
        self._seed_quiz()
        res = client.post("/quiz/fraudq/start")
        data = res.json()
        assert data.get("success") is True
        assert data.get("session_token"), "start must return a session_token"

    def test_submit_without_token_is_rejected(self, client):
        self._seed_quiz()
        res = client.post("/quiz/fraudq/submit", json={
            "student_name": "Alice",
            "answers": {}, "score": 0, "total": 0, "pct": 0,
        })
        data = res.json()
        assert "error" in data
        assert "session" in data["error"].lower()

    def test_submit_with_valid_token_succeeds(self, client):
        self._seed_quiz()
        start = client.post("/quiz/fraudq/start").json()
        res = client.post("/quiz/fraudq/submit", json={
            "student_name": "Alice",
            "session_token": start["session_token"],
            "answers": {}, "score": 0, "total": 0, "pct": 0,
        })
        data = res.json()
        assert data.get("success") is True

    def test_token_replay_is_blocked(self, client):
        self._seed_quiz()
        start = client.post("/quiz/fraudq/start").json()
        payload = {
            "student_name": "Alice",
            "session_token": start["session_token"],
            "answers": {}, "score": 0, "total": 0, "pct": 0,
        }
        first = client.post("/quiz/fraudq/submit", json=payload).json()
        assert first.get("success") is True

        # Same token, different name → must be blocked (nonce already consumed or name check)
        payload["student_name"] = "Bob"
        second = client.post("/quiz/fraudq/submit", json=payload).json()
        assert "error" in second

    def test_token_from_other_quiz_is_rejected(self, client):
        self._seed_quiz()
        # Seed a second quiz
        import database
        conn = database.get_db()
        conn.execute(
            "INSERT INTO shared_quizzes (id, teacher_id, title, quiz_type, questions_json) "
            "VALUES (?, ?, ?, ?, ?)",
            ("otherq", 1, "t", "cloze", "[]"),
        )
        conn.commit()
        conn.close()

        start = client.post("/quiz/fraudq/start").json()
        # Try to submit to a different quiz using fraudq's token
        res = client.post("/quiz/otherq/submit", json={
            "student_name": "Alice",
            "session_token": start["session_token"],
            "answers": {}, "score": 0, "total": 0, "pct": 0,
        })
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


# ── END-TO-END FLOW ──

def _build_sample_pdf() -> bytes:
    """Create a valid PDF with enough real sentences for quiz extraction
    (the pipeline rejects texts with fewer than 15 usable sentences)."""
    import fitz
    sentences = [
        "Photosynthesis is the process used by plants to convert light energy into chemical energy.",
        "Chlorophyll is the green pigment that absorbs sunlight in the chloroplasts of plant cells.",
        "Carbon dioxide from the atmosphere combines with water from the roots to produce glucose.",
        "Mitochondria are the powerhouses of the cell and generate most of the energy used by animals.",
        "The nucleus contains the genetic material of the cell, organized into chromosomes and DNA.",
        "Ribosomes synthesize proteins by translating messenger RNA into chains of amino acids.",
        "The cell membrane is a selectively permeable barrier that regulates what enters and leaves the cell.",
        "Enzymes are biological catalysts that accelerate chemical reactions inside living organisms.",
        "Glucose is a simple sugar that serves as the primary source of energy for most cells.",
        "Cellular respiration converts glucose and oxygen into carbon dioxide, water and ATP energy.",
        "The Golgi apparatus modifies, sorts and packages proteins for secretion or use within the cell.",
        "Lysosomes contain digestive enzymes that break down waste materials and cellular debris.",
        "DNA replication occurs during the S phase of the cell cycle before mitosis begins.",
        "Proteins are long chains of amino acids folded into specific three-dimensional shapes.",
        "The endoplasmic reticulum is a network of membranes involved in protein and lipid synthesis.",
        "Osmosis is the movement of water molecules across a semipermeable membrane down a concentration gradient.",
        "Photosynthesis takes place primarily in the leaves of green plants during daylight hours.",
        "Oxygen is released as a byproduct of photosynthesis when water molecules are split apart.",
        "The mitochondrial matrix is the site where the Krebs cycle reactions occur in animal cells.",
        "Stomata are tiny pores on the surface of leaves that regulate gas exchange and transpiration.",
        "Chromosomes are condensed structures made of DNA and histone proteins found in the nucleus.",
        "Transcription is the process by which genetic information in DNA is copied into messenger RNA.",
        "The chloroplast is the organelle where photosynthesis happens in plant and algae cells.",
        "Translation is the process by which ribosomes build proteins using messenger RNA as a template.",
        "Active transport requires ATP energy to move molecules against their concentration gradient.",
    ]
    doc = fitz.open()
    page = doc.new_page()
    y = 50
    for s in sentences:
        if y > 780:
            page = doc.new_page()
            y = 50
        page.insert_text((40, y), s, fontsize=10)
        y += 18
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class TestEndToEndFlow:
    """Full pipeline: teacher registers, uploads PDF, generates quiz,
    saves it, a student fetches/starts/submits, and the teacher sees results."""

    def _register_teacher(self, client, email="teach@e2e.com"):
        res = client.post("/auth/register", json={
            "email": email,
            "password": "e2epass",
            "full_name": "E2E Teacher",
            "institution": "Test U",
        })
        data = res.json()
        assert data.get("success") is True, f"register failed: {data}"
        return data["token"]

    def test_full_flow_teacher_to_student_to_results(self, client):
        # 1. Teacher registers and gets a token
        token = self._register_teacher(client)
        auth = {"Authorization": f"Bearer {token}"}

        # 2. Teacher generates quiz from PDF (no save yet)
        pdf = _build_sample_pdf()
        gen = client.post(
            "/teacher/generate-quiz",
            headers=auth,
            data={"quiz_type": "cloze", "difficulty": "medium", "n_questions": "3"},
            files={"file": ("biology.pdf", pdf, "application/pdf")},
        ).json()
        assert gen.get("success") is True, f"generate failed: {gen}"
        questions = gen["questions"]
        assert len(questions) >= 1, "pipeline produced no questions"

        # 3. Teacher saves the quiz → gets a shareable quiz_id
        saved = client.post(
            "/teacher/save-quiz",
            headers=auth,
            json={
                "title": "Biology Basics",
                "quiz_type": "cloze",
                "difficulty": "medium",
                "questions": questions,
                "timer_minutes": 0,
                "show_answers": 1,
            },
        ).json()
        assert saved.get("success") is True, f"save failed: {saved}"
        quiz_id = saved["quiz_id"]

        # 4. Student fetches the quiz payload
        student_view = client.get(f"/quiz/{quiz_id}").json()
        assert student_view["title"] == "Biology Basics"
        assert student_view["question_count"] == len(questions)

        # 5. Student starts the quiz → anti-fraud token issued
        start = client.post(f"/quiz/{quiz_id}/start").json()
        assert start.get("success") is True
        session_token = start["session_token"]

        # 6. Student submits answers (all correct index 0 as placeholder)
        answers = {str(i): 0 for i in range(len(questions))}
        score = sum(1 for i, q in enumerate(questions) if q.get("correct_index") == 0)
        total = len(questions)
        pct = round(score / total * 100) if total else 0
        submit = client.post(
            f"/quiz/{quiz_id}/submit",
            json={
                "student_name": "Alice Student",
                "session_token": session_token,
                "answers": answers,
                "score": score,
                "total": total,
                "pct": pct,
            },
        ).json()
        assert submit.get("success") is True, f"submit failed: {submit}"

        # 7. Teacher inspects the results
        results = client.get(f"/teacher/quiz/{quiz_id}/results", headers=auth).json()
        assert results["quiz"]["title"] == "Biology Basics"
        assert len(results["submissions"]) == 1
        sub = results["submissions"][0]
        assert sub["student_name"] == "Alice Student"
        assert sub["score"] == score
        assert sub["total"] == total

        # 8. my-quizzes reflects the new quiz with a submission count
        mine = client.get("/teacher/my-quizzes", headers=auth).json()
        ids = [q["id"] for q in mine["quizzes"]]
        assert quiz_id in ids
        mine_entry = next(q for q in mine["quizzes"] if q["id"] == quiz_id)
        assert mine_entry["submission_count"] == 1

    def test_student_cannot_submit_twice_same_ip(self, client):
        token = self._register_teacher(client)
        auth = {"Authorization": f"Bearer {token}"}
        pdf = _build_sample_pdf()

        gen = client.post(
            "/teacher/generate-quiz", headers=auth,
            data={"quiz_type": "cloze", "difficulty": "medium", "n_questions": "2"},
            files={"file": ("bio.pdf", pdf, "application/pdf")},
        ).json()
        saved = client.post(
            "/teacher/save-quiz", headers=auth,
            json={"title": "Q", "quiz_type": "cloze", "difficulty": "medium",
                  "questions": gen["questions"]},
        ).json()
        quiz_id = saved["quiz_id"]

        # First submission succeeds
        tok1 = client.post(f"/quiz/{quiz_id}/start").json()["session_token"]
        r1 = client.post(f"/quiz/{quiz_id}/submit", json={
            "student_name": "Alice",
            "session_token": tok1,
            "answers": {}, "score": 0, "total": 1, "pct": 0,
        }).json()
        assert r1.get("success") is True

        # Second attempt from same IP with different name must be blocked
        tok2 = client.post(f"/quiz/{quiz_id}/start").json()["session_token"]
        r2 = client.post(f"/quiz/{quiz_id}/submit", json={
            "student_name": "Bob",
            "session_token": tok2,
            "answers": {}, "score": 0, "total": 1, "pct": 0,
        }).json()
        assert "error" in r2

    def test_delete_quiz_removes_submissions(self, client):
        token = self._register_teacher(client)
        auth = {"Authorization": f"Bearer {token}"}
        pdf = _build_sample_pdf()

        gen = client.post(
            "/teacher/generate-quiz", headers=auth,
            data={"quiz_type": "cloze", "difficulty": "medium", "n_questions": "2"},
            files={"file": ("bio.pdf", pdf, "application/pdf")},
        ).json()
        saved = client.post(
            "/teacher/save-quiz", headers=auth,
            json={"title": "Q", "quiz_type": "cloze", "difficulty": "medium",
                  "questions": gen["questions"]},
        ).json()
        quiz_id = saved["quiz_id"]

        tok = client.post(f"/quiz/{quiz_id}/start").json()["session_token"]
        client.post(f"/quiz/{quiz_id}/submit", json={
            "student_name": "Alice", "session_token": tok,
            "answers": {}, "score": 0, "total": 1, "pct": 0,
        })

        # Teacher deletes the quiz
        dres = client.delete(f"/teacher/quiz/{quiz_id}", headers=auth).json()
        assert dres.get("success") is True

        # Quiz is gone, results endpoint fails gracefully
        gone = client.get(f"/teacher/quiz/{quiz_id}/results", headers=auth).json()
        assert "error" in gone


class TestEmailSending:
    """Verify /send-results-email builds a correct message and talks to SMTP.
    smtplib.SMTP is patched so no real mail is sent."""

    def test_email_sent_with_mocked_smtp(self, client, monkeypatch):
        sent = {}

        class FakeSMTP:
            def __init__(self, host, port):
                sent["host"] = host
                sent["port"] = port
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def starttls(self): sent["starttls"] = True
            def login(self, u, p): sent["login"] = u
            def send_message(self, msg):
                sent["to"] = msg["To"]
                sent["subject"] = msg["Subject"]
                sent["body"] = str(msg)

        import main
        monkeypatch.setattr(main.smtplib, "SMTP", FakeSMTP)
        monkeypatch.setattr(main, "SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr(main, "SMTP_USER", "robot@example.com")
        monkeypatch.setattr(main, "SMTP_PASS", "secret")
        monkeypatch.setattr(main, "SMTP_FROM", "robot@example.com")

        res = client.post("/send-results-email", json={
            "email": "student@example.com",
            "score": 7, "total": 10, "pct": 70,
            "rows": [
                {"question": "What is the powerhouse of the cell?",
                 "chosen": "Mitochondria", "correct_answer": "Mitochondria", "status": "OK"},
                {"question": "Green pigment in plants?",
                 "chosen": "Haemoglobin", "correct_answer": "Chlorophyll", "status": "WRONG"},
            ],
        }).json()

        assert res.get("success") is True, f"email send failed: {res}"
        assert sent["host"] == "smtp.example.com"
        assert sent["to"] == "student@example.com"
        assert "70" in sent["body"] or "7" in sent["body"]

    def test_email_rejects_invalid_address(self, client):
        res = client.post("/send-results-email", json={
            "email": "not-an-email",
            "score": 0, "total": 0, "pct": 0, "rows": [],
        }).json()
        assert res.get("success") is False
        assert "email" in res["error"].lower()

    def test_email_fails_when_smtp_not_configured(self, client, monkeypatch):
        import main
        monkeypatch.setattr(main, "SMTP_HOST", "")
        monkeypatch.setattr(main, "SMTP_USER", "")
        monkeypatch.setattr(main, "SMTP_PASS", "")
        res = client.post("/send-results-email", json={
            "email": "student@example.com",
            "score": 0, "total": 0, "pct": 0, "rows": [],
        }).json()
        assert res.get("success") is False
        assert "configured" in res["error"].lower()
