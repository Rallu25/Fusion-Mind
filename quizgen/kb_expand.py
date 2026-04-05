"""
Auto-expand the knowledge base by extracting related terms from PDF text.

Detects patterns like:
- "X, Y, and Z" (coordination) → X: [Y, Z], Y: [X, Z], Z: [X, Y]
- "such as X, Y, and Z" → parent: [X, Y, Z]
- "including X, Y, and Z" → parent: [X, Y, Z]
- "X or Y" → X: [Y], Y: [X]
- "e.g. X, Y, Z" → parent: [X, Y, Z]
"""

import json
import os
import re

from .distractors import KNOWLEDGE_BASE_PATH, normalize_word


# Minimum word length to be considered a term
MIN_TERM_LEN = 3

# Words to skip (too generic)
_SKIP_WORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "has", "its", "how", "man", "new",
    "now", "old", "see", "way", "who", "did", "get", "let", "say", "too",
    "use", "also", "been", "more", "most", "much", "some", "such", "than",
    "that", "them", "then", "they", "this", "very", "when", "will", "with",
    "each", "from", "have", "just", "like", "make", "many", "only", "over",
    "well", "what", "your", "about", "after", "other", "which", "their",
    "there", "these", "those", "would", "could", "should", "where", "while",
    "being", "between", "through", "during", "before", "process", "method",
    "system", "result", "model", "data", "structure", "information",
}


def _clean_term(term: str) -> str:
    """Clean a term for KB entry."""
    t = term.strip().strip(".,;:()\"'").strip()
    # Remove leading articles
    t = re.sub(r"^(?:a|an|the)\s+", "", t, flags=re.IGNORECASE).strip()
    return t


def _is_valid_term(term: str) -> bool:
    """Check if a term is valid for KB."""
    t = term.lower().strip()
    if len(t) < MIN_TERM_LEN:
        return False
    if t in _SKIP_WORDS:
        return False
    if not re.match(r"^[a-zA-Z]", t):
        return False
    # Max 3 words
    words = t.split()
    if len(words) > 3:
        return False
    # Each word must be a real word
    for w in words:
        if len(w) < 2:
            return False
        if w in _SKIP_WORDS:
            return False
    # First word must not be a preposition/article/conjunction
    _BAD_FIRST = {"to", "in", "on", "at", "by", "for", "of", "as", "or",
                  "an", "if", "so", "up", "no", "do", "we", "he", "my"}
    if words[0] in _BAD_FIRST:
        return False
    return True


def _extract_coordination(sentences: list[str]) -> list[list[str]]:
    """Extract groups of related terms from coordination patterns."""
    groups = []

    # Pattern: "X, Y, and Z" or "X, Y, Z, and W"
    pat_and = re.compile(
        r"(\b[A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*)?"
        r"(?:\s*,\s*[A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*)?)*"
        r"\s*,?\s+and\s+[A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*)?)\b"
    )

    # Pattern: "X or Y"
    pat_or = re.compile(
        r"\b([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*)?)\s+or\s+([A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*)?)\b"
    )

    for sent in sentences:
        # "X, Y, and Z"
        for m in pat_and.finditer(sent):
            text = m.group(1)
            # Split by comma and "and"
            parts = re.split(r"\s*,\s*|\s+and\s+", text)
            terms = [_clean_term(p) for p in parts if _clean_term(p)]
            terms = [t for t in terms if _is_valid_term(t)]
            if 2 <= len(terms) <= 6:
                groups.append(terms)

        # "X or Y"
        for m in pat_or.finditer(sent):
            t1 = _clean_term(m.group(1))
            t2 = _clean_term(m.group(2))
            if _is_valid_term(t1) and _is_valid_term(t2):
                groups.append([t1, t2])

    return groups


def _extract_such_as(sentences: list[str]) -> list[tuple[str, list[str]]]:
    """Extract 'X such as Y, Z, W' patterns."""
    results = []

    pat = re.compile(
        r"(\b[A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*)?)\s+"
        r"(?:such\s+as|including|like|e\.g\.?|for\s+example)\s+"
        r"([^.;]{5,80})",
        re.IGNORECASE
    )

    for sent in sentences:
        for m in pat.finditer(sent):
            parent = _clean_term(m.group(1))
            rest = m.group(2)

            # Split the examples
            parts = re.split(r"\s*,\s*|\s+and\s+|\s+or\s+", rest)
            terms = [_clean_term(p) for p in parts if _clean_term(p)]
            terms = [t for t in terms if _is_valid_term(t)]

            if _is_valid_term(parent) and len(terms) >= 2:
                results.append((parent, terms[:5]))

    return results


