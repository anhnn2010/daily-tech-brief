from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import src.main as main_module
from src.config_loader import ProjectConfig
from src.content.enricher import (
    ContentEnrichmentRecord,
    ContentEnrichmentResult,
)
from src.main import _process_and_write_ranked_articles
from src.models import Article


NOW = datetime(2026, 7, 31, 8, 0, tzinfo=timezone.utc)


def _config(*, full_content_epub: bool) -> ProjectConfig:
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
                    "daily_quota": 2,
                },
            },
            "keywords": {
                "high_priority": ["linux"],
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
                "content_timeout_seconds": 7,
                "content_max_download_bytes": 123456,
            },
            "features": {
                "ranking": True,
                "render_markdown": True,
                "render_html": True,
                "render_epub": True,
                "full_content_epub": full_content_epub,
            },
        },
    )


def _articles() -> tuple[Article, ...]:
    return (
        Article(
            source_id="linux_source",
            source_name="Linux Source",
            category="linux",
            source_priority=10,
            source_tags=("linux",),
            title="Linux Article One",
            url="https://example.com/linux-one",
            external_id="one",
            published_at="2026-07-31T07:00:00Z",
            updated_at=None,
            summary="Public summary one.",
            author="Author One",
            fetched_at="2026-07-31T08:00:00Z",
        ),
        Article(
            source_id="linux_source",
            source_name="Linux Source",
            category="linux",
            source_priority=9,
            source_tags=("linux",),
            title="Linux Article Two",
            url="https://example.com/linux-two",
            external_id="two",
            published_at="2026-07-31T06:00:00Z",
            updated_at=None,
            summary="Public summary two.",
            author="Author Two",
            fetched_at="2026-07-31T08:00:00Z",
        ),
    )


def _record(article: Article, word_count: int) -> ContentEnrichmentRecord:
    return ContentEnrichmentRecord(
        source_id=article.source_id,
        title=article.title,
        url=article.url,
        status="extracted",
        http_status=200,
        content_type="text/html",
        selector="[itemprop='articleBody']",
        word_count=word_count,
        duration_seconds=0.1,
        error=None,
    )


