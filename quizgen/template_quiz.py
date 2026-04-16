import random
import re

from .pdf_text import extract_text_from_pdf
from .preprocess import split_sentences
from .tfidf_rank import rank_sentences
from .distractors import build_vocab, normalize_word, shares_stem, KNOWLEDGE_BASE
from .template_patterns import match_sentence, clean_answer
from .kb_expand import expand_knowledge_base
from .utils import filter_by_difficulty


# Regex simplu pentru extragerea sintagmelor nominale (fallback distractors)
_NP_PATTERN = re.compile(
    r"\b(?:the|a|an)\s+(?:[a-z]+\s+){0,3}[a-z]+(?:\s+of\s+[a-z\s]+)?",
    re.IGNORECASE
)


def _word_set(text: str) -> set[str]:
    """Returnează mulțimea de cuvinte normalizate dintr-un text."""
    return {w.lower() for w in re.findall(r"[A-Za-z]+", text)}


def _word_overlap_ratio(a: str, b: str) -> float:
    """Calculează raportul de overlap între cuvintele a două texte."""
    wa, wb = _word_set(a), _word_set(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _is_substring_match(a: str, b: str) -> bool:
    """Verifică dacă unul e substring al celuilalt."""
    a_low, b_low = a.lower().strip(), b.lower().strip()
    return a_low in b_low or b_low in a_low


def _answer_length_ok(answer: str, reference: str, factor: float = 2.5) -> bool:
    """Verifică dacă lungimea răspunsului e rezonabilă comparativ cu referința."""
    a_words = len(answer.split())
    r_words = len(reference.split())
    if r_words == 0:
        return False
    return (1.0 / factor) <= (a_words / r_words) <= factor


def filter_distractors(correct: str, candidates: list[str], evidence: str) -> list[str]:
    """Filtrează distractorii ambigui sau triviabili."""
    correct_lower = correct.lower().strip()
    evidence_lower = evidence.lower()
    filtered = []

    for d in candidates:
        d_clean = d.strip()
        d_lower = d_clean.lower()

        # identic cu răspunsul corect
        if d_lower == correct_lower:
            continue

        # substring match
        if _is_substring_match(d_clean, correct):
            continue

        # overlap prea mare de cuvinte (>60%)
        if _word_overlap_ratio(d_clean, correct) > 0.6:
            continue

        # distractorul apare exact în evidence
        if d_lower in evidence_lower:
            continue

        # lungime prea diferită
        if not _answer_length_ok(d_clean, correct):
            continue

        # verifică stem pe cuvântul principal
        d_words = [w for w in re.findall(r"[A-Za-z]+", d_clean) if len(w) > 3]
        c_words = [w for w in re.findall(r"[A-Za-z]+", correct) if len(w) > 3]
        stem_conflict = False
        for dw in d_words[:2]:
            for cw in c_words[:2]:
                if shares_stem(dw, cw):
                    stem_conflict = True
                    break
            if stem_conflict:
                break
        if stem_conflict:
            continue

        filtered.append(d_clean)

    return filtered


def _get_same_pattern_distractors(
    pattern_name: str,
    current_subject: str,
    pattern_answers: dict[str, list[tuple[str, str]]],
    correct: str,
    k: int = 5
) -> list[str]:
    """Distractori din alte răspunsuri cu același tip de pattern."""
    candidates = []
    current_subj_lower = current_subject.lower().strip()

    for subj, answer in pattern_answers.get(pattern_name, []):
        if subj.lower().strip() == current_subj_lower:
            continue
        if answer.lower().strip() == correct.lower().strip():
            continue
        candidates.append(answer)

    random.shuffle(candidates)
    return candidates[:k]


def _get_cross_pattern_distractors(
    current_pattern: str,
    current_subject: str,
    pattern_answers: dict[str, list[tuple[str, str]]],
    correct: str,
    k: int = 5
) -> list[str]:
    """Distractori din alte tipuri de pattern, filtrați pe lungime similară."""
    candidates = []
    current_subj_lower = current_subject.lower().strip()

    for pname, answers_list in pattern_answers.items():
        if pname == current_pattern:
            continue
        for subj, answer in answers_list:
            if subj.lower().strip() == current_subj_lower:
                continue
            if _answer_length_ok(answer, correct, factor=2.0):
                candidates.append(answer)

    random.shuffle(candidates)
    return candidates[:k]


def _get_np_distractors(sentences: list[str], correct: str, evidence: str, k: int = 5) -> list[str]:
    """Fallback: extrage sintagme nominale din alte propoziții."""
    candidates = []
    evidence_lower = evidence.lower()

    for sent in sentences:
        if sent.lower() == evidence_lower:
            continue
        for m in _NP_PATTERN.finditer(sent):
            np = clean_answer(m.group(0))
            if len(np) >= 5 and _answer_length_ok(np, correct, factor=2.5):
                candidates.append(np)

    random.shuffle(candidates)
    # deduplică
    seen = set()
    unique = []
    for c in candidates:
        c_lower = c.lower()
        if c_lower not in seen:
            seen.add(c_lower)
            unique.append(c)
    return unique[:k]


def pick_template_distractors(
    correct: str,
    evidence: str,
    pattern_name: str,
    subject: str,
    pattern_answers: dict[str, list[tuple[str, str]]],
    all_sentences: list[str],
    k: int = 3
) -> tuple[list[str], str]:
    """
    Generează k distractori pentru un răspuns de tip frază.
    Returnează (distractori, sursă) unde sursă e "same"/"cross"/"fallback".
    """
    # Strategia 1: same-pattern
    raw = _get_same_pattern_distractors(pattern_name, subject, pattern_answers, correct, k=k + 3)
    filtered = filter_distractors(correct, raw, evidence)
    if len(filtered) >= k:
        return filtered[:k], "same"

    # Strategia 2: cross-pattern
    raw2 = _get_cross_pattern_distractors(pattern_name, subject, pattern_answers, correct, k=k + 3)
    combined = filtered + filter_distractors(correct, raw2, evidence)
    # deduplică
    seen = {d.lower() for d in filtered}
    for d in filter_distractors(correct, raw2, evidence):
        if d.lower() not in seen:
            combined.append(d)
            seen.add(d.lower())
    if len(combined) >= k:
        return combined[:k], "cross"

    # Strategia 3: noun-phrase fallback
    raw3 = _get_np_distractors(all_sentences, correct, evidence, k=k + 3)
    for d in filter_distractors(correct, raw3, evidence):
        if d.lower() not in seen:
            combined.append(d)
            seen.add(d.lower())

    return combined[:k], "fallback"


def score_template_question(
    question: str,
    answer: str,
    options: list[str],
    sentence: str,
    pattern_name: str,
    distractor_source: str
) -> int:
    """Calculează scorul de calitate al unei întrebări template."""
    score = 0

    # pattern-uri care produc întrebări mai clare
    if pattern_name in ("definition", "value"):
        score += 20

    # subiect în knowledge base
    for word in re.findall(r"[A-Za-z]+", question):
        if normalize_word(word) in KNOWLEDGE_BASE:
            score += 15
            break

    # 4 opțiuni unice
    if len(set(opt.lower().strip() for opt in options)) == 4:
        score += 20

    # lungimi similare ale opțiunilor
    lengths = [len(opt.split()) for opt in options]
    if lengths:
        max_l, min_l = max(lengths), min(lengths)
        if min_l > 0 and max_l / min_l <= 2:
            score += 15

    # lungime propoziție
    if 60 <= len(sentence) <= 160:
        score += 10
    elif 40 <= len(sentence) <= 220:
        score += 5

    # calitatea distractorilor
    if distractor_source == "same":
        score += 20
    elif distractor_source == "cross":
        score += 10
    elif distractor_source == "fallback":
        score -= 10

    # răspuns pur numeric fără context
    if re.match(r"^[0-9\s.,]+$", answer):
        score -= 15

    # bonus dacă răspunsul conține termen tehnic
    tech_pattern = re.compile(
        r"\b[A-Z][a-z]?\d+[A-Za-z0-9]*\b|"
        r"\b\d+(\.\d+)?\s?(°C|%|mg/L|g/L|kg|mL|L|V|Hz|kHz|GHz|ms|nm|TB|GB)\b"
    )
    if tech_pattern.search(answer) or tech_pattern.search(sentence):
        score += 10

    return score


def generate_template_quiz_from_pdf(pdf_path: str, n_questions: int = 10, seed: int = 42, difficulty: str = "medium") -> dict:
    """Generează un quiz cu întrebări complete (template-based) din PDF."""
    random.seed(seed)

    text = extract_text_from_pdf(pdf_path)
    sentences = split_sentences(text)

    if len(sentences) < 15:
        return {
            "error": "Too little usable text after segmentation. Try a clearer PDF with selectable text."
        }

    try:
        expand_knowledge_base(sentences)
    except Exception:
        from logging_config import get_logger
        get_logger().exception("kb.expand.failed", extra={"event": "kb.expand.failed"})

    ranked_sentences = rank_sentences(sentences, top_k=220)

    # Pasul 1: match toate propozițiile și colectează răspunsuri pe pattern
    pattern_answers: dict[str, list[tuple[str, str]]] = {}
    matched_data: list[tuple[str, str, str, str, str, float]] = []
    # (sentence, question, answer, subject, pattern_name, tfidf_score)

    used_subjects = set()
    used_questions = set()

    for sentence, tfidf_score in ranked_sentences:
        # filtre de bază
        words = sentence.split()
        if len(words) < 8 or len(words) > 35:
            continue

        if sentence.count(",") > 4:
            continue

        result = match_sentence(sentence)
        if result is None:
            continue

        rule, m = result
        question_text = rule.make_question(m)
        answer = rule.extract_answer(m)
        subject = rule.extract_subject(m)

        # validări
        if not answer or len(answer) < 3:
            continue

        # Skip present perfect: "X has/have + past participle" produces bad questions
        # e.g., "Research has identified..." → "What does Research have?" + "identified..."
        if rule.name == "property":
            verb_text = m.group("verb").lower()
            if verb_text in ("has", "have"):
                first_answer_word = answer.split()[0].lower() if answer.split() else ""
                if (first_answer_word.endswith("ed") or first_answer_word.endswith("en")
                        or first_answer_word in ("been", "become", "begun", "broken",
                        "chosen", "done", "driven", "eaten", "fallen", "given", "gone",
                        "grown", "known", "made", "met", "run", "seen", "shown",
                        "spoken", "taken", "thought", "told", "understood", "written")):
                    continue

        if not question_text or len(question_text) < 10:
            continue

        # respinge răspunsuri prea scurte sau prea generice
        if len(answer.split()) < 2 and rule.name not in ("value", "comparison"):
            continue

        # respinge întrebări unde subiectul pare trunchiat sau invalid
        if subject and len(subject) < 3:
            continue

        # respinge subiecte cu paranteze neîmpereechiate sau caractere stray
        if subject.count("(") != subject.count(")"):
            continue
        if any(ch in subject for ch in "=+^{}[]<>"):
            continue

        # respinge subiecte prea lungi (>5 cuvinte = probabil fragment de propoziție)
        subj_words = subject.split()
        if len(subj_words) > 5:
            continue

        # respinge dacă subiectul conține cuvinte funcționale (fragment de propoziție)
        subj_lower_words = [w.lower() for w in subj_words]
        _BAD_IN_SUBJECT = {"to", "of", "after", "before", "could", "would", "should",
                           "might", "may", "those", "their", "whose", "which",
                           "where", "when", "how", "what", "why", "whether",
                           "because", "although", "since", "while", "until",
                           "into", "from", "between", "through", "during"}
        if _BAD_IN_SUBJECT & set(subj_lower_words):
            continue

        # respinge dacă întrebarea conține cuvinte funcționale care sugerează fragment
        q_lower = question_text.lower()
        if "begins after" in q_lower or "could produce" in q_lower or "have been" in q_lower:
            continue

        # respinge răspunsuri trunchiate (se termină cu cuvânt incomplet)
        last_answer_word = answer.split()[-1] if answer.split() else ""
        if last_answer_word and not last_answer_word[-1].isalnum() and last_answer_word[-1] not in ")]}%°":
            continue

        # respinge dacă întrebarea conține cuvânt trunchiat la sfârșit
        # "normaliz", "regulariz" sunt trunchiate — nu se termină cu sufix valid
        _TRUNCATED = re.compile(r"(?:liz|riz|miz|niz|tiz|giz|biz|diz|fiz|piz|viz|wiz|abl|ibl|nabl|enabl)$", re.I)
        q_last = question_text.rstrip("?").strip().split()[-1] if question_text else ""
        if q_last and _TRUNCATED.search(q_last):
            continue

        # respinge dacă răspunsul începe cu prepoziție/conjuncție (sugerează captură greșită)
        first_answer_word = answer.split()[0].lower() if answer.split() else ""
        if first_answer_word in ("to", "for", "with", "by", "from", "in", "on", "at",
                                  "and", "or", "but", "as", "if", "when", "while"):
            # excepție: "to + verb" e ok ca scop
            if first_answer_word == "to" and len(answer.split()) > 2:
                pass  # ok, e un scop
            else:
                continue

        # evită duplicate
        q_norm = question_text.lower().strip()
        if q_norm in used_questions:
            continue

        subj_norm = subject.lower().strip()
        if subj_norm in used_subjects:
            continue

        # acumulează
        if rule.name not in pattern_answers:
            pattern_answers[rule.name] = []
        pattern_answers[rule.name].append((subject, answer))

        matched_data.append((sentence, question_text, answer, subject, rule.name, tfidf_score))
        used_questions.add(q_norm)
        used_subjects.add(subj_norm)

    # Pasul 2: generează distractori și scorează
    candidates = []

    for sentence, question_text, answer, subject, pattern_name, tfidf_score in matched_data:
        distractors, dist_source = pick_template_distractors(
            correct=answer,
            evidence=sentence,
            pattern_name=pattern_name,
            subject=subject,
            pattern_answers=pattern_answers,
            all_sentences=sentences,
            k=3
        )

        if len(distractors) < 3:
            continue

        options = [answer] + distractors[:3]
        random.shuffle(options)

        # verifică unicitate
        if len(set(opt.lower().strip() for opt in options)) < 4:
            continue

        correct_index = options.index(answer)

        quality = score_template_question(
            question_text, answer, options, sentence, pattern_name, dist_source
        )

        candidates.append({
            "question": question_text,
            "options": options,
            "correct_index": correct_index,
            "evidence": sentence,
            "quality_score": quality
        })

    # Pasul 3: sortează și selectează
    candidates.sort(key=lambda x: x["quality_score"], reverse=True)

    MIN_QUALITY_SCORE = 20 if difficulty == "hard" else 30 if difficulty == "medium" else 40
    filtered = [q for q in candidates if q["quality_score"] >= MIN_QUALITY_SCORE]

    questions = filter_by_difficulty(filtered, difficulty, n_questions)

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
            "warning": f"Only {len(clean_questions)} full questions were generated. "
                       f"Try the Cloze type for more questions.",
            "questions": clean_questions
        }

    return {
        "questions": clean_questions
    }
