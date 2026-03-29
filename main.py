import os
import uuid
import random
import smtplib
from dotenv import load_dotenv

load_dotenv()
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI, UploadFile, File, Form, Body, Header, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from quizgen import generate_quiz_from_pdf, generate_template_quiz_from_pdf, generate_image_quiz_from_pdf, generate_truefalse_quiz_from_pdf, generate_matching_quiz_from_pdf
from translator import translate_text
from database import init_db, create_teacher, get_teacher_by_email, get_teacher_by_id, update_teacher, create_shared_quiz, get_shared_quiz, get_teacher_quizzes, delete_shared_quiz, save_submission, get_quiz_submissions, student_already_submitted, ip_already_submitted
from auth import hash_password, verify_password, create_token, verify_token

from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI(title="NLP Disertatie Quiz Generator")

# Initialize database on startup
init_db()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    file: UploadFile = File(...),
    n_questions: int = Form(10),
    quiz_type: str = Form("cloze"),
    difficulty: str = Form("medium")
):
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Please upload a PDF file."}

    filename = f"{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(UPLOAD_DIR, filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        if quiz_type == "template":
            result = generate_template_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)
        elif quiz_type == "visual":
            result = _generate_visual_with_fallback(file_path, n_questions=n_questions, difficulty=difficulty)
        elif quiz_type == "truefalse":
            result = generate_truefalse_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)
        elif quiz_type == "matching":
            result = _generate_matching_with_fallback(file_path, n_questions=n_questions, difficulty=difficulty)
        elif quiz_type == "mixed":
            result = _generate_mixed_quiz(file_path, n_questions=n_questions, difficulty=difficulty)
        else:
            result = generate_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)
    finally:
        os.remove(file_path)
    return result


@app.post("/generate-quiz-two-pdfs")
async def generate_quiz_two_pdfs(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
    n_questions_file1: int = Form(10),
    n_questions_file2: int = Form(10)
):
    if not file1.filename.lower().endswith(".pdf"):
        return {"error": "The first file is not a PDF."}

    if not file2.filename.lower().endswith(".pdf"):
        return {"error": "The second file is not a PDF."}

    filename1 = f"{uuid.uuid4().hex}_1.pdf"
    filename2 = f"{uuid.uuid4().hex}_2.pdf"

    file_path1 = os.path.join(UPLOAD_DIR, filename1)
    file_path2 = os.path.join(UPLOAD_DIR, filename2)

    content1 = await file1.read()
    with open(file_path1, "wb") as f:
        f.write(content1)

    content2 = await file2.read()
    with open(file_path2, "wb") as f:
        f.write(content2)

    try:
        result1 = generate_quiz_from_pdf(file_path1, n_questions=n_questions_file1)
        result2 = generate_quiz_from_pdf(file_path2, n_questions=n_questions_file2)
    finally:
        os.remove(file_path1)
        os.remove(file_path2)

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


@app.post("/translate-quiz")
async def translate_quiz(payload: dict = Body(...)):
    questions = payload.get("questions", [])
    target_language = payload.get("target_language", "ro")

    translated_questions = []

    for q in questions:
        translated_question = translate_text(q["question"], target_language)
        translated_evidence = translate_text(q.get("evidence", ""), target_language)

        translated_questions.append({
            "question": translated_question,
            "options": q["options"],
            "correct_index": q["correct_index"],
            "evidence": translated_evidence
        })

    return {
        "target_language": target_language,
        "questions": translated_questions
    }

