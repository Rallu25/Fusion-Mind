from quizgen.matching_quiz import _extract_pairs


class TestExtractPairs:
    def test_extracts_definition_pairs(self):
        sentences = [
            "An algorithm is a step-by-step procedure for solving a problem.",
            "A sensor is a device that measures physical quantities.",
            "Encryption is a technique for converting readable data into encoded form.",
            "A database is an organized collection of structured data.",
            "The cat sat on the mat near the door.",
        ]
        # ranked format: (sentence, score)
        ranked = [(s, 1.0) for s in sentences]
        pairs = _extract_pairs(sentences, ranked)

        assert len(pairs) >= 3
        terms = [p["term"].lower() for p in pairs]
        assert "algorithm" in terms or "sensor" in terms

    def test_skips_blocked_subjects(self):
        sentences = [
            "It is a common technique used in many fields of research.",
            "This is a well-known approach in computer science today.",
        ]
        ranked = [(s, 1.0) for s in sentences]
        pairs = _extract_pairs(sentences, ranked)
        assert len(pairs) == 0

    def test_no_duplicate_terms(self):
        sentences = [
            "Encryption is a technique for protecting sensitive data.",
            "Encryption is a method of converting readable information.",
        ]
        ranked = [(s, 1.0) for s in sentences]
        pairs = _extract_pairs(sentences, ranked)
        terms = [p["term"].lower() for p in pairs]
        assert len(terms) == len(set(terms))

    def test_pair_structure(self):
        sentences = [
            "A database is an organized collection of structured data stored electronically.",
        ]
        ranked = [(s, 1.0) for s in sentences]
        pairs = _extract_pairs(sentences, ranked)
        if pairs:
            p = pairs[0]
            assert "term" in p
            assert "definition" in p
            assert "evidence" in p
            assert len(p["definition"]) >= 10
