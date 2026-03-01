from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
import time
import requests

from ..models import Item

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HN_BASE = "https://hacker-news.firebaseio.com/v0"
UA = "paper-digest/0.1"

_session = requests.Session()
_retries = Retry(
    total=3,
    backoff_factor=0.3,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
    raise_on_status=False,
)
_session.mount("https://", HTTPAdapter(max_retries=_retries))

def _get_json(url: str, timeout: tuple[float, float] = (3.0, 6.0)) -> dict | list | None:
    # timeout = (connect_timeout, read_timeout)
    try:
        r = _session.get(url, timeout=timeout, headers={"User-Agent": UA})
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def fetch_hn_story_ids(kind: str, limit: int) -> List[int]:
    data = _get_json(f"{HN_BASE}/{kind}.json")
    if not isinstance(data, list):
        return []
    return [int(x) for x in data[:limit]]

def fetch_hn_item(item_id: int) -> Optional[dict]:
    data = _get_json(f"{HN_BASE}/item/{item_id}.json")
    if not isinstance(data, dict):
        return None
    if data.get("type") != "story":
        return None
    if data.get("deleted") or data.get("dead"):
        return None
    return data

def hn_item_to_digest_item(d: dict) -> Item:
    ts = int(d.get("time", 0))
    published = datetime.fromtimestamp(ts, tz=timezone.utc)

    url = d.get("url") or f"https://news.ycombinator.com/item?id={d.get('id')}"
    title = (d.get("title") or "").strip()

    score = int(d.get("score", 0) or 0)
    comments = int(d.get("descendants", 0) or 0)

    it = Item(
        id=f"hn:{d.get('id')}",
        source="hn",
        title=title,
        url=url,
        published=published,
        authors=[d.get("by")] if d.get("by") else [],
        summary=None,
        tags=["hackernews"],
    )

    # store HN engagement into existing fields if you added them; otherwise keep as tags/score
    # recommended: add hn_points/hn_comments/hn_activity fields to Item (as discussed)
    if hasattr(it, "hn_points"):
        it.hn_points = score
        it.hn_comments = comments
        it.hn_activity = float(score + 2 * comments)

    return it

def fetch_hn_latest(limit: int = 30, sleep_s: float = 0.05) -> List[Item]:
    items: List[Item] = []
    for i in fetch_hn_story_ids("newstories", limit):
        d = fetch_hn_item(i)
        if d:
            items.append(hn_item_to_digest_item(d))
        time.sleep(sleep_s)
    return items

def fetch_hn_best(limit: int = 30, sleep_s: float = 0.05) -> List[Item]:
    items: List[Item] = []
    for i in fetch_hn_story_ids("topstories", limit):
        d = fetch_hn_item(i)
        if d:
            items.append(hn_item_to_digest_item(d))
        time.sleep(sleep_s)
    return items