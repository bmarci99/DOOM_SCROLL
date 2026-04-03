from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Tuple


def _tokenize(text: str) -> List[str]:
    """Lowercase, strip punctuation, split into tokens."""
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())


# Common English stop words (kept minimal to avoid large lists)
_STOP = frozenset(
    "a an the and or but is are was were be been being have has had do does did "
    "will would shall should may might can could of in to for on with at by from "
    "as into through during before after above below between out off over under "
    "again further then once here there when where why how all each every both "
    "few more most other some such no not only own same so than too very this "
    "that these those it its he she they them their what which who whom i we you "
    "your my his her our about up also just".split()
)


def _build_tfidf(sentences: List[List[str]]) -> List[Dict[str, float]]:
    """Compute TF-IDF vectors for each sentence."""
    n = len(sentences)
    if n == 0:
        return []

    # document frequency
    df: Counter = Counter()
    for tokens in sentences:
        df.update(set(tokens))

    vectors: List[Dict[str, float]] = []
    for tokens in sentences:
        tf: Counter = Counter(tokens)
        total = len(tokens) or 1
        vec: Dict[str, float] = {}
        for word, count in tf.items():
            if word in _STOP or len(word) < 2:
                continue
            idf = math.log((n + 1) / (1 + df.get(word, 0)))
            vec[word] = (count / total) * idf
        vectors.append(vec)

    return vectors


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    # iterate over the smaller dict
    if len(a) > len(b):
        a, b = b, a
    dot = sum(a[k] * b[k] for k in a if k in b)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _pagerank(
    matrix: List[List[float]], d: float = 0.85, max_iter: int = 50, tol: float = 1e-4
) -> List[float]:
    """Simple PageRank on an adjacency matrix."""
    n = len(matrix)
    if n == 0:
        return []

    scores = [1.0 / n] * n

    for _ in range(max_iter):
        prev = scores[:]
        for i in range(n):
            rank_sum = 0.0
            for j in range(n):
                if i == j:
                    continue
                # weight from j to i
                out_weight = sum(matrix[j])
                if out_weight > 0:
                    rank_sum += matrix[j][i] / out_weight
            scores[i] = (1 - d) / n + d * rank_sum

        # convergence check
        diff = sum(abs(scores[i] - prev[i]) for i in range(n))
        if diff < tol:
            break

    return scores


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences with basic heuristics."""
    # Split on sentence-ending punctuation followed by space or end of string
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in raw if len(s.strip()) >= 20]


def textrank_summary(text: str, num_sentences: int = 3) -> str:
    """Extract key sentences from text using TextRank algorithm.

    1. Split into sentences
    2. Build TF-IDF vectors per sentence
    3. Compute pairwise cosine similarity -> adjacency matrix
    4. Run PageRank to rank sentences
    5. Return top-K sentences in original order
    """
    if not text or len(text.strip()) < 50:
        return text.strip() if text else ""

    sentences = _split_sentences(text)
    if len(sentences) <= num_sentences:
        return " ".join(sentences)

    # tokenize
    tokenized = [_tokenize(s) for s in sentences]

    # TF-IDF
    vectors = _build_tfidf(tokenized)

    # similarity matrix
    n = len(sentences)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine(vectors[i], vectors[j])
            matrix[i][j] = sim
            matrix[j][i] = sim

    # PageRank
    scores = _pagerank(matrix)

    # pick top-K by rank, reorder by original position
    ranked = sorted(range(n), key=lambda i: scores[i], reverse=True)
    top_indices = sorted(ranked[:num_sentences])

    return " ".join(sentences[i] for i in top_indices)


def quick_summary(text: str, max_sentences: int = 4) -> str:
    """Fast fallback: first N qualifying sentences."""
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    sents = [s for s in sents if 40 <= len(s) <= 300]
    return " ".join(sents[:max_sentences])