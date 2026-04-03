from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader

from ..models import Item
from .digest_html import render_html

logger = logging.getLogger("paper_digest")

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_ARCHIVE_PAGE = "archive.html"
_SITE_DATA_FILE = "site-data.json"


def _load_site_data(data_path: Path) -> Dict[str, Any]:
    if not data_path.exists():
        return {}
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning(f"site: could not read {data_path}; rebuilding metadata")
        return {}
    return data if isinstance(data, dict) else {}


def build_site(
    items: List[Item],
    digest_html: str | None = None,
    site_dir: str | Path = "docs",
    deep_dive_count: int = 5,
) -> Path:
    """Build the static GitHub Pages site under site_dir.

    Creates:
      - docs/YYYY-MM-DD.html   (today's digest)
      - docs/archive.html      (archive listing)
      - docs/site-data.json    (lightweight site metadata for the landing page)
    """
    site = Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{today}.html"

    if digest_html is None:
        digest_html = render_html(
            items,
            deep_dive_count=deep_dive_count,
            archive_url=_ARCHIVE_PAGE,
        )

    (site / filename).write_text(digest_html, encoding="utf-8")
    logger.info(f"site: wrote {site / filename}")

    metadata_path = site / _SITE_DATA_FILE
    existing_data = _load_site_data(metadata_path)
    existing_archive = existing_data.get("archive", [])
    archived_by_filename: Dict[str, Dict[str, Any]] = {}
    if isinstance(existing_archive, list):
        for entry in existing_archive:
            if not isinstance(entry, dict):
                continue
            entry_name = str(entry.get("filename", "")).strip()
            if entry_name:
                archived_by_filename[entry_name] = dict(entry)

    today_count = len(items)
    today_sources = len({it.source for it in items})

    entries: List[Dict[str, Any]] = []
    for html_file in sorted(site.glob("2*.html"), reverse=True):
        date_str = html_file.stem
        previous = archived_by_filename.get(html_file.name, {})
        count = previous.get("count")
        sources = previous.get("sources")

        if html_file.name == filename:
            count = today_count
            sources = today_sources

        entries.append(
            {
                "filename": html_file.name,
                "title": f"Daily AI Digest — {date_str}",
                "date": date_str,
                "count": count,
                "sources": sources,
            }
        )

    latest = entries[0] if entries else None
    site_data = {
        "project_name": "DOOM_SCROLL",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "latest": latest,
        "archive": entries,
    }
    metadata_path.write_text(
        json.dumps(site_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"site: wrote {metadata_path}")

    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)
    archive_tmpl = env.get_template(_ARCHIVE_PAGE)
    archive_html = archive_tmpl.render(entries=entries, latest=latest)
    (site / _ARCHIVE_PAGE).write_text(archive_html, encoding="utf-8")
    logger.info(f"site: wrote {site / _ARCHIVE_PAGE} ({len(entries)} entries)")

    return site
