from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader

from ..models import Item
from .digest_html import render_html

logger = logging.getLogger("paper_digest")

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def build_site(
    items: List[Item],
    digest_html: str,
    site_dir: str | Path = "docs",
) -> Path:
    """Build a static GitHub Pages site under site_dir.

    Creates:
      - docs/index.html        (archive listing)
      - docs/YYYY-MM-DD.html   (today's digest)
    """
    site = Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{today}.html"

    # Write today's digest
    (site / filename).write_text(digest_html, encoding="utf-8")
    logger.info(f"site: wrote {site / filename}")

    # Build archive index from existing HTML files
    entries: List[Dict] = []
    for html_file in sorted(site.glob("2*.html"), reverse=True):
        date_str = html_file.stem
        count = "?"
        sources = "?"
        if html_file.stem == today and items:
            src_set = {it.source for it in items}
            count = str(len(items))
            sources = str(len(src_set))

        entries.append({
            "filename": html_file.name,
            "title": f"Daily AI Digest — {date_str}",
            "date": date_str,
            "count": count,
            "sources": sources,
        })

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)
    index_tmpl = env.get_template("index.html")
    index_html = index_tmpl.render(entries=entries)
    (site / "index.html").write_text(index_html, encoding="utf-8")
    logger.info(f"site: wrote {site / 'index.html'} ({len(entries)} entries)")

    return site
