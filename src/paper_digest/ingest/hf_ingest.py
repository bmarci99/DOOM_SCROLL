from __future__ import annotations

import re
from typing import List
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from ..models import Item

HF_URL = "https://huggingface.co/papers"
_ARXIV_ID_RE = re.compile(r"^/papers/(\d{4}\.\d{5})(v\d+)?$")

def fetch_hf_papers(limit: int = 30) -> List[Item]:
    headers = {"User-Agent": "DOOM_SCROLL/1.0 (GitHub Actions)"}
    r = requests.get(HF_URL, headers=headers, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    out: List[Item] = []
    seen = set()
    now = datetime.now(timezone.utc)

    for a in soup.find_all("a", href=True):
        m = _ARXIV_ID_RE.match(a["href"])
        if not m:
            continue
        arxiv_id = m.group(1)
        if arxiv_id in seen:
            continue
        seen.add(arxiv_id)

        out.append(
            Item(
                id=f"hf:{arxiv_id}",
                source="hf",
                title=f"HF Papers: {arxiv_id}",  # will be replaced by arXiv title in enrichment
                url=f"https://huggingface.co/papers/{arxiv_id}",
                published=now,  # HF page doesn't reliably expose timestamps; set now
                tags=["huggingface"],
            )
        )
        if len(out) >= limit:
            break

    return out