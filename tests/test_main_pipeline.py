from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config_loader import ProjectConfig
from src.main import _process_and_write_ranked_articles
from src.models import Article


NOW = datetime(2026, 7, 30, 3, 0, tzinfo=timezone.utc)


def make_config() -> ProjectConfig:
    return ProjectConfig(
        sources=(),
        profile={
            "categories": {
                "ai": {
                    "label": "AI",
                    "weight": 10,
                    "daily_quota": 1,
                },
                "linux": {
                    "label": "Linux",
                    "weight": 9,
                    "daily_quota": 1,
                },
                "python": {
                    "label": "Python",
                    "weight": 8,
                    "daily_quota": 1,
                },
            },
            "keywords": {
                "high_priority": ["github actions", "arch linux"],
                "low_priority": ["smartphone rumor"],
            },
        },
        settings={
            "project": {
                "name": "Daily Tech Brief",
                "version": "0.3.0",
            },
            "runtime": {
                "lookback_hours": 48,
                "max_articles": 3,
            },
            "features": {
                "ranking": True,
            },
        },
    )


def make_article(
    title: str,
    category: str,
    url: str,
    published_at: str | None,
    *,
    source_priority: int = 5,
    summary: str = "",
    updated_at: str | None = None,
) -> Article:
    return Article(
        source_id=f"{category}_source",
        source_name=f"{category.title()} Source",
        category=category,
        source_priority=source_priority,
        source_tags=(),
        title=title,
        url=url,
        external_id=None,
        published_at=published_at,
        updated_at=updated_at,
        summary=summary,
        author=None,
        fetched_at="2026-07-30T03:00:00Z",
    )


def test_processing_pipeline_filters_deduplicates_ranks_and_selects(
    tmp_path: Path,
) -> None:
    articles = (
        make_article(
            "GitHub Actions improves reusable workflows",
            "ai",
            "https://example.com/ai-actions",
            "2026-07-30T01:00:00Z",
            source_priority=10,
        ),
        make_article(
            "Another AI platform release",
            "ai",
            "https://example.com/ai-platform",
            "2026-07-30T00:00:00Z",
            source_priority=9,
        ),
        make_article(
            "Arch Linux package update",
            "linux",
            "https://example.com/arch-update",
            "2026-07-29T23:00:00Z",
            source_priority=8,
        ),
        make_article(
            "Arch Linux package update mirror",
            "linux",
            "https://example.com/arch-update?utm_source=rss",
            "2026-07-29T23:00:00Z",
            source_priority=7,
            summary="A duplicate feed entry with a longer summary.",
        ),
        make_article(
            "Python packaging guide",
            "python",
            "https://example.com/python-packaging",
            "2026-07-29T22:00:00Z",
            source_priority=7,
        ),
        make_article(
            "Old Linux article",
            "linux",
            "https://example.com/old-linux",
            "2026-07-27T00:00:00Z",
        ),
        make_article(
            "Undated Python article",
            "python",
            "https://example.com/undated-python",
            None,
        ),
        make_article(
            "Invalid URL article",
            "python",
            "not-a-valid-url",
            "2026-07-29T21:00:00Z",
        ),
    )

    output_path, summary = _process_and_write_ranked_articles(
        config=make_config(),
        articles=articles,
        output_dir=tmp_path,
        now=NOW,
    )

    assert output_path == tmp_path / "ranked_articles.json"
    assert output_path.exists()

    assert summary["time_filter"]["total_articles"] == 8
    assert summary["time_filter"]["kept_articles"] == 6
    assert summary["time_filter"]["too_old_articles"] == 1
    assert summary["time_filter"]["missing_date_articles"] == 1

    assert summary["deduplication"] == {
        "total_articles": 6,
        "unique_articles": 4,
        "duplicate_articles": 1,
        "invalid_url_articles": 1,
        "duplicate_groups": 1,
    }
    assert summary["ranking"]["total_articles"] == 4
    assert summary["selection"]["selected_articles"] == 3
    assert summary["selection"]["selected_within_quota"] == 3
    assert summary["selection"]["selected_from_overflow"] == 0
    assert summary["selection"]["category_counts"] == {
        "ai": 1,
        "linux": 1,
        "python": 1,
    }

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["project"]["version"] == "0.3.0"
    assert payload["article_count"] == 3
    assert [article["category"] for article in payload["articles"]] == [
        "ai",
        "linux",
        "python",
    ]
    assert [article["title"] for article in payload["articles"]] == [
        "GitHub Actions improves reusable workflows",
        "Arch Linux package update mirror",
        "Python packaging guide",
    ]
    assert payload["articles"][0]["score"] > payload["articles"][2]["score"]
    assert payload["articles"][0]["score_reasons"]
