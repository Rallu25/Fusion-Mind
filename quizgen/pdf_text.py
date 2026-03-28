from pypdf import PdfReader


def extract_text_from_pdf(pdf_path: str, max_pages: int | None = None) -> str:
    reader = PdfReader(pdf_path)
    texts = []

    pages = reader.pages[:max_pages] if max_pages else reader.pages

    for page in pages:
        text = page.extract_text() or ""
        texts.append(text)

    return "\n".join(texts)