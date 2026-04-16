import os
import uuid
import random
import smtplib
from dotenv import load_dotenv

load_dotenv()
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email_validator import validate_email, EmailNotValidError

from fastapi import FastAPI, UploadFile, File, Form, Body, Header, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from quizgen import generate_quiz_from_pdf, generate_template_quiz_from_pdf, generate_image_quiz_from_pdf, generate_truefalse_quiz_from_pdf, generate_matching_quiz_from_pdf
from database import init_db, create_teacher, get_teacher_by_email, get_teacher_by_id, update_teacher, create_shared_quiz, get_shared_quiz, get_teacher_quizzes, delete_shared_quiz, save_submission, get_quiz_submissions, student_already_submitted, ip_already_submitted, record_quiz_start, get_quiz_start_time, create_quiz_session, consume_quiz_session
from auth import hash_password, verify_password, create_token, verify_token, create_session_token, verify_session_token, ua_fingerprint
from logging_config import get_logger

log = get_logger()
from quiz_export import generate_quiz_pdf
from quiz_gift import generate_gift

from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
import json
import time
from collections import defaultdict

app = FastAPI(title="NLP Disertatie Quiz Generator")


# ── In-memory rate limiter ──

_rate_buckets: dict[tuple[str, str], list[float]] = defaultdict(list)

RATE_LIMITS: dict[str, tuple[int, int]] = {
    "login":    (5, 300),   # 5 attempts / 5 minutes
    "generate": (5, 60),    # 5 PDF generations / minute
    "submit":   (10, 60),   # 10 quiz submissions / minute
    "email":    (5, 60),    # 5 result emails / minute
}


def _is_rate_limited(ip: str, bucket: str = "login") -> bool:
    """Return True if IP has exceeded the rate limit for the given bucket."""
    limit, window = RATE_LIMITS[bucket]
    now = time.time()
    key = (bucket, ip)
    attempts = [t for t in _rate_buckets[key] if now - t < window]
    _rate_buckets[key] = attempts
    return len(attempts) >= limit


def _record_attempt(ip: str, bucket: str = "login"):
    _rate_buckets[(bucket, ip)].append(time.time())


def _record_login_attempt(ip: str):
    _record_attempt(ip, "login")

# Initialize database on startup
init_db()
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

VALID_QUIZ_TYPES = {"cloze", "template", "visual", "truefalse", "matching", "mixed"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
MAX_QUESTIONS = 50
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _validate_quiz_params(n_questions: int, quiz_type: str, difficulty: str) -> str | None:
    """Return error message if params are invalid, None if OK."""
    if n_questions < 1 or n_questions > MAX_QUESTIONS:
        return f"n_questions must be between 1 and {MAX_QUESTIONS}."
    if quiz_type not in VALID_QUIZ_TYPES:
        return f"Invalid quiz_type. Must be one of: {', '.join(sorted(VALID_QUIZ_TYPES))}."
    if difficulty not in VALID_DIFFICULTIES:
        return f"Invalid difficulty. Must be one of: {', '.join(sorted(VALID_DIFFICULTIES))}."
    return None


def _validate_pdf(content: bytes, filename: str) -> str | None:
    """Return error message if file is not a valid PDF, None if OK."""
    if not filename.lower().endswith(".pdf"):
        return "Please upload a PDF file."
    if not content.startswith(b"%PDF-"):
        return "File does not appear to be a valid PDF (invalid header)."
    if len(content) > MAX_FILE_SIZE:
        return f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)} MB."
    return None


def _safe_remove(path: str):
    """Remove a file, ignoring errors if it doesn't exist."""
    try:
        os.remove(path)
    except OSError:
        pass


@app.get("/", response_class=HTMLResponse)
async def home():
    with open("fusion_mind.html", "r", encoding="utf-8") as f:
        return f.read()


def _generate_visual_with_fallback(file_path: str, n_questions: int, difficulty: str) -> dict:
    """Try visual quiz, fallback to cloze if not enough images."""
    result = generate_image_quiz_from_pdf(file_path, n_questions=n_questions)
    if "error" in result:
        result = generate_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)
        if "questions" in result:
            result["warning"] = "Not enough images in PDF. Generated cloze quiz instead."
    return result


