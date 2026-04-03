from __future__ import annotations

from typing import List

from ..models import Item


# Emoji mapping for signal types
_EMOJI = {
    "trending": "\U0001f525",       # 🔥
    "debate": "\U0001f4ac",         # 💬
    "code": "\U0001f4bb",           # 💻
    "multi_source": "\U0001f310",   # 🌐
    "paper": "\U0001f4c4",          # 📄
    "new": "\U0001f195",            # 🆕
    "star": "\u2b50",               # ⭐
}


def _fmt_number(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def generate_why_it_matters(item: Item) -> str:
    """Generate a 1-line editorial context string for an item based on its signals."""
    parts: List[str] = []

    # Cross-source signal (strongest signal)
    sources = item.sources_seen or [item.source]
    source_names = {
        "arxiv": "arXiv",
        "hn": "Hacker News",
        "hf": "Hugging Face",
        "github": "GitHub",
        "pwc": "Papers With Code",
        "rss": "RSS",
    }

    if len(sources) >= 3:
        named = [source_names.get(s, s) for s in sources[:4]]
        parts.append(f"{_EMOJI['multi_source']} Surfaced across {', '.join(named)}")

    # HN engagement
    if item.hn_comments >= 100:
        parts.append(f"{_EMOJI['debate']} Major HN discussion ({_fmt_number(item.hn_comments)} comments)")
    elif item.hn_comments >= 30:
        parts.append(f"{_EMOJI['debate']} Active HN discussion ({item.hn_comments} comments)")

    if item.hn_points >= 500:
        parts.append(f"{_EMOJI['trending']} Trending on HN ({_fmt_number(item.hn_points)} pts)")

    # GitHub stars
    if item.stars_today >= 100:
        parts.append(f"{_EMOJI['star']} {_fmt_number(item.stars_today)} GitHub stars today")
    elif item.stars_today >= 20:
        parts.append(f"{_EMOJI['star']} {item.stars_today} stars today on GitHub")

    if item.total_stars >= 10000:
        parts.append(f"{_EMOJI['star']} {_fmt_number(item.total_stars)} total stars")

    # Code availability
    if item.code_url and item.source not in ("github",):
        parts.append(f"{_EMOJI['code']} Code available")

    # Source-specific
    if item.source == "pwc":
        parts.append(f"{_EMOJI['paper']} Tracked by Papers With Code")

    if item.source == "hf" and "hf" in item.tags:
        parts.append(f"{_EMOJI['paper']} Featured on Hugging Face Daily Papers")

    # Fallback: at least say something
    if not parts:
        if item.source == "arxiv":
            if item.tags:
                cats = [t for t in item.tags if t.startswith("cs.") or t.startswith("stat.")]
                if cats:
                    parts.append(f"{_EMOJI['paper']} New in {', '.join(cats[:2])}")
        elif item.source == "hn":
            parts.append(f"{_EMOJI['trending']} {item.hn_points} pts on Hacker News")
        elif item.source == "github":
            parts.append(f"{_EMOJI['code']} Trending on GitHub")
        elif item.source == "rss":
            parts.append(f"{_EMOJI['new']} New article")

    # Join (limit to 2 signals for readability)
    return " · ".join(parts[:2]) if parts else ""


def enrich_why_it_matters(items: List[Item]) -> None:
    """Set why_it_matters on each item in-place."""
    for item in items:
        item.why_it_matters = generate_why_it_matters(item)
