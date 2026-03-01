from __future__ import annotations

from typing import List, Dict
from datetime import timezone
from ..models import Item
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

def _src_title(src: str) -> str:
    return {
        "hn": "Hacker News",
        "arxiv": "arXiv Research",
        "rss": "Articles",
        "hf": "Hugging Face Papers",
    }.get(src, src)

def render_markdown(items: List[Item]) -> str:
    if not items:
        return "# Daily Digest\n\n_No items today._\n"

    groups: Dict[str, List[Item]] = {}
    for it in items:
        groups.setdefault(it.source, []).append(it)

    newest = max((it.published for it in items), default=None)
    date_str = newest.astimezone(timezone.utc).strftime("%Y-%m-%d") if newest else ""

    lines: List[str] = []

    # Header
    lines.append(f"# 📰 Daily AI Digest — {date_str}")
    lines.append("")
    lines.append(
        f"**{len(items)} curated signals**  \n"
        f"HN: {len(groups.get('hn', []))} · "
        f"arXiv: {len(groups.get('arxiv', []))} · "
        f"HF: {len(groups.get('hf', []))} · "
        f"RSS: {len(groups.get('rss', []))}"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Render sections in preferred order
    for src in ("hn", "arxiv", "hf", "rss"):
        section = groups.get(src)
        if not section:
            continue

        lines.append(f"## {_src_title(src)}")
        lines.append("")

        for it in section:
            title = clean_text(it.title, max_len=140)
            url = str(it.url)

            # Title (bold link)
            lines.append(f"### [{title}]({url})")

            meta_parts = []

            # Time
            try:
                meta_parts.append(
                    it.published.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                )
            except Exception:
                pass

            if src == "hn":
                pts = getattr(it, "hn_points", 0)
                com = getattr(it, "hn_comments", 0)
                meta_parts.append(f"{pts} pts")
                meta_parts.append(f"{com} comments")

            if src in ("arxiv", "hf"):
                if it.tags:
                    meta_parts.append(" · ".join(it.tags[:2]))
                if it.authors:
                    meta_parts.append(", ".join(it.authors[:2]) + ("…" if len(it.authors) > 2 else ""))

            if src == "rss" and it.authors:
                meta_parts.append(", ".join(it.authors[:2]))

            if meta_parts:
                lines.append(f"_ {' · '.join(meta_parts)} _")

            # Summary
            if it.summary:
                summary = clean_text(it.summary, max_len=280)
                lines.append("")
                lines.append(summary)

            lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"