def _generate_matching_with_fallback(file_path: str, n_questions: int, difficulty: str) -> dict:
    """Try matching quiz, fallback to template if not enough definitions."""
    result = generate_matching_quiz_from_pdf(file_path, n_questions=n_questions)
    if "error" in result:
        result = generate_template_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)
        if "questions" in result:
            result["warning"] = "Not enough definitions for matching. Generated full questions instead."
    return result


def _generate_quiz_by_type(file_path: str, quiz_type: str, n_questions: int, difficulty: str) -> dict:
    """Route quiz generation to the correct generator based on quiz_type."""
    if quiz_type == "template":
        return generate_template_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)
    elif quiz_type == "visual":
        return _generate_visual_with_fallback(file_path, n_questions=n_questions, difficulty=difficulty)
    elif quiz_type == "truefalse":
        return generate_truefalse_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)
    elif quiz_type == "matching":
        return _generate_matching_with_fallback(file_path, n_questions=n_questions, difficulty=difficulty)
    elif quiz_type == "mixed":
        return _generate_mixed_quiz(file_path, n_questions=n_questions, difficulty=difficulty)
    else:
        return generate_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)


def _generate_mixed_quiz(file_path: str, n_questions: int, difficulty: str) -> dict:
    """Generate a mixed quiz combining multiple question types."""
    # Split n_questions across types: ~30% cloze, ~30% template, ~20% T/F, ~20% matching
    n_cloze = max(1, round(n_questions * 0.3))
    n_template = max(1, round(n_questions * 0.3))
    n_tf = max(1, round(n_questions * 0.2))
    n_match = max(1, n_questions - n_cloze - n_template - n_tf)

    all_questions = []

    # Generate each type (silently handle failures)
    r = generate_quiz_from_pdf(file_path, n_questions=n_cloze, difficulty=difficulty)
    all_questions.extend(r.get("questions", []))

    r = generate_template_quiz_from_pdf(file_path, n_questions=n_template, difficulty=difficulty)
    all_questions.extend(r.get("questions", []))

    r = generate_truefalse_quiz_from_pdf(file_path, n_questions=n_tf, difficulty=difficulty)
    all_questions.extend(r.get("questions", []))

    r = generate_matching_quiz_from_pdf(file_path, n_questions=n_match)
    all_questions.extend(r.get("questions", []))

    random.shuffle(all_questions)

    if not all_questions:
        return {"error": "Could not generate any questions from this PDF."}

    if len(all_questions) < n_questions:
        return {
            "warning": f"Only {len(all_questions)} mixed questions were generated.",
            "questions": all_questions
        }

    return {"questions": all_questions[:n_questions]}


@app.post("/generate-quiz")
async def generate_quiz(
    request: Request,
    file: UploadFile = File(...),
    n_questions: int = Form(10),
    quiz_type: str = Form("cloze"),
    difficulty: str = Form("medium")
):
    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip, "generate"):
        return {"error": "Too many quiz generations. Please wait a minute and try again."}
    _record_attempt(client_ip, "generate")

    param_err = _validate_quiz_params(n_questions, quiz_type, difficulty)
    if param_err:
        return {"error": param_err}

    content = await file.read()
    pdf_err = _validate_pdf(content, file.filename)
    if pdf_err:
        return {"error": pdf_err}

    filename = f"{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        result = _generate_quiz_by_type(file_path, quiz_type, n_questions, difficulty)
    finally:
        _safe_remove(file_path)
    return result


