from __future__ import annotations

from pydantic import BaseModel, HttpUrl
from typing import Literal, Optional, List
from datetime import datetime


Source = Literal["arxiv", "rss", "hn", "hf"]



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