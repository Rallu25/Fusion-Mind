"""Integration tests for the full quiz generation pipeline.
These tests use the generate_*_from_pdf functions with a sample text.
Since we don't have a test PDF, we test the internal logic with mock data.
"""
from quizgen import _filter_by_difficulty


class TestFilterByDifficulty:
    def _make_candidates(self, scores):
        return [{"quality_score": s, "question": f"Q{i}"} for i, s in enumerate(scores)]

    def test_easy_takes_highest(self):
        candidates = self._make_candidates([100, 80, 60, 40, 20])
        result = _filter_by_difficulty(candidates, "easy", 3)
        scores = [r["quality_score"] for r in result]
        assert scores == [100, 80, 60]

    def test_hard_takes_lowest(self):
        candidates = self._make_candidates([100, 80, 60, 40, 20])
        result = _filter_by_difficulty(candidates, "hard", 3)
        scores = [r["quality_score"] for r in result]
        assert scores == [60, 40, 20]

    def test_medium_takes_middle(self):
        candidates = self._make_candidates([100, 90, 80, 70, 60, 50, 40, 30])
        result = _filter_by_difficulty(candidates, "medium", 3)
        # Should skip top quarter and take from middle
        assert len(result) == 3
        scores = [r["quality_score"] for r in result]
        assert 100 not in scores  # top should be skipped

    def test_empty_input(self):
        assert _filter_by_difficulty([], "easy", 5) == []

    def test_fewer_than_n(self):
        candidates = self._make_candidates([80, 60])
        result = _filter_by_difficulty(candidates, "easy", 5)
        assert len(result) == 2
