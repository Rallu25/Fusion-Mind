"""Tests for the structured JSON logger."""

import io
import json
import logging
import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from logging_config import JsonFormatter, get_logger

TEST_DB = os.path.join("data", "test_logging.db")


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    with patch("database.DB_PATH", TEST_DB):
        import database
        database.DB_PATH = TEST_DB
        database.init_db()
        import main
        main._rate_buckets.clear()
        yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


class TestJsonFormatter:
    def _format(self, record: logging.LogRecord) -> dict:
        return json.loads(JsonFormatter().format(record))

    def test_basic_fields_emitted(self):
        rec = logging.LogRecord("fusion_mind", logging.INFO, __file__, 1,
                                "hello world", (), None)
        payload = self._format(rec)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "fusion_mind"
        assert payload["msg"] == "hello world"
        assert "ts" in payload and payload["ts"].endswith("+00:00")

    def test_extra_fields_are_promoted_to_top_level(self):
        rec = logging.LogRecord("fusion_mind", logging.INFO, __file__, 1,
                                "quiz saved", (), None)
        rec.quiz_id = "abc123"
        rec.teacher_id = 7
        rec.event = "quiz.save.ok"
        payload = self._format(rec)
        assert payload["quiz_id"] == "abc123"
        assert payload["teacher_id"] == 7
        assert payload["event"] == "quiz.save.ok"

    def test_reserved_fields_are_not_leaked(self):
        rec = logging.LogRecord("fusion_mind", logging.INFO, __file__, 1,
                                "x", (), None)
        payload = self._format(rec)
        assert "pathname" not in payload
        assert "process" not in payload
        assert "threadName" not in payload

    def test_exception_info_is_formatted(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            rec = logging.LogRecord("fusion_mind", logging.ERROR, __file__, 1,
                                    "failure", (), sys.exc_info())
        payload = self._format(rec)
        assert "exc" in payload
        assert "ValueError: boom" in payload["exc"]

    def test_emitted_lines_are_valid_json(self):
        logger = get_logger()
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        try:
            logger.info("test.event", extra={"event": "test.event", "quiz_id": "q1"})
        finally:
            logger.removeHandler(handler)
        line = buf.getvalue().strip()
        parsed = json.loads(line)
        assert parsed["event"] == "test.event"
        assert parsed["quiz_id"] == "q1"


class TestLoggedEndpoints:
    """Assert that endpoints emit structured log records for key events.
    We attach a capturing handler, not caplog, because the app logger sets
    propagate=False so caplog does not see its records by default."""

    def _capture(self, logger_name="fusion_mind"):
        buf = []

        class MemHandler(logging.Handler):
            def emit(self, record):
                buf.append(record)

        h = MemHandler(level=logging.DEBUG)
        logger = logging.getLogger(logger_name)
        logger.addHandler(h)
        return buf, logger, h

    def test_register_emits_auth_register_ok(self, client):
        buf, logger, h = self._capture()
        try:
            res = client.post("/auth/register", json={
                "email": "logged@test.com",
                "password": "pass1234",
                "full_name": "Logged User",
            })
            assert res.json().get("success") is True
        finally:
            logger.removeHandler(h)

        events = [getattr(r, "event", None) for r in buf]
        assert "auth.register.ok" in events
        rec = next(r for r in buf if getattr(r, "event", None) == "auth.register.ok")
        assert rec.email == "logged@test.com"
        assert isinstance(rec.teacher_id, int)

    def test_login_failure_logs_warning(self, client):
        # Need a real account for the login to route past the 404
        client.post("/auth/register", json={
            "email": "real@test.com", "password": "realpass", "full_name": "Real",
        })

        buf, logger, h = self._capture()
        try:
            res = client.post("/auth/login", json={
                "email": "real@test.com", "password": "wrong",
            })
            assert "error" in res.json()
        finally:
            logger.removeHandler(h)

        events = [getattr(r, "event", None) for r in buf]
        assert "auth.login.failed" in events
