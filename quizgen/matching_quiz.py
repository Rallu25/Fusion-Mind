import random
import re

from .pdf_text import extract_text_from_pdf
from .preprocess import split_sentences
from .tfidf_rank import rank_sentences
from .template_patterns import clean_subject, clean_answer, _subject_valid
from .kb_expand import expand_knowledge_base

# Patterns that extract term-definition pairs
_DEFINITION_PATTERNS = [
    # "X is/are a/an/the Y"
    re.compile(
        r"(?P<subject>[A-Za-z][A-Za-z0-9°µ\-/]+(?:\s+[A-Za-z0-9°µ\-/]+){0,3})"
        r"\s+(?:is|are)\s+"
        r"(?P<object>(?:a|an|the)\s+[^.;]{5,120})",
        re.IGNORECASE
    ),
    # "X refers to / is defined as / is known as Y"
    re.compile(
        r"(?P<subject>[A-Z][A-Za-z0-9°µ\-/]+(?:\s+[A-Za-z0-9°µ\-/]+){0,3})"
        r"\s+(?:refers?\s+to|is\s+defined\s+as|is\s+known\s+as|is\s+called)\s+"
        r"(?P<object>[^.;]{5,120})",
        re.IGNORECASE
    ),
    # "X consists of / is composed of / is made of Y"
    re.compile(
        r"(?P<subject>[A-Z][A-Za-z0-9°µ\-/]+(?:\s+[A-Za-z0-9°µ\-/]+){0,3})"
        r"\s+(?:consists?\s+of|is\s+composed\s+of|is\s+made\s+(?:up\s+)?of)\s+"
        r"(?P<object>[^.;]{5,120})",
        re.IGNORECASE
    ),
    # "X is used for/to Y"
    re.compile(
        r"(?P<subject>[A-Z][A-Za-z0-9°µ\-/]+(?:\s+[A-Za-z0-9°µ\-/]+){0,3})"
        r"\s+(?:is|are)\s+used\s+(?:for|to|in)\s+"
        r"(?P<object>[^.;]{5,120})",
        re.IGNORECASE
    ),
]

# Blocked first words for subjects
_BLOCKED = {
    "it", "they", "this", "that", "these", "those", "there", "here",
    "one", "some", "we", "he", "she", "following", "above", "below",
}


def _extract_pairs(sentences: list[str], ranked: list[tuple[str, float]]) -> list[dict]:
    """Extract term-definition pairs from ranked sentences."""
    pairs = []
    used_terms = set()

    for sentence, _score in ranked:
        words = sentence.split()
        if len(words) < 6 or len(words) > 35:
            continue
        if sentence.count(",") > 4:
            continue

        for pat in _DEFINITION_PATTERNS:
            m = pat.search(sentence)
            if not m:
                continue

            # Validate subject
            if not _subject_valid(m):
                continue

            term = clean_subject(m.group("subject"))
            definition = clean_answer(m.group("object"))

            if not term or len(term) < 2:
                continue
            if not definition or len(definition) < 10:
                continue

            # Skip blocked subjects
            first_word = term.split()[0].lower()
            if first_word in _BLOCKED:
                continue

            # Skip duplicate terms
            term_lower = term.lower()
            if term_lower in used_terms:
                continue
            used_terms.add(term_lower)

            pairs.append({
                "term": term,
                "definition": definition,
                "evidence": sentence,
            })
            break  # one match per sentence

    return pairs


def generate_matching_quiz_from_pdf(pdf_path: str, n_questions: int = 10, seed: int = 42) -> dict:
    """
    Generate a matching quiz from a PDF.
    Each question is a set of 4-6 term-definition pairs to match.
    """
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

    ranked = rank_sentences(sentences, top_k=220)
    all_pairs = _extract_pairs(sentences, ranked)

    if len(all_pairs) < 4:
        return {
            "error": f"Not enough term-definition pairs found ({len(all_pairs)}). "
                     f"Need at least 4. Try a PDF with more definitions."
        }

    # Generate matching rounds — each round has 4-6 pairs
    pairs_per_round = min(6, max(4, len(all_pairs) // max(1, n_questions)))
    pairs_per_round = min(pairs_per_round, len(all_pairs))

    questions = []
    remaining = all_pairs[:]
    random.shuffle(remaining)

    while len(questions) < n_questions and len(remaining) >= 4:
        take = min(pairs_per_round, len(remaining))
        round_pairs = remaining[:take]
        remaining = remaining[take:]

        # Build the question
        terms = [p["term"] for p in round_pairs]
        definitions = [p["definition"] for p in round_pairs]

        # Scramble definitions
        correct_order = list(range(len(round_pairs)))
        shuffled_defs = list(enumerate(definitions))
        random.shuffle(shuffled_defs)

        # correct_mapping: for each term index, which shuffled definition index is correct
        shuffled_indices = [orig_idx for orig_idx, _ in shuffled_defs]
        correct_mapping = []
        for term_idx in range(len(terms)):
            correct_mapping.append(shuffled_indices.index(term_idx))

        questions.append({
            "question": f"Match each term with its correct definition ({len(terms)} pairs)",
            "terms": terms,
            "definitions": [d for _, d in shuffled_defs],
            "correct_mapping": correct_mapping,
            "evidence": "; ".join(p["evidence"][:60] + "..." for p in round_pairs),
            "quiz_type": "matching",
        })

    if not questions:
        return {
            "error": "Could not generate matching questions from this PDF."
        }

    if len(questions) < n_questions:
        return {
            "warning": f"Only {len(questions)} matching rounds were generated "
                       f"({len(all_pairs)} pairs found in total).",
            "questions": questions,
        }

    return {"questions": questions}
