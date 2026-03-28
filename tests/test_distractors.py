from quizgen.distractors import (
    normalize_word, build_vocab, get_simple_stem, shares_stem,
    get_kb_distractors, get_doc_distractors, filter_ambiguous_distractors,
    grammatical_filter, pick_distractors, KNOWLEDGE_BASE,
    _guess_word_type, _is_likely_plural, _get_preceding_word,
)


class TestNormalizeWord:
    def test_basic(self):
        assert normalize_word("Hello!") == "hello"
        assert normalize_word("CO2,") == "co"

    def test_preserves_hyphens(self):
        assert normalize_word("self-attention") == "self-attention"

    def test_empty(self):
        assert normalize_word("!!!") == ""


class TestBuildVocab:
    def test_builds_from_sentences(self):
        sentences = ["The algorithm works well", "Data is important"]
        vocab = build_vocab(sentences)
        assert "algorithm" in vocab
        assert "works" in vocab

    def test_excludes_short_words(self):
        vocab = build_vocab(["An is ok"])
        assert "an" not in vocab
        assert "is" not in vocab

    def test_excludes_generic(self):
        vocab = build_vocab(["The process and model are generic"])
        assert "process" not in vocab
        assert "model" not in vocab


class TestStems:
    def test_get_simple_stem(self):
        assert get_simple_stem("encryption") == "encryp"  # strips "tion"
        assert get_simple_stem("classification") == "classifica"

    def test_shares_stem_true(self):
        assert shares_stem("supervised", "supervision")
        assert shares_stem("encrypt", "encryption")

    def test_shares_stem_false(self):
        assert not shares_stem("chloroplasts", "mitochondria")
        assert not shares_stem("temperature", "pressure")


class TestKBDistractors:
    def test_returns_distractors(self):
        if "photosynthesis" in KNOWLEDGE_BASE:
            result = get_kb_distractors("photosynthesis", "Photosynthesis converts light.", k=3)
            assert len(result) > 0
            assert "photosynthesis" not in [r.lower() for r in result]

    def test_returns_empty_for_unknown(self):
        result = get_kb_distractors("xyznonexistent", "Some sentence.", k=3)
        assert result == []

    def test_excludes_words_in_sentence(self):
        result = get_kb_distractors("photosynthesis", "Photosynthesis and respiration are related.", k=3)
        assert "respiration" not in [r.lower() for r in result]


class TestDocDistractors:
    def test_returns_candidates(self):
        vocab = {"algorithm", "heuristic", "protocol", "method", "database"}
        result = get_doc_distractors("algorithm", vocab, "The algorithm is fast.", k=3)
        assert len(result) > 0
        assert "algorithm" not in result

    def test_excludes_sentence_words(self):
        vocab = {"fast", "slow", "algorithm"}
        result = get_doc_distractors("algorithm", vocab, "The algorithm is fast.", k=3)
        assert "fast" not in result

    def test_length_filter(self):
        vocab = {"cat", "internationalization", "dog"}
        result = get_doc_distractors("cat", vocab, "The cat sat.", k=5)
        assert "internationalization" not in result


class TestFilterAmbiguous:
    def test_removes_same_stem(self):
        result = filter_ambiguous_distractors(
            "supervised", ["supervision", "reinforcement"], "In supervised learning.", []
        )
        assert "supervision" not in result
        assert "reinforcement" in result

    def test_removes_context_match(self):
        result = filter_ambiguous_distractors(
            "supervised",
            ["unsupervised", "reinforcement"],
            "In supervised learning the model trains on labeled data.",
            ["In unsupervised learning the model finds hidden patterns in unlabeled data."]
        )
        assert "unsupervised" not in result


class TestGrammaticalFilter:
    def test_article_a(self):
        result = grammatical_filter("sensor", ["detector", "encoder", "probe"],
                                    "A sensor measures temperature.")
        assert "encoder" not in result  # vowel after "a"
        assert "detector" in result

    def test_article_an(self):
        result = grammatical_filter("algorithm", ["procedure", "operation", "approach"],
                                    "An algorithm solves the problem.")
        assert "procedure" not in result  # consonant after "an"
        assert "operation" in result

    def test_plural_agreement(self):
        result = grammatical_filter("sensors", ["motors", "algorithm", "detectors"],
                                    "The sensors measure temperature.")
        assert "algorithm" not in result  # singular
        assert "motors" in result

    def test_word_type_consistency(self):
        result = grammatical_filter("encryption", ["rapidly", "compression"],
                                    "The encryption protects data.")
        assert "rapidly" not in result  # adverb vs noun
        assert "compression" in result

    def test_common_verb_filter(self):
        result = grammatical_filter("database", ["running", "spreadsheet"],
                                    "The database stores information.")
        assert "running" not in result
        assert "spreadsheet" in result


class TestWordTypeGuessing:
    def test_noun(self):
        assert _guess_word_type("encryption") == "noun"
        assert _guess_word_type("classification") == "noun"

    def test_adjective(self):
        assert _guess_word_type("predictable") == "adjective"
        assert _guess_word_type("dangerous") == "adjective"

    def test_verb(self):
        assert _guess_word_type("optimize") == "verb"
        assert _guess_word_type("stabilize") == "verb"

    def test_adverb(self):
        assert _guess_word_type("efficiently") == "adverb"
        assert _guess_word_type("rapidly") == "adverb"


class TestPluralDetection:
    def test_plural(self):
        assert _is_likely_plural("sensors") is True
        assert _is_likely_plural("neurons") is True

    def test_singular(self):
        assert _is_likely_plural("analysis") is False
        assert _is_likely_plural("process") is False

    def test_singular_s_words(self):
        assert _is_likely_plural("photosynthesis") is False
        assert _is_likely_plural("virus") is False


class TestPrecedingWord:
    def test_basic(self):
        assert _get_preceding_word("A sensor measures temperature.", "sensor") == "a"
        assert _get_preceding_word("The encryption is strong.", "encryption") == "the"

    def test_no_preceding(self):
        assert _get_preceding_word("Encryption is strong.", "Encryption") == ""


class TestPickDistractors:
    def test_returns_k_distractors(self):
        vocab = {"hashing", "encoding", "compression", "obfuscation", "streaming", "decoding"}
        result = pick_distractors("encryption", vocab, "Encryption is a technique.", k=3)
        assert len(result) <= 3
        assert all(isinstance(d, str) for d in result)

    def test_no_duplicates(self):
        vocab = {"hashing", "encoding", "compression", "obfuscation"}
        result = pick_distractors("encryption", vocab, "Encryption is a technique.", k=3)
        assert len(result) == len(set(r.lower() for r in result))
