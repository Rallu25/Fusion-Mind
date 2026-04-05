"""Tests for database.py — CRUD operations using a temporary DB."""

import os
import json
import pytest
from unittest.mock import patch

# Patch DB_PATH before importing database module
TEST_DB_PATH = os.path.join("data", "test_fusion_mind.db")


@pytest.fixture(autouse=True)
def setup_teardown():
    """Use a temporary test database for each test."""
    with patch("database.DB_PATH", TEST_DB_PATH):
        import database
        database.DB_PATH = TEST_DB_PATH
        database.init_db()
        yield database
        # Cleanup
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


class TestTeacherCRUD:
    def test_create_teacher(self, setup_teardown):
        db = setup_teardown
        tid = db.create_teacher("test@example.com", "hash123", "Test User", "MIT")
        assert tid > 0

    def test_create_duplicate_email(self, setup_teardown):
        db = setup_teardown
        db.create_teacher("dup@test.com", "hash1", "User1")
        result = db.create_teacher("dup@test.com", "hash2", "User2")
        assert result == -1

    def test_get_teacher_by_email(self, setup_teardown):
        db = setup_teardown
        db.create_teacher("find@test.com", "hash", "Findable", "UVT")
        teacher = db.get_teacher_by_email("find@test.com")
        assert teacher is not None
        assert teacher["full_name"] == "Findable"
        assert teacher["institution"] == "UVT"

    def test_get_teacher_by_email_not_found(self, setup_teardown):
        db = setup_teardown
        assert db.get_teacher_by_email("nobody@test.com") is None

    def test_get_teacher_by_id(self, setup_teardown):
        db = setup_teardown
        tid = db.create_teacher("byid@test.com", "hash", "ById")
        teacher = db.get_teacher_by_id(tid)
        assert teacher is not None
        assert teacher["email"] == "byid@test.com"

    def test_update_teacher(self, setup_teardown):
        db = setup_teardown
        tid = db.create_teacher("upd@test.com", "hash", "Old Name")
        db.update_teacher(tid, full_name="New Name", institution="Harvard")
        teacher = db.get_teacher_by_id(tid)
        assert teacher["full_name"] == "New Name"
        assert teacher["institution"] == "Harvard"

    def test_update_teacher_partial(self, setup_teardown):
        db = setup_teardown
        tid = db.create_teacher("partial@test.com", "hash", "Name", "Inst")
        db.update_teacher(tid, full_name="Updated")
        teacher = db.get_teacher_by_id(tid)
        assert teacher["full_name"] == "Updated"
        assert teacher["institution"] == "Inst"  # unchanged

    def test_update_teacher_no_changes(self, setup_teardown):
        db = setup_teardown
        tid = db.create_teacher("noop@test.com", "hash", "Name")
        result = db.update_teacher(tid)
        assert result is False


