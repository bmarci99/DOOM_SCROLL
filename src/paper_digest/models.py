from __future__ import annotations

from pydantic import BaseModel, HttpUrl
from typing import Literal, Optional, List
from datetime import datetime


Source = Literal["arxiv", "rss", "hn", "hf", "github", "pwc"]



class Item(BaseModel):
    id: str
    source: Source
    title: str
    url: HttpUrl
    published: datetime

    authors: List[str] = []
    summary: Optional[str] = None          # abstract / rss summary
    tags: List[str] = []

    score: float = 0.0

    hn_id: int | None = None
    hn_points: int = 0
    hn_comments: int = 0
    hn_activity: float = 0.0

    # cross-source tracking
    sources_seen: List[str] = []           # which sources surfaced this item
    code_url: Optional[str] = None         # link to code repo (GitHub / PwC)

    # GitHub Trending specific
    stars_today: int = 0
    total_stars: int = 0
    language: Optional[str] = None

    # scoring breakdown
    score_recency: float = 0.0
    score_engagement: float = 0.0
    score_cross_source: float = 0.0
    score_keywords: float = 0.0
    score_novelty: float = 0.0

    # intelligence layer
    topic: Optional[str] = None            # cluster label
    why_it_matters: Optional[str] = None   # editorial one-liner