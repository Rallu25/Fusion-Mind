from quizgen.image_extract import _fix_encoding, _find_caption


class TestFixEncoding:
    def test_fixes_emdash(self):
        result = _fix_encoding("hello \u2014 world")
        assert "-" in result

    def test_fixes_endash(self):
        result = _fix_encoding("hello \u2013 world")
        assert "-" in result

    def test_fixes_smart_quotes(self):
        result = _fix_encoding("\u201chello\u201d")
        assert '"hello"' in result

    def test_plain_text_unchanged(self):
        assert _fix_encoding("hello world") == "hello world"


class TestFindCaption:
    def test_finds_text_below(self):
        # image at y=100-200, text block at y=210
        text_blocks = [
            {"text": "Figure 1: Neural network architecture", "bbox": (50, 210, 400, 230)},
        ]
        caption = _find_caption((50, 100, 400, 200), text_blocks, 800)
        assert "Neural network architecture" in caption

    def test_finds_text_above(self):
        text_blocks = [
            {"text": "Figure 2: Data flow diagram", "bbox": (50, 50, 400, 70)},
        ]
        caption = _find_caption((50, 80, 400, 200), text_blocks, 800)
        assert "Data flow diagram" in caption

    def test_returns_empty_when_no_text_nearby(self):
        text_blocks = [
            {"text": "Very far away text block", "bbox": (50, 600, 400, 620)},
        ]
        caption = _find_caption((50, 100, 400, 200), text_blocks, 800)
        assert caption == ""

    def test_ignores_horizontally_distant(self):
        text_blocks = [
            {"text": "Misaligned text", "bbox": (600, 210, 800, 230)},
        ]
        caption = _find_caption((50, 100, 400, 200), text_blocks, 800)
        assert caption == ""
