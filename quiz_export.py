"""Export quiz questions to a printable PDF with answer key."""

import os
import uuid
from fpdf import FPDF


class QuizPDF(FPDF):
    def __init__(self, title: str = "Quiz"):
        super().__init__()
        self.quiz_title = title

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(80, 40, 180)
        self.cell(0, 8, "FUSION MIND", 0, 0, "L")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, self.quiz_title, 0, 1, "R")
        self.set_draw_color(80, 40, 180)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", 0, 0, "C")


def _safe_text(text: str) -> str:
    """Replace characters that fpdf can't handle."""
    replacements = {
        "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00b0": "deg",
        "\u2264": "<=", "\u2265": ">=", "\u00d7": "x", "\u00f7": "/",
        "\u03c0": "pi", "\u03bc": "u", "\u2192": "->", "\u2190": "<-",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def generate_quiz_pdf(questions: list[dict], title: str = "Quiz") -> str:
    """Generate a printable PDF from quiz questions.

    Returns the file path of the generated PDF.
    """
    pdf = QuizPDF(title=title)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.add_page()

    # Name and date fields at top
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(95, 8, "Name: ___________________________________", 0, 0)
    pdf.cell(95, 8, "Date: ________________", 0, 1)
    pdf.ln(6)

    letters = ["A", "B", "C", "D", "E", "F"]
    q_num = 0

    for q in questions:
        quiz_type = q.get("quiz_type", "")

        # Skip matching questions (not suitable for print)
        if quiz_type == "matching":
            continue

        q_num += 1
        question_text = _safe_text(q.get("question", ""))
        options = q.get("options", [])
        correct_index = q.get("correct_index", 0)

        # Check if we need a new page (estimate space needed)
        space_needed = 20 + len(options) * 8
        if pdf.get_y() + space_needed > 270:
            pdf.add_page()

        # Question number + text
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(10, 7, f"{q_num}.", 0, 0)
        pdf.set_font("Helvetica", "", 11)

        # Handle True/False vs regular questions
        is_tf = (len(options) == 2 and options[0] == "True" and options[1] == "False")

        if is_tf:
            pdf.multi_cell(0, 6, question_text)
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            pdf.cell(15)
            pdf.cell(20, 6, "[ ] True", 0, 0)
            pdf.cell(20, 6, "[ ] False", 0, 1)
        else:
            pdf.multi_cell(0, 6, question_text)
            pdf.ln(2)

            for i, opt in enumerate(options):
                if i >= len(letters):
                    break
                opt_text = _safe_text(str(opt))
                # Truncate very long options for print
                if len(opt_text) > 120:
                    opt_text = opt_text[:117] + "..."

                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(60, 60, 60)
                pdf.cell(15)
                pdf.cell(0, 6, f"[ {letters[i]} ]  {opt_text}", 0, 1)

        pdf.ln(4)

    # Save PDF
    os.makedirs("exports", exist_ok=True)
    filename = f"quiz_{uuid.uuid4().hex[:8]}.pdf"
    filepath = os.path.join("exports", filename)
    pdf.output(filepath)
    return filepath
