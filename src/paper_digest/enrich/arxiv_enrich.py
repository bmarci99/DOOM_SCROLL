from __future__ import annotations

from typing import Dict, List
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import requests

from ..models import Item

ARXIV_API = "http://export.arxiv.org/api/query"

def _parse_dt(s: str) -> datetime:
    # arXiv gives ISO8601 like 2026-02-26T18:59:32Z
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s).astimezone(timezone.utc)

def enrich_from_arxiv(items: List[Item], batch_size: int = 25) -> None:
    hf_items = [it for it in items if it.source == "hf"]
    if not hf_items:
        return

    # map arxiv_id -> Item
    by_arxiv_id: Dict[str, Item] = {}
    ids: List[str] = []
    for it in hf_items:
        # id format hf:<arxiv_id>
        arxiv_id = it.id.split("hf:", 1)[-1] if it.id.startswith("hf:") else it.id
        by_arxiv_id[arxiv_id] = it
        ids.append(arxiv_id)

    headers = {"User-Agent": "DOOM_SCROLL/1.0 (GitHub Actions)"}

    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        r = requests.get(ARXIV_API, params={"id_list": ",".join(chunk)}, headers=headers, timeout=25)
        r.raise_for_status()

        root = ET.fromstring(r.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}

        for entry in root.findall("a:entry", ns):
            id_url = entry.findtext("a:id", default="", namespaces=ns)
            # http://arxiv.org/abs/2602.23360v1
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

            # overwrite HF item fields with arXiv metadata
            it.title = title or it.title
            it.summary = summary or it.summary
            it.authors = authors
            it.tags = ["hf"] + tags  # keep a marker
            if published:
                it.published = _parse_dt(published)