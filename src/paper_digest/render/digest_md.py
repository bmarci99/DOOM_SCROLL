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
    return {"hn": "Hacker News", "arxiv": "arXiv", "rss": "RSS"}.get(src, src)

def render_markdown(items: List[Item]) -> str:
    if not items:
        return "# Daily Digest\n\nNo items today.\n"

    # Group
    groups: Dict[str, List[Item]] = {"hn": [], "arxiv": [], "rss": []}
    for it in items:
        groups.setdefault(it.source, []).append(it)

    # Date line
    newest = max((it.published for it in items), default=None)
    date_str = newest.astimezone(timezone.utc).date().isoformat() if newest else ""

    lines: List[str] = []
    lines.append(f"# Daily Digest — {date_str}".rstrip(" —"))
    lines.append("")
    lines.append(
        f"**{len(items)} items** · "
        f"HN: {len(groups.get('hn', []))} · "
        f"arXiv: {len(groups.get('arxiv', []))} · "
        f"RSS: {len(groups.get('rss', []))}"
    )
    lines.append("")

    # Render each section
    for src in ("hn", "arxiv", "rss"):
        section = groups.get(src, [])
        if not section:
            continue

        lines.append(f"## {_src_title(src)}")
        lines.append("")

        for idx, it in enumerate(section, start=1):
            title = clean_text(it.title, max_len=140) if it.title else "(untitled)"
            url = str(it.url)

            meta_parts = []

            # published
            try:
                meta_parts.append(it.published.strftime("%Y-%m-%d %H:%M UTC"))
            except Exception:
                pass

            # source-specific bits
            if src == "hn":
                pts = getattr(it, "hn_points", 0) or 0
                com = getattr(it, "hn_comments", 0) or 0
                if pts or com:
                    meta_parts.append(f"{pts} pts · {com} comments")
            elif src == "arxiv":
                if it.tags:
                    meta_parts.append(", ".join(it.tags[:3]) + ("…" if len(it.tags) > 3 else ""))
                if it.authors:
                    meta_parts.append(", ".join(it.authors[:3]) + ("…" if len(it.authors) > 3 else ""))
            elif src == "rss":
                if it.authors:
                    meta_parts.append(", ".join(it.authors[:2]) + ("…" if len(it.authors) > 2 else ""))

            meta = " · ".join([m for m in meta_parts if m])

            # Summary: strip HTML + shorten
            summary = ""
            if it.summary:
                summary = clean_text(it.summary, max_len=260)

            lines.append(f"{idx}. [{title}]({url})")
            if meta:
                lines.append(f"   {meta}")
            if summary:
                lines.append(f"   {summary}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"