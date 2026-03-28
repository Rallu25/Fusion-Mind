import re
from dataclasses import dataclass
from typing import Callable, Optional


BLOCKED_SUBJECTS = {
    "it", "they", "this", "that", "these", "those",
    "there", "here", "one", "some", "we", "he", "she",
    "following", "above", "below", "end", "rest"
}

# Subiect = 1-6 cuvinte, fiecare cuvânt e litere/cifre/simboluri, separate de spații
# Nu mai include \s în character class → elimină ambiguitatea lazy/greedy
_WORD = r"[A-Za-z0-9°µ₂₆₁₃\-/]+"
_SUBJ = rf"(?P<subject>{_WORD}(?:\s+{_WORD}){{0,5}})"
_SUBJ_CAP = rf"(?P<subject>[A-Z]{_WORD[1:]}(?:\s+{_WORD}){{0,5}})"


@dataclass
class PatternRule:
    name: str
    pattern: re.Pattern
    make_question: Callable[[re.Match], str]
    extract_answer: Callable[[re.Match], str]
    extract_subject: Callable[[re.Match], str]


def clean_answer(text: str) -> str:
    """Curăță un răspuns extras: strip, elimină punct final, limitează lungimea."""
    text = text.strip()
    text = re.sub(r"[.;,]+$", "", text).strip()
    if len(text) > 100:
        # trunchiază pe limită de cuvânt
        cut = text[:100].rsplit(" ", 1)
        text = cut[0] if len(cut) > 1 else text[:100]
    return text


def clean_subject(text: str) -> str:
    """Curăță subiectul extras."""
    text = text.strip()
    text = re.sub(r"[,;:]+$", "", text).strip()
    text = re.sub(r"^(?:A|An|The)\s+", "", text, flags=re.IGNORECASE)
    return text


_SINGULAR_S_WORDS = {
    "photosynthesis", "analysis", "synthesis", "osmosis", "diagnosis",
    "thesis", "hypothesis", "basis", "crisis", "emphasis", "paralysis",
    "metamorphosis", "process", "progress", "success", "access", "address",
    "mass", "class", "glass", "gas", "bus", "focus", "status", "virus",
    "apparatus", "radius", "nucleus", "stimulus", "campus", "census",
    "consensus", "bonus", "minus", "plus", "surplus", "corpus", "loss",
    "bias", "atlas", "canvas", "series",
}


def _is_plural(subject: str) -> bool:
    """Euristică simplă pentru detectarea pluralului."""
    last_word = subject.strip().split()[-1].lower() if subject.strip().split() else ""
    if last_word in _SINGULAR_S_WORDS:
        return False
    if last_word.endswith("sis") or last_word.endswith("us"):
        return False
    return last_word.endswith("s") and not last_word.endswith("ss")


_BAD_SUBJECT_WORDS = {
    "often", "also", "usually", "always", "never", "just", "only",
    "then", "when", "if", "so", "yet", "but", "and", "or", "nor",
    "very", "too", "quite", "rather", "most", "many", "much",
    "however", "therefore", "moreover", "furthermore", "nevertheless",
    "each", "every", "either", "neither", "both", "few", "several",
    "not", "no", "yes", "well", "now", "still", "already",
    "of", "in", "on", "at", "to", "for", "with", "by", "from",
    "up", "down", "out", "off", "over", "under",
}

_VERB_LIKE = re.compile(
    r"^(?:assigns?|runs?|sets?|gets?|puts?|lets?|makes?|takes?|"
    r"gives?|does?|goes?|says?|uses?|finds?|keeps?|helps?|shows?|"
    r"adds?|moves?|calls?|turns?|plays?|works?|looks?|needs?|"
    r"starts?|tries?|brings?|means?|seems?|wants?|becomes?|"
    r"provides?|ensures?|allows?|requires?|maintains?|"
    r"trains?|learns?|averages?|reduces?|measures?|predicts?|"
    r"combines?|discovers?|computes?|produces?|systematically|"
    r"using|having|being|getting|making|running|setting|"
    r"given|based|used|applied|trained|computed|designed|"
    r"overly|newly|highly|closely|commonly|typically|"
    r"increasingly|especially|particularly|approximately|"
    r"fine-tuning|unfreeze|replace|technique)\b",
    re.IGNORECASE
)


