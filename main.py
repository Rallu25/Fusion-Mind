import os
import uuid

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