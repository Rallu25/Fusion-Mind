import json
import os
import random
import re


GENERIC_WORDS = {
    "process", "model", "models", "data", "system", "systems", "result", "results",
    "method", "methods", "structure", "energy", "learning", "rules", "cells",
    "plant", "plants", "human", "brain", "noise", "random", "tasks", "branch",
    "object", "objects", "study", "problem", "information", "science", "space",
    "term", "concept", "phenomenon", "substance", "element", "unit",
    "property", "characteristic", "feature", "aspect", "attribute",
    "type", "kind", "form", "category", "class",
    "theory", "principle", "law", "rule", "mechanism",
    "example", "case", "instance", "factor", "component",
}

# sufixe comune pentru detectarea rădăcinii comune
COMMON_SUFFIXES = [
    "tion", "sion", "ment", "ness", "ity", "ous", "ive", "able", "ible",
    "ing", "ated", "ized", "ised", "al", "ful", "less", "ly", "er", "or",
    "ist", "ism", "ence", "ance", "ure", "ical", "ology", "eous", "ious"
]

KNOWLEDGE_BASE_PATH = os.path.join("data", "knowledge_base.json")


def load_knowledge_base() -> dict:
    if not os.path.exists(KNOWLEDGE_BASE_PATH):
        return {}

    with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


KNOWLEDGE_BASE = load_knowledge_base()


def build_vocab(sentences: list[str]) -> set[str]:
    vocab = set()

    for sentence in sentences:
        for word in sentence.split():
            cleaned_word = normalize_word(word)
            cleaned_word = cleaned_word.lower()

            if len(cleaned_word) >= 3 and cleaned_word not in GENERIC_WORDS:
                vocab.add(cleaned_word)

    return vocab


def normalize_word(word: str) -> str:
    return "".join(ch for ch in word.lower() if ch.isalpha() or ch == "-").strip()


def get_kb_distractors(correct: str, sentence: str, k: int = 3) -> list[str]:
    correct_norm = normalize_word(correct)
    sentence_lower = sentence.lower()

    if correct_norm not in KNOWLEDGE_BASE:
        return []

    candidates = []
    for item in KNOWLEDGE_BASE[correct_norm]:
        item_norm = normalize_word(item)

        if not item_norm:
            continue

        if item_norm == correct_norm:
            continue

        if item_norm in sentence_lower:
            continue

        candidates.append(item)

    return candidates[:k]


def get_doc_distractors(correct: str, vocab: set[str], sentence: str, k: int = 3) -> list[str]:
    correct_lower = normalize_word(correct)

    sentence_words = set()
    for word in sentence.split():
        cleaned_word = normalize_word(word)
        if cleaned_word:
            sentence_words.add(cleaned_word)

    candidates = []
    for word in vocab:
        if word == correct_lower:
            continue

        if word in sentence_words:
            continue

        if not word.isalpha():
            continue

        if abs(len(word) - len(correct_lower)) > 3:
            continue

        candidates.append(word)

    random.shuffle(candidates)
    return candidates[:k]


def get_simple_stem(word: str) -> str:
    """Scoate un stem simplu prin eliminarea sufixelor comune."""
    w = word.lower()
    for suffix in sorted(COMMON_SUFFIXES, key=len, reverse=True):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[:-len(suffix)]
    return w


def shares_stem(word1: str, word2: str) -> bool:
    """Verifică dacă două cuvinte au aceeași rădăcină."""
    s1 = get_simple_stem(word1)
    s2 = get_simple_stem(word2)
    if s1 == s2:
        return True
    # verifică și dacă unul e prefix al celuilalt (ex: "supervise" / "supervised")
    shorter, longer = sorted([s1, s2], key=len)
    if len(shorter) >= 4 and longer.startswith(shorter):
        return True
    return False


def get_context_words(sentence: str, target: str, window: int = 2) -> set[str]:
    """Extrage cuvintele vecine (context) din jurul target-ului."""
    words = re.findall(r"[A-Za-z]+", sentence.lower())
    target_lower = target.lower()
    context = set()
    for i, w in enumerate(words):
        if w == target_lower:
            for j in range(max(0, i - window), min(len(words), i + window + 1)):
                if j != i:
                    context.add(words[j])
            break
    return context


