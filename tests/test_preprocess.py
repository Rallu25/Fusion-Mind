from quizgen.preprocess import normalize_text, split_sentences


class TestNormalizeText:
    def test_replaces_bad_characters(self):
        # Â°C -> °C replacement
        result = normalize_text("Temperature is Â°C measured.")
        assert "°C" in result

    def test_removes_hyphen_line_breaks(self):
        # Hyphen at end of line joins with next word
        result = normalize_text("This is about photo-\nsynthesis in plants and biology.")
        assert "photosynthesis" in result

    def test_removes_short_headings(self):
        text = "Chapter One\nThis is a full sentence that ends with a period."
        result = normalize_text(text)
        assert "Chapter One" not in result

    def test_joins_broken_lines(self):
        # Line break within a sentence (no period before newline) should join
        # First line needs >8 words to not be filtered as a heading
        text = "This is a long sentence about science and biology research\nthat continues here with more words."
        result = normalize_text(text)
        assert "research that" in result

    def test_collapses_whitespace(self):
        text = "Too   many    spaces   here."
        result = normalize_text(text)
        assert "  " not in result


class TestSplitSentences:
    def test_splits_on_period(self):
        text = "First sentence here. Second sentence here. Third sentence that is also long enough."
        sentences = split_sentences(text)
        assert len(sentences) >= 1

    def test_filters_short_sentences(self):
        text = "Hi. This is a much longer sentence that should definitely pass the length filter for quiz generation."
        sentences = split_sentences(text)
        assert not any(s == "Hi" for s in sentences)

    def test_filters_long_sentences(self):
        long = "word " * 100 + "end."
        sentences = split_sentences(long)
        assert len(sentences) == 0

    def test_filters_bad_patterns(self):
        text = "This is fine and long enough to pass the filter. Such as a device stores data in memory banks."
        sentences = split_sentences(text)
        assert not any("such as a device stores" in s.lower() for s in sentences)
