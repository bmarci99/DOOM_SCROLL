from __future__ import annotations

import logging
import re
from typing import List
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from ..models import Item

logger = logging.getLogger("paper_digest")

TRENDING_URL = "https://github.com/trending"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

_STARS_RE = re.compile(r"([\d,]+)\s+stars?\s+today", re.IGNORECASE)


def _parse_stars(text: str) -> int:
    text = text.strip().replace(",", "")
    try:
        return int(text)
    except ValueError:
        return 0


def fetch_github_trending(
    limit: int = 30,
    languages: List[str] | None = None,
    keywords: List[str] | None = None,
) -> List[Item]:
    """Scrape GitHub Trending page for ML/AI repos."""
    languages = languages or ["python"]
    keywords = [k.lower() for k in (keywords or [])]
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    items: List[Item] = []
    seen = set()
    now = datetime.now(timezone.utc)

    for lang in languages:
        url = f"{TRENDING_URL}/{lang}?since=daily"
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(f"GitHub Trending fetch failed for {lang}: {exc}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")

        for article in soup.select("article.Box-row"):
            # repo name: h2 > a
            link_el = article.select_one("h2 a")
            if not link_el:
                continue

            href = link_el.get("href", "").strip()
            if not href or href in seen:
                continue

            repo_slug = href.strip("/")  # e.g., "user/repo"
            repo_url = f"https://github.com/{repo_slug}"

            # description
            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # total stars
            star_els = article.select("a.Link--muted")
            total_stars = 0
            if star_els:
                total_stars = _parse_stars(star_els[0].get_text())

            # stars today
            stars_today = 0
            today_el = article.select_one("span.d-inline-block.float-sm-right")
            if today_el:
                m = _STARS_RE.search(today_el.get_text())
                if m:
                    stars_today = int(m.group(1).replace(",", ""))

            # language
            lang_el = article.select_one("[itemprop='programmingLanguage']")
            repo_lang = lang_el.get_text(strip=True) if lang_el else lang

            # keyword filter: if keywords given, require at least one match
            if keywords:
                haystack = f"{repo_slug} {description}".lower()
                if not any(k in haystack for k in keywords):
                    continue

            seen.add(href)
            items.append(
                Item(
                    id=f"github:{repo_slug}",
                    source="github",
                    title=repo_slug.replace("/", " / "),
                    url=repo_url,
                    published=now,
                    summary=description or None,
                    tags=[repo_lang.lower()] if repo_lang else [],
                    stars_today=stars_today,
                    total_stars=total_stars,
                    language=repo_lang,
                    code_url=repo_url,
                    # map stars_today to hn_activity for unified engagement scoring
                    hn_activity=float(stars_today),
                )
            )

            if len(items) >= limit:
                break

        if len(items) >= limit:
            break

    logger.info(f"GitHub Trending: fetched {len(items)} repos")
    return items
