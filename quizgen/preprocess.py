import re

_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+')

REPLACEMENTS = {
    "■": "",
    "–": "-",
    "—": "-",
    "−": "-",
    "Â°C": "°C",
    "Â": "",
    "Î¼": "μ",
    "Âµ": "µ",
    "CO■": "CO2",
    "C■H■■O■": "C6H12O6"
}

BAD_PATTERNS = [
    r"\bsuch as a \w+ (stores|contains|uses|provides)\b",  # "such as a X verb"
    r"\bsuch as (a|an) \w+,? (is|are|was|were)\b",
]

def normalize_text(text: str) -> str:
    # înlocuiri pentru caractere corupte / encoding prost
    for bad, good in REPLACEMENTS.items():
        text = text.replace(bad, good)

    text = re.sub(r'-\s*\n\s*', '', text)

    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # elimină heading-uri scurte
        if len(line.split()) <= 8 and not re.search(r'[.!?]$', line):
            continue

        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # unește doar liniile rupte din interiorul propozițiilor
    text = re.sub(r'(?<![.!?])\n(?!\n)', ' ', text)

    # păstrează paragrafele separate
    text = re.sub(r'\n+', '\n', text)

    # apoi transformă în spații pentru segmentare
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def split_sentences(text: str) -> list[str]:
    text = normalize_text(text)
    sentences = _SENT_SPLIT.split(text)

    result = []
    for sentence in sentences:
        sentence = sentence.strip()

        if not (40 <= len(sentence) <= 220):
            continue

        if "Test PDF for Quiz Generator" in sentence:
            continue

        # filtru nou: propoziții cu structură gramaticală stricată
        if any(re.search(p, sentence, re.IGNORECASE) for p in BAD_PATTERNS):
            continue

        result.append(sentence)

    return result