@app.post("/generate-quiz-two-pdfs")
async def generate_quiz_two_pdfs(
    request: Request,
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
    n_questions_file1: int = Form(10),
    n_questions_file2: int = Form(10)
):
    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip, "generate"):
        return {"error": "Too many quiz generations. Please wait a minute and try again."}
    _record_attempt(client_ip, "generate")

    if n_questions_file1 < 1 or n_questions_file1 > MAX_QUESTIONS:
        return {"error": f"n_questions_file1 must be between 1 and {MAX_QUESTIONS}."}
    if n_questions_file2 < 1 or n_questions_file2 > MAX_QUESTIONS:
        return {"error": f"n_questions_file2 must be between 1 and {MAX_QUESTIONS}."}

    content1 = await file1.read()
    pdf_err1 = _validate_pdf(content1, file1.filename)
    if pdf_err1:
        return {"error": f"File 1: {pdf_err1}"}

    content2 = await file2.read()
    pdf_err2 = _validate_pdf(content2, file2.filename)
    if pdf_err2:
        return {"error": f"File 2: {pdf_err2}"}

    filename1 = f"{uuid.uuid4().hex}_1.pdf"
    filename2 = f"{uuid.uuid4().hex}_2.pdf"

    file_path1 = os.path.join(UPLOAD_DIR, filename1)
    file_path2 = os.path.join(UPLOAD_DIR, filename2)

    with open(file_path1, "wb") as f:
        f.write(content1)

    with open(file_path2, "wb") as f:
        f.write(content2)

    try:
        result1 = generate_quiz_from_pdf(file_path1, n_questions=n_questions_file1)
        result2 = generate_quiz_from_pdf(file_path2, n_questions=n_questions_file2)
    finally:
        _safe_remove(file_path1)
        _safe_remove(file_path2)

    questions1 = result1.get("questions", [])
    questions2 = result2.get("questions", [])

    # eliminare duplicate simple
    all_questions = []
    seen = set()

    for q in questions1 + questions2:
        q_text = q.get("question", "").strip()
        if q_text and q_text not in seen:
            all_questions.append(q)
            seen.add(q_text)

    return {
        "file1_name": file1.filename,
        "file2_name": file2.filename,
        "requested_questions": {
            "file1": n_questions_file1,
            "file2": n_questions_file2
        },
        "generated_questions": {
            "file1": len(questions1),
            "file2": len(questions2),
            "total": len(all_questions)
        },
        "results_by_file": [
            {
                "filename": file1.filename,
                "questions": questions1
            },
            {
                "filename": file2.filename,
                "questions": questions2
            }
        ],
        "questions": all_questions
    }



@app.post("/generate-quiz-multi")
async def generate_quiz_multi(
    request: Request,
    files: List[UploadFile] = File(...),
    n_questions_per_file: int = Form(10),
    quiz_type: str = Form("cloze"),
    difficulty: str = Form("medium")
):
    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip, "generate"):
        return {"error": "Too many quiz generations. Please wait a minute and try again."}
    _record_attempt(client_ip, "generate")

    if not files:
        return {"error": "No files were sent."}

    param_err = _validate_quiz_params(n_questions_per_file, quiz_type, difficulty)
    if param_err:
        return {"error": param_err}

    results_by_file = []
    all_questions = []
    seen = set()

    for file in files:
        content = await file.read()
        pdf_err = _validate_pdf(content, file.filename)
        if pdf_err:
            return {"error": f"File '{file.filename}': {pdf_err}"}

        filename = f"{uuid.uuid4().hex}.pdf"
        file_path = os.path.join(UPLOAD_DIR, filename)

        with open(file_path, "wb") as f:
            f.write(content)

        try:
            result = _generate_quiz_by_type(file_path, quiz_type, n_questions_per_file, difficulty)
        finally:
            _safe_remove(file_path)
        questions = result.get("questions", [])

        results_by_file.append({
            "filename": file.filename,
            "generated": len(questions),
            "questions": questions
        })

        for q in questions:
            q_text = q.get("question", "").strip()
            if q_text and q_text not in seen:
                all_questions.append(q)
                seen.add(q_text)

    return {
        "total_files": len(files),
        "n_questions_per_file": n_questions_per_file,
        "total_unique_questions": len(all_questions),
        "results_by_file": results_by_file,
        "questions": all_questions
    }


# ── EMAIL RESULTS ──

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")


