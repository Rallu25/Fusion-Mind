from quizgen.truefalse_quiz import (
    _find_swappable_term, _swap_term, _negate_sentence,
    _swap_number, _make_false_sentence, _score_tf_sentence,
)


class TestFindSwappableTerm:
    def test_finds_kb_term(self):
        vocab = {"photosynthesis", "light", "energy"}
        result = _find_swappable_term("Photosynthesis converts light energy.", vocab)
        assert result is not None
        term, distractors = result
        assert len(distractors) > 0

    def test_returns_none_for_no_kb(self):
        vocab = {"xyz", "abc"}
        result = _find_swappable_term("Xyz and abc are random words.", vocab)
        assert result is None


class TestSwapTerm:
    def test_swaps_word(self):
        result = _swap_term("Photosynthesis converts energy.", "Photosynthesis", "respiration")
        assert "Respiration" in result
        assert "Photosynthesis" not in result

    def test_preserves_case(self):
        result = _swap_term("The encryption is strong.", "encryption", "hashing")
        assert "hashing" in result

    def test_capitalizes_when_original_caps(self):
        result = _swap_term("Mars is a planet.", "Mars", "venus")
        assert "Venus" in result


class TestNegateSentence:
    def test_negates_is(self):
        result = _negate_sentence("Encryption is a technique.")
        assert result is not None
        assert "is not" in result

    def test_negates_are(self):
        result = _negate_sentence("Sensors are devices.")
        assert result is not None
        assert "are not" in result

    def test_negates_verb(self):
        result = _negate_sentence("Water contains minerals.")
        assert result is not None
        assert "does not contain" in result

    def test_skips_already_negated(self):
        result = _negate_sentence("It is not a problem.")
        assert result is None

    def test_returns_none_for_no_verb(self):
        result = _negate_sentence("Just some random words here.")
        assert result is None


class TestSwapNumber:
    def test_swaps_integer(self):
        result, did = _swap_number("The pH is 7 under normal conditions.")
        assert did is True
        assert "7" not in result or result != "The pH is 7 under normal conditions."

    def test_swaps_float(self):
        result, did = _swap_number("The pH of blood is 7.4 normally.")
        assert did is True

    def test_no_swap_without_number(self):
        result, did = _swap_number("No numbers here at all.")
        assert did is False


class TestMakeFalseSentence:
    def test_returns_false_version(self):
        vocab = {"photosynthesis", "light", "energy", "chemical"}
        result = _make_false_sentence("Photosynthesis converts light energy.", vocab)
        # Should return something (at least negation should work)
        # May return None if no strategy works
        if result:
            false_sent, method = result
            assert false_sent != "Photosynthesis converts light energy."
            assert method in ("term_swap", "negation", "number_swap")


class TestScoreTfSentence:
    def test_good_sentence_scores_high(self):
        score = _score_tf_sentence(
            "Photosynthesis is a process that converts light energy into chemical energy in plants."
        )
        assert score > 20

    def test_bad_start_penalized(self):
        score1 = _score_tf_sentence("It is a common process in biology and chemistry research.")
        score2 = _score_tf_sentence("Photosynthesis is a common process in biology and chemistry.")
        assert score2 > score1

    def test_number_bonus(self):
        s1 = _score_tf_sentence("The temperature was measured at 25 degrees in the lab room.")
        s2 = _score_tf_sentence("The temperature was measured in the laboratory testing room.")
        assert s1 >= s2
