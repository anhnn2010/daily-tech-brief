from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from src.config_loader import ProjectConfig
from src.main import _process_and_write_ranked_articles
from src.models import Article


NOW = datetime(2026, 7, 30, 4, 0, tzinfo=timezone.utc)


def make_config(*, render_epub: bool | None = True) -> ProjectConfig:
    features: dict[str, bool] = {
        "ranking": True,
        "render_markdown": True,
        "render_html": True,
    }
    if render_epub is not None:
        features["render_epub"] = render_epub

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
                "version": "0.7.0",
            },
            "runtime": {
                "lookback_hours": 48,
                "max_articles": 2,
            },
            "features": features,
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


def make_articles() -> tuple[Article, ...]:
    return (
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


def test_processing_pipeline_writes_markdown_html_and_epub_digests(
    tmp_path: Path,
) -> None:
    ranked_path, summary = _process_and_write_ranked_articles(
        config=make_config(),
        articles=make_articles(),
        output_dir=tmp_path,
        now=NOW,
    )

    markdown_path = tmp_path / "digest.md"
    html_path = tmp_path / "digest.html"
    epub_path = tmp_path / "digest.epub"

    assert ranked_path.exists()
    assert markdown_path.exists()
    assert html_path.exists()
    assert epub_path.exists()

    epub_size = epub_path.stat().st_size
    assert epub_size > 0
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
        "epub": {
            "enabled": True,
            "path": str(epub_path),
            "article_count": 2,
            "size_bytes": epub_size,
            "content_mode": "summary",
            "published_to_site": True,
        },
        "full_epub": {
            "enabled": False,
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
    assert 'class="download-link"' in html
    assert 'href="digest.epub"' in html
    assert "Download EPUB" in html

    with ZipFile(epub_path) as epub:
        assert epub.read("mimetype") == b"application/epub+zip"
        assert "EPUB/category-linux.xhtml" in epub.namelist()
        assert "EPUB/category-python.xhtml" in epub.namelist()

        linux_chapter = epub.read("EPUB/category-linux.xhtml").decode("utf-8")
        python_chapter = epub.read("EPUB/category-python.xhtml").decode("utf-8")
        assert "Arch Linux release update" in linux_chapter
        assert "Pytest workflow improvements" in python_chapter

    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    assert payload["project"]["version"] == "0.7.0"
    assert payload["summary"]["rendering"] == summary["rendering"]
    assert payload["article_count"] == 2


def test_processing_pipeline_skips_epub_when_disabled(
    tmp_path: Path,
) -> None:
    ranked_path, summary = _process_and_write_ranked_articles(
        config=make_config(render_epub=False),
        articles=make_articles(),
        output_dir=tmp_path,
        now=NOW,
    )

    assert not (tmp_path / "digest.epub").exists()
    assert summary["rendering"]["epub"] == {"enabled": False}
    assert summary["rendering"]["full_epub"] == {
        "enabled": False
    }

    html = (tmp_path / "digest.html").read_text(encoding="utf-8")
    assert "Download EPUB" not in html
    assert 'href="digest.epub"' not in html
    assert 'class="edition-actions"' not in html

    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    assert payload["summary"]["rendering"]["epub"] == {"enabled": False}
    assert payload["summary"]["rendering"]["full_epub"] == {
        "enabled": False
    }


def test_processing_pipeline_keeps_legacy_summary_without_epub_setting(
    tmp_path: Path,
) -> None:
    ranked_path, summary = _process_and_write_ranked_articles(
        config=make_config(render_epub=None),
        articles=make_articles(),
        output_dir=tmp_path,
        now=NOW,
    )

    assert not (tmp_path / "digest.epub").exists()
    assert "epub" not in summary["rendering"]

    html = (tmp_path / "digest.html").read_text(encoding="utf-8")
    assert "Download EPUB" not in html
    assert 'href="digest.epub"' not in html
    assert 'class="edition-actions"' not in html

    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    assert "epub" not in payload["summary"]["rendering"]
