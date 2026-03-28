import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer


def rank_sentences(sentences: list[str], top_k: int = 30) -> list[tuple[str, float]]:
    if not sentences:
        return []

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1
    )

    X = vectorizer.fit_transform(sentences)

    scores = np.asarray(X.power(2).sum(axis=1)).reshape(-1)
    sorted_indexes = np.argsort(-scores)

    ranked = [
        (sentences[i], float(scores[i]))
        for i in sorted_indexes[:min(top_k, len(sentences))]
    ]

    return ranked