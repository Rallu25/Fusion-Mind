import sqlite3
import os

DB_PATH = os.path.join("data", "fusion_mind.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            institution TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS shared_quizzes (
            id TEXT PRIMARY KEY,
            teacher_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            quiz_type TEXT NOT NULL,
            difficulty TEXT DEFAULT 'medium',
            questions_json TEXT NOT NULL,
            timer_minutes INTEGER DEFAULT 0,
            allow_retry INTEGER DEFAULT 0,
            show_answers INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_id) REFERENCES teachers(id)
        );

        CREATE TABLE IF NOT EXISTS quiz_starts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id TEXT NOT NULL,
            student_ip TEXT NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(quiz_id, student_ip)
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            answers_json TEXT NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            pct INTEGER NOT NULL,
            ip TEXT DEFAULT '',
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (quiz_id) REFERENCES shared_quizzes(id)
        );

        CREATE INDEX IF NOT EXISTS idx_quizzes_teacher ON shared_quizzes(teacher_id);
        CREATE INDEX IF NOT EXISTS idx_submissions_quiz ON submissions(quiz_id);
        CREATE INDEX IF NOT EXISTS idx_quiz_starts_quiz ON quiz_starts(quiz_id, student_ip);
    """)
    conn.commit()
    conn.close()


# ── Teacher CRUD ──

def create_teacher(email: str, password_hash: str, full_name: str = "", institution: str = "") -> int:
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO teachers (email, password_hash, full_name, institution) VALUES (?, ?, ?, ?)",
            (email, password_hash, full_name, institution)
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return -1  # email already exists
    finally:
        conn.close()


def get_teacher_by_email(email: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM teachers WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_teacher_by_id(teacher_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM teachers WHERE id = ?", (teacher_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_teacher(teacher_id: int, full_name: str = None, institution: str = None) -> bool:
    conn = get_db()
    updates = []
    params = []
    if full_name is not None:
        updates.append("full_name = ?")
        params.append(full_name)
    if institution is not None:
        updates.append("institution = ?")
        params.append(institution)
    if not updates:
        conn.close()
        return False
    params.append(teacher_id)
    conn.execute(f"UPDATE teachers SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return True


# ── Shared Quiz CRUD ──

def create_shared_quiz(quiz_id: str, teacher_id: int, title: str, quiz_type: str,
                       difficulty: str, questions_json: str, timer_minutes: int = 0,
                       allow_retry: int = 0, show_answers: int = 0) -> bool:
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO shared_quizzes
               (id, teacher_id, title, quiz_type, difficulty, questions_json,
                timer_minutes, allow_retry, show_answers)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (quiz_id, teacher_id, title, quiz_type, difficulty, questions_json,
             timer_minutes, allow_retry, show_answers)
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_shared_quiz(quiz_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM shared_quizzes WHERE id = ?", (quiz_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_teacher_quizzes(teacher_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, quiz_type, difficulty, timer_minutes, created_at "
        "FROM shared_quizzes WHERE teacher_id = ? ORDER BY created_at DESC",
        (teacher_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_shared_quiz(quiz_id: str, teacher_id: int) -> bool:
    conn = get_db()
    try:
        conn.execute("DELETE FROM quiz_starts WHERE quiz_id = ?", (quiz_id,))
        conn.execute("DELETE FROM submissions WHERE quiz_id = ?", (quiz_id,))
        cur = conn.execute(
            "DELETE FROM shared_quizzes WHERE id = ? AND teacher_id = ?",
            (quiz_id, teacher_id)
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


# ── Submission CRUD ──

def save_submission(quiz_id: str, student_name: str, answers_json: str,
                    score: int, total: int, pct: int, ip: str = "") -> int:
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO submissions (quiz_id, student_name, answers_json, score, total, pct, ip)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (quiz_id, student_name, answers_json, score, total, pct, ip)
    )
    conn.commit()
    sub_id = cur.lastrowid
    conn.close()
    return sub_id


def get_quiz_submissions(quiz_id: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM submissions WHERE quiz_id = ? ORDER BY submitted_at DESC",
        (quiz_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def student_already_submitted(quiz_id: str, student_name: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM submissions WHERE quiz_id = ? AND student_name = ?",
        (quiz_id, student_name)
    ).fetchone()
    conn.close()
    return row is not None


def ip_already_submitted(quiz_id: str, ip: str) -> bool:
    if not ip:
        return False
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM submissions WHERE quiz_id = ? AND ip = ?",
        (quiz_id, ip)
    ).fetchone()
    conn.close()
    return row is not None


# ── Quiz Start Tracking ──

def record_quiz_start(quiz_id: str, student_ip: str) -> bool:
    """Record when a student started a quiz. Returns False if already started."""
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO quiz_starts (quiz_id, student_ip) VALUES (?, ?)",
            (quiz_id, student_ip)
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_quiz_start_time(quiz_id: str, student_ip: str) -> str | None:
    """Return the started_at timestamp for this student/quiz, or None."""
    conn = get_db()
    row = conn.execute(
        "SELECT started_at FROM quiz_starts WHERE quiz_id = ? AND student_ip = ?",
        (quiz_id, student_ip)
    ).fetchone()
    conn.close()
    return row["started_at"] if row else None
