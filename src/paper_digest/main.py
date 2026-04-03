from __future__ import annotations
import os, time, json, yaml, logging, re
from pathlib import Path
from typing import Any, Dict, List, Set
from datetime import timedelta, datetime, timezone

from .delivery.email_sender import send_email
from .enrich.arxiv_enrich import enrich_from_arxiv
from .enrich.hn_match import match_hn
from .ingest.arxiv_ingest import fetch_arxiv_items
from .ingest.hf_ingest import fetch_hf_papers
from .ingest.hn_ingest import fetch_hn_best, fetch_hn_latest
from .ingest.rss_ingest import fetch_rss_items
from .ingest.github_ingest import fetch_github_trending
from .ingest.pwc_ingest import fetch_pwc_papers
from .rank.scoring import score_items
from .rank.topics import assign_topics
from .rank.explain import enrich_why_it_matters
from .render.digest_md import render_markdown
from .render.digest_html import render_html
from .render.rss_out import generate_rss
from .render.site_builder import build_site
from .util.history import (
    load_history, save_history, prune_history,
    get_seen_ids, filter_novel_items, record_items,
)
from .util.logging import setup_logger

logger, console = setup_logger()
logging.getLogger("arxiv").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


def section(title: str):
    console.rule(f"[bold cyan]{title}[/bold cyan]")


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _normalize_title(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", t.lower().strip()))


def dedup(items: List) -> List:
    """Deduplicate by ID, arxiv-ID, and fuzzy title, merging sources_seen for cross-source items."""
    seen: Dict[str, Any] = {}
    title_map: Dict[str, str] = {}
    arxiv_map: Dict[str, str] = {}  # arxiv_id -> item.id for cross-source matching

    def _extract_arxiv_id(item) -> str | None:
        """Extract bare arXiv ID from item ID (works for hf:, arxiv:, pwc: prefixes)."""
        raw = item.id
        for prefix in ("hf:", "arxiv:", "pwc:"):
            if raw.startswith(prefix):
                return raw[len(prefix):]
        return None

    def _merge(existing, new_item):
        if new_item.source not in existing.sources_seen:
            existing.sources_seen.append(new_item.source)
        existing.hn_points = max(existing.hn_points, new_item.hn_points)
        existing.hn_comments = max(existing.hn_comments, new_item.hn_comments)
        existing.hn_activity = max(existing.hn_activity, new_item.hn_activity)
        existing.stars_today = max(existing.stars_today, new_item.stars_today)
        existing.total_stars = max(existing.total_stars, new_item.total_stars)
        if new_item.code_url and not existing.code_url:
            existing.code_url = new_item.code_url

    for it in items:
        norm = _normalize_title(it.title)
        arxiv_id = _extract_arxiv_id(it)

        # Match by exact ID
        if it.id in seen:
            _merge(seen[it.id], it)
            continue

        # Match by arXiv ID (cross-source: hf vs arxiv vs pwc)
        if arxiv_id and arxiv_id in arxiv_map:
            existing_id = arxiv_map[arxiv_id]
            if existing_id in seen:
                _merge(seen[existing_id], it)
                continue

        # Match by fuzzy title
        if norm in title_map:
            existing_id = title_map[norm]
            if existing_id in seen:
                _merge(seen[existing_id], it)
                continue

        if it.source not in it.sources_seen:
            it.sources_seen = [it.source]
        seen[it.id] = it
        title_map[norm] = it.id
        if arxiv_id:
            arxiv_map[arxiv_id] = it.id

    return list(seen.values())


def _counts(items) -> str:
    sources = ["arxiv", "rss", "hn", "hf", "github", "pwc"]
    parts = [f"{s}={sum(1 for i in items if i.source == s)}" for s in sources]
    return " ".join(parts)


def run(config_path: str = "config.yaml", keywords: List[str] | None = None) -> None:
    t_total = time.time()
    now = datetime.now(timezone.utc)

    cfg = load_config(config_path)
    arxiv_cfg = cfg.get("arxiv", {})
    rss_cfg = cfg.get("rss", {})
    out_cfg = cfg.get("output", {})
    hn_cfg = cfg.get("hackernews", {})
    hf_cfg = cfg.get("huggingface", {})
    gh_cfg = cfg.get("github_trending", {})
    pwc_cfg = cfg.get("papers_with_code", {})
    q = cfg.get("quality", {})
    scoring_cfg = cfg.get("scoring", {})
    history_cfg = cfg.get("history", {})

    section("RUN")
    logger.info(f"now={now.isoformat()} | config={config_path}")

    # ---- HISTORY ----
    section("HISTORY")
    hist_path = out_cfg.get("history_json", "outputs/history.json")
    history = load_history(hist_path)
    history = prune_history(history, rolling_days=int(history_cfg.get("rolling_days", 14)))
    seen_ids = get_seen_ids(history)
    logger.info(f"loaded history entries={len(history.get('items', []))} seen_ids={len(seen_ids)}")

    # ---- INGEST ----
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

    if gh_cfg.get("enabled", True):
        items += fetch_github_trending(
            limit=int(gh_cfg.get("limit", 30)),
            languages=gh_cfg.get("languages", ["python"]),
            keywords=gh_cfg.get("keywords", []),
        )

    if pwc_cfg.get("enabled", True):
        items += fetch_pwc_papers(limit=int(pwc_cfg.get("limit", 20)))

    logger.info(f"[green]done[/green] n={len(items)} | {_counts(items)} | dt={time.time()-t:.2f}s")

    # ---- FILTER: HN quality ----
    section("FILTER: QUALITY")
    hn_min_points = int(q.get("hn_min_points", 50))
    hn_min_comments = int(q.get("hn_min_comments", 20))
    before = len(items)
    items = [
        it for it in items
        if it.source != "hn"
        or (getattr(it, "hn_points", 0) >= hn_min_points
            and getattr(it, "hn_comments", 0) >= hn_min_comments)
    ]
    logger.info(f"HN min pts={hn_min_points} com={hn_min_comments} | {before}->{len(items)} | {_counts(items)}")

    rss_require_hn = bool(q.get("rss_require_hn", True))
    rss_hn_min_points = int(q.get("rss_hn_min_points", 20))
    rss_hn_min_comments = int(q.get("rss_hn_min_comments", 5))

    # ---- DEDUP (cross-source merge) ----
    section("DEDUP")
    before = len(items)
    items = dedup(items)
    multi_src = sum(1 for it in items if len(it.sources_seen) > 1)
    logger.info(f"{before}->{len(items)} | multi_source={multi_src} | {_counts(items)}")

    # ---- FILTER: TIME WINDOWS ----
    section("FILTER: TIME")
    window = {
        "rss": timedelta(hours=int(out_cfg.get("last_hours_rss", 24))),
        "hn": timedelta(hours=int(out_cfg.get("last_hours_hn", 24))),
        "arxiv": timedelta(hours=int(out_cfg.get("last_hours_arxiv", 72))),
        "hf": timedelta(hours=int(out_cfg.get("last_hours_hf", 72))),
        "github": timedelta(hours=int(out_cfg.get("last_hours_github", 24))),
        "pwc": timedelta(hours=int(out_cfg.get("last_hours_pwc", 168))),
    }
    before = len(items)
    items = [it for it in items if it.published >= now - window.get(it.source, timedelta(hours=72))]
    logger.info(f"time windows | {before}->{len(items)} | {_counts(items)}")

    # ---- FILTER: Novelty (cross-day dedup) ----
    section("FILTER: NOVELTY")
    before = len(items)
    items, dupes = filter_novel_items(items, history)
    logger.info(f"novel={len(items)} dupes={len(dupes)} | {_counts(items)}")

    # ---- ENRICH: HF -> arXiv metadata ----
    section("ENRICH: HF -> arXiv")
    t = time.time()
    enrich_from_arxiv(items)
    logger.info(f"[green]done[/green] dt={time.time()-t:.2f}s")

    # ---- ENRICH: match HN for rss/arxiv/hf ----
    section("ENRICH: HN MATCH")
    t = time.time()
    n_match = 0
    for it in items:
        if it.source not in ("rss", "arxiv", "hf", "pwc", "github"):
            continue
        pts, com = match_hn(str(it.url), it.title)
        if it.source in ("hf", "pwc"):
            arxiv_id = it.id.split(":", 1)[-1]
            arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"
            pts2, com2 = match_hn(arxiv_url, it.title)
            pts, com = max(pts, pts2), max(com, com2)
        it.hn_points = max(getattr(it, "hn_points", 0), int(pts))
        it.hn_comments = max(getattr(it, "hn_comments", 0), int(com))
        it.hn_activity = float(it.hn_points + 2 * it.hn_comments)
        n_match += 1
    logger.info(f"[green]done[/green] matched={n_match} | dt={time.time()-t:.2f}s")

    # ---- FILTER: RSS require HN (after matching) ----
    if rss_require_hn:
        section("FILTER: RSS REQUIRE HN")
        before = len(items)
        items = [
            it for it in items
            if it.source != "rss"
            or (it.hn_points >= rss_hn_min_points and it.hn_comments >= rss_hn_min_comments)
        ]
        logger.info(f"thresholds pts>={rss_hn_min_points} com>={rss_hn_min_comments} | {before}->{len(items)} | {_counts(items)}")

    # ---- SCORE ----
    section("SCORE")
    t = time.time()
    items = score_items(
        items,
        keywords=keywords or [],
        seen_ids=seen_ids,
        w_recency=float(scoring_cfg.get("w_recency", 0.25)),
        w_engagement=float(scoring_cfg.get("w_engagement", 0.30)),
        w_cross_source=float(scoring_cfg.get("w_cross_source", 0.25)),
        w_keywords=float(scoring_cfg.get("w_keywords", 0.15)),
        w_novelty=float(scoring_cfg.get("w_novelty", 0.05)),
    )
    items_sorted = sorted(items, key=lambda x: x.score, reverse=True)
    logger.info(f"[green]scored[/green] n={len(items_sorted)} | dt={time.time()-t:.2f}s")

    # ---- PICK (quota-based selection) ----
    section("PICK")
    top_k = int(out_cfg.get("top_k", 20))
    quotas = {
        "arxiv": int(out_cfg.get("arxiv_quota", 7)),
        "hn": int(out_cfg.get("hn_quota", 4)),
        "hf": int(out_cfg.get("hf_quota", 3)),
        "github": int(out_cfg.get("github_quota", 3)),
        "pwc": int(out_cfg.get("pwc_quota", 2)),
        "rss": int(out_cfg.get("rss_quota", 1)),
    }
    picked: List = []
    picked_ids: Set[str] = set()

    def take(src: str, n: int):
        if n <= 0:
            return
        for it in items_sorted:
            if sum(1 for x in picked if x.source == src) >= n:
                break
            if it.source == src and it.id not in picked_ids:
                picked.append(it)
                picked_ids.add(it.id)

    for src in ["hn", "hf", "arxiv", "github", "pwc", "rss"]:
        take(src, quotas.get(src, 0))

    for it in items_sorted:
        if len(picked) >= top_k:
            break
        if it.id not in picked_ids:
            picked.append(it)
            picked_ids.add(it.id)

    items_top = picked
    logger.info(f"top_k={top_k} | picked={len(items_top)} | {_counts(items_top)}")

    # ---- TOPICS + EXPLAIN ----
    section("TOPICS + EXPLAIN")
    t = time.time()
    deep_dive_count = int(out_cfg.get("deep_dive_count", 5))
    assign_topics(items_top, max_clusters=min(7, max(2, len(items_top) // 3)))
    enrich_why_it_matters(items_top)
    logger.info(f"[green]done[/green] topics + explain | dt={time.time()-t:.2f}s")

    # ---- WRITE OUTPUTS ----
    section("WRITE")
    md = render_markdown(items_top, deep_dive_count=deep_dive_count)
    html = render_html(items_top, deep_dive_count=deep_dive_count)

    md_path = Path(out_cfg.get("digest_md", "outputs/digest.md"))
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")

    json_path = Path(out_cfg.get("digest_json", "outputs/digest.json"))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps([it.model_dump() for it in items_top], ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    html_path = md_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    logger.info(f"[green]done[/green] md={md_path} json={json_path} html={html_path}")

    # ---- SITE + RSS ----
    section("SITE + RSS")
    site_dir = build_site(items_top, html, site_dir="docs")
    rss_xml = generate_rss(items_top)
    (site_dir / "feed.xml").write_text(rss_xml, encoding="utf-8")
    logger.info(f"[green]done[/green] site={site_dir} feed.xml")

    # ---- SAVE HISTORY ----
    section("HISTORY: SAVE")
    record_items(history, items_top)
    save_history(hist_path, history)
    logger.info(f"[green]saved[/green] {hist_path}")

    # ---- RUN STATS ----
    stats_path = Path(out_cfg.get("run_stats_json", "outputs/run_stats.json"))
    stats = {
        "timestamp": now.isoformat(),
        "total_ingested": len(items) + len(dupes),
        "after_novelty": len(items),
        "picked": len(items_top),
        "sources": {s: sum(1 for it in items_top if it.source == s)
                    for s in ["arxiv", "hn", "hf", "github", "pwc", "rss"]},
        "multi_source_items": multi_src,
        "duration_s": round(time.time() - t_total, 2),
    }
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

    # ---- EMAIL ----
    if out_cfg.get("send_email", False):
        section("EMAIL")
        to_email = os.getenv("DIGEST_TO_EMAIL")
        from_email = os.getenv("GMAIL_ADDRESS")
        app_password = os.getenv("GMAIL_APP_PASSWORD")
        if not (to_email and from_email and app_password):
            logger.warning("email enabled but DIGEST_TO_EMAIL/GMAIL_ADDRESS/GMAIL_APP_PASSWORD not set — skipping")
        else:
            send_email(
                subject=f"Daily AI Digest \u2014 {now.strftime('%Y-%m-%d')}",
                body_plain=md,
                to_email=to_email,
                from_email=from_email,
                app_password=app_password,
                body_html=html,
            )
            logger.info(f"[green]sent[/green] to={to_email}")

    section("DONE")
    logger.info(f"total_dt={time.time()-t_total:.2f}s | picked={len(items_top)} items")
