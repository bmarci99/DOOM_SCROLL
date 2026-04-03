from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

from ..models import Item

logger = logging.getLogger("paper_digest")


def _normalize_title(t: str) -> str:
    """Normalize for fuzzy matching: lowercase, strip punctuation, collapse whitespace."""
    import re
    t = t.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def load_history(path: str | Path) -> Dict:
    """Load history from JSON file. Returns dict with 'items' list."""
    p = Path(path)
    if not p.exists():
        return {"items": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "items" not in data:
            return {"items": []}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Could not load history from {p}: {exc}")
        return {"items": []}


def save_history(path: str | Path, history: Dict) -> None:
    """Save history to JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(history, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def prune_history(history: Dict, rolling_days: int = 14) -> Dict:
    """Remove entries older than rolling_days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=rolling_days)).isoformat()
    history["items"] = [
        entry for entry in history["items"]
        if entry.get("date", "") >= cutoff
    ]
    return history


def get_seen_ids(history: Dict) -> Set[str]:
    """Get set of all item IDs from history."""
    return {entry["id"] for entry in history.get("items", []) if "id" in entry}


def get_seen_titles(history: Dict) -> Set[str]:
    """Get set of normalized titles from history."""
    return {_normalize_title(entry["title"]) for entry in history.get("items", []) if "title" in entry}


def filter_novel_items(items: List[Item], history: Dict) -> Tuple[List[Item], List[Item]]:
    """Split items into novel and duplicate lists.

    Returns (novel_items, duplicate_items).
    Exact ID match = definitely duplicate.
    Fuzzy title match = flagged as duplicate.
    """
    seen_ids = get_seen_ids(history)
    seen_titles = get_seen_titles(history)

    novel: List[Item] = []
    dupes: List[Item] = []

    for it in items:
        if it.id in seen_ids:
            dupes.append(it)
        elif _normalize_title(it.title) in seen_titles:
            dupes.append(it)
        else:
            novel.append(it)

    return novel, dupes


def record_items(history: Dict, items: List[Item]) -> Dict:
    """Add today's items to history."""
    today = datetime.now(timezone.utc).isoformat()
    for it in items:
        history["items"].append({
            "id": it.id,
            "title": it.title,
            "date": today,
            "source": it.source,
        })
    return history
