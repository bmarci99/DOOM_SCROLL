from __future__ import annotations

import logging
import re
from typing import List
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from ..models import Item

logger = logging.getLogger("paper_digest")

PWC_LATEST = "https://paperswithcode.com/latest"
PWC_GREATEST = "https://paperswithcode.com/greatest"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})")


def _fetch_page(url: str, limit: int) -> List[Item]:
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(f"PwC fetch failed for {url}: {exc}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items: List[Item] = []
    seen = set()
    now = datetime.now(timezone.utc)

    # PwC lists papers in rows/cards
    for row in soup.select("div.row.infinite-item, div.paper-card"):
        # Title and link
        title_el = row.select_one("h1 a, a.paper-card-title")
        if not title_el:
            continue

        href = title_el.get("href", "").strip()
        if not href:
            continue

        paper_url = f"https://paperswithcode.com{href}" if href.startswith("/") else href
        title = title_el.get_text(strip=True)

        if paper_url in seen:
            continue
        seen.add(paper_url)

        # Try to extract arXiv ID from any link on the row
        arxiv_id = None
        for a in row.select("a[href]"):
            m = _ARXIV_RE.search(a.get("href", ""))
            if m:
                arxiv_id = m.group(1)
                break

        # Abstract / description
        abstract_el = row.select_one("p.item-strip-abstract, p.paper-card-abstract")
        abstract = abstract_el.get_text(strip=True) if abstract_el else None

        # Stars / implementations count
        stars = 0
        star_el = row.select_one("span.badge, span.paper-card-stars")
        if star_el:
            text = re.sub(r"[^\d]", "", star_el.get_text())
            stars = int(text) if text else 0

        # Code repo link
        code_url = None
        code_el = row.select_one("a[href*='github.com']")
        if code_el:
            code_url = code_el.get("href")

        # Tasks / tags
        tags = []
        for tag_el in row.select("span.badge-primary, a.badge"):
            t = tag_el.get_text(strip=True)
            if t:
                tags.append(t)

        item_id = f"pwc:{arxiv_id}" if arxiv_id else f"pwc:{href.strip('/')}"

        items.append(
            Item(
                id=item_id,
                source="pwc",
                title=title,
                url=paper_url,
                published=now,
                summary=abstract,
                tags=tags[:5],
                code_url=code_url,
                total_stars=stars,
                hn_activity=float(stars),  # for unified engagement scoring
            )
        )

        if len(items) >= limit:
            break

    return items


def fetch_pwc_papers(limit: int = 20) -> List[Item]:
    """Fetch papers from Papers With Code (latest + greatest)."""
    half = max(1, limit // 2)
    latest = _fetch_page(PWC_LATEST, half)
    greatest = _fetch_page(PWC_GREATEST, half)

    # merge, dedup by id
    seen = set()
    merged: List[Item] = []
    for it in latest + greatest:
        if it.id not in seen:
            seen.add(it.id)
            merged.append(it)

    logger.info(f"Papers With Code: fetched {len(merged)} papers")
    return merged[:limit]
