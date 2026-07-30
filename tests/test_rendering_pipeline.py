from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.config_loader import ProjectConfig
from src.main import _process_and_write_ranked_articles
from src.models import Article


NOW = datetime(2026, 7, 30, 4, 0, tzinfo=timezone.utc)


def make_config() -> ProjectConfig:
    return ProjectConfig(
        sources=(),
        profile={
            "profile": {
                "name": "test-profile",
                "language": "en",
                "timezone": "Asia/Ho_Chi_Minh",
            },
            "categories": {
                "linux": {
                    "label": "Linux",
                    "weight": 10,
                    "daily_quota": 1,
                },
                "python": {
                    "label": "Python",
                    "weight": 9,
                    "daily_quota": 1,
                },
            },
            "keywords": {
                "high_priority": ["arch linux", "pytest"],
                "low_priority": [],
            },
        },
        settings={
            "project": {
                "name": "Daily Tech Brief",
                "version": "0.4.0",
            },
            "runtime": {
                "lookback_hours": 48,
                "max_articles": 2,
            },
            "features": {
                "ranking": True,
                "render_markdown": True,
                "render_html": True,
            },
        },
    )


def make_article(
    *,
    title: str,
    category: str,
    url: str,
    published_at: str,
    summary: str,
) -> Article:
    return Article(
        source_id=f"{category}_source",
        source_name=f"{category.title()} Source",
        category=category,
        source_priority=10,
        source_tags=(),
        title=title,
        url=url,
        external_id=None,
        published_at=published_at,
        updated_at=None,
        summary=summary,
        author=None,
        fetched_at="2026-07-30T04:00:00Z",
    )


def test_processing_pipeline_writes_markdown_and_html_digests(
    tmp_path: Path,
) -> None:
    articles = (
        make_article(
            title="Arch Linux release update",
            category="linux",
            url="https://example.com/arch-linux",
            published_at="2026-07-30T02:00:00Z",
            summary="An important Arch Linux update.",
        ),
        make_article(
            title="Pytest workflow improvements",
            category="python",
            url="https://example.com/pytest",
            published_at="2026-07-30T01:00:00Z",
            summary="A practical testing workflow update.",
        ),
    )

    ranked_path, summary = _process_and_write_ranked_articles(
        config=make_config(),
        articles=articles,
        output_dir=tmp_path,
        now=NOW,
    )

    markdown_path = tmp_path / "digest.md"
    html_path = tmp_path / "digest.html"

    assert ranked_path.exists()
    assert markdown_path.exists()
    assert html_path.exists()

    assert summary["rendering"] == {
        "markdown": {
            "enabled": True,
            "path": str(markdown_path),
            "article_count": 2,
        },
        "html": {
            "enabled": True,
            "path": str(html_path),
            "article_count": 2,
        },
    }

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Daily Tech Brief — July 30, 2026" in markdown
    assert "## Linux" in markdown
    assert "## Python" in markdown
    assert "Arch Linux release update" in markdown
    assert "Pytest workflow improvements" in markdown

    html = html_path.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert '<section class="category-section" id="linux">' in html
    assert '<section class="category-section" id="python">' in html
    assert "Arch Linux release update" in html
    assert "Pytest workflow improvements" in html

    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    assert payload["project"]["version"] == "0.4.0"
    assert payload["summary"]["rendering"] == summary["rendering"]
    assert payload["article_count"] == 2