def _subject_valid(match: re.Match) -> bool:
    """Verifică dacă subiectul extras e valid."""
    subj = clean_subject(match.group("subject"))
    words = subj.split()
    if not words:
        return False
    first_word = words[0].lower()
    if first_word in BLOCKED_SUBJECTS:
        return False
    if first_word in _BAD_SUBJECT_WORDS:
        return False
    if len(subj) < 3:
        return False
    # respinge subiecte prea scurte
    if len(words) == 1 and len(words[0]) <= 2:
        return False
    # respinge subiecte care încep cu verbe/adverbe/participii
    if _VERB_LIKE.match(words[0]):
        return False
    # prea multe cuvinte = probabil o propoziție capturată greșit
    if len(words) > 6:
        return False
    # respinge dacă vreun cuvânt (nu primul) e un verb conjugat evident
    _VERBS_IN_SUBJ = {
        "learns", "trains", "encompasses", "combines", "averages",
        "produces", "predicts", "discovers", "computes", "normalizes",
        "maximizes", "minimizes", "generates", "identifies", "calculates",
        "unfreeze", "closest", "removing", "including", "excluding",
    }
    for w in words:
        if w.lower() in _VERBS_IN_SUBJ:
            return False
    # subiectul trebuie să conțină cel puțin un cuvânt cu >2 litere
    if not any(len(w) > 2 for w in words):
        return False
    return True


# ═══════════════════════════════════════════════════════════
# PATTERN A: Definiție — "X is/are a/an/the Y"
# ═══════════════════════════════════════════════════════════
_pat_definition = re.compile(
    rf"{_SUBJ}\s+(?:is|are)\s+(?P<object>(?:a|an|the)\s+[^.;]{{5,100}})",
    re.IGNORECASE
)


def _q_definition(m: re.Match) -> str:
    subj = clean_subject(m.group("subject"))
    verb = "are" if _is_plural(subj) else "is"
    return f"What {verb} {subj}?"


def _a_definition(m: re.Match) -> str:
    return clean_answer(m.group("object"))


