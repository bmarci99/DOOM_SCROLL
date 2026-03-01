from __future__ import annotations
import os, time, json, yaml, logging
from pathlib import Path
from typing import Any, Dict, List
from datetime import timedelta, datetime, timezone

from .delivery.email_sender import send_email
from .enrich.arxiv_enrich import enrich_from_arxiv
from .enrich.hn_match import match_hn
from .ingest.arxiv_ingest import fetch_arxiv_items
from .ingest.hf_ingest import fetch_hf_papers
from .ingest.hn_ingest import fetch_hn_best, fetch_hn_latest
from .ingest.rss_ingest import fetch_rss_items
from .rank.scoring import score_items
from .render.digest_md import render_markdown
from .util.logging import setup_logger

logger, console = setup_logger()
logging.getLogger("arxiv").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

def section(title: str):
    console.rule(f"[bold cyan]{title}[/bold cyan]")


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


def _counts(items) -> str:
    return (
        f"arXiv={sum(i.source == 'arxiv' for i in items)} "
        f"RSS={sum(i.source == 'rss' for i in items)} "
        f"HN={sum(i.source == 'hn' for i in items)} "
        f"HF={sum(i.source == 'hf' for i in items)}"
    )


def run(config_path: str = "config.yaml", keywords: List[str] | None = None) -> None:
    t_total = time.time()
    now = datetime.now(timezone.utc)

    cfg = load_config(config_path)
    arxiv_cfg = cfg.get("arxiv", {})
    rss_cfg = cfg.get("rss", {})
    out_cfg = cfg.get("output", {})
    hn_cfg = cfg.get("hackernews", {})
    hf_cfg = cfg.get("huggingface", {})
    q = cfg.get("quality", {})

    section("RUN")
    logger.info(f"now={now.isoformat()} | config={config_path}")

    # -------------------------
    # INGEST
    # -------------------------
    section("INGEST")

    t = time.time()
    items = []

    if arxiv_cfg.get("queries"):
        items += fetch_arxiv_items(
            queries=arxiv_cfg["queries"],
            max_results_per_query=int(arxiv_cfg.get("max_results_per_query", 20)),
            sort_by=str(arxiv_cfg.get("sort_by", "submittedDate")),
            sort_order=str(arxiv_cfg.get("sort_order", "descending")),
        )


    if rss_cfg.get("feeds"):
        items += fetch_rss_items(
            feeds=rss_cfg["feeds"],
            per_feed_limit=int(rss_cfg.get("per_feed_limit", 30)),
        )

    if hn_cfg.get("enabled", True):
        items += fetch_hn_latest(limit=int(hn_cfg.get("latest_n", 50)))
        items += fetch_hn_best(limit=int(hn_cfg.get("best_n", 50)))

    if hf_cfg.get("enabled", True):
        items += fetch_hf_papers(limit=int(hf_cfg.get("daily_n", 30)))

    logger.info(f"[green]done[/green] n={len(items)} | {_counts(items)} | dt={time.time()-t:.2f}s")

    """
    arxiv_items = [i for i in items if i.source == "arxiv"]
    if arxiv_items:
        oldest = min(i.published for i in arxiv_items)
        newest = max(i.published for i in arxiv_items)
        logger.info(f"arXiv date range: {oldest.isoformat()} .. {newest.isoformat()}")
    """
    # -------------------------
    # FILTER: HN quality
    # -------------------------
    section("FILTER: QUALITY")

    hn_min_points = int(q.get("hn_min_points", 50))
    hn_min_comments = int(q.get("hn_min_comments", 20))

    before = len(items)
    items = [
        it for it in items
        if it.source != "hn"
        or (getattr(it, "hn_points", 0) >= hn_min_points and getattr(it, "hn_comments", 0) >= hn_min_comments)
    ]
    logger.info( f"HN min pts={hn_min_points} com={hn_min_comments} | {before}->{len(items)} | {_counts(items)}")

    # RSS require HN thresholds (applied later, after HN matching)
    rss_require_hn = bool(q.get("rss_require_hn", True))
    rss_hn_min_points = int(q.get("rss_hn_min_points", 20))
    rss_hn_min_comments = int(q.get("rss_hn_min_comments", 5))

    # -------------------------
    # DEDUP
    # -------------------------
    section("DEDUP")
    before = len(items)
    items = dedup(items)
    logger.info(f"{before}->{len(items)} | {_counts(items)}")

    # -------------------------
    # FILTER: TIME WINDOWS
    # -------------------------
    section("FILTER: TIME")

    hrs_rss = int(out_cfg.get("last_hours_rss", 24))
    hrs_hn = int(out_cfg.get("last_hours_hn", 24))
    hrs_arxiv = int(out_cfg.get("last_hours_arxiv", 72))
    hrs_hf = int(out_cfg.get("last_hours_hf", 72))

    before = len(items)
    items = [
        it
        for it in items
        if (
            (it.source == "rss" and it.published >= now - timedelta(hours=hrs_rss))
            or (it.source == "hn" and it.published >= now - timedelta(hours=hrs_hn))
            or (it.source == "arxiv" and it.published >= now - timedelta(hours=hrs_arxiv))
            or (it.source == "hf" and it.published >= now - timedelta(hours=hrs_hf))
        )
    ]
    logger.info(
        f"windows rss={hrs_rss}h hn={hrs_hn}h arxiv={hrs_arxiv}h hf={hrs_hf}h | {before}->{len(items)} | {_counts(items)}"
    )

    # -------------------------
    # ENRICH: HF -> arXiv metadata
    # -------------------------

    section("ENRICH: HF → arXiv")
    t = time.time()
    enrich_from_arxiv(items)
    logger.info(f"[green]done[/green] dt={time.time()-t:.2f}s")

    # -------------------------
    # ENRICH: match HN for rss/arxiv/hf
    # -------------------------
    section("ENRICH: HN MATCH")

    t = time.time()
    n_match = 0

    for it in items:
        if it.source not in ("rss", "arxiv", "hf"):
            continue

        pts, com = match_hn(str(it.url), it.title)

        # HF: also try arXiv URL (better HN hit-rate)
        if it.source == "hf":
            arxiv_id = it.id.split("hf:", 1)[-1]
            arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
            pts2, com2 = match_hn(arxiv_url, it.title)
            pts, com = max(pts, pts2), max(com, com2)

        it.hn_points = max(getattr(it, "hn_points", 0), int(pts))
        it.hn_comments = max(getattr(it, "hn_comments", 0), int(com))
        it.hn_activity = float(it.hn_points + 2 * it.hn_comments)
        n_match += 1

    logger.info(f"[green]done[/green] matched={n_match} | dt={time.time()-t:.2f}s")

    # -------------------------
    # FILTER: RSS require HN (after matching)
    # -------------------------
    if rss_require_hn:
        section("FILTER: RSS REQUIRE HN")
        before = len(items)
        items = [
            it
            for it in items
            if it.source != "rss"
            or (it.hn_points >= rss_hn_min_points and it.hn_comments >= rss_hn_min_comments)
        ]
        logger.info( f"thresholds pts>={rss_hn_min_points} com>={rss_hn_min_comments} | {before}->{len(items)} | {_counts(items)}")

    # -------------------------
    # SCORE + PICK
    # -------------------------
    section("SCORE + PICK")
    #logger.info(Rule("[bold cyan]SCORE + PICK[/bold cyan]"))
    t = time.time()
    items = score_items(items, keywords=keywords or [])
    items_sorted = sorted(items, key=lambda x: x.score, reverse=True)
    logger.info(f"[green]scored[/green] n={len(items_sorted)} | dt={time.time()-t:.2f}s")

    top_k = int(out_cfg.get("top_k", 15))
    hn_quota = int(out_cfg.get("hn_quota", 0))
    hf_quota = int(out_cfg.get("hf_quota", 5))
    arxiv_quota = int(out_cfg.get("arxiv_quota", 10))
    rss_quota = max(0, top_k - arxiv_quota - hn_quota - hf_quota)  # FIXED

    picked = []
    picked_ids = set()

    def take(src: str, n: int):
        if n <= 0:
            return
        for it in items_sorted:
            if sum(1 for x in picked if x.source == src) >= n:
                break
            if it.source == src and it.id not in picked_ids:
                picked.append(it)
                picked_ids.add(it.id)

    # order is preference
    take("hn", hn_quota)
    take("hf", hf_quota)
    take("arxiv", arxiv_quota)
    take("rss", rss_quota)

    for it in items_sorted:
        if len(picked) >= top_k:
            break
        if it.id not in picked_ids:
            picked.append(it)
            picked_ids.add(it.id)

    items_top = picked
    logger.info(
        f"top_k={top_k} quotas hn={hn_quota} hf={hf_quota} arxiv={arxiv_quota} rss={rss_quota} | "
        f"picked={len(items_top)} | {_counts(items_top)}"
    )

    # -------------------------
    # WRITE OUTPUTS
    # -------------------------
    section("WRITE")
    md = render_markdown(items_top)

    md_path = Path(out_cfg.get("digest_md", "digest.md"))
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")

    json_path = Path(out_cfg.get("digest_json", "digest.json"))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps([it.model_dump() for it in items_top], ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    logger.info(f"[green]done[/green] md={md_path} json={json_path}")

    # -------------------------
    # EMAIL
    # -------------------------
    if out_cfg.get("send_email", False):
        section("EMAIL")
        to_email = os.getenv("DIGEST_TO_EMAIL")
        from_email = os.getenv("GMAIL_ADDRESS")
        app_password = os.getenv("GMAIL_APP_PASSWORD")
        if not (to_email and from_email and app_password):
            raise RuntimeError("Email enabled but DIGEST_TO_EMAIL/GMAIL_ADDRESS/GMAIL_APP_PASSWORD not set.")

        send_email(subject="Daily AI Digest", body=md, to_email=to_email, from_email=from_email, app_password=app_password)
        logger.info(f"[green]sent[/green] to={to_email}")

    section("DONE")
    logger.info(f"total_dt={time.time()-t_total:.2f}s")