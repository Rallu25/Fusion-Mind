"""Shared constants and helpers used across quiz generation modules."""

BAD_STARTS = {"it", "they", "this", "that", "these", "those", "as", "such"}


def filter_by_difficulty(candidates: list[dict], difficulty: str, n: int) -> list[dict]:
    """Select questions based on difficulty level.
    Easy = highest quality scores (clearest questions).
    Hard = lowest quality scores (trickier/more nuanced).
    Medium = middle range.
    """
    if not candidates:
        return []

    sorted_c = sorted(candidates, key=lambda x: x["quality_score"], reverse=True)

    if difficulty == "easy":
        return sorted_c[:n]
    elif difficulty == "hard":
        return sorted_c[-n:] if len(sorted_c) >= n else sorted_c
    else:  # medium
        mid = len(sorted_c) // 4
        end = mid + n
        return sorted_c[mid:end] if end <= len(sorted_c) else sorted_c[mid:]
