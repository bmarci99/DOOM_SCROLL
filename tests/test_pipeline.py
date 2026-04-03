"""Integration tests for the DOOM_SCROLL pipeline modules."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

import pytest

from src.paper_digest.models import Item


# ---------- Helpers ----------

def _make_item(
    id: str = "test:1",
    source: str = "arxiv",
    title: str = "Test Paper Title",
    url: str = "https://example.com/paper",
    published: datetime | None = None,
    summary: str | None = "A short summary of the paper.",
    tags: list[str] | None = None,
    hn_points: int = 0,
    hn_comments: int = 0,
    stars_today: int = 0,
    total_stars: int = 0,
    sources_seen: list[str] | None = None,
) -> Item:
    return Item(
        id=id,
        source=source,
        title=title,
        url=url,
        published=published or datetime.now(timezone.utc),
        summary=summary,
        tags=tags or [],
        hn_points=hn_points,
        hn_comments=hn_comments,
        hn_activity=float(hn_points + 2 * hn_comments),
        stars_today=stars_today,
        total_stars=total_stars,
        sources_seen=sources_seen or [source],
    )


def _make_items(n: int = 10) -> List[Item]:
    now = datetime.now(timezone.utc)
    items = []
    for i in range(n):
        items.append(_make_item(
            id=f"test:{i}",
            source=["arxiv", "hn", "hf", "github", "rss"][i % 5],
            title=f"Paper #{i}: {'Neural' if i % 2 == 0 else 'Reinforcement'} Learning Approach",
            published=now - timedelta(hours=i * 2),
            hn_points=100 - i * 10,
            hn_comments=50 - i * 5,
            stars_today=i * 10 if i % 5 == 3 else 0,
            summary=f"This paper presents a novel {'neural' if i % 2 == 0 else 'reinforcement'} learning approach to problem #{i}.",
        ))
    return items


# ---------- Scoring ----------

class TestScoring:
    def test_score_items_basic(self):
        from src.paper_digest.rank.scoring import score_items

        items = _make_items(10)
        scored = score_items(items)
        assert len(scored) == 10
        assert all(it.score > 0 for it in scored)

    def test_score_dimensions_bounded(self):
        from src.paper_digest.rank.scoring import score_items

        items = _make_items(10)
        scored = score_items(items)
        for it in scored:
            assert 0 <= it.score_recency <= 1
            assert 0 <= it.score_engagement <= 1
            assert 0 <= it.score_cross_source <= 1
            assert 0 <= it.score_keywords <= 1
            assert 0 <= it.score_novelty <= 1

    def test_cross_source_boost(self):
        from src.paper_digest.rank.scoring import score_items

        single = _make_item(sources_seen=["arxiv"])
        multi = _make_item(id="test:2", sources_seen=["arxiv", "hf"])
        scored = score_items([single, multi])
        assert scored[1].score_cross_source > scored[0].score_cross_source

    def test_keyword_scoring(self):
        from src.paper_digest.rank.scoring import score_items

        items = [
            _make_item(id="test:1", title="Transformer Architecture for NLP"),
            _make_item(id="test:2", title="Random Cooking Recipe"),
        ]
        scored = score_items(items, keywords=["transformer", "NLP"])
        assert scored[0].score_keywords > scored[1].score_keywords

    def test_novelty_scoring(self):
        from src.paper_digest.rank.scoring import score_items

        items = _make_items(5)
        seen = {"test:0", "test:1"}
        scored = score_items(items, seen_ids=seen)
        assert scored[0].score_novelty == 0.0  # seen
        assert scored[2].score_novelty == 1.0  # not seen


# ---------- Topics ----------

class TestTopics:
    def test_assign_topics(self):
        from src.paper_digest.rank.topics import assign_topics

        items = _make_items(10)
        topic_map = assign_topics(items, max_clusters=3)
        assert len(topic_map) <= 3
        assert all(it.topic is not None for it in items)

    def test_empty_items(self):
        from src.paper_digest.rank.topics import assign_topics

        assert assign_topics([]) == {}

    def test_single_item(self):
        from src.paper_digest.rank.topics import assign_topics

        items = [_make_item()]
        assign_topics(items, max_clusters=3)
        assert items[0].topic is not None


# ---------- Explain ----------

class TestExplain:
    def test_enrich_why_it_matters(self):
        from src.paper_digest.rank.explain import enrich_why_it_matters

        items = _make_items(5)
        items[0].hn_points = 200
        items[0].hn_comments = 100
        items[1].stars_today = 500
        items[1].source = "github"
        enrich_why_it_matters(items)
        assert items[0].why_it_matters is not None
        assert items[1].why_it_matters is not None


# ---------- TextRank ----------

class TestTextRank:
    def test_textrank_summary(self):
        from src.paper_digest.summarize.extractive import textrank_summary

        text = (
            "Neural networks have revolutionized machine learning. "
            "They learn hierarchical representations of data. "
            "Deep learning models can capture complex patterns. "
            "Transfer learning enables reuse of pre-trained features. "
            "This has led to breakthroughs in computer vision and NLP."
        )
        result = textrank_summary(text, num_sentences=2)
        assert len(result) > 0
        assert result.count(".") >= 1

    def test_short_text(self):
        from src.paper_digest.summarize.extractive import textrank_summary

        text = "One sentence only."
        result = textrank_summary(text, num_sentences=3)
        assert result == text


# ---------- Dedup ----------

class TestDedup:
    def test_basic_dedup(self):
        from src.paper_digest.main import dedup

        items = [
            _make_item(id="a:1", title="Same Paper"),
            _make_item(id="a:1", title="Same Paper"),
        ]
        result = dedup(items)
        assert len(result) == 1

    def test_title_dedup(self):
        from src.paper_digest.main import dedup

        items = [
            _make_item(id="a:1", title="A Novel Approach"),
            _make_item(id="b:2", title="A Novel Approach"),
        ]
        result = dedup(items)
        assert len(result) == 1

    def test_arxiv_cross_source(self):
        from src.paper_digest.main import dedup

        items = [
            _make_item(id="arxiv:2604.01234", source="arxiv", title="Paper One"),
            _make_item(id="hf:2604.01234", source="hf", title="Different Title"),
        ]
        result = dedup(items)
        assert len(result) == 1
        assert len(result[0].sources_seen) == 2

    def test_different_items_preserved(self):
        from src.paper_digest.main import dedup

        items = [
            _make_item(id="a:1", title="First Paper"),
            _make_item(id="b:2", title="Second Paper"),
        ]
        result = dedup(items)
        assert len(result) == 2


# ---------- Markdown Renderer ----------

class TestMarkdownRenderer:
    def test_render_markdown(self):
        from src.paper_digest.render.digest_md import render_markdown

        items = _make_items(10)
        for it in items:
            it.topic = "General"
            it.score = 1.0
        md = render_markdown(items, deep_dive_count=3)
        assert "Deep Dives" in md
        assert "Quick Signals" in md
        assert "curated signals" in md

    def test_empty_items(self):
        from src.paper_digest.render.digest_md import render_markdown

        md = render_markdown([])
        assert "No items today" in md


# ---------- HTML Renderer ----------

class TestHTMLRenderer:
    def test_render_html(self):
        from src.paper_digest.render.digest_html import render_html

        items = _make_items(10)
        for it in items:
            it.topic = "General"
            it.score = 1.0
        html = render_html(items, deep_dive_count=3)
        assert "<html" in html
        assert "Deep Dives" in html
        assert "Quick Signals" in html

    def test_empty_items(self):
        from src.paper_digest.render.digest_html import render_html

        html = render_html([])
        assert "No items today" in html


# ---------- RSS Output ----------

class TestRSSOutput:
    def test_generate_rss(self):
        from src.paper_digest.render.rss_out import generate_rss

        items = _make_items(5)
        rss = generate_rss(items, "Test Feed", "https://example.com", "Test desc")
        assert "<?xml" in rss
        assert "<rss" in rss
        assert "<item>" in rss
        assert "Test Feed" in rss


# ---------- History ----------

class TestHistory:
    def test_history_roundtrip(self, tmp_path):
        from src.paper_digest.util.history import save_history, load_history

        history_file = tmp_path / "history.json"
        items = _make_items(3)
        data = {
            "items": [
                {"id": it.id, "title": it.title, "date": "2026-04-03"}
                for it in items
            ]
        }
        history_file.write_text(json.dumps(data))
        history = load_history(str(history_file))
        assert len(history["items"]) == 3

    def test_filter_novel_items(self):
        from src.paper_digest.util.history import filter_novel_items

        items = _make_items(5)
        history = {
            "items": [
                {"id": "test:0", "title": "Paper #0", "date": "2026-04-02"},
                {"id": "test:1", "title": "Paper #1", "date": "2026-04-02"},
            ]
        }
        novel, dupes = filter_novel_items(items, history)
        assert len(novel) == 3
        assert len(dupes) == 2


# ---------- Site Builder ----------

class TestSiteBuilder:
    def test_build_site(self, tmp_path):
        from src.paper_digest.render.site_builder import build_site

        items = _make_items(5)
        for it in items:
            it.topic = "General"
            it.score = 1.0
        html = "<html><body>test</body></html>"
        build_site(items, html, site_dir=str(tmp_path / "docs"))
        assert (tmp_path / "docs" / "index.html").exists()
        # daily file exists
        daily_files = list((tmp_path / "docs").glob("2*.html"))
        assert len(daily_files) == 1