@app.post("/generate-quiz-multi")
async def generate_quiz_multi(
    files: List[UploadFile] = File(...),
    n_questions_per_file: int = Form(10),
    quiz_type: str = Form("cloze"),
    difficulty: str = Form("medium")
):
    if not files:
        return {"error": "No files were sent."}

    results_by_file = []
    all_questions = []
    seen = set()

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            return {"error": f"File '{file.filename}' is not a PDF."}

        filename = f"{uuid.uuid4().hex}.pdf"
        file_path = os.path.join(UPLOAD_DIR, filename)

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        try:
            if quiz_type == "template":
                result = generate_template_quiz_from_pdf(file_path, n_questions=n_questions_per_file, difficulty=difficulty)
            elif quiz_type == "visual":
                result = _generate_visual_with_fallback(file_path, n_questions=n_questions_per_file, difficulty=difficulty)
            elif quiz_type == "truefalse":
                result = generate_truefalse_quiz_from_pdf(file_path, n_questions=n_questions_per_file, difficulty=difficulty)
            elif quiz_type == "matching":
                result = _generate_matching_with_fallback(file_path, n_questions=n_questions_per_file, difficulty=difficulty)
            elif quiz_type == "mixed":
                result = _generate_mixed_quiz(file_path, n_questions=n_questions_per_file, difficulty=difficulty)
            else:
                result = generate_quiz_from_pdf(file_path, n_questions=n_questions_per_file, difficulty=difficulty)
        finally:
            os.remove(file_path)
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

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.mail.yahoo.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "ralucaosman@yahoo.com")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "ralucaosman@yahoo.com")


@app.post("/send-results-email")
async def send_results_email(payload: dict = Body(...)):
    to_email = payload.get("email", "")
    score = payload.get("score", 0)
    total = payload.get("total", 0)
    pct = payload.get("pct", 0)
    rows = payload.get("rows", [])

    if not to_email or "@" not in to_email:
        return {"success": False, "error": "Invalid email address."}

    if not SMTP_USER or not SMTP_PASS:
        return {"success": False, "error": "Email not configured. Set SMTP_USER and SMTP_PASS environment variables."}

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
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


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

    if not email or "@" not in email:
        return {"error": "Please enter a valid email address."}
    if not password or len(password) < 4:
        return {"error": "Password must be at least 4 characters."}
    if not full_name:
        return {"error": "Please enter your full name."}

    pw_hash = hash_password(password)
    teacher_id = create_teacher(email, pw_hash, full_name, institution)

    if teacher_id == -1:
        return {"error": "An account with this email already exists."}

    token = create_token(teacher_id)
    return {"success": True, "token": token, "email": email, "full_name": full_name}


@app.post("/auth/login")
async def auth_login(payload: dict = Body(...)):
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    teacher = get_teacher_by_email(email)
    if not teacher or not verify_password(password, teacher["password_hash"]):
        return {"error": "Invalid email or password."}

    token = create_token(teacher["id"])
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

    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Please upload a PDF file."}

    filename = f"{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(UPLOAD_DIR, filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        if quiz_type == "template":
            result = generate_template_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)
        elif quiz_type == "visual":
            result = _generate_visual_with_fallback(file_path, n_questions=n_questions, difficulty=difficulty)
        elif quiz_type == "truefalse":
            result = generate_truefalse_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)
        elif quiz_type == "matching":
            result = _generate_matching_with_fallback(file_path, n_questions=n_questions, difficulty=difficulty)
        elif quiz_type == "mixed":
            result = _generate_mixed_quiz(file_path, n_questions=n_questions, difficulty=difficulty)
        else:
            result = generate_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)
    finally:
        os.remove(file_path)

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


@app.post("/quiz/{quiz_id}/submit")
async def submit_quiz(quiz_id: str, request: Request, payload: dict = Body(...)):
    quiz = get_shared_quiz(quiz_id)
    if not quiz:
        return {"error": "Quiz not found."}

    student_name = payload.get("student_name", "").strip()
    if not student_name:
        return {"error": "Please enter your name."}

    client_ip = request.client.host if request.client else ""

    # Check if already submitted (by name or by IP)
    if student_already_submitted(quiz_id, student_name):
        return {"error": "You have already submitted this quiz."}
    if ip_already_submitted(quiz_id, client_ip):
        return {"error": "A submission from this device has already been recorded."}

    answers = payload.get("answers", {})
    score = payload.get("score", 0)
    total = payload.get("total", 0)
    pct = payload.get("pct", 0)

    answers_json = json.dumps(answers)
    save_submission(quiz_id, student_name, answers_json, score, total, pct, ip=client_ip)

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