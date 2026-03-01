from __future__ import annotations

import json, yaml, os
from pathlib import Path
from typing import Any, Dict, List
from datetime import timedelta, datetime, timezone

from .ingest.arxiv_ingest import fetch_arxiv_items
from .ingest.rss_ingest import fetch_rss_items
from .rank.scoring import score_items
from .render.digest_md import render_markdown
from .ingest.hn_ingest import fetch_hn_latest, fetch_hn_best
from .util.time_filter import filter_last_hours
from .enrich.hn_match import match_hn
from .delivery.email_sender import send_email

def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def dedup(items):
    seen = set()
    out = []
    for it in items:
        if it.id in seen:
            continue
        seen.add(it.id)
        out.append(it)
    return out


def run(config_path: str = "config.yaml", keywords: List[str] | None = None) -> None:
    cfg = load_config(config_path)

    arxiv_cfg = cfg.get("arxiv", {})
    rss_cfg = cfg.get("rss", {})
    out_cfg = cfg.get("output", {})
    hn_cfg = cfg.get("hackernews", {})
    now = datetime.now(timezone.utc)


    items = []
    if arxiv_cfg.get("queries"):
        items += fetch_arxiv_items(
            queries=arxiv_cfg["queries"],
            max_results_per_query=int(arxiv_cfg.get("max_results_per_query", 20)),
            sort_by=str(arxiv_cfg.get("sort_by", "submittedDate")),
            sort_order=str(arxiv_cfg.get("sort_order", "descending")),
        )
    if rss_cfg.get("feeds"):
        items += fetch_rss_items(feeds=rss_cfg["feeds"], per_feed_limit=int(rss_cfg.get("per_feed_limit", 30)))

    if hn_cfg.get("enabled", True):
        items += fetch_hn_latest(limit=int(hn_cfg.get("latest_n", 50)))
        items += fetch_hn_best(limit=int(hn_cfg.get("best_n", 50)))

    print("INGEST:",
          "arXiv", sum(i.source == "arxiv" for i in items),
          "RSS", sum(i.source == "rss" for i in items),
          "HN", sum(i.source == "hn" for i in items))

    q = cfg.get("quality", {})
    hn_min_points = int(q.get("hn_min_points", 50))
    hn_min_comments = int(q.get("hn_min_comments", 20))

    items = [
        it for it in items
        if it.source != "hn" or (getattr(it, "hn_points", 0) >= hn_min_points and getattr(it, "hn_comments", 0) >= hn_min_comments)
    ]

    rss_require_hn = bool(q.get("rss_require_hn", True))
    rss_hn_min_points = int(q.get("rss_hn_min_points", 20))
    rss_hn_min_comments = int(q.get("rss_hn_min_comments", 5))

    items = dedup(items)
    hours = int(out_cfg.get("last_hours", 24))

    hrs_rss = int(out_cfg.get("last_hours_rss", 24))
    hrs_hn = int(out_cfg.get("last_hours_hn", 24))
    hrs_arxiv = int(out_cfg.get("last_hours_arxiv", 72))

    items = [it for it in items if (
            (it.source == "rss" and it.published >= now - timedelta(hours=hrs_rss)) or
            (it.source == "hn" and it.published >= now - timedelta(hours=hrs_hn)) or
            (it.source == "arxiv" and it.published >= now - timedelta(hours=hrs_arxiv))
    )]

    print("AFTER TIME FILTER:",
          "arXiv", sum(i.source == "arxiv" for i in items),
          "RSS", sum(i.source == "rss" for i in items),
          "HN", sum(i.source == "hn" for i in items))

    #items = filter_last_hours(items, hours)
    for it in items:
        if it.source in ("rss", "arxiv"):
            pts, com = match_hn(str(it.url), it.title)
            it.hn_points = max(getattr(it, "hn_points", 0), pts)
            it.hn_comments = max(getattr(it, "hn_comments", 0), com)
            it.hn_activity = float(it.hn_points + 2 * it.hn_comments)

    if rss_require_hn:
        items = [
            it for it in items
            if it.source != "rss" or (getattr(it, "hn_points", 0) >= rss_hn_min_points and getattr(it, "hn_comments", 0) >= rss_hn_min_comments)]

    print("AFTER QUALITY FILTER:",
          "arXiv", sum(i.source == "arxiv" for i in items),
          "RSS", sum(i.source == "rss" for i in items),
          "HN", sum(i.source == "hn" for i in items))

    items = score_items(items, keywords=keywords or [])
    items_sorted = sorted(items, key=lambda x: x.score, reverse=True)
    top_k = int(out_cfg.get("top_k", 15))
    hn_quota = int(out_cfg.get("hn_quota", 0))
    arxiv_quota = int(out_cfg.get("arxiv_quota", 10))
    rss_quota = max(0, top_k - arxiv_quota - hn_quota)

    picked = []
    picked_ids = set()

    def take(src: str, n: int):
        for it in items_sorted:
            if len([x for x in picked if x.source == src]) >= n:
                break
            if it.source == src and it.id not in picked_ids:
                picked.append(it)
                picked_ids.add(it.id)

    take("hn", hn_quota)
    take("arxiv", arxiv_quota)
    take("rss", rss_quota)

    # fill remainder by best overall
    for it in items_sorted:
        if len(picked) >= top_k:
            break
        if it.id not in picked_ids:
            picked.append(it)
            picked_ids.add(it.id)

    items_top = picked

    print(f"After time windows (rss={hrs_rss}h, hn={hrs_hn}h, arxiv={hrs_arxiv}h): {len(items)} items")
    print(f"Counts -> arXiv: {sum(1 for i in items if i.source == 'arxiv')}, "
          f"RSS: {sum(1 for i in items if i.source == 'rss')}, "
          f"HN: {sum(1 for i in items if i.source == 'hn')}")


    top_hn = sum(1 for i in items_top if i.source == "hn")
    top_arxiv = sum(1 for i in items_top if i.source == "arxiv")
    top_rss = sum(1 for i in items_top if i.source == "rss")
    print(f"Top {len(items_top)} breakdown -> arXiv: {top_arxiv}, RSS: {top_rss}, HN: {top_hn}")

    md = render_markdown(items_top)
    Path(out_cfg.get("digest_md", "digest.md")).write_text(md, encoding="utf-8")

    # JSON output for future UI / LLM step
    json_path = out_cfg.get("digest_json", "digest.json")
    Path(json_path).write_text( json.dumps([it.model_dump() for it in items_top], ensure_ascii=False, indent=2, default=str), encoding="utf-8")


    print(f"Wrote {out_cfg.get('digest_md', 'digest.md')} and {json_path} ({len(items_top)} items).")

    if out_cfg.get("send_email", False):
        body = Path(out_cfg.get("digest_md")).read_text(encoding="utf-8")
        send_email(subject="Daily AI Digest", body=body, to_email=os.environ["DIGEST_TO_EMAIL"], from_email=os.environ["GMAIL_ADDRESS"], app_password=os.environ["GMAIL_APP_PASSWORD"])


if __name__ == "__main__":
    run()