from __future__ import annotations
import requests
from urllib.parse import quote_plus

UA = "paper-digest/0.1"

def _search(query: str) -> dict | None:
    url = f"https://hn.algolia.com/api/v1/search?query={quote_plus(query)}&tags=story"
    try:
        r = requests.get(url, timeout=(3, 6), headers={"User-Agent": UA})
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def match_hn(url: str, title: str) -> tuple[int, int]:
    # return (points, comments)
    data = _search(url) or _search(title)
    if not data:
        return 0, 0
    hits = data.get("hits") or []
    if not hits:
        return 0, 0
    h = hits[0]
    return int(h.get("points", 0) or 0), int(h.get("num_comments", 0) or 0)