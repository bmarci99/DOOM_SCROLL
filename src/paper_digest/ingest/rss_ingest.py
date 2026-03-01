from __future__ import annotations

from typing import List
from datetime import datetime, timezone
import feedparser
from dateutil import parser as dtparser

from ..models import Item


def fetch_rss_items(feeds: List[str], per_feed_limit: int = 30) -> List[Item]:
    items: List[Item] = []
    for feed_url in feeds:
        d = feedparser.parse(feed_url)
        entries = (d.entries or [])[:per_feed_limit]
        for e in entries:
            link = getattr(e, "link", None)
            if not link:
                continue

            # Published time handling (best-effort)
            published_raw = getattr(e, "published", None) or getattr(e, "updated", None)
            if published_raw:
                published = dtparser.parse(published_raw)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            else:
                published = datetime.now(tz=timezone.utc)

            guid = getattr(e, "id", None) or link
            title = (getattr(e, "title", "") or "").strip().replace("\n", " ")
            summary = getattr(e, "summary", None)

            tags = []
            for t in getattr(e, "tags", []) or []:
                term = getattr(t, "term", None)
                if term:
                    tags.append(str(term))

            items.append(
                Item(
                    id=f"rss:{guid}",
                    source="rss",
                    title=title,
                    url=link,
                    published=published,
                    authors=[getattr(a, "name", "") for a in getattr(e, "authors", []) or [] if getattr(a, "name", "")],
                    summary=summary,
                    tags=tags,
                )
            )
    return items