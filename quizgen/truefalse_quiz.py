import random
import re

from .pdf_text import extract_text_from_pdf
from .preprocess import split_sentences
from .tfidf_rank import rank_sentences
from .distractors import build_vocab, normalize_word, KNOWLEDGE_BASE
from .kb_expand import expand_knowledge_base


BAD_STARTS = {"it", "they", "this", "that", "these", "those", "as", "such"}

# Strategies for making a sentence false
# 1. Swap a key term with a distractor from knowledge base
# 2. Swap two key terms within the sentence
# 3. Negate the sentence (add "not" / "does not")
# 4. Swap a number/value


def _find_swappable_term(sentence: str, vocab: set[str]) -> tuple[str, list[str]] | None:
    """Find a term in the sentence that has KB distractors."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]+", sentence)
    for word in words:
        norm = normalize_word(word)
        if norm in KNOWLEDGE_BASE and len(KNOWLEDGE_BASE[norm]) >= 1:
            # Check the word is actually meaningful (not too short)
            if len(norm) >= 3:
                return (word, KNOWLEDGE_BASE[norm])
    return None


def _swap_term(sentence: str, original: str, replacement: str) -> str:
    """Replace original term with replacement, preserving case."""
    if original[0].isupper():
        replacement = replacement[0].upper() + replacement[1:]
    else:
        replacement = replacement.lower()
    pattern = re.compile(rf"\b{re.escape(original)}\b")
    return pattern.sub(replacement, sentence, count=1)


def _negate_sentence(sentence: str) -> str | None:
    """Try to negate a sentence by inserting 'not' or changing verb form."""
    # Pattern: "X is Y" → "X is not Y"
    m = re.search(r"\b(is|are|was|were)\b", sentence)
    if m:
        pos = m.end()
        # Don't negate if already negated
        rest = sentence[pos:pos+10].strip().lower()
        if rest.startswith("not"):
            return None
        return sentence[:pos] + " not" + sentence[pos:]

    # Pattern: "X verb Y" → "X does not verb Y"
    m = re.search(r"\b(contains?|includes?|produces?|causes?|allows?|enables?|prevents?|requires?)\b", sentence)
    if m:
        verb = m.group(0)
        base = verb.rstrip("s") if verb.endswith("s") and not verb.endswith("ss") else verb
        return sentence[:m.start()] + "does not " + base + sentence[m.end():]

    return None


def _swap_number(sentence: str) -> tuple[str, bool]:
    """Swap a number in the sentence with a different one."""
    m = re.search(r"\b(\d+\.?\d*)\b", sentence)
    if not m:
        return sentence, False

    original_num = float(m.group(1))
    if original_num == 0:
        return sentence, False

    # Generate a plausible but wrong number
    multipliers = [0.5, 0.75, 1.5, 2.0, 0.1, 10.0]
    fake_num = original_num * random.choice(multipliers)

    # Keep same format
    if "." in m.group(1):
        decimals = len(m.group(1).split(".")[1])
        fake_str = f"{fake_num:.{decimals}f}"
    else:
        fake_str = str(int(fake_num))

    if fake_str == m.group(1):
        return sentence, False

    new_sentence = sentence[:m.start()] + fake_str + sentence[m.end():]
    return new_sentence, True


def _make_false_sentence(sentence: str, vocab: set[str]) -> tuple[str, str] | None:
    """
    Try to make a sentence false.
    Returns (false_sentence, method_used) or None if can't.
    """
    strategies = []

    # Strategy 1: Swap KB term
    swap_result = _find_swappable_term(sentence, vocab)
    if swap_result:
        original, distractors = swap_result
        replacement = random.choice(distractors)
        false_sent = _swap_term(sentence, original, replacement)
        if false_sent != sentence:
            strategies.append((false_sent, "term_swap"))

    # Strategy 2: Negate
    negated = _negate_sentence(sentence)
    if negated:
        strategies.append((negated, "negation"))

    # Strategy 3: Swap number
    num_swapped, did_swap = _swap_number(sentence)
    if did_swap:
        strategies.append((num_swapped, "number_swap"))

    if not strategies:
        return None

    return random.choice(strategies)


def _score_tf_sentence(sentence: str) -> int:
    """Score how good a sentence is for true/false."""
    score = 0
    words = sentence.split()

    if not words:
        return 0

    # Good length
    if 60 <= len(sentence) <= 160:
        score += 15
    elif 40 <= len(sentence) <= 220:
        score += 5

    # Doesn't start with bad words
    if words[0].lower() not in BAD_STARTS:
        score += 10
    else:
        score -= 20

    # Contains a KB term (easier to make false)
    for w in words:
        if normalize_word(w) in KNOWLEDGE_BASE:
            score += 20
            break

    # Contains a number (can swap it)
    if re.search(r"\b\d+\.?\d*\b", sentence):
        score += 10

    # Contains is/are (can negate)
    if re.search(r"\b(?:is|are|was|were|contains?|includes?|produces?)\b", sentence):
        score += 10

    # Not too many commas
    if sentence.count(",") <= 2:
        score += 5

    return score


def generate_truefalse_quiz_from_pdf(pdf_path: str, n_questions: int = 10, seed: int = 42, difficulty: str = "medium") -> dict:
    """Generate a True/False quiz from a PDF."""
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
        pass

    vocab = build_vocab(sentences)
    ranked_sentences = rank_sentences(sentences, top_k=220)

    # Score all sentences for T/F suitability
    scored = []
    for sentence, tfidf_score in ranked_sentences:
        words = sentence.split()
        if len(words) < 6 or len(words) > 35:
            continue
        if sentence.count(",") > 4:
            continue

        tf_score = _score_tf_sentence(sentence)
        scored.append((sentence, tf_score + tfidf_score * 10))

    scored.sort(key=lambda x: x[1], reverse=True)

    # Generate questions — aim for ~50% true, ~50% false
    candidates = []
    used_sentences = set()

    for sentence, score in scored:
        if sentence in used_sentences:
            continue

        # Decide: true or false
        make_true = random.random() < 0.5

        if make_true:
            # TRUE question — use original sentence
            candidates.append({
                "question": sentence,
                "options": ["True", "False"],
                "correct_index": 0,
                "evidence": sentence,
                "quality_score": score,
            })
            used_sentences.add(sentence)
        else:
            # FALSE question — modify the sentence
            result = _make_false_sentence(sentence, vocab)
            if result:
                false_sentence, method = result
                # Make sure it's actually different
                if false_sentence.lower() != sentence.lower():
                    candidates.append({
                        "question": false_sentence,
                        "options": ["True", "False"],
                        "correct_index": 1,
                        "evidence": f"Original: {sentence}",
                        "quality_score": score + 5,  # slight bonus for false (harder to generate)
                    })
                    used_sentences.add(sentence)

        if len(candidates) >= n_questions * 2:
            break

    # Sort by quality — easy takes top (clearest), hard takes bottom (trickiest)
    candidates.sort(key=lambda x: x["quality_score"], reverse=True)

    if difficulty == "hard":
        candidates = candidates[len(candidates)//2:] + candidates[:len(candidates)//2]
    elif difficulty == "easy":
        pass  # already sorted best-first
    else:  # medium
        mid = len(candidates) // 4
        candidates = candidates[mid:] + candidates[:mid]

    true_qs = [q for q in candidates if q["correct_index"] == 0]
    false_qs = [q for q in candidates if q["correct_index"] == 1]

    # Difficulty affects true/false ratio
    if difficulty == "easy":
        n_true = int(n_questions * 0.6)  # more true = easier
    elif difficulty == "hard":
        n_true = int(n_questions * 0.3)  # more false = harder
    else:
        n_true = n_questions // 2
    n_false = n_questions - n_true

    selected = true_qs[:n_true] + false_qs[:n_false]

    # If not enough of one type, fill with the other
    if len(selected) < n_questions:
        remaining = [q for q in candidates if q not in selected]
        selected.extend(remaining[:n_questions - len(selected)])

    random.shuffle(selected)

    questions = []
    for q in selected[:n_questions]:
        questions.append({
            "question": q["question"],
            "options": q["options"],
            "correct_index": q["correct_index"],
            "evidence": q["evidence"],
        })

    if not questions:
        return {
            "error": "Could not generate True/False questions from this PDF."
        }

    if len(questions) < n_questions:
        return {
            "warning": f"Only {len(questions)} True/False questions were generated.",
            "questions": questions,
        }

    return {"questions": questions}
