from quizgen.template_patterns import (
    match_sentence, clean_subject, clean_answer,
    _is_plural, _subject_valid, BLOCKED_SUBJECTS,
)


class TestMatchSentence:
    def test_definition_pattern(self):
        result = match_sentence("Encryption is a technique used to convert readable information into encoded form.")
        assert result is not None
        rule, m = result
        assert rule.name == "definition"
        q = rule.make_question(m)
        assert "Encryption" in q

    def test_property_pattern(self):
        result = match_sentence("Water contains dissolved minerals and salts.")
        assert result is not None
        rule, m = result
        assert rule.name == "property"

    def test_function_pattern(self):
        result = match_sentence("A telescope is used to observe distant celestial objects.")
        assert result is not None
        rule, m = result
        assert rule.name == "function"

    def test_cause_pattern(self):
        result = match_sentence("Heat causes expansion of metal materials.")
        assert result is not None
        rule, m = result
        assert rule.name == "cause"

    def test_location_pattern(self):
        result = match_sentence("Chloroplasts are found in plant cells.")
        assert result is not None
        rule, m = result
        assert rule.name == "location"

    def test_composition_pattern(self):
        result = match_sentence("DNA consists of four types of nucleotides.")
        assert result is not None
        rule, m = result
        assert rule.name == "composition"

    def test_comparison_pattern(self):
        result = match_sentence("Jupiter is larger than Earth in both mass and diameter.")
        assert result is not None
        rule, m = result
        assert rule.name == "comparison"

    def test_no_match(self):
        result = match_sentence("Hello world.")
        assert result is None

    def test_blocked_subject(self):
        result = match_sentence("It is a process that converts energy into light.")
        assert result is None

    def test_following_blocked(self):
        result = match_sentence("The following is a curated list of high-quality resources.")
        assert result is None


class TestCleanSubject:
    def test_strips_article(self):
        assert clean_subject("The algorithm") == "Algorithm"
        assert clean_subject("A sensor") == "Sensor"
        assert clean_subject("An encoder") == "Encoder"

    def test_strips_punctuation(self):
        assert clean_subject("algorithm,") == "Algorithm"

    def test_preserves_normal(self):
        assert clean_subject("Neural network") == "Neural network"


class TestCleanAnswer:
    def test_strips_trailing_punct(self):
        assert clean_answer("some process.") == "some process"
        assert clean_answer("some process;") == "some process"

    def test_truncates_long(self):
        long = "word " * 30
        result = clean_answer(long)
        assert len(result) <= 100

    def test_preserves_normal(self):
        assert clean_answer("a chemical reaction") == "a chemical reaction"


class TestIsPlural:
    def test_plural(self):
        assert _is_plural("sensors") is True
        assert _is_plural("networks") is True

    def test_singular_s(self):
        assert _is_plural("photosynthesis") is False
        assert _is_plural("analysis") is False
        assert _is_plural("virus") is False

    def test_regular_singular(self):
        assert _is_plural("algorithm") is False
