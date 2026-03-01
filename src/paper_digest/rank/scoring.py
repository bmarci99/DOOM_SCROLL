from __future__ import annotations

from datetime import datetime, timezone
from math import log1p
from typing import List

from ..models import Item


def score_items(items: List[Item], keywords: List[str] | None = None,
               w_recency: float = 0.55, w_activity: float = 0.40, w_keywords: float = 0.05) -> List[Item]:
    keywords = [k.lower() for k in (keywords or [])]
    now = datetime.now(timezone.utc)

    rec_vals = []
    act_vals = []
    key_vals = []

    for it in items:
        age_hours = max(0.0, (now - it.published).total_seconds() / 3600.0)
        rec = 1.0 / (1.0 + age_hours)  # (0,1]
        act = log1p(float(getattr(it, "hn_activity", 0.0)))

        text = f"{it.title} {' '.join(getattr(it, 'tags', []) or [])}".lower()
        key = sum(1 for k in keywords if k and k in text)

        rec_vals.append(rec)
        act_vals.append(act)
        key_vals.append(float(key))

    rec_max = max(rec_vals) if rec_vals else 1.0
    act_max = max(act_vals) if act_vals else 1.0
    key_max = max(key_vals) if key_vals else 1.0

    for it, rec, act, key in zip(items, rec_vals, act_vals, key_vals):
        rec_n = rec / rec_max if rec_max else 0.0
        act_n = act / act_max if act_max else 0.0
        key_n = key / key_max if key_max else 0.0

        it.score = w_recency * rec_n + w_activity * act_n + w_keywords * key_n

    return items