def _extract_is_found_in(sentences: list[str]) -> list[tuple[str, str]]:
    """Extract 'X is found in Y' patterns → related locations/habitats."""
    results = []
    pat = re.compile(
        r"([A-Z][A-Za-z\s\-()]+?)\s*-?\s*(?:is|are)\s+found\s+in\s+([^.;]{5,60})",
        re.IGNORECASE
    )
    for sent in sentences:
        for m in pat.finditer(sent):
            subject = _clean_term(m.group(1))
            location = _clean_term(m.group(2))
            # Clean subject: take only the last capitalized noun phrase
            # Handles "...text African Lion - Panthera..." → "African Lion"
            subject = re.split(r"\s*[-\(]", subject)[0].strip()
            # If subject has junk prefix, take last 2-3 capitalized words
            words = subject.split()
            cap_start = 0
            for idx in range(len(words) - 1, -1, -1):
                if words[idx][0].isupper():
                    cap_start = idx
                else:
                    break
            if cap_start > 0:
                subject = " ".join(words[cap_start:])
            # Skip if subject looks like a number, measurement, or has junk
            if re.match(r"^\d", subject) or len(subject) < 3:
                continue
            # If subject has a lowercase word in the middle, take only after it
            # e.g., "Tigers Bengal Tiger" → "Bengal Tiger"
            swords = subject.split()
            for idx in range(len(swords) - 1, 0, -1):
                if swords[idx - 1][0].islower():
                    subject = " ".join(swords[idx:])
                    break
            # Skip subjects with more than 3 words (likely junk concatenation)
            if len(subject.split()) > 3:
                continue
            # Skip if subject contains common non-name words
            subj_lower = subject.lower()
            if any(w in subj_lower for w in ["metre", "second", "minute", "hour", "year", "kilomet"]):
                continue
            if _is_valid_term(subject) and len(location) >= 3 and len(subject) >= 6:
                results.append((subject, location))
    return results


def _extract_parenthetical(sentences: list[str]) -> list[list[str]]:
    """Extract 'X (A, B, C)' patterns → A, B, C are mutual distractors."""
    results = []
    pat = re.compile(
        r"[A-Za-z][\w\s\-]*?\s*\(([^)]{5,80})\)"
    )
    for sent in sentences:
        for m in pat.finditer(sent):
            inside = m.group(1)
            # Only process if it looks like a list (has commas or "and")
            if "," not in inside and " and " not in inside:
                continue
            parts = re.split(r"\s*,\s*|\s+and\s+|\s+or\s+", inside)
            terms = [_clean_term(p) for p in parts if _clean_term(p)]
            terms = [t for t in terms if _is_valid_term(t)]
            if len(terms) >= 2:
                results.append(terms[:5])
    return results


def _extract_colon_list(sentences: list[str]) -> list[list[str]]:
    """Extract 'X: A, B, C' patterns → A, B, C are mutual distractors."""
    results = []
    pat = re.compile(
        r"[A-Za-z][\w\s\-]*?:\s*([^.;]{5,80})"
    )
    for sent in sentences:
        for m in pat.finditer(sent):
            rest = m.group(1)
            # Only process if it looks like a list
            if "," not in rest and " and " not in rest:
                continue
            parts = re.split(r"\s*,\s*|\s+and\s+|\s+or\s+", rest)
            terms = [_clean_term(p) for p in parts if _clean_term(p)]
            terms = [t for t in terms if _is_valid_term(t)]
            if len(terms) >= 2:
                results.append(terms[:5])
    return results


def _extract_definitions(sentences: list[str]) -> list[tuple[str, str]]:
    """Extract 'X is/are the Y' patterns to find related category terms."""
    results = []
    pat = re.compile(
        r"([A-Z][A-Za-z\s\-]+?)\s+(?:is|are)\s+(?:the\s+)?(?:largest|smallest|fastest|slowest|"
        r"most|only|first|second|third|main|primary|key)\s+([^.;]{5,60})",
        re.IGNORECASE
    )
    for sent in sentences:
        for m in pat.finditer(sent):
            subject = _clean_term(m.group(1))
            desc = _clean_term(m.group(2))
            if _is_valid_term(subject):
                results.append((subject, desc))
    return results