def test_full_content_is_used_only_for_epub(
    tmp_path: Path,
    monkeypatch,
) -> None:
    enrichment_call: dict[str, Any] = {}
    epub_calls: list[dict[str, Any]] = []

    def fake_enrich(
        articles: Any,
        *,
        timeout_seconds: float,
        maximum_download_bytes: int,
    ) -> ContentEnrichmentResult:
        original = tuple(articles)
        enrichment_call["articles"] = original
        enrichment_call["timeout_seconds"] = timeout_seconds
        enrichment_call["maximum_download_bytes"] = maximum_download_bytes

        enriched = tuple(
            replace(
                article,
                content_html=(
                    f"<h2>Full section {index}</h2>"
                    f"<p>Private EPUB body {index}.</p>"
                ),
                content_text=f"Private EPUB body {index}.",
                content_status="extracted",
            )
            for index, article in enumerate(original, start=1)
        )
        return ContentEnrichmentResult(
            articles=enriched,
            records=tuple(
                _record(article, word_count=100 + index)
                for index, article in enumerate(original, start=1)
            ),
        )

    def fake_render_epub(
        articles: Any,
        profile: dict[str, Any],
        *,
        generated_at: str,
        project_name: str,
    ) -> bytes:
        captured_articles = tuple(articles)
        epub_calls.append(
            {
                "articles": captured_articles,
                "profile": profile,
                "generated_at": generated_at,
                "project_name": project_name,
            }
        )
        has_full_content = any(
            ranked.article.has_full_content
            for ranked in captured_articles
        )
        return (
            b"full-epub"
            if has_full_content
            else b"summary-epub"
        )

    monkeypatch.setattr(
        main_module,
        "enrich_selected_articles",
        fake_enrich,
    )
    monkeypatch.setattr(
        main_module,
        "render_epub_digest",
        fake_render_epub,
    )

    ranked_path, summary = _process_and_write_ranked_articles(
        config=_config(full_content_epub=True),
        articles=_articles(),
        output_dir=tmp_path,
        now=NOW,
    )

    assert enrichment_call["timeout_seconds"] == 7.0
    assert enrichment_call["maximum_download_bytes"] == 123456
    assert [
        article.title
        for article in enrichment_call["articles"]
    ] == [
        "Linux Article One",
        "Linux Article Two",
    ]

    assert len(epub_calls) == 2

    public_epub_articles = tuple(
        ranked.article
        for ranked in epub_calls[0]["articles"]
    )
    assert all(
        article.content_status == "not_requested"
        for article in public_epub_articles
    )
    assert all(
        not article.has_full_content
        for article in public_epub_articles
    )

    epub_articles = tuple(
        ranked.article
        for ranked in epub_calls[1]["articles"]
    )
    assert [
        article.content_status
        for article in epub_articles
    ] == [
        "extracted",
        "extracted",
    ]
    assert "Private EPUB body 1." in epub_articles[0].content_html
    assert "Private EPUB body 2." in epub_articles[1].content_html

    assert (
        tmp_path / "digest.epub"
    ).read_bytes() == b"summary-epub"
    assert (
        tmp_path / "digest-full.epub"
    ).read_bytes() == b"full-epub"

    rendering = summary["rendering"]
    assert rendering["epub"]["content_mode"] == "summary"
    assert rendering["epub"]["published_to_site"] is True
    assert rendering["full_epub"]["content_mode"] == "full"
    assert rendering["full_epub"]["published_to_site"] is False

    payload = json.loads(
        ranked_path.read_text(encoding="utf-8")
    )
    assert [
        article["content_status"]
        for article in payload["articles"]
    ] == [
        "not_requested",
        "not_requested",
    ]
    assert all(
        article["content_html"] == ""
        for article in payload["articles"]
    )
    assert all(
        article["content_text"] == ""
        for article in payload["articles"]
    )

    markdown = (tmp_path / "digest.md").read_text(
        encoding="utf-8"
    )
    html = (tmp_path / "digest.html").read_text(
        encoding="utf-8"
    )
    assert "Public summary one." in markdown
    assert "Public summary one." in html
    assert "Private EPUB body" not in markdown
    assert "Private EPUB body" not in html

    enrichment_summary = summary["content_enrichment"]
    assert enrichment_summary["requested_articles"] == 2
    assert enrichment_summary["extracted_articles"] == 2
    assert enrichment_summary["summary_fallback_articles"] == 0
    assert enrichment_summary["failed_articles"] == 0


def test_disabled_feature_does_not_enrich_articles(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_if_called(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("content enrichment must remain disabled")

    captured: dict[str, Any] = {"calls": 0}

    def fake_render_epub(
        articles: Any,
        profile: dict[str, Any],
        *,
        generated_at: str,
        project_name: str,
    ) -> bytes:
        captured["calls"] += 1
        captured["articles"] = tuple(articles)
        return b"summary-epub"

    monkeypatch.setattr(
        main_module,
        "enrich_selected_articles",
        fail_if_called,
    )
    monkeypatch.setattr(
        main_module,
        "render_epub_digest",
        fake_render_epub,
    )

    ranked_path, summary = _process_and_write_ranked_articles(
        config=_config(full_content_epub=False),
        articles=_articles(),
        output_dir=tmp_path,
        now=NOW,
    )

    assert "content_enrichment" not in summary
    assert captured["calls"] == 1
    assert all(
        ranked.article.content_status == "not_requested"
        for ranked in captured["articles"]
    )

    assert (tmp_path / "digest.epub").is_file()
    assert not (tmp_path / "digest-full.epub").exists()
    assert summary["rendering"]["full_epub"] == {
        "enabled": False
    }

    payload = json.loads(
        ranked_path.read_text(encoding="utf-8")
    )
    assert all(
        article["content_status"] == "not_requested"
        for article in payload["articles"]
    )
