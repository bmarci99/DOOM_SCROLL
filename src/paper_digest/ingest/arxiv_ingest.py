from __future__ import annotations

from datetime import timezone
import logging
import time
from typing import List

import arxiv

from ..models import Item

logger = logging.getLogger("paper_digest")


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
    client = arxiv.Client(page_size=min(int(max_results_per_query), 100), delay_seconds=4.0, num_retries=5)

    for q in queries:
        search = arxiv.Search(
            query=q,
            max_results=max_results_per_query,
            sort_by=sort_by_map.get(sort_by, arxiv.SortCriterion.SubmittedDate),
            sort_order=sort_order_map.get(sort_order, arxiv.SortOrder.Descending),
        )

        last_err: Exception | None = None
        for attempt in range(1, 4):
            try:
                for r in client.results(search):
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
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                msg = str(exc)
                if "429" in msg:
                    sleep_s = 10 * attempt
                    logger.warning(
                        f"arXiv rate limit for query='{q}' attempt={attempt}/3; sleeping {sleep_s}s"
                    )
                    time.sleep(sleep_s)
                    continue
                logger.warning(f"arXiv query failed query='{q}' attempt={attempt}/3 err={exc}")
                time.sleep(2 * attempt)

        if last_err is not None:
            logger.warning(f"Skipping arXiv query after retries query='{q}' err={last_err}")

    return items