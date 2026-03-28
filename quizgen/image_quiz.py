import random
import re

from .image_extract import extract_images_from_pdf


# Minimum useful caption length
MIN_CAPTION_LEN = 10

# Question templates
_TEMPLATES = [
    "Which image shows {caption}?",
    "Which of the following represents {caption}?",
    "Identify the image that illustrates {caption}.",
    "Which figure corresponds to {caption}?",
]


def _clean_caption_for_question(caption: str) -> str:
    """Clean caption text for use in a question."""
    # Remove "Figure X:" prefix if still present
    caption = re.sub(
        r"^(?:Figure|Fig\.?|Diagram|Table|Chart|Image)\s*\d*\s*[:\.\-–—]\s*",
        "", caption, flags=re.IGNORECASE
    ).strip()
    # Lowercase first letter only if it's a common word (not acronym/proper noun)
    # Keep uppercase if: all caps word, short word (acronym), or has mixed case
    if caption:
        first_word = caption.split()[0] if caption.split() else ""
        is_acronym = len(first_word) <= 4 and first_word.isupper()
        has_inner_upper = any(c.isupper() for c in first_word[1:])
        if not is_acronym and not has_inner_upper and first_word[0].isupper():
            caption = caption[0].lower() + caption[1:]
    # Truncate if too long
    if len(caption) > 100:
        caption = caption[:100].rsplit(" ", 1)[0]
    # Remove trailing punctuation
    caption = re.sub(r"[.;,]+$", "", caption).strip()
    return caption


def _score_image(img: dict) -> int:
    """Score an image's suitability for quiz questions."""
    score = 0
    caption = img.get("caption", "")
    w, h = img.get("width", 0), img.get("height", 0)

    # Has a meaningful caption
    if len(caption) >= MIN_CAPTION_LEN:
        score += 50
    elif len(caption) >= 5:
        score += 20
    else:
        score -= 50  # no caption = bad for questions

    # Has "Figure/Diagram/Table" in caption
    if re.match(r"(?:Figure|Fig|Diagram|Table|Chart)", caption, re.I):
        score += 20

    # Reasonable size (not too small, not logo-sized squares)
    if 100 <= w <= 2000 and 100 <= h <= 2000:
        score += 20
    elif w >= 50 and h >= 50:
        score += 5

    # Not a perfect square (likely a logo/icon)
    if w > 0 and h > 0:
        ratio = max(w, h) / min(w, h)
        if 1.0 < ratio < 5.0:
            score += 10  # normal aspect ratio

    # Penalize very small base64 (likely placeholder or tiny icon)
    b64_len = len(img.get("image_b64", ""))
    if b64_len < 1000:
        score -= 30
    elif b64_len > 5000:
        score += 10

    return score


def generate_image_quiz_from_pdf(pdf_path: str, n_questions: int = 10, seed: int = 42) -> dict:
    """Generate a quiz where answer options are images from the PDF."""
    random.seed(seed)

    # Extract images
    images = extract_images_from_pdf(pdf_path)

    if len(images) < 4:
        return {
            "error": f"Not enough images in PDF ({len(images)} found, minimum 4 required). "
                     f"Try a PDF with more figures, diagrams, or charts."
        }

    # Score and filter images
    scored_images = []
    for img in images:
        score = _score_image(img)
        if score > 0:  # only keep usable images
            scored_images.append((score, img))

    scored_images.sort(key=lambda x: x[0], reverse=True)

    # Need at least 4 usable images
    usable_images = [img for _, img in scored_images]
    if len(usable_images) < 4:
        return {
            "error": f"Not enough usable images ({len(usable_images)} found after filtering). "
                     f"Images need to be at least 50x50 pixels and have associated text."
        }

    # Generate questions from images with captions
    candidates = []
    used_captions = set()

    for img in usable_images:
        caption = img.get("caption", "")
        if len(caption) < MIN_CAPTION_LEN:
            continue

        clean_cap = _clean_caption_for_question(caption)
        if not clean_cap or len(clean_cap) < 5:
            continue

        cap_norm = clean_cap.lower()
        if cap_norm in used_captions:
            continue
        used_captions.add(cap_norm)

        # Pick question template
        template = random.choice(_TEMPLATES)
        question_text = template.format(caption=clean_cap)

        # Correct answer is this image
        correct_b64 = img["image_b64"]

        # Pick 3 distractor images (different from correct)
        other_images = [
            other for other in usable_images
            if other["image_b64"] != correct_b64
        ]

        if len(other_images) < 3:
            continue

        distractors = random.sample(other_images, 3)
        distractor_b64s = [d["image_b64"] for d in distractors]

        # Assemble options
        options = [correct_b64] + distractor_b64s
        random.shuffle(options)
        correct_index = options.index(correct_b64)

        candidates.append({
            "question": question_text,
            "options": options,
            "correct_index": correct_index,
            "evidence": caption,
            "options_are_images": True,
            "_score": _score_image(img),
        })

    # Sort by score and pick top N
    candidates.sort(key=lambda x: x["_score"], reverse=True)

    questions = []
    for c in candidates[:n_questions]:
        questions.append({
            "question": c["question"],
            "options": c["options"],
            "correct_index": c["correct_index"],
            "evidence": c["evidence"],
            "options_are_images": True,
        })

    if not questions:
        return {
            "error": "Could not generate image-based questions. "
                     "The images in the PDF don't have clear captions or descriptions."
        }

    if len(questions) < n_questions:
        return {
            "warning": f"Only {len(questions)} image questions were generated "
                       f"(PDF has {len(usable_images)} usable images).",
            "questions": questions,
        }

    return {"questions": questions}
