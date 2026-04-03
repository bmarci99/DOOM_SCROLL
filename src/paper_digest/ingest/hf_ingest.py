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
    now = datetime.now(timezone.utc)

    # Collect all link texts per arxiv ID — pick the longest as the title
    titles: dict[str, str] = {}
    upvotes: dict[str, int] = {}
    for a in soup.find_all("a", href=True):
        m = _ARXIV_ID_RE.match(a["href"])
        if not m:
            continue
        arxiv_id = m.group(1)
        text = a.get_text(strip=True)
        if text and len(text) > len(titles.get(arxiv_id, "")):
            # Skip short numeric strings (upvote counts) — keep actual titles
            if not text.isdigit() and not text.startswith("·"):
                titles[arxiv_id] = text
        # Capture upvote count (short numeric link text)
        if text.isdigit():
            upvotes[arxiv_id] = max(upvotes.get(arxiv_id, 0), int(text))

    out: List[Item] = []
    for arxiv_id in titles:
        if len(out) >= limit:
            break
        title_text = titles[arxiv_id]
        if len(title_text) < 5:
            title_text = f"HF Papers: {arxiv_id}"

        out.append(
            Item(
                id=f"hf:{arxiv_id}",
                source="hf",
                title=title_text,
                url=f"https://huggingface.co/papers/{arxiv_id}",
                published=now,
                tags=["huggingface"],
                hn_points=upvotes.get(arxiv_id, 0),
            )
        )

    return out