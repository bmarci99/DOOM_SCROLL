from __future__ import annotations

import re
from datetime import timezone
from html import unescape, escape
from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader

from ..models import Item
from ..summarize.extractive import textrank_summary

_TAG_RE = re.compile(r"<[^>]+>")
_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _clean(s: str, max_len: int = 320) -> str:
    s = unescape(s or "")
    s = _TAG_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def _fmt_number(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


SOURCE_BADGES = {
    "hn": "HN",
    "arxiv": "arXiv",
    "hf": "HF",
    "github": "GitHub",
    "pwc": "PwC",
    "rss": "RSS",
}


class _RenderItem:
    """Lightweight wrapper that adds display fields to an Item for templates."""

    def __init__(self, item: Item):
        self._item = item
        self.source = item.source
        self.url = str(item.url)
        self.display_title = _clean(item.title, max_len=140)
        self.why_it_matters = item.why_it_matters or ""
        self.code_url = item.code_url

        # Meta line
        parts = []
        try:
            parts.append(item.published.astimezone(timezone.utc).strftime("%Y-%m-%d"))
        except Exception:
            pass
        if item.hn_points > 0:
            parts.append(f"{_fmt_number(item.hn_points)} pts")
        if item.hn_comments > 0:
            parts.append(f"{item.hn_comments} comments")
        if item.stars_today > 0:
            parts.append(f"⭐ {_fmt_number(item.stars_today)} today")
        if item.source in ("arxiv", "hf", "pwc"):
            cats = [t for t in (item.tags or []) if t.startswith("cs.") or t.startswith("stat.")]
            if cats:
                parts.append(" · ".join(cats[:2]))
            if item.authors:
                parts.append(", ".join(item.authors[:2]) + ("…" if len(item.authors) > 2 else ""))
        self.meta_line = " · ".join(parts)

        # Summary (TextRank for long, direct for short)
        if item.summary:
            raw = _clean(item.summary, max_len=2000)
            if len(raw) > 300:
                self.display_summary = escape(textrank_summary(raw, num_sentences=3))
            else:
                self.display_summary = escape(raw)
        else:
            self.display_summary = ""

        # Quick signal compact meta
        qs_parts = []
        if item.hn_points > 0:
            qs_parts.append(f"{_fmt_number(item.hn_points)} pts")
        if item.stars_today > 0:
            qs_parts.append(f"⭐{_fmt_number(item.stars_today)}")
        if item.why_it_matters:
            wim = item.why_it_matters
            if len(wim) > 50:
                wim = wim[:47] + "…"
            qs_parts.append(wim)
        self.qs_meta = " · ".join(qs_parts)


def render_html(
    items: List[Item], deep_dive_count: int = 5, archive_url: str | None = None
) -> str:
    """Render digest as HTML email using Jinja2 template."""
    if not items:
        return "<p>No items today.</p>"

    newest = max((it.published for it in items), default=None)
    date_str = newest.astimezone(timezone.utc).strftime("%Y-%m-%d") if newest else ""

    src_counts: Dict[str, int] = {}
    for it in items:
        src_counts[it.source] = src_counts.get(it.source, 0) + 1

    sorted_items = sorted(items, key=lambda x: x.score, reverse=True)
    deep_dives = [_RenderItem(it) for it in sorted_items[:deep_dive_count]]
    quick_signals = [_RenderItem(it) for it in sorted_items[deep_dive_count:]]

    def _group_by_topic(render_items: List[_RenderItem], source_items: List[Item], start: int) -> Dict[str, List[_RenderItem]]:
        groups: Dict[str, List[_RenderItem]] = {}
        for j, ri in enumerate(render_items):
            topic = source_items[start + j].topic or "General"
            groups.setdefault(topic, []).append(ri)
        return groups

    deep_dive_topics = _group_by_topic(deep_dives, sorted_items, 0)
    quick_signal_topics = _group_by_topic(quick_signals, sorted_items, deep_dive_count)

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)
    template = env.get_template("email.html")

    return template.render(
        title=f"Daily AI Digest — {date_str}",
        date_str=date_str,
        total_items=len(items),
        source_count=len(src_counts),
        deep_dive_topics=deep_dive_topics,
        quick_signals=quick_signals,
        quick_signal_topics=quick_signal_topics,
        source_badges=SOURCE_BADGES,
        archive_url=archive_url,
    )
