import os
import uuid
import random
import smtplib
from dotenv import load_dotenv

load_dotenv()
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI, UploadFile, File, Form, Body
from quizgen import generate_quiz_from_pdf, generate_template_quiz_from_pdf, generate_image_quiz_from_pdf, generate_truefalse_quiz_from_pdf, generate_matching_quiz_from_pdf
from translator import translate_text

from typing import List
from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI(title="NLP Disertatie Quiz Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def home():
    return {"message": "API is running."}


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
            result = generate_image_quiz_from_pdf(file_path, n_questions=n_questions)
        elif quiz_type == "truefalse":
            result = generate_truefalse_quiz_from_pdf(file_path, n_questions=n_questions, difficulty=difficulty)
        elif quiz_type == "matching":
            result = generate_matching_quiz_from_pdf(file_path, n_questions=n_questions)
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
                result = generate_image_quiz_from_pdf(file_path, n_questions=n_questions_per_file)
            elif quiz_type == "truefalse":
                result = generate_truefalse_quiz_from_pdf(file_path, n_questions=n_questions_per_file, difficulty=difficulty)
            elif quiz_type == "matching":
                result = generate_matching_quiz_from_pdf(file_path, n_questions=n_questions_per_file)
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