def extract_new_terms(sentences: list[str]) -> dict[str, list[str]]:
    """
    Extract new term-distractor pairs from sentences.
    Returns dict of {term: [related_terms]}.
    """
    new_entries = {}

    def _make_key(term):
        """Make a KB key: lowercase, strip, single words use normalize_word, multi-word keep spaces."""
        t = term.strip().lower()
        if " " in t:
            return t
        return normalize_word(t)

    # From coordination patterns (X, Y, and Z → each is distractor for the others)
    coord_groups = _extract_coordination(sentences)
    for group in coord_groups:
        for i, term in enumerate(group):
            key = _make_key(term)
            if not key or len(key) < MIN_TERM_LEN:
                continue
            others = [g for j, g in enumerate(group) if j != i]
            if key not in new_entries:
                new_entries[key] = []
            for other in others:
                if other.lower() not in [x.lower() for x in new_entries[key]]:
                    new_entries[key].append(other)

    # From "such as" patterns (parent → children are distractors for each other)
    such_as_groups = _extract_such_as(sentences)
    for parent, children in such_as_groups:
        for i, child in enumerate(children):
            key = _make_key(child)
            if not key or len(key) < MIN_TERM_LEN:
                continue
            others = [c for j, c in enumerate(children) if j != i]
            if key not in new_entries:
                new_entries[key] = []
            for other in others:
                if other.lower() not in [x.lower() for x in new_entries[key]]:
                    new_entries[key].append(other)

    # From parenthetical lists: "X (A, B, C)" → mutual distractors
    for group in _extract_parenthetical(sentences):
        for i, term in enumerate(group):
            key = _make_key(term)
            if not key or len(key) < MIN_TERM_LEN:
                continue
            others = [g for j, g in enumerate(group) if j != i]
            if key not in new_entries:
                new_entries[key] = []
            for other in others:
                if other.lower() not in [x.lower() for x in new_entries[key]]:
                    new_entries[key].append(other)

    # From colon lists: "X: A, B, C" → mutual distractors
    for group in _extract_colon_list(sentences):
        for i, term in enumerate(group):
            key = _make_key(term)
            if not key or len(key) < MIN_TERM_LEN:
                continue
            others = [g for j, g in enumerate(group) if j != i]
            if key not in new_entries:
                new_entries[key] = []
            for other in others:
                if other.lower() not in [x.lower() for x in new_entries[key]]:
                    new_entries[key].append(other)

    # From "is found in" patterns → all subjects are related (same domain)
    found_in = _extract_is_found_in(sentences)
    found_subjects = [subj for subj, _ in found_in if _is_valid_term(subj)]
    if len(found_subjects) >= 2:
        for i, subj in enumerate(found_subjects):
            key = _make_key(subj)
            if not key or len(key) < MIN_TERM_LEN:
                continue
            others = [s for j, s in enumerate(found_subjects) if j != i]
            if key not in new_entries:
                new_entries[key] = []
            for other in others[:4]:
                if other.lower() not in [x.lower() for x in new_entries[key]]:
                    new_entries[key].append(other)

    # From superlative definitions → group subjects by category
    definitions = _extract_definitions(sentences)
    for subject, desc in definitions:
        key = _make_key(subject)
        if not key or len(key) < MIN_TERM_LEN:
            continue
        # Find other subjects with definitions (they're in the same domain)
        others = [s for s, d in definitions if s.lower() != subject.lower()]
        if others and key not in new_entries:
            new_entries[key] = []
        for other in others[:4]:
            if key in new_entries and other.lower() not in [x.lower() for x in new_entries[key]]:
                new_entries[key].append(other)

    # Limit distractors per term to 5
    for key in new_entries:
        new_entries[key] = new_entries[key][:5]

    return new_entries


def expand_knowledge_base(sentences: list[str]) -> int:
    """
    Extract new terms from sentences and add them to knowledge_base.json.
    Returns the number of new terms added.
    """
    # Load current KB
    if os.path.exists(KNOWLEDGE_BASE_PATH):
        with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
            kb = json.load(f)
    else:
        kb = {}

    new_terms = extract_new_terms(sentences)
    added = 0

    for term, distractors in new_terms.items():
        if not distractors:
            continue

        if term in kb:
            # Add new distractors to existing entry (avoid duplicates)
            existing = {d.lower() for d in kb[term]}
            for d in distractors:
                if d.lower() not in existing and len(kb[term]) < 6:
                    kb[term].append(d)
                    existing.add(d.lower())
        else:
            # New entry
            kb[term] = distractors
            added += 1

    # Save updated KB
    with open(KNOWLEDGE_BASE_PATH, "w", encoding="utf-8") as f:
        json.dump(kb, f, indent=2, ensure_ascii=False)

    return added
