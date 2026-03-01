from __future__ import annotations

from typing import List
from ..models import Item


def render_markdown(items: List[Item]) -> str:
    lines = []

    lines.append("# Daily Digest")
    lines.append("")
    for it in items:

        lines.append(f"## {it.title}")
        lines.append(f"- Source: `{it.source}`")
        lines.append(f"- Published: {it.published.isoformat()}")
        lines.append(f"- Link: {it.url}")
        if it.authors:
            lines.append(f"- Authors: {', '.join(it.authors[:12])}{'…' if len(it.authors) > 12 else ''}")
        if it.tags:
            lines.append(f"- Tags: {', '.join(it.tags[:12])}{'…' if len(it.tags) > 12 else ''}")
        lines.append(f"- Score: {it.score:.3f}")
        if it.summary:
            s = it.summary.strip()
            if len(s) > 900:
                s = s[:900].rsplit(" ", 1)[0] + "…"
            lines.append("")
            lines.append(s)
        lines.append("")
    return "\n".join(lines)