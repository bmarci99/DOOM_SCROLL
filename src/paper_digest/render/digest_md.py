from __future__ import annotations

from typing import List, Dict
from datetime import timezone
from ..models import Item
from ..summarize.extractive import textrank_summary
import re
from html import unescape

_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(s: str, max_len: int = 320) -> str:
    s = unescape(s or "")
    s = _TAG_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def _source_badge(src: str) -> str:
    return {
        "hn": "🟠 HN",
        "arxiv": "📝 arXiv",
        "rss": "📰 RSS",
        "hf": "🤗 HF",
        "github": "🐙 GitHub",
        "pwc": "📊 PwC",
    }.get(src, src)


def _source_full(src: str) -> str:
    return {
        "hn": "Hacker News",
        "arxiv": "arXiv Research",
        "rss": "Articles",
        "hf": "Hugging Face Papers",
        "github": "GitHub Trending",
        "pwc": "Papers With Code",
    }.get(src, src)


def _fmt_number(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _meta_line(it: Item) -> str:
    parts = []

    parts.append(_source_badge(it.source))

    try:
        parts.append(it.published.astimezone(timezone.utc).strftime("%Y-%m-%d"))
    except Exception:
        pass

    if it.hn_points > 0:
        parts.append(f"{_fmt_number(it.hn_points)} pts")
    if it.hn_comments > 0:
        parts.append(f"{it.hn_comments} comments")
    if it.stars_today > 0:
        parts.append(f"⭐ {_fmt_number(it.stars_today)} today")
    if it.total_stars >= 1000:
        parts.append(f"{_fmt_number(it.total_stars)} stars")

    if it.source in ("arxiv", "hf", "pwc"):
        cats = [t for t in (it.tags or []) if t.startswith("cs.") or t.startswith("stat.")]
        if cats:
            parts.append(" · ".join(cats[:2]))
        if it.authors:
            parts.append(", ".join(it.authors[:2]) + ("…" if len(it.authors) > 2 else ""))

    if it.source == "rss" and it.authors:
        parts.append(", ".join(it.authors[:2]))

    if it.code_url and it.source not in ("github",):
        parts.append(f"[code]({it.code_url})")

    return " · ".join(parts)


def _render_deep_dive(it: Item) -> List[str]:
    """Full rendering for top items (tier 1)."""
    lines: List[str] = []
    title = clean_text(it.title, max_len=160)
    url = str(it.url)

    lines.append(f"### [{title}]({url})")
    lines.append(f"_{_meta_line(it)}_")

    if it.why_it_matters:
        lines.append(f"> {it.why_it_matters}")

    if it.summary:
        # Use TextRank for longer summaries, keep short ones as-is
        raw = clean_text(it.summary, max_len=2000)
        if len(raw) > 300:
            summary = textrank_summary(raw, num_sentences=3)
        else:
            summary = raw
        lines.append("")
        lines.append(summary)

    lines.append("")
    return lines


def _render_quick_signal(it: Item) -> str:
    """Compact one-liner for tier 2 items."""
    title = clean_text(it.title, max_len=100)
    url = str(it.url)
    badge = _source_badge(it.source)

    parts = [f"[{title}]({url}) {badge}"]

    if it.hn_points > 0:
        parts.append(f"{_fmt_number(it.hn_points)} pts")
    if it.stars_today > 0:
        parts.append(f"⭐{_fmt_number(it.stars_today)}")

    if it.why_it_matters:
        # Truncate to keep it compact
        wim = it.why_it_matters
        if len(wim) > 60:
            wim = wim[:57] + "…"
        parts.append(wim)

    return " · ".join(parts)


def render_markdown(items: List[Item], deep_dive_count: int = 5) -> str:
    """Render a tiered digest: Deep Dives (top N) + Quick Signals (rest), grouped by topic."""
    if not items:
        return "# Daily Digest\n\n_No items today._\n"

    newest = max((it.published for it in items), default=None)
    date_str = newest.astimezone(timezone.utc).strftime("%Y-%m-%d") if newest else ""

    # count sources
    src_counts: Dict[str, int] = {}
    for it in items:
        src_counts[it.source] = src_counts.get(it.source, 0) + 1
    stats = " · ".join(f"{_source_full(s)}: {c}" for s, c in sorted(src_counts.items()))

    lines: List[str] = []

    # --- Header ---
    lines.append(f"# 📰 Daily AI Digest — {date_str}")
    lines.append("")
    lines.append(f"**{len(items)} curated signals** from {len(src_counts)} sources")
    lines.append(f"_{stats}_")
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Split tiers ---
    sorted_items = sorted(items, key=lambda x: x.score, reverse=True)
    deep_dives = sorted_items[:deep_dive_count]
    quick_signals = sorted_items[deep_dive_count:]

    # --- Tier 1: Deep Dives ---
    lines.append("## 🔬 Deep Dives")
    lines.append("")

    # Group deep dives by topic
    topic_groups: Dict[str, List[Item]] = {}
    for it in deep_dives:
        topic = it.topic or "General"
        topic_groups.setdefault(topic, []).append(it)

    for topic, group in topic_groups.items():
        if len(topic_groups) > 1:
            lines.append(f"#### {topic}")
            lines.append("")
        for it in group:
            lines.extend(_render_deep_dive(it))
            lines.append("---")
            lines.append("")

    # --- Tier 2: Quick Signals ---
    if quick_signals:
        lines.append("## ⚡ Quick Signals")
        lines.append("")

        # Group by topic
        qs_topics: Dict[str, List[Item]] = {}
        for it in quick_signals:
            topic = it.topic or "General"
            qs_topics.setdefault(topic, []).append(it)

        for topic, group in qs_topics.items():
            if len(qs_topics) > 1:
                lines.append(f"**{topic}**")
                lines.append("")
            for it in group:
                lines.append(f"- {_render_quick_signal(it)}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"