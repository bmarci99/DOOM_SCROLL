from __future__ import annotations

import logging
import time
from typing import Dict, List
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import requests

from ..models import Item

logger = logging.getLogger("paper_digest")

ARXIV_API = "http://export.arxiv.org/api/query"

def _parse_dt(s: str) -> datetime:
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s).astimezone(timezone.utc)

def enrich_from_arxiv(items: List[Item], batch_size: int = 25) -> int:
    """Enrich HF items with arXiv metadata. Returns count of successfully enriched items."""
    hf_items = [it for it in items if it.source == "hf"]
    if not hf_items:
        return 0

    by_arxiv_id: Dict[str, Item] = {}
    ids: List[str] = []
    for it in hf_items:
        arxiv_id = it.id.split("hf:", 1)[-1] if it.id.startswith("hf:") else it.id
        by_arxiv_id[arxiv_id] = it
        ids.append(arxiv_id)

    headers = {"User-Agent": "DOOM_SCROLL/1.0 (GitHub Actions)"}
    enriched = 0

    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        try:
            r = requests.get(ARXIV_API, params={"id_list": ",".join(chunk)}, headers=headers, timeout=25)
            r.raise_for_status()
        except requests.RequestException as exc:
            logger.warning(f"arXiv enrichment batch {i//batch_size} failed: {exc}")
            time.sleep(1)
            continue

        try:
            root = ET.fromstring(r.text)
        except ET.ParseError as exc:
            logger.warning(f"arXiv XML parse error for batch {i//batch_size}: {exc}")
            continue

        ns = {"a": "http://www.w3.org/2005/Atom"}

        for entry in root.findall("a:entry", ns):
            id_url = entry.findtext("a:id", default="", namespaces=ns)
            arxiv_id = id_url.rsplit("/", 1)[-1].split("v", 1)[0]
            it = by_arxiv_id.get(arxiv_id)
            if not it:
                continue

            title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip().replace("\n", " ")
            summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
            published = (entry.findtext("a:published", default="", namespaces=ns) or "").strip()

            authors = []
            for a in entry.findall("a:author/a:name", ns):
                if a.text:
                    authors.append(a.text.strip())

            tags = []
            for c in entry.findall("a:category", ns):
                term = c.attrib.get("term")
                if term:
                    tags.append(term)

            it.title = title or it.title
            it.summary = summary or it.summary
            it.authors = authors
            it.tags = ["hf"] + tags
            if published:
                try:
                    it.published = _parse_dt(published)
                except (ValueError, TypeError):
                    pass
            enriched += 1

        # respect rate limit between batches
        if i + batch_size < len(ids):
            time.sleep(0.5)

    logger.info(f"enriched {enriched}/{len(hf_items)} HF items from arXiv")
    return enriched