def _s_definition(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# PATTERN B: Proprietate — "X has/contains/includes Y"
# ═══════════════════════════════════════════════════════════
_pat_property = re.compile(
    rf"{_SUBJ}\s+(?P<verb>has|have|contains?|includes?)\s+(?P<object>[^.;]{{5,100}})",
    re.IGNORECASE
)


def _verb_base(verb: str) -> str:
    v = verb.lower()
    if v in ("has", "have"):
        return "have"
    if v.startswith("contain"):
        return "contain"
    if v.startswith("include"):
        return "include"
    return v


def _q_property(m: re.Match) -> str:
    subj = clean_subject(m.group("subject"))
    verb = _verb_base(m.group("verb"))
    return f"What does {subj} {verb}?"


def _a_property(m: re.Match) -> str:
    return clean_answer(m.group("object"))


def _s_property(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# PATTERN C: Funcție/Scop — "X is used for/to/in Y"
# ═══════════════════════════════════════════════════════════
_pat_function = re.compile(
    rf"{_SUBJ}\s+(?:is|are)\s+used\s+(?P<prep>for|to|in)\s+(?P<object>[^.;]{{5,100}})",
    re.IGNORECASE
)


def _q_function(m: re.Match) -> str:
    subj = clean_subject(m.group("subject"))
    prep = m.group("prep").lower()
    verb = "are" if _is_plural(subj) else "is"
    return f"What {verb} {subj} used {prep}?"


def _a_function(m: re.Match) -> str:
    return clean_answer(m.group("object"))


def _s_function(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# PATTERN D: Cauză-Efect — "X causes/leads to/results in/produces Y"
# ═══════════════════════════════════════════════════════════
_pat_cause = re.compile(
    rf"{_SUBJ}\s+(?P<verb>causes?|leads?\s+to|results?\s+in|produces?)\s+(?P<object>[^.;]{{5,100}})",
    re.IGNORECASE
)


def _verb_question_form(verb: str) -> str:
    v = verb.lower().strip()
    if "lead" in v:
        return "lead to"
    if "result" in v:
        return "result in"
    if "produce" in v:
        return "produce"
    return "cause"


def _q_cause(m: re.Match) -> str:
    subj = clean_subject(m.group("subject"))
    verb = _verb_question_form(m.group("verb"))
    return f"What does {subj} {verb}?"


def _a_cause(m: re.Match) -> str:
    return clean_answer(m.group("object"))


def _s_cause(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# PATTERN E: Locație — "X is found/located/present/stored in Y"
# ═══════════════════════════════════════════════════════════
_pat_location = re.compile(
    rf"{_SUBJ}\s+(?:is|are)\s+(?:found|located|present|stored)\s+in\s+(?P<object>[^.;]{{5,100}})",
    re.IGNORECASE
)


def _q_location(m: re.Match) -> str:
    subj = clean_subject(m.group("subject"))
    verb = "are" if _is_plural(subj) else "is"
    return f"Where {verb} {subj} found?"


def _a_location(m: re.Match) -> str:
    return clean_answer(m.group("object"))


def _s_location(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# PATTERN F: Compoziție — "X consists of / is made of / is composed of Y"
# ═══════════════════════════════════════════════════════════
_pat_composition = re.compile(
    rf"{_SUBJ}\s+(?:consists?\s+of|is\s+made\s+(?:up\s+)?of|is\s+composed\s+of)\s+(?P<object>[^.;]{{5,100}})",
    re.IGNORECASE
)


def _q_composition(m: re.Match) -> str:
    subj = clean_subject(m.group("subject"))
    return f"What does {subj} consist of?"


def _a_composition(m: re.Match) -> str:
    return clean_answer(m.group("object"))


def _s_composition(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# PATTERN G: Valoare/Măsurare — "The pH/temperature/... of X is Y"
# ═══════════════════════════════════════════════════════════
_MEASURES = (
    r"pH|temperature|concentration|pressure|voltage|"
    r"frequency|wavelength|density|mass|weight|speed|velocity|value|level|"
    r"amount|percentage|ratio|rate|cost|price|diameter|radius|height|depth|"
    r"length|width|area|volume|capacity|power|resistance|intensity|"
    r"boiling point|melting point|half-life|atomic number|"
    r"molecular weight|molar mass|accuracy|precision|recall|"
    r"learning rate|batch size|number|size|dimension|complexity"
)

_pat_value = re.compile(
    rf"(?:[Tt]he\s+)?(?P<measure>{_MEASURES})"
    rf"\s+of\s+(?P<subject>.+?)\s+"
    r"(?:is|are|equals?|was|were)\s+"
    r"(?P<object>\S[^;]{1,60})",
    re.IGNORECASE
)


def _q_value(m: re.Match) -> str:
    measure = m.group("measure").strip()
    subj = clean_subject(m.group("subject"))
    return f"What is the {measure} of {subj}?"


def _a_value(m: re.Match) -> str:
    return clean_answer(m.group("object"))


def _s_value(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# PATTERN H: Comparație — "X is larger/smaller/... than Y"
# ═══════════════════════════════════════════════════════════
_pat_comparison = re.compile(
    rf"{_SUBJ}\s+(?:is|are)\s+"
    r"(?P<comparison>(?:much\s+)?(?:larger|smaller|greater|higher|lower|faster|slower|"
    r"heavier|lighter|stronger|weaker|hotter|colder|denser|better|worse|"
    r"more\s+[a-z]+|less\s+[a-z]+)\s+than)\s+"
    r"(?P<object>[^.;]{3,60})",
    re.IGNORECASE
)


def _q_comparison(m: re.Match) -> str:
    comp = m.group("comparison").strip()
    obj = clean_answer(m.group("object"))
    return f"Which of the following is {comp} {obj}?"


def _a_comparison(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


def _s_comparison(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# PATTERN I: Acțiune/Verb — "X verb(s) Y" (compute, measure, reduce, etc.)
# ═══════════════════════════════════════════════════════════
_ACTION_VERBS = (
    r"computes?|calculates?|measures?|reduces?|increases?|"
    r"minimizes?|maximizes?|optimizes?|evaluates?|estimates?|"
    r"predicts?|classifies?|transforms?|converts?|generates?|"
    r"detects?|identifies?|maps?|assigns?|combines?|"
    r"learns?|trains?|encodes?|decodes?|splits?|"
    r"regularizes?|normalizes?|penalizes?|prevents?"
)

_pat_action = re.compile(
    rf"(?P<subject>[A-Z][A-Za-z0-9°µ₂₆₁₃\-/]+(?:\s+[A-Za-z0-9°µ₂₆₁₃\-/]+){{0,4}})"
    rf"\s+(?P<verb>{_ACTION_VERBS})\s+(?P<object>[^.;]{{5,100}})"
)


def _verb_to_base(verb: str) -> str:
    """Transformă verb conjugat în forma de bază."""
    v = verb.lower()
    if v.endswith("ies"):
        return v[:-3] + "y"
    if v.endswith("es"):
        return v[:-2]
    if v.endswith("s"):
        return v[:-1]
    return v


def _q_action(m: re.Match) -> str:
    subj = clean_subject(m.group("subject"))
    verb = _verb_to_base(m.group("verb"))
    return f"What does {subj} {verb}?"


def _a_action(m: re.Match) -> str:
    return clean_answer(m.group("object"))


def _s_action(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# PATTERN J: Scop — "X verb(s) ... to/for Y"
# ═══════════════════════════════════════════════════════════
_pat_purpose = re.compile(
    rf"{_SUBJ_CAP}\s+(?:is|are)\s+(?:designed|meant|intended|built)\s+"
    r"(?:to|in order to)\s+(?P<object>[^.;]{5,100})",
    re.IGNORECASE
)


def _q_purpose(m: re.Match) -> str:
    subj = clean_subject(m.group("subject"))
    return f"What is the purpose of {subj}?"


def _a_purpose(m: re.Match) -> str:
    return clean_answer(m.group("object"))


def _s_purpose(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# PATTERN K: Referire — "X refers to / is known as / is called Y"
# ═══════════════════════════════════════════════════════════
_pat_refers = re.compile(
    rf"{_SUBJ_CAP}\s+(?:refers?\s+to|is\s+known\s+as|is\s+called|is\s+defined\s+as)\s+"
    r"(?P<object>[^.;]{5,100})",
    re.IGNORECASE
)


def _q_refers(m: re.Match) -> str:
    subj = clean_subject(m.group("subject"))
    return f"What does {subj} refer to?"


def _a_refers(m: re.Match) -> str:
    return clean_answer(m.group("object"))


def _s_refers(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# PATTERN L: Permite/Ajută — "X allows/enables/helps Y"
# ═══════════════════════════════════════════════════════════
_pat_enables = re.compile(
    rf"{_SUBJ}\s+(?P<verb>allows?|enables?|helps?|permits?|facilitates?|supports?)\s+"
    r"(?P<object>[^.;]{5,100})",
    re.IGNORECASE
)


def _q_enables(m: re.Match) -> str:
    subj = clean_subject(m.group("subject"))
    verb = _verb_to_base(m.group("verb"))
    return f"What does {subj} {verb}?"


def _a_enables(m: re.Match) -> str:
    return clean_answer(m.group("object"))


def _s_enables(m: re.Match) -> str:
    return clean_subject(m.group("subject"))


# ═══════════════════════════════════════════════════════════
# Lista tuturor pattern-urilor în ordine de prioritate
# Cele mai specifice primele (evită match-uri false)
# ═══════════════════════════════════════════════════════════
PATTERN_RULES: list[PatternRule] = [
    PatternRule("value", _pat_value, _q_value, _a_value, _s_value),
    PatternRule("refers", _pat_refers, _q_refers, _a_refers, _s_refers),
    PatternRule("location", _pat_location, _q_location, _a_location, _s_location),
    PatternRule("function", _pat_function, _q_function, _a_function, _s_function),
    PatternRule("composition", _pat_composition, _q_composition, _a_composition, _s_composition),
    PatternRule("cause", _pat_cause, _q_cause, _a_cause, _s_cause),
    PatternRule("comparison", _pat_comparison, _q_comparison, _a_comparison, _s_comparison),
    PatternRule("enables", _pat_enables, _q_enables, _a_enables, _s_enables),
    PatternRule("action", _pat_action, _q_action, _a_action, _s_action),
    PatternRule("property", _pat_property, _q_property, _a_property, _s_property),
    PatternRule("definition", _pat_definition, _q_definition, _a_definition, _s_definition),
    PatternRule("purpose", _pat_purpose, _q_purpose, _a_purpose, _s_purpose),
]


def match_sentence(sentence: str) -> Optional[tuple[PatternRule, re.Match]]:
    """Încearcă fiecare pattern pe propoziție. Returnează primul match valid."""
    for rule in PATTERN_RULES:
        m = rule.pattern.search(sentence)
        if m and _subject_valid(m):
            return (rule, m)
    return None
