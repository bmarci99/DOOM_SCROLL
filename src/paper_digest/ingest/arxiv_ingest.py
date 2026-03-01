from __future__ import annotations

from datetime import datetime, timezone
from typing import List
import arxiv

from ..models import Item

def fetch_arxiv_items(
    queries: List[str],
    max_results_per_query: int,
    sort_by: str,
    sort_order: str
) -> List[Item]:
    sort_by_map = {
        "relevance": arxiv.SortCriterion.Relevance,
        "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
        "submittedDate": arxiv.SortCriterion.SubmittedDate,
    }
    sort_order_map = {
        "ascending": arxiv.SortOrder.Ascending,
        "descending": arxiv.SortOrder.Descending,
    }

    items: List[Item] = []

    for q in queries:
        search = arxiv.Search(
            query=q,
            max_results=max_results_per_query,
            sort_by=sort_by_map.get(sort_by, arxiv.SortCriterion.SubmittedDate),
            sort_order=sort_order_map.get(sort_order, arxiv.SortOrder.Descending),
        )

        for r in search.results():
            # Prefer "updated" for freshness filtering; fallback to published
            dt = getattr(r, "updated", None) or r.published
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)

            items.append(
                Item(
                    id=f"arxiv:{r.get_short_id()}",
                    source="arxiv",
                    title=r.title.strip().replace("\n", " "),
                    url=str(r.entry_id),
                    published=dt,
                    authors=[a.name for a in (r.authors or [])],
                    summary=(r.summary or "").strip(),
                    tags=list(r.categories or []),
                )
            )

    return items