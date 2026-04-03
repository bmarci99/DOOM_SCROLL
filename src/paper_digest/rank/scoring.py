from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from ..models import Item


# ---------- TF-IDF keyword scoring (replaces naive substring) ----------

_STOP = frozenset(
    "a an the and or but is are was were be been being have has had do does did "
    "will would shall should may might can could of in to for on with at by from "
    "as into through during before after above below between out off over under "
    "again further then once here there when where why how all each every both "
    "few more most other some such no not only own same so than too very this "
    "that these those it its he she they them their what which who whom i we you "
    "your my his her our about up also just".split()
)


def _tokenize(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) >= 2]


def _tfidf_keyword_score(item_text: str, keyword_idf: Dict[str, float]) -> float:
    """Score an item's text against pre-computed keyword IDF weights."""
    if not keyword_idf:
        return 0.0
    tokens = _tokenize(item_text)
    tf = Counter(tokens)
    total = len(tokens) or 1
    score = 0.0
    for kw, idf in keyword_idf.items():
        if kw in tf:
            score += (tf[kw] / total) * idf
    return score


def _build_keyword_idf(keywords: List[str], items: List[Item]) -> Dict[str, float]:
    """Build IDF weights for keywords across all items."""
    if not keywords:
        return {}
    n = len(items) or 1
    kw_tokens = {_tokenize(k)[0] if _tokenize(k) else k.lower() for k in keywords}
    # count how many items contain each keyword
    df: Counter = Counter()
    for it in items:
        text = f"{it.title} {it.summary or ''} {' '.join(it.tags)}".lower()
        for kw in kw_tokens:
            if kw in text:
                df[kw] += 1
    return {kw: math.log((n + 1) / (1 + df.get(kw, 0))) for kw in kw_tokens}


# ---------- Main scoring function ----------

def score_items(
    items: List[Item],
    keywords: List[str] | None = None,
    seen_ids: Set[str] | None = None,
    w_recency: float = 0.25,
    w_engagement: float = 0.30,
    w_cross_source: float = 0.25,
    w_keywords: float = 0.15,
    w_novelty: float = 0.05,
) -> List[Item]:
    """Score items using 5-dimension fusion scoring.

    Dimensions:
        1. Recency (w_recency): Inverse age decay
        2. Engagement (w_engagement): Unified engagement from HN, GitHub stars, PwC
        3. Cross-source (w_cross_source): Exponential boost for multi-source items
        4. Keywords (w_keywords): TF-IDF weighted keyword matching
        5. Novelty (w_novelty): Penalty for items seen in previous digests
    """
    keywords = [k.lower() for k in (keywords or [])]
    seen_ids = seen_ids or set()
    now = datetime.now(timezone.utc)

    keyword_idf = _build_keyword_idf(keywords, items)

    # --- Raw values ---
    rec_vals: List[float] = []
    eng_vals: List[float] = []
    xsrc_vals: List[float] = []
    key_vals: List[float] = []
    nov_vals: List[float] = []

    for it in items:
        # 1. Recency: inverse age decay (gentler — half-life ~24h)
        age_hours = max(0.0, (now - it.published).total_seconds() / 3600.0)
        rec = 1.0 / (1.0 + age_hours / 24.0)
        rec_vals.append(rec)

        # 2. Engagement: unified from multiple signals
        # HN activity (points + 2*comments), GitHub stars_today
        hn_eng = math.log1p(float(it.hn_activity))
        gh_eng = math.log1p(float(it.stars_today))
        total_eng = hn_eng + gh_eng
        eng_vals.append(total_eng)

        # 3. Cross-source: exponential boost for items on multiple sources
        n_sources = max(1, len(it.sources_seen)) if it.sources_seen else 1
        xsrc = math.exp(n_sources - 1) - 1  # 1 source=0, 2 sources=1.7, 3=6.4
        xsrc_vals.append(xsrc)

        # 4. Keywords: TF-IDF weighted
        text = f"{it.title} {it.summary or ''} {' '.join(it.tags)}"
        key = _tfidf_keyword_score(text, keyword_idf)
        key_vals.append(key)

        # 5. Novelty: 1.0 if new, 0.0 if seen before
        nov = 0.0 if it.id in seen_ids else 1.0
        nov_vals.append(nov)

    # --- Normalize each dimension to [0, 1] ---
    def _normalize(vals: List[float]) -> List[float]:
        mx = max(vals) if vals else 1.0
        if mx == 0:
            return [0.0] * len(vals)
        return [v / mx for v in vals]

    rec_n = _normalize(rec_vals)
    eng_n = _normalize(eng_vals)
    xsrc_n = _normalize(xsrc_vals)
    key_n = _normalize(key_vals)
    nov_n = _normalize(nov_vals)

    # --- Weighted combination ---
    for i, it in enumerate(items):
        it.score_recency = rec_n[i]
        it.score_engagement = eng_n[i]
        it.score_cross_source = xsrc_n[i]
        it.score_keywords = key_n[i]
        it.score_novelty = nov_n[i]

        it.score = (
            w_recency * rec_n[i]
            + w_engagement * eng_n[i]
            + w_cross_source * xsrc_n[i]
            + w_keywords * key_n[i]
            + w_novelty * nov_n[i]
        )

    return items