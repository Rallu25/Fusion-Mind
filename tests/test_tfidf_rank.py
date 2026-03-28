from quizgen.tfidf_rank import rank_sentences


class TestRankSentences:
    def test_returns_ranked_list(self):
        sentences = [
            "Photosynthesis converts light energy into chemical energy in plants.",
            "The cat sat on the mat in the room.",
            "Encryption algorithms protect sensitive data from unauthorized access.",
            "It was a nice day outside today.",
            "Neural networks learn hierarchical representations of data.",
        ]
        result = rank_sentences(sentences, top_k=3)
        assert len(result) == 3
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_scores_are_descending(self):
        sentences = [
            "Photosynthesis converts light energy into chemical energy.",
            "The dog barked loudly at the mailman.",
            "Machine learning algorithms optimize objective functions.",
        ]
        result = rank_sentences(sentences, top_k=3)
        scores = [s for _, s in result]
        assert scores == sorted(scores, reverse=True)

    def test_empty_input(self):
        assert rank_sentences([], top_k=5) == []

    def test_top_k_limits_output(self):
        sentences = [f"Sentence number {i} with enough words to pass." for i in range(20)]
        result = rank_sentences(sentences, top_k=5)
        assert len(result) == 5

    def test_technical_sentences_rank_higher(self):
        sentences = [
            "The temperature was measured at 25°C using a calibrated thermometer.",
            "It was a nice sunny day and everyone was happy about it.",
        ]
        result = rank_sentences(sentences, top_k=2)
        # Technical sentence should have higher score
        top_sentence = result[0][0]
        assert "temperature" in top_sentence or "thermometer" in top_sentence
