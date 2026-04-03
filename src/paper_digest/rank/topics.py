from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from ..models import Item


_STOP = frozenset(
    "a an the and or but is are was were be been being have has had do does did "
    "will would shall should may might can could of in to for on with at by from "
    "as into through during before after above below between out off over under "
    "again further then once here there when where why how all each every both "
    "few more most other some such no not only own same so than too very this "
    "that these those it its he she they them their what which who whom i we you "
    "your my his her our about up also just model models paper propose proposed "
    "method approach results show we present work use using used new based via "
    "data dataset learning training inference system framework tool code research "
    "hf github arxiv rss hn pwc papers http https www com org stars today source "
    "huggingface medium article blog post hackernews trending daily "
    "investigating contributions local deep".split()
)

_NUM_RE = re.compile(r"^\d+$")


def _tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())
    return [w for w in words if w not in _STOP and len(w) >= 3 and not _NUM_RE.match(w)]


def _build_tfidf_matrix(docs: List[List[str]]) -> List[Dict[str, float]]:
    n = len(docs)
    if n == 0:
        return []

    df: Counter = Counter()
    for tokens in docs:
        df.update(set(tokens))

    vectors: List[Dict[str, float]] = []
    for tokens in docs:
        tf = Counter(tokens)
        total = len(tokens) or 1
        vec: Dict[str, float] = {}
        for word, count in tf.items():
            idf = math.log((n + 1) / (1 + df.get(word, 0)))
            vec[word] = (count / total) * idf
        vectors.append(vec)

    return vectors


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(a[k] * b[k] for k in a if k in b)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _cluster_items(
    sim_matrix: List[List[float]], threshold: float = 0.15, max_clusters: int = 7
) -> List[int]:
    """Simple single-linkage agglomerative clustering. Returns cluster ID per item."""
    n = len(sim_matrix)
    labels = list(range(n))  # each item starts in its own cluster

    # find all pairs sorted by descending similarity
    pairs: List[Tuple[float, int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i][j] >= threshold:
                pairs.append((sim_matrix[i][j], i, j))
    pairs.sort(reverse=True)

    def _find(x: int) -> int:
        while labels[x] != x:
            labels[x] = labels[labels[x]]
            x = labels[x]
        return x

    def _union(a: int, b: int):
        ra, rb = _find(a), _find(b)
        if ra != rb:
            labels[rb] = ra

    num_clusters = n
    for _, i, j in pairs:
        if num_clusters <= max_clusters:
            break
        if _find(i) != _find(j):
            _union(i, j)
            num_clusters -= 1

    # normalize labels to 0..k
    roots = {}
    final = [0] * n
    for i in range(n):
        r = _find(i)
        if r not in roots:
            roots[r] = len(roots)
        final[i] = roots[r]

    return final


def _label_cluster(items: List[Item], indices: List[int], vectors: List[Dict[str, float]]) -> str:
    """Generate a human-readable label for a cluster from top TF-IDF terms."""
    # Aggregate TF-IDF across cluster members
    agg: Counter = Counter()
    for idx in indices:
        for word, weight in vectors[idx].items():
            agg[word] += weight

    top_terms = [term for term, _ in agg.most_common(6)]
    if not top_terms:
        return "General"

    # Pick up to 2 meaningful terms for a concise label
    label_terms = top_terms[:2]
    return " / ".join(t.title() for t in label_terms)


def assign_topics(items: List[Item], max_clusters: int = 7) -> Dict[str, List[int]]:
    """Cluster items by content similarity and assign topic labels.

    Modifies items in-place (sets item.topic).
    Returns mapping of topic_label -> list of item indices.
    """
    if not items:
        return {}

    # Build documents from title + summary + tags
    docs: List[List[str]] = []
    for it in items:
        text = f"{it.title} {it.summary or ''} {' '.join(it.tags)}"
        docs.append(_tokenize(text))

    vectors = _build_tfidf_matrix(docs)
    n = len(items)

    # Similarity matrix
    sim_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            s = _cosine(vectors[i], vectors[j])
            sim_matrix[i][j] = s
            sim_matrix[j][i] = s

    # Cluster — use a low threshold to allow merging even for dissimilar items
    # since we only have ~20 items and want compact topic groups
    cluster_ids = _cluster_items(sim_matrix, threshold=0.02, max_clusters=max_clusters)

    # Group indices by cluster
    clusters: Dict[int, List[int]] = {}
    for idx, cid in enumerate(cluster_ids):
        clusters.setdefault(cid, []).append(idx)

    # Label clusters and assign to items
    topic_map: Dict[str, List[int]] = {}
    for cid, indices in clusters.items():
        label = _label_cluster(items, indices, vectors)
        topic_map[label] = indices
        for idx in indices:
            items[idx].topic = label

    return topic_map