class TestQuizCRUD:
    def _create_teacher(self, db):
        return db.create_teacher("teacher@test.com", "hash", "Teacher")

    def test_create_and_get_quiz(self, setup_teardown):
        db = setup_teardown
        tid = self._create_teacher(db)
        ok = db.create_shared_quiz("quiz1", tid, "My Quiz", "cloze", "medium", '[]', 10, 0, 1)
        assert ok is True
        quiz = db.get_shared_quiz("quiz1")
        assert quiz is not None
        assert quiz["title"] == "My Quiz"
        assert quiz["timer_minutes"] == 10
        assert quiz["show_answers"] == 1

    def test_get_quiz_not_found(self, setup_teardown):
        db = setup_teardown
        assert db.get_shared_quiz("nonexistent") is None

    def test_get_teacher_quizzes(self, setup_teardown):
        db = setup_teardown
        tid = self._create_teacher(db)
        db.create_shared_quiz("q1", tid, "Quiz 1", "cloze", "easy", '[]')
        db.create_shared_quiz("q2", tid, "Quiz 2", "template", "hard", '[]')
        quizzes = db.get_teacher_quizzes(tid)
        assert len(quizzes) == 2
        titles = {q["title"] for q in quizzes}
        assert titles == {"Quiz 1", "Quiz 2"}

    def test_delete_quiz(self, setup_teardown):
        db = setup_teardown
        tid = self._create_teacher(db)
        db.create_shared_quiz("del1", tid, "Delete Me", "cloze", "medium", '[]')
        result = db.delete_shared_quiz("del1", tid)
        assert result is True
        assert db.get_shared_quiz("del1") is None

    def test_delete_quiz_wrong_teacher(self, setup_teardown):
        db = setup_teardown
        tid = self._create_teacher(db)
        db.create_shared_quiz("del2", tid, "Quiz", "cloze", "medium", '[]')
        result = db.delete_shared_quiz("del2", 9999)  # wrong teacher
        assert result is False
        assert db.get_shared_quiz("del2") is not None  # still exists

    def test_delete_quiz_cascades_submissions(self, setup_teardown):
        db = setup_teardown
        tid = self._create_teacher(db)
        db.create_shared_quiz("casc", tid, "Quiz", "cloze", "medium", '[]')
        db.save_submission("casc", "Student", '{}', 5, 10, 50)
        db.delete_shared_quiz("casc", tid)
        subs = db.get_quiz_submissions("casc")
        assert len(subs) == 0


class TestSubmissions:
    def _setup_quiz(self, db):
        tid = db.create_teacher("sub@test.com", "hash", "Teacher")
        db.create_shared_quiz("subq", tid, "Quiz", "cloze", "medium", '[]')
        return tid

    def test_save_and_get_submission(self, setup_teardown):
        db = setup_teardown
        self._setup_quiz(db)
        sub_id = db.save_submission("subq", "Alice", '{"0": 1}', 8, 10, 80, ip="1.2.3.4")
        assert sub_id > 0
        subs = db.get_quiz_submissions("subq")
        assert len(subs) == 1
        assert subs[0]["student_name"] == "Alice"
        assert subs[0]["score"] == 8

    def test_student_already_submitted(self, setup_teardown):
        db = setup_teardown
        self._setup_quiz(db)
        db.save_submission("subq", "Bob", '{}', 5, 10, 50)
        assert db.student_already_submitted("subq", "Bob") is True
        assert db.student_already_submitted("subq", "Charlie") is False

    def test_ip_already_submitted(self, setup_teardown):
        db = setup_teardown
        self._setup_quiz(db)
        db.save_submission("subq", "Dave", '{}', 5, 10, 50, ip="10.0.0.1")
        assert db.ip_already_submitted("subq", "10.0.0.1") is True
        assert db.ip_already_submitted("subq", "10.0.0.2") is False

    def test_ip_empty_not_blocked(self, setup_teardown):
        db = setup_teardown
        assert db.ip_already_submitted("subq", "") is False


class TestQuizStarts:
    def test_record_and_get_start(self, setup_teardown):
        db = setup_teardown
        tid = db.create_teacher("start@test.com", "hash", "T")
        db.create_shared_quiz("startq", tid, "Q", "cloze", "medium", '[]')
        db.record_quiz_start("startq", "1.1.1.1")
        started = db.get_quiz_start_time("startq", "1.1.1.1")
        assert started is not None

    def test_get_start_not_found(self, setup_teardown):
        db = setup_teardown
        assert db.get_quiz_start_time("nope", "0.0.0.0") is None

    def test_double_start_no_error(self, setup_teardown):
        db = setup_teardown
        tid = db.create_teacher("dbl@test.com", "hash", "T")
        db.create_shared_quiz("dblq", tid, "Q", "cloze", "medium", '[]')
        db.record_quiz_start("dblq", "2.2.2.2")
        db.record_quiz_start("dblq", "2.2.2.2")  # should not crash (INSERT OR IGNORE)
        started = db.get_quiz_start_time("dblq", "2.2.2.2")
        assert started is not None
