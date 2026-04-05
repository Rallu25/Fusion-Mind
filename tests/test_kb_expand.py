"""Tests for kb_expand.py — knowledge base term extraction patterns."""

from quizgen.kb_expand import (
    _clean_term,
    _is_valid_term,
    _extract_coordination,
    _extract_such_as,
    _extract_parenthetical,
    _extract_colon_list,
    _extract_is_found_in,
    _extract_definitions,
    extract_new_terms,
)


class TestCleanTerm:
    def test_strips_whitespace_and_punctuation(self):
        assert _clean_term("  hello, ") == "hello"
        assert _clean_term("(test)") == "test"
        assert _clean_term('"quoted"') == "quoted"

    def test_strips_articles(self):
        assert _clean_term("the algorithm") == "algorithm"
        assert _clean_term("a sensor") == "sensor"
        assert _clean_term("an encoder") == "encoder"

    def test_preserves_valid_terms(self):
        assert _clean_term("Neural Network") == "Neural Network"
        assert _clean_term("DNA") == "DNA"


class TestIsValidTerm:
    def test_rejects_short_terms(self):
        assert _is_valid_term("ab") is False
        assert _is_valid_term("") is False

    def test_rejects_skip_words(self):
        assert _is_valid_term("the") is False
        assert _is_valid_term("process") is False
        assert _is_valid_term("system") is False

    def test_accepts_valid_terms(self):
        assert _is_valid_term("photosynthesis") is True
        assert _is_valid_term("Neural Network") is True
        assert _is_valid_term("DNA") is True


class TestExtractCoordination:
    def test_extracts_comma_and_list(self):
        # Pattern needs "X, Y, and Z" at start of list
        sents = ["Classification, regression, and clustering are common techniques."]
        groups = _extract_coordination(sents)
        assert len(groups) >= 1
        flat = [t.lower() for g in groups for t in g]
        assert "classification" in flat or "regression" in flat

    def test_extracts_or_pattern(self):
        sents = ["Cells can be prokaryotic or eukaryotic."]
        groups = _extract_coordination(sents)
        assert len(groups) >= 1
        # Terms may include extra words from regex capture
        flat = " ".join(t.lower() for g in groups for t in g)
        assert "prokaryotic" in flat
        assert "eukaryotic" in flat

    def test_no_match_on_generic(self):
        sents = ["The cat sat on the mat."]
        groups = _extract_coordination(sents)
        flat = [t.lower() for g in groups for t in g]
        assert "the" not in flat


class TestExtractSuchAs:
    def test_such_as_pattern(self):
        # Single-letter terms (A, B, C) are too short for MIN_TERM_LEN=3
        sents = ["Nutrients such as protein, calcium, and iron are essential."]
        results = _extract_such_as(sents)
        assert len(results) >= 1

    def test_including_pattern(self):
        sents = ["Metals including iron, copper, and zinc are conductors."]
        results = _extract_such_as(sents)
        assert len(results) >= 1
        _, children = results[0]
        child_lower = [c.lower() for c in children]
        assert "iron" in child_lower
        assert "copper" in child_lower

    def test_no_match_single_item(self):
        sents = ["Animals such as dogs are pets."]
        results = _extract_such_as(sents)
        # Need at least 2 children
        assert len(results) == 0


class TestExtractParenthetical:
    def test_parenthetical_list(self):
        sents = ["Carbohydrates (glucose, fructose, sucrose) provide energy."]
        results = _extract_parenthetical(sents)
        assert len(results) >= 1
        terms_lower = [t.lower() for t in results[0]]
        assert "glucose" in terms_lower
        assert "fructose" in terms_lower
        assert "sucrose" in terms_lower

    def test_no_match_single_item_parens(self):
        sents = ["The brain (cerebrum) controls thought."]
        results = _extract_parenthetical(sents)
        assert len(results) == 0  # single item, no list


class TestExtractColonList:
    def test_colon_list(self):
        sents = ["Three layers: epidermis, dermis, and hypodermis."]
        results = _extract_colon_list(sents)
        assert len(results) >= 1
        terms_lower = [t.lower() for t in results[0]]
        assert "epidermis" in terms_lower
        assert "dermis" in terms_lower

    def test_no_match_without_list(self):
        sents = ["Note: this is important."]
        results = _extract_colon_list(sents)
        assert len(results) == 0  # no comma/and list


class TestExtractIsFoundIn:
    def test_found_in_pattern(self):
        sents = [
            "The Bengal Tiger is found in India.",
            "The Snow Leopard is found in Central Asia.",
        ]
        results = _extract_is_found_in(sents)
        assert len(results) >= 1

    def test_no_match(self):
        sents = ["Water is a liquid."]
        results = _extract_is_found_in(sents)
        assert len(results) == 0


class TestExtractDefinitions:
    def test_superlative_definition(self):
        sents = ["The cheetah is the fastest land animal."]
        results = _extract_definitions(sents)
        assert len(results) >= 1

    def test_no_match_generic(self):
        sents = ["The sky is blue."]
        results = _extract_definitions(sents)
        assert len(results) == 0


class TestExtractNewTerms:
    def test_combines_all_patterns(self):
        sents = [
            "Machine learning algorithms include classification, regression, and clustering.",
            "Supervised learning such as SVM, Random Forest, and Logistic Regression are popular.",
            "Key metrics: precision, recall, and F1-score.",
        ]
        terms = extract_new_terms(sents)
        assert len(terms) > 0
        # At least some terms should have distractors
        has_distractors = any(len(v) > 0 for v in terms.values())
        assert has_distractors

    def test_empty_sentences(self):
        terms = extract_new_terms([])
        assert terms == {}

    def test_no_valid_terms(self):
        sents = ["The cat sat on the mat.", "It was a good day."]
        terms = extract_new_terms(sents)
        assert len(terms) == 0
