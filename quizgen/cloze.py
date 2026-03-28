import re

WORD = re.compile(r"[A-Za-z][A-Za-z0-9°/%\-\+/]*")

BAD_TARGETS = {
    "located", "contains", "called", "used", "known", "helps", "study",
    "keeps", "works", "learn", "designed", "observe", "collect", "detect",
    "responsible", "finite", "common", "correct", "clear",
    "modern", "scientific", "industrial", "astronomical", "optical"
}

def _load_preferred_targets() -> set[str]:
    """Load preferred targets dynamically from knowledge base keys."""
    import json, os
    targets = {
        "ph", "nacl", "co2", "co₂", "c₆h₁₂o₆", "mol/l",
        "ghz", "khz", "hz", "ms", "gb", "tb", "a_w"
    }
    kb_path = os.path.join("data", "knowledge_base.json")
    if os.path.exists(kb_path):
        with open(kb_path, "r", encoding="utf-8") as f:
            kb = json.load(f)
            targets.update(kb.keys())
    return targets


PREFERRED_TARGETS = _load_preferred_targets()


def pick_target_word(sentence: str, doc_vocab: set[str]) -> str | None:
    tokens = [m.group(0) for m in WORD.finditer(sentence)]
    if not tokens:
        return None

    candidates = []
    for idx, w in enumerate(tokens):
        lw = w.lower()

        if lw not in doc_vocab:
            continue

        if len(lw) < 2:
            continue

        if lw in BAD_TARGETS:
            continue

        score = 0

        if lw in PREFERRED_TARGETS:
            score += 100

        # penalizează primul cuvânt dacă pare doar introductiv
        if idx == 0 and lw not in PREFERRED_TARGETS:
            score -= 20

        # preferă termeni mai lungi
        score += len(lw)

        # preferă termeni cu cifre/simboluri utile în documente tehnice
        if any(ch.isdigit() for ch in w):
            score += 10

        # preferă majuscule doar dacă nu sunt adjective banale
        if w[0].isupper() and lw not in BAD_TARGETS:
            score += 5

        candidates.append((score, w))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]


def make_cloze(sentence: str, target: str) -> str:
    pattern = re.compile(rf"\b{re.escape(target)}\b")
    return pattern.sub("____", sentence, count=1)