@app.post("/send-results-email")
async def send_results_email(request: Request, payload: dict = Body(...)):
    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip, "email"):
        return {"success": False, "error": "Too many email requests. Please wait a minute and try again."}
    _record_attempt(client_ip, "email")

    to_email = payload.get("email", "")
    score = payload.get("score", 0)
    total = payload.get("total", 0)
    pct = payload.get("pct", 0)
    rows = payload.get("rows", [])

    try:
        to_email = validate_email(to_email, check_deliverability=False).normalized
    except EmailNotValidError:
        return {"success": False, "error": "Invalid email address."}

    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        return {"success": False, "error": "Email not configured. Set SMTP_HOST, SMTP_USER and SMTP_PASS environment variables."}

    # Build HTML email
    rows_html = ""
    for i, r in enumerate(rows, 1):
        color = "#b97aff" if r["status"] == "OK" else "#ff4d6a"
        rows_html += f"""<tr>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;color:#999;font-size:12px">{i}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;font-size:13px">{r['question']}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;font-size:13px">{r['chosen']}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;font-size:13px">{r['correct_answer']}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #eee"><span style="color:{color};font-weight:700;font-size:12px">{r['status']}</span></td>
        </tr>"""

    html = f"""
    <div style="font-family:monospace;max-width:700px;margin:0 auto;padding:20px">
        <h2 style="color:#b97aff;margin-bottom:4px">FUSION MIND</h2>
        <p style="color:#666;font-size:13px">Quiz Results Report</p>
        <hr style="border:1px solid #eee;margin:16px 0">

        <div style="text-align:center;padding:24px 0">
            <div style="font-size:48px;font-weight:800;color:#b97aff">{score}/{total}</div>
            <div style="font-size:14px;color:#999;margin-top:4px">{pct}% correct</div>
        </div>

        <table style="width:100%;border-collapse:collapse;font-family:monospace">
            <thead>
                <tr style="background:#f8f8f8">
                    <th style="padding:8px 10px;text-align:left;font-size:11px;color:#999">#</th>
                    <th style="padding:8px 10px;text-align:left;font-size:11px;color:#999">Question</th>
                    <th style="padding:8px 10px;text-align:left;font-size:11px;color:#999">Chosen</th>
                    <th style="padding:8px 10px;text-align:left;font-size:11px;color:#999">Correct</th>
                    <th style="padding:8px 10px;text-align:left;font-size:11px;color:#999">Status</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>

        <hr style="border:1px solid #eee;margin:16px 0">
        <p style="color:#999;font-size:11px;text-align:center">Generated by Fusion Mind · PDF Quiz Generator</p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Fusion Mind Quiz Results — {score}/{total} ({pct}%)"
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        log.info("email.sent", extra={"event": "email.sent", "to": to_email, "score": score, "total": total})
        return {"success": True}
    except Exception as e:
        log.exception("email.failed", extra={"event": "email.failed", "to": to_email})
        return {"success": False, "error": str(e)}


# ── EXPORT QUIZ AS PDF ──

@app.post("/export-quiz-pdf")
async def export_quiz_pdf(payload: dict = Body(...)):
    questions = payload.get("questions", [])
    title = payload.get("title", "Quiz")

    if not questions:
        return {"error": "No questions to export."}

    try:
        filepath = generate_quiz_pdf(questions, title=title)
        return FileResponse(
            filepath,
            media_type="application/pdf",
            filename=f"{title.replace(' ', '_')}.pdf",
        )
    except Exception as e:
        log.exception("export.pdf.failed", extra={"event": "export.pdf.failed", "title": title})
        return {"error": f"PDF generation failed: {str(e)}"}


@app.post("/export-quiz-gift")
async def export_quiz_gift(payload: dict = Body(...)):
    questions = payload.get("questions", [])
    title = payload.get("title", "Quiz")

    if not questions:
        return {"error": "No questions to export."}

    gift_text = generate_gift(questions, title=title)
    # Write to temp file and return
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.write(gift_text)
    tmp.close()
    return FileResponse(
        tmp.name,
        media_type="text/plain",
        filename=f"{title.replace(' ', '_')}_GIFT.txt",
    )


# ── AUTH ENDPOINTS ──

def _get_teacher_from_token(authorization: Optional[str]) -> dict | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    teacher_id = verify_token(token)
    if teacher_id is None:
        return None
    return get_teacher_by_id(teacher_id)


@app.post("/auth/register")
async def auth_register(payload: dict = Body(...)):
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")
    full_name = payload.get("full_name", "").strip()
    institution = payload.get("institution", "").strip()

    try:
        email = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return {"error": "Please enter a valid email address."}
    if not password or len(password) < 4:
        return {"error": "Password must be at least 4 characters."}
    if not full_name:
        return {"error": "Please enter your full name."}

    pw_hash = hash_password(password)
    teacher_id = create_teacher(email, pw_hash, full_name, institution)

    if teacher_id == -1:
        log.info("auth.register.duplicate", extra={"event": "auth.register.duplicate", "email": email})
        return {"error": "An account with this email already exists."}

    token = create_token(teacher_id)
    log.info("auth.register.ok", extra={"event": "auth.register.ok", "teacher_id": teacher_id, "email": email})
    return {"success": True, "token": token, "email": email, "full_name": full_name}


@app.post("/auth/login")
async def auth_login(request: Request, payload: dict = Body(...)):
    client_ip = request.client.host if request.client else "unknown"

    if _is_rate_limited(client_ip):
        log.warning("auth.login.rate_limited", extra={"event": "auth.login.rate_limited", "ip": client_ip})
        return {"error": "Too many login attempts. Please try again in a few minutes."}

    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    teacher = get_teacher_by_email(email)
    if not teacher or not verify_password(password, teacher["password_hash"]):
        _record_login_attempt(client_ip)
        log.warning("auth.login.failed", extra={"event": "auth.login.failed", "email": email, "ip": client_ip})
        return {"error": "Invalid email or password."}

    token = create_token(teacher["id"])
    log.info("auth.login.ok", extra={"event": "auth.login.ok", "teacher_id": teacher["id"], "ip": client_ip})
    return {
        "success": True, "token": token,
        "email": teacher["email"],
        "full_name": teacher["full_name"],
        "institution": teacher.get("institution", ""),
    }


@app.get("/auth/me")
async def auth_me(authorization: Optional[str] = Header(None)):
    teacher = _get_teacher_from_token(authorization)
    if not teacher:
        return {"error": "Not authenticated."}
    return {
        "email": teacher["email"],
        "full_name": teacher["full_name"],
        "institution": teacher.get("institution", ""),
    }


@app.post("/auth/update-profile")
async def auth_update_profile(payload: dict = Body(...), authorization: Optional[str] = Header(None)):
    teacher = _get_teacher_from_token(authorization)
    if not teacher:
        return {"error": "Not authenticated."}

    full_name = payload.get("full_name")
    institution = payload.get("institution")
    update_teacher(teacher["id"], full_name=full_name, institution=institution)
    return {"success": True}


# ── TEACHER ENDPOINTS ──

@app.post("/teacher/create-quiz")
async def teacher_create_quiz(
    file: UploadFile = File(...),
    title: str = Form("Quiz"),
    quiz_type: str = Form("cloze"),
    difficulty: str = Form("medium"),
    n_questions: int = Form(10),
    timer_minutes: int = Form(0),
    show_answers: int = Form(0),
    authorization: Optional[str] = Header(None)
):
    teacher = _get_teacher_from_token(authorization)
    if not teacher:
        return {"error": "Not authenticated."}

    param_err = _validate_quiz_params(n_questions, quiz_type, difficulty)
    if param_err:
        return {"error": param_err}

    content = await file.read()
    pdf_err = _validate_pdf(content, file.filename)
    if pdf_err:
        return {"error": pdf_err}

    filename = f"{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        result = _generate_quiz_by_type(file_path, quiz_type, n_questions, difficulty)
    finally:
        _safe_remove(file_path)

    if "error" in result:
        return result

    questions = result.get("questions", [])
    if not questions:
        return {"error": "No questions generated."}

    quiz_id = uuid.uuid4().hex[:12]
    questions_json = json.dumps(questions)

    ok = create_shared_quiz(
        quiz_id=quiz_id,
        teacher_id=teacher["id"],
        title=title,
        quiz_type=quiz_type,
        difficulty=difficulty,
        questions_json=questions_json,
        timer_minutes=timer_minutes,
        show_answers=show_answers,
    )

    if not ok:
        return {"error": "Failed to save quiz."}

    return {
        "success": True,
        "quiz_id": quiz_id,
        "question_count": len(questions),
    }


@app.post("/teacher/generate-quiz")
async def teacher_generate_quiz(
    request: Request,
    file: UploadFile = File(...),
    quiz_type: str = Form("cloze"),
    difficulty: str = Form("medium"),
    n_questions: int = Form(10),
    authorization: Optional[str] = Header(None)
):
    """Generate quiz questions and return them for review (no saving)."""
    teacher = _get_teacher_from_token(authorization)
    if not teacher:
        return {"error": "Not authenticated."}

    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip, "generate"):
        return {"error": "Too many quiz generations. Please wait a minute and try again."}
    _record_attempt(client_ip, "generate")

    param_err = _validate_quiz_params(n_questions, quiz_type, difficulty)
    if param_err:
        return {"error": param_err}

    content = await file.read()
    pdf_err = _validate_pdf(content, file.filename)
    if pdf_err:
        return {"error": pdf_err}

    filename = f"{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        result = _generate_quiz_by_type(file_path, quiz_type, n_questions, difficulty)
    finally:
        _safe_remove(file_path)

    if "error" in result:
        return result

    questions = result.get("questions", [])
    if not questions:
        return {"error": "No questions generated."}

    return {"success": True, "questions": questions}


@app.post("/teacher/save-quiz")
async def teacher_save_quiz(payload: dict = Body(...), authorization: Optional[str] = Header(None)):
    """Save edited questions as a shared quiz."""
    teacher = _get_teacher_from_token(authorization)
    if not teacher:
        return {"error": "Not authenticated."}

    questions = payload.get("questions", [])
    title = payload.get("title", "Quiz")
    quiz_type = payload.get("quiz_type", "mixed")
    difficulty = payload.get("difficulty", "medium")
    timer_minutes = payload.get("timer_minutes", 0)
    show_answers = payload.get("show_answers", 0)

    if not questions:
        return {"error": "No questions to save."}

    quiz_id = uuid.uuid4().hex[:12]
    questions_json = json.dumps(questions)

    ok = create_shared_quiz(
        quiz_id=quiz_id,
        teacher_id=teacher["id"],
        title=title,
        quiz_type=quiz_type,
        difficulty=difficulty,
        questions_json=questions_json,
        timer_minutes=timer_minutes,
        show_answers=show_answers,
    )

    if not ok:
        log.error("quiz.save.failed", extra={
            "event": "quiz.save.failed", "teacher_id": teacher["id"], "quiz_id": quiz_id,
        })
        return {"error": "Failed to save quiz."}

    log.info("quiz.save.ok", extra={
        "event": "quiz.save.ok", "teacher_id": teacher["id"], "quiz_id": quiz_id,
        "quiz_type": quiz_type, "question_count": len(questions),
    })
    return {"success": True, "quiz_id": quiz_id, "question_count": len(questions)}


@app.get("/teacher/my-quizzes")
async def teacher_my_quizzes(authorization: Optional[str] = Header(None)):
    teacher = _get_teacher_from_token(authorization)
    if not teacher:
        return {"error": "Not authenticated."}

    quizzes = get_teacher_quizzes(teacher["id"])
    # Add submission count
    for q in quizzes:
        subs = get_quiz_submissions(q["id"])
        q["submission_count"] = len(subs)

    return {"quizzes": quizzes}


@app.get("/teacher/quiz/{quiz_id}/results")
async def teacher_quiz_results(quiz_id: str, authorization: Optional[str] = Header(None)):
    teacher = _get_teacher_from_token(authorization)
    if not teacher:
        return {"error": "Not authenticated."}

    quiz = get_shared_quiz(quiz_id)
    if not quiz or quiz["teacher_id"] != teacher["id"]:
        return {"error": "Quiz not found."}

    submissions = get_quiz_submissions(quiz_id)
    # Parse answers JSON for each submission
    for s in submissions:
        s["answers"] = json.loads(s["answers_json"])
        del s["answers_json"]

    return {
        "quiz": {
            "id": quiz["id"],
            "title": quiz["title"],
            "quiz_type": quiz["quiz_type"],
            "timer_minutes": quiz["timer_minutes"],
            "questions": json.loads(quiz["questions_json"]),
        },
        "submissions": submissions,
    }


@app.delete("/teacher/quiz/{quiz_id}")
async def teacher_delete_quiz(quiz_id: str, authorization: Optional[str] = Header(None)):
    teacher = _get_teacher_from_token(authorization)
    if not teacher:
        return {"error": "Not authenticated."}

    deleted = delete_shared_quiz(quiz_id, teacher["id"])
    return {"success": deleted}


# ── STUDENT ENDPOINTS ──

@app.get("/quiz/{quiz_id}")
async def get_quiz_for_student(quiz_id: str):
    quiz = get_shared_quiz(quiz_id)
    if not quiz:
        return {"error": "Quiz not found."}

    questions = json.loads(quiz["questions_json"])

    return {
        "title": quiz["title"],
        "quiz_type": quiz["quiz_type"],
        "timer_minutes": quiz["timer_minutes"],
        "show_answers": quiz["show_answers"],
        "question_count": len(questions),
        "questions": questions,
    }


@app.post("/quiz/{quiz_id}/start")
async def start_quiz(quiz_id: str, request: Request):
    """Record that a student started this quiz and issue an anti-fraud session token."""
    quiz = get_shared_quiz(quiz_id)
    if not quiz:
        return {"error": "Quiz not found."}

    client_ip = request.client.host if request.client else ""
    ua_fp = ua_fingerprint(request.headers.get("user-agent", ""))

    record_quiz_start(quiz_id, client_ip)
    token, nonce = create_session_token(quiz_id, client_ip, ua_fp)
    create_quiz_session(nonce, quiz_id, client_ip, ua_fp)

    return {"success": True, "session_token": token}


@app.post("/quiz/{quiz_id}/submit")
async def submit_quiz(quiz_id: str, request: Request, payload: dict = Body(...)):
    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip, "submit"):
        return {"error": "Too many submissions. Please wait a minute and try again."}
    _record_attempt(client_ip, "submit")

    quiz = get_shared_quiz(quiz_id)
    if not quiz:
        return {"error": "Quiz not found."}

    student_name = payload.get("student_name", "").strip()
    if not student_name:
        return {"error": "Please enter your name."}

    # Verify session token (binds this submission to the original /start)
    session_token = payload.get("session_token", "")
    ua_fp = ua_fingerprint(request.headers.get("user-agent", ""))
    session = verify_session_token(session_token, quiz_id, client_ip, ua_fp)
    if not session:
        log.warning("quiz.submit.invalid_session", extra={
            "event": "quiz.submit.invalid_session",
            "quiz_id": quiz_id, "ip": client_ip,
        })
        return {"error": "Invalid or expired session. Please restart the quiz."}
    if not consume_quiz_session(session["nonce"]):
        log.warning("quiz.submit.replay", extra={
            "event": "quiz.submit.replay",
            "quiz_id": quiz_id, "ip": client_ip, "nonce": session["nonce"],
        })
        return {"error": "This session has already been used. Please restart the quiz."}

    # Check if already submitted (by name or by IP)
    if student_already_submitted(quiz_id, student_name):
        log.info("quiz.submit.duplicate_name", extra={
            "event": "quiz.submit.duplicate_name",
            "quiz_id": quiz_id, "student_name": student_name,
        })
        return {"error": "You have already submitted this quiz."}
    if ip_already_submitted(quiz_id, client_ip):
        log.info("quiz.submit.duplicate_ip", extra={
            "event": "quiz.submit.duplicate_ip",
            "quiz_id": quiz_id, "ip": client_ip,
        })
        return {"error": "A submission from this device has already been recorded."}

    # Server-side timer validation
    timer_minutes = quiz.get("timer_minutes", 0)
    if timer_minutes > 0:
        from datetime import datetime
        started_at_str = get_quiz_start_time(quiz_id, client_ip)
        if started_at_str:
            started_at = datetime.strptime(started_at_str, "%Y-%m-%d %H:%M:%S")
            elapsed_seconds = (datetime.utcnow() - started_at).total_seconds()
            # Allow 30 seconds grace period for network latency
            allowed_seconds = timer_minutes * 60 + 30
            if elapsed_seconds > allowed_seconds:
                return {"error": "Time expired. Your submission was not accepted."}

    answers = payload.get("answers", {})
    score = payload.get("score", 0)
    total = payload.get("total", 0)
    pct = payload.get("pct", 0)

    answers_json = json.dumps(answers)
    save_submission(quiz_id, student_name, answers_json, score, total, pct, ip=client_ip)

    log.info("quiz.submit.ok", extra={
        "event": "quiz.submit.ok",
        "quiz_id": quiz_id, "student_name": student_name,
        "score": score, "total": total, "pct": pct, "ip": client_ip,
    })
    return {"success": True, "score": score, "total": total, "pct": pct}


# ── SERVE STATIC HTML ──

@app.get("/teacher", response_class=HTMLResponse)
async def serve_teacher_dashboard():
    with open("teacher_dashboard.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/student/{quiz_id}", response_class=HTMLResponse)
async def serve_student_quiz(quiz_id: str):
    with open("student_quiz.html", "r", encoding="utf-8") as f:
        html = f.read()
    return html.replace("{{QUIZ_ID}}", quiz_id)