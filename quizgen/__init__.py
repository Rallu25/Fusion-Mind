import random
import re

from .pdf_text import extract_text_from_pdf
from .preprocess import split_sentences
from .tfidf_rank import rank_sentences
from .distractors import build_vocab, pick_distractors, normalize_word, KNOWLEDGE_BASE, shares_stem
from .cloze import pick_target_word, make_cloze
from .template_quiz import generate_template_quiz_from_pdf
from .image_quiz import generate_image_quiz_from_pdf
from .truefalse_quiz import generate_truefalse_quiz_from_pdf
from .matching_quiz import generate_matching_quiz_from_pdf
from .kb_expand import expand_knowledge_base
from .utils import BAD_STARTS, filter_by_difficulty

WEAK_TARGETS = {
    "solar", "optical", "electric", "predictable", "surface",
    "located", "performs", "called", "known", "used"
}


def is_technical_sentence(sentence: str) -> bool:
    patterns = [
        r"\b[A-Z][a-z]?\d+[A-Za-z0-9]*\b",   # H2O, C6H8O7
        r"\b\d+(\.\d+)?\s?(°C|%|mg/L|g/L|kg|mL|L|V|Hz|kHz|GHz|ms|nm|TB|GB)\b",
        r"\bpH\s?\d+(\.\d+)?\b"
    ]
    return any(re.search(pattern, sentence) for pattern in patterns)


def score_question(sentence: str, target: str, options: list[str]) -> int:
    score = 0
    target_norm = normalize_word(target)

    if target_norm in KNOWLEDGE_BASE:
        score += 50

    if target_norm not in WEAK_TARGETS:
        score += 20

    if target[:1].isupper():
        score += 10

    if len(set(opt.lower() for opt in options)) == 4:
        score += 20

    words = sentence.split()
    if not words:
        return score

    first_word = words[0].lower()
    if first_word not in BAD_STARTS:
        score += 15
    else:
        score -= 20

    if 60 <= len(sentence) <= 160:
        score += 10
    elif 40 <= len(sentence) <= 220:
        score += 5

    # pentru documente tehnice, cifrele nu sunt un defect
    if any(char.isdigit() for char in sentence):
        score += 5

    # bonus pentru propoziții tehnice utile
    if is_technical_sentence(sentence):
        score += 10

    # penalizare dacă vreun distractor partajează rădăcina cu target-ul
    for opt in options:
        if normalize_word(opt) != target_norm and shares_stem(target_norm, normalize_word(opt)):
            score -= 30
            break

    return score


def generate_quiz_from_pdf(pdf_path: str, n_questions: int = 10, seed: int = 42, difficulty: str = "medium") -> dict:
    random.seed(seed)

    text = extract_text_from_pdf(pdf_path)
    sentences = split_sentences(text)

    if len(sentences) < 15:
        return {
            "error": "Too little usable text after segmentation. Try a clearer PDF with selectable text."
        }

    # Auto-expand knowledge base with terms from this PDF
    try:
        expand_knowledge_base(sentences)
    except Exception:
        pass  # don't fail quiz generation if KB expansion fails

    vocab = build_vocab(sentences)
    ranked_sentences = rank_sentences(sentences, top_k=220)

    candidates = []
    used_questions = set()
    used_targets = set()

    for sentence, _score in ranked_sentences:
        sentence_lower = sentence.lower()

        if " and with " in sentence_lower:
            continue

        if sentence.count(",") > 4:
            continue

        if len(sentence.split()) < 6:
            continue

        target = pick_target_word(sentence, vocab)
        if not target:
            continue

        target_norm = normalize_word(target)

        # evită întrebări repetitive pe același concept
        if target_norm in used_targets:
            continue

        question_text = make_cloze(sentence, target)
        correct_answer = target
        wrong_answers = pick_distractors(correct_answer, vocab, sentence, k=3, all_sentences=sentences)

        if len(wrong_answers) < 3:
            continue

        options = [correct_answer] + wrong_answers
        random.shuffle(options)

        if len(set(opt.lower() for opt in options)) < 4:
            continue

        correct_index = options.index(correct_answer)

        if question_text in used_questions:
            continue

        quality = score_question(sentence, correct_answer, options)

        candidates.append({
            "question": question_text,
            "options": options,
            "correct_index": correct_index,
            "evidence": sentence,
            "quality_score": quality
        })

        used_questions.add(question_text)
        used_targets.add(target_norm)

    MIN_QUALITY_SCORE = 40 if difficulty == "hard" else 50 if difficulty == "medium" else 60
    filtered_candidates = [q for q in candidates if q["quality_score"] >= MIN_QUALITY_SCORE]

    questions = filter_by_difficulty(filtered_candidates, difficulty, n_questions)

    clean_questions = []
    for q in questions:
        clean_questions.append({
            "question": q["question"],
            "options": q["options"],
            "correct_index": q["correct_index"],
            "evidence": q["evidence"]
        })

    if len(clean_questions) < n_questions:
        return {
            "warning": f"Only {len(clean_questions)} good questions were generated.",
            "questions": clean_questions
        }

    return {
        "questions": clean_questions
    }