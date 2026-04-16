"""Export quiz questions to Moodle GIFT format.

GIFT format reference: https://docs.moodle.org/en/GIFT_format
"""


def _escape_gift(text: str) -> str:
    """Escape special GIFT characters: ~ = # { } :"""
    for ch in ("~", "=", "#", "{", "}", ":"):
        text = text.replace(ch, "\\" + ch)
    return text


def _export_mcq(q: dict, idx: int) -> str:
    """Export a multiple-choice question to GIFT format."""
    question = _escape_gift(q.get("question", ""))
    options = q.get("options", [])
    correct_index = q.get("correct_index", 0)

    lines = [f"::Q{idx}:: {question} {{"]
    for i, opt in enumerate(options):
        opt_text = _escape_gift(str(opt))
        prefix = "=" if i == correct_index else "~"
        lines.append(f"  {prefix}{opt_text}")
    lines.append("}")
    return "\n".join(lines)


def _export_tf(q: dict, idx: int) -> str:
    """Export a True/False question to GIFT format."""
    question = _escape_gift(q.get("question", ""))
    correct_index = q.get("correct_index", 0)
    answer = "TRUE" if correct_index == 0 else "FALSE"
    return f"::Q{idx}:: {question} {{{answer}}}"


def _export_matching(q: dict, idx: int) -> str:
    """Export a matching question to GIFT format."""
    question = _escape_gift(q.get("question", ""))
    terms = q.get("terms", [])
    definitions = q.get("definitions", [])
    correct_mapping = q.get("correct_mapping", [])

    lines = [f"::Q{idx}:: {question} {{"]
    for i, term in enumerate(terms):
        # correct_mapping[i] = index in shuffled definitions array
        if i < len(correct_mapping) and correct_mapping[i] < len(definitions):
            defn = definitions[correct_mapping[i]]
        elif i < len(definitions):
            defn = definitions[i]
        else:
            continue
        lines.append(f"  ={_escape_gift(term)} -> {_escape_gift(defn)}")
    lines.append("}")
    return "\n".join(lines)


def generate_gift(questions: list[dict], title: str = "Quiz") -> str:
    """Convert quiz questions to Moodle GIFT format string.

    Returns the GIFT-formatted text.
    """
    parts = [f"// {title}", f"// Exported from Fusion Mind", ""]

    for i, q in enumerate(questions, 1):
        options = q.get("options", [])
        quiz_type = q.get("quiz_type", "")

        is_tf = (len(options) == 2
                 and options[0] == "True"
                 and options[1] == "False")
        is_matching = quiz_type == "matching"

        if is_matching:
            parts.append(_export_matching(q, i))
        elif is_tf:
            parts.append(_export_tf(q, i))
        else:
            parts.append(_export_mcq(q, i))

        parts.append("")  # blank line between questions

    return "\n".join(parts)
