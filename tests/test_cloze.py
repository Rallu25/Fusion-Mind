from quizgen.cloze import pick_target_word, make_cloze, BAD_TARGETS, PREFERRED_TARGETS


class TestPickTargetWord:
    def test_picks_preferred_target(self):
        vocab = {"photosynthesis", "converts", "light", "energy"}
        result = pick_target_word("Photosynthesis converts light energy.", vocab)
        assert result is not None
        assert result.lower() == "photosynthesis"

    def test_skips_bad_targets(self):
        vocab = {"located", "cell", "plant"}
        result = pick_target_word("The cell is located in the plant.", vocab)
        if result:
            assert result.lower() not in BAD_TARGETS

    def test_returns_none_for_no_vocab(self):
        result = pick_target_word("The cat sat on the mat.", set())
        assert result is None

    def test_prefers_longer_words(self):
        vocab = {"the", "big", "mitochondria", "cell"}
        result = pick_target_word("The big mitochondria in the cell.", vocab)
        assert result is not None
        assert result.lower() == "mitochondria"


class TestMakeCloze:
    def test_replaces_target(self):
        result = make_cloze("Photosynthesis converts light energy.", "Photosynthesis")
        assert "____" in result
        assert "Photosynthesis" not in result

    def test_replaces_only_first_occurrence(self):
        result = make_cloze("The cell contains another cell inside.", "cell")
        assert result.count("____") == 1

    def test_preserves_rest(self):
        result = make_cloze("Encryption protects data.", "Encryption")
        assert "protects data." in result


class TestPreferredTargets:
    def test_loaded_from_kb(self):
        # PREFERRED_TARGETS should include KB keys
        assert "photosynthesis" in PREFERRED_TARGETS
        assert "encryption" in PREFERRED_TARGETS
        assert "neural network" in PREFERRED_TARGETS or "neuron" in PREFERRED_TARGETS

    def test_includes_static_terms(self):
        assert "ph" in PREFERRED_TARGETS
        assert "co2" in PREFERRED_TARGETS