def distractor_fits_context(distractor: str, context_words: set[str],
                            all_sentences: list[str], threshold: int = 2) -> bool:
    """
    Verifică dacă distractorul apare în contexte similare în document.
    Dacă distractorul apare lângă >= threshold cuvinte din contextul original,
    e posibil să fie un răspuns valid → ambiguu.
    """
    dist_lower = distractor.lower()
    for sent in all_sentences:
        sent_lower = sent.lower()
        if dist_lower not in sent_lower.split():
            continue
        sent_words = set(re.findall(r"[A-Za-z]+", sent_lower))
        overlap = context_words & sent_words
        if len(overlap) >= threshold:
            return True
    return False


def filter_ambiguous_distractors(correct: str, distractors: list[str],
                                  sentence: str, all_sentences: list[str]) -> list[str]:
    """Elimină distractorii ambigui care ar putea fi și ei corecți."""
    correct_norm = normalize_word(correct)
    context_words = get_context_words(sentence, correct, window=2)
    filtered = []

    for d in distractors:
        d_norm = normalize_word(d)

        # 1. Elimină dacă au aceeași rădăcină (ex: "supervised" vs "supervision")
        if shares_stem(correct_norm, d_norm):
            continue

        # 2. Elimină dacă distractorul apare în context similar în document
        if context_words and distractor_fits_context(d_norm, context_words, all_sentences):
            continue

        filtered.append(d)

    return filtered


# ── GRAMMATICAL VALIDATION ──

_VOWELS = set("aeiouAEIOU")

_NOUN_SUFFIXES = {"tion", "sion", "ment", "ness", "ity", "ance", "ence", "ism",
                  "ist", "ogy", "ure", "dom", "ship", "hood", "age", "ery"}
_ADJ_SUFFIXES = {"ous", "ive", "able", "ible", "ful", "less", "ical", "eous",
                 "ious", "ular", "ary", "ory", "ant", "ent"}
_VERB_SUFFIXES = {"ate", "ize", "ise", "ify"}
_ADVERB_SUFFIX = "ly"

# Common verbs that shouldn't be distractors for nouns
_COMMON_VERBS = {
    "run", "runs", "running", "make", "makes", "making", "take", "takes",
    "give", "gives", "go", "goes", "come", "comes", "see", "sees",
    "know", "knows", "think", "thinks", "find", "finds", "become",
    "keep", "keeps", "begin", "begins", "seem", "seems", "help", "helps",
    "show", "shows", "hear", "hears", "play", "plays", "move", "moves",
    "try", "tries", "ask", "asks", "need", "needs", "call", "calls",
    "bring", "brings", "write", "writes", "provide", "provides",
    "happen", "happens", "include", "includes", "allow", "allows",
}


def _guess_word_type(word: str) -> str:
    """Guess if a word is noun, adjective, verb, or adverb based on suffix."""
    w = word.lower()
    if w.endswith(_ADVERB_SUFFIX) and len(w) > 4:
        return "adverb"
    for suf in sorted(_VERB_SUFFIXES, key=len, reverse=True):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return "verb"
    for suf in sorted(_ADJ_SUFFIXES, key=len, reverse=True):
        if w.endswith(suf) and len(w) - len(suf) >= 2:
            return "adjective"
    for suf in sorted(_NOUN_SUFFIXES, key=len, reverse=True):
        if w.endswith(suf) and len(w) - len(suf) >= 2:
            return "noun"
    return "unknown"


def _is_likely_plural(word: str) -> bool:
    """Check if word looks plural."""
    w = word.lower()
    if w.endswith("ss") or w.endswith("us") or w.endswith("is"):
        return False
    if w.endswith("ies") or w.endswith("es") or w.endswith("s"):
        return True
    return False


def _get_preceding_word(sentence: str, target: str) -> str:
    """Get the word immediately before the target in the sentence."""
    words = sentence.split()
    target_lower = target.lower()
    for i, w in enumerate(words):
        if normalize_word(w) == normalize_word(target_lower) and i > 0:
            return words[i - 1].lower().strip(".,;:()\"'")
    return ""


