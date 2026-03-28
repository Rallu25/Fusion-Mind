import json
import os
import random
import re


GENERIC_WORDS = {
    "process", "model", "models", "data", "system", "systems", "result", "results",
    "method", "methods", "structure", "energy", "learning", "rules", "cells",
    "plant", "plants", "human", "brain", "noise", "random", "tasks", "branch",
    "object", "objects", "study", "problem", "information", "science", "space"
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

    kb_distractors = get_kb_distractors(correct, sentence, k=k + 2)
    doc_distractors = get_doc_distractors(correct, vocab, sentence, k=k * 3)

    # combinăm toți candidații
    combined = kb_distractors[:]
    for item in doc_distractors:
        item_norm = normalize_word(item)
        existing_norms = {normalize_word(x) for x in combined}
        if item_norm not in existing_norms:
            combined.append(item)

    # filtrăm distractorii ambigui
    combined = filter_ambiguous_distractors(correct, combined, sentence, all_sentences)

    return format_options(correct, combined[:k])