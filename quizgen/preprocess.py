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


def _fix_glued_sentences(text: str) -> str:
    """Insert period where two sentences are glued without punctuation.
    Detects patterns like '...lowercase word Uppercase word...' mid-text
    where a sentence boundary is missing."""
    # Match: lowercase word followed by space and uppercase word that starts a new sentence
    # Avoid splitting on acronyms, proper nouns after articles, etc.
    _GLUE_PAT = re.compile(
        r'([a-z]{2,})\s+((?:The|A|An|This|These|That|Those|It|They|In|On|As|'
        r'Modern|Most|Many|Some|Each|Every|However|Furthermore|Moreover|'
        r'Although|Because|Since|While|After|Before|During|Between|'
        r'According|Recently|Currently|Today|Now)\s+[A-Za-z])'
    )
    return _GLUE_PAT.sub(r'\1. \2', text)


def split_sentences(text: str) -> list[str]:
    text = normalize_text(text)
    text = _fix_glued_sentences(text)
    sentences = _SENT_SPLIT.split(text)

    # Heading labels to strip from start of sentences
    _HEADING_LABELS = re.compile(
        r"^(?:Key\s+Insight|Note|Example|Definition|Important|Summary|"
        r"Tip|Warning|Reminder|Observation|Conclusion|Overview|"
        r"Fun\s+Fact|Did\s+You\s+Know|Quick\s+Review)\s*:\s*",
        re.IGNORECASE
    )

    result = []
    for sentence in sentences:
        # Strip normal and non-breaking whitespace
        sentence = sentence.strip().strip("\xa0\u200b\ufeff")

        # Remove heading labels from start of sentence
        sentence = _HEADING_LABELS.sub("", sentence).strip()

        if not (30 <= len(sentence) <= 300):
            continue

        if "Test PDF for Quiz Generator" in sentence:
            continue

        # filtru nou: propoziții cu structură gramaticală stricată
        if any(re.search(p, sentence, re.IGNORECASE) for p in BAD_PATTERNS):
            continue

        result.append(sentence)

    return result