def grammatical_filter(correct: str, distractors: list[str],
                       sentence: str) -> list[str]:
    """Filter distractors that don't fit grammatically in the sentence context."""
    correct_lower = correct.lower()
    preceding = _get_preceding_word(sentence, correct)
    correct_type = _guess_word_type(correct_lower)
    correct_plural = _is_likely_plural(correct_lower)

    filtered = []
    correct_word_count = len(correct.split())

    for d in distractors:
        d_lower = d.lower()

        # 0. Multi-word distractors for single-word targets (and vice versa) are suspicious
        d_word_count = len(d.split())
        if correct_word_count == 1 and d_word_count > 1:
            continue
        if correct_word_count > 1 and d_word_count == 1:
            continue

        # 0b. Reject gerund phrases as distractors for non-gerund targets
        if d_lower.split()[0].endswith("ing") and not correct_lower.split()[0].endswith("ing"):
            if d_word_count > 1:
                continue

        # 1. Article agreement: "a" + consonant, "an" + vowel
        if preceding == "a" and d_lower and d_lower[0] in _VOWELS:
            continue
        if preceding == "an" and d_lower and d_lower[0] not in _VOWELS:
            continue

        # 2. Number agreement: plural target needs plural distractor
        d_plural = _is_likely_plural(d_lower)
        if correct_plural != d_plural:
            # Exception: some words don't follow simple plural rules
            # Only enforce if both are clearly regular words
            if len(correct_lower) > 4 and len(d_lower) > 4:
                continue

        # 3. Word type consistency
        d_type = _guess_word_type(d_lower)
        if correct_type != "unknown" and d_type != "unknown":
            if correct_type != d_type:
                # Nouns and adjectives can sometimes interchange, allow it
                if not ({correct_type, d_type} <= {"noun", "adjective"}):
                    continue

        # 4. Don't use common verbs as distractors for nouns
        _NOUN_CONTEXT = {"the", "a", "an", "this", "that", "each", "every",
                         "in", "of", "for", "by", "with", "from", "on", "at",
                         "through", "between", "during", "about", "into"}
        if preceding in _NOUN_CONTEXT:
            if d_lower in _COMMON_VERBS:
                continue
            # Also reject past tenses and adjectives after prepositions
            if preceding in ("in", "of", "for", "by", "with", "from", "on", "at",
                             "through", "between", "during", "about", "into"):
                d_type_check = _guess_word_type(d_lower)
                if d_type_check in ("verb", "adjective") and d_lower.endswith(("ed", "er", "est")):
                    continue

        # 5. Adverbs should not be distractors for non-adverbs
        if d_lower.endswith("ly") and not correct_lower.endswith("ly"):
            if len(d_lower) > 4:
                continue
        if correct_lower.endswith("ly") and not d_lower.endswith("ly"):
            if len(correct_lower) > 4:
                continue

        filtered.append(d)

    return filtered


def format_options(correct: str, distractors: list[str]) -> list[str]:
    formatted = []

    for item in distractors:
        if correct[:1].isupper():
            formatted.append(item.capitalize())
        else:
            formatted.append(item.lower())

    return formatted


def pick_distractors(correct: str, vocab: set[str], sentence: str,
                     k: int = 3, all_sentences: list[str] = None) -> list[str]:
    if all_sentences is None:
        all_sentences = []

    kb_distractors = get_kb_distractors(correct, sentence, k=k + 4)
    doc_distractors = get_doc_distractors(correct, vocab, sentence, k=k * 4)

    # combinăm toți candidații
    combined = kb_distractors[:]
    for item in doc_distractors:
        item_norm = normalize_word(item)
        existing_norms = {normalize_word(x) for x in combined}
        if item_norm not in existing_norms:
            combined.append(item)

    # filtrăm distractorii ambigui
    combined = filter_ambiguous_distractors(correct, combined, sentence, all_sentences)

    # filtrăm distractorii care nu se potrivesc gramatical
    combined = grammatical_filter(correct, combined, sentence)

    return format_options(correct, combined[:k])