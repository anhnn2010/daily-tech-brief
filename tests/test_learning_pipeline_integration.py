from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import src.main as main_module
from src.collector import CollectionResult
from src.config_loader import ProjectConfig
from src.main import _process_and_write_ranked_articles
from src.models import Article, Source, SourceReport


NOW = datetime(2026, 7, 31, 6, 0, tzinfo=timezone.utc)


def _write_learning_library(config_dir: Path) -> None:
    payload = {
        "schema_version": 1,
        "selection": {
            "enabled": True,
            "daily_count": 1,
            "rotation": "sequential",
            "include_in_max_articles": True,
            "history_source": "site_archive",
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "lessons": [
            {
                "id": "lesson_a",
                "order": 10,
                "title": "Current Mirror Fundamentals",
                "source_name": "Example Learning Source",
                "url": "https://example.com/learning/current-mirror",
                "track": "analog_foundations",
                "topics": ["current_mirror", "biasing"],
                "difficulty": "intermediate",
                "estimated_minutes": 20,
                "summary": "Learn how current mirrors create analog bias currents.",
                "why_it_matters": "Bias currents are used throughout analog blocks.",
                "enabled": True,
            },
            {
                "id": "lesson_b",
                "order": 20,
                "title": "PLL Fundamentals",
                "source_name": "Example Learning Source",
                "url": "https://example.com/learning/pll",
                "track": "pll_and_clocking",
                "topics": ["pll", "clocking"],
                "difficulty": "intermediate",
                "estimated_minutes": 25,
                "summary": "Learn the main blocks in a phase-locked loop.",
                "why_it_matters": "PLL knowledge supports clock bring-up and debug.",
                "enabled": True,
            },
        ],
    }
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "learning_library.yml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def _make_config(tmp_path: Path) -> ProjectConfig:
    source = Source(
        id="linux_source",
        name="Linux Source",
        provider="feed",
        format="rss",
        url="https://example.com/feed.xml",
        category="linux",
        priority=10,
        cadence="daily",
        enabled=True,
        official=True,
        tags=("linux",),
    )
    return ProjectConfig(
        sources=(source,),
        profile={
            "profile": {
                "name": "integration-profile",
                "language": "en",
                "timezone": "Asia/Ho_Chi_Minh",
            },
            "categories": {
                "linux": {
                    "label": "Linux",
                    "weight": 10,
                    "daily_quota": 12,
                },
                "analog_mixed_signal": {
                    "label": "Analog / Mixed-Signal",
                    "weight": 10,
                    "daily_quota": 1,
                },
                "test_engineering": {
                    "label": "Test Engineering",
                    "weight": 9,
                    "daily_quota": 1,
                },
                "technical_learning": {
                    "label": "Technical Learning",
                    "weight": 10,
                    "daily_quota": 0,
                },
            },
            "keywords": {
                "high_priority": ["pll", "current mirror"],
                "low_priority": [],
            },
        },
        settings={
            "project": {
                "name": "Daily Tech Brief",
                "version": "0.7.0",
            },
            "runtime": {
                "output_dir": str(tmp_path / "output"),
                "site_dir": str(tmp_path / "site"),
                "lookback_hours": 48,
                "request_timeout_seconds": 20,
                "max_articles": 12,
                "max_summary_chars": 2000,
                "user_agent": "DailyTechBrief/0.7.0",
                "fail_on_source_error": False,
            },
            "features": {
                "fetch_feeds": True,
                "ranking": True,
                "render_markdown": False,
                "render_html": False,
                "render_epub": False,
                "build_site": False,
                "ai_editor": False,
            },
        },
    )


def _make_news_articles(count: int = 12) -> tuple[Article, ...]:
    articles: list[Article] = []
    for index in range(count):
        published_at = NOW - timedelta(hours=index + 1)
        articles.append(
            Article(
                source_id="linux_source",
                source_name="Linux Source",
                category="linux",
                source_priority=10,
                source_tags=("linux",),
                title=f"Linux automation article {index + 1}",
                url=f"https://example.com/news/{index + 1}",
                external_id=f"news-{index + 1}",
                published_at=published_at.isoformat().replace("+00:00", "Z"),
                updated_at=None,
                summary="A practical Linux automation article.",
                author="Example Author",
                fetched_at=NOW.isoformat().replace("+00:00", "Z"),
            )
        )
    return tuple(articles)


def _write_archive_payload(
    archive_root: Path,
    *,
    date: str,
    payload: dict[str, object],
) -> None:
    year, month, day = date.split("-")
    path = archive_root / year / month / day / "ranked_articles.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def test_processing_reserves_one_slot_for_learning(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    archive_root = tmp_path / "site" / "archive"
    _write_learning_library(config_dir)

    output_path, summary = _process_and_write_ranked_articles(
        config=_make_config(tmp_path),
        articles=_make_news_articles(),
        output_dir=tmp_path / "output",
        config_dir=config_dir,
        archive_root=archive_root,
        enable_learning=True,
        now=NOW,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    news_articles = [
        article
        for article in payload["articles"]
        if article["source_id"] != "technical_learning"
    ]
    learning_articles = [
        article
        for article in payload["articles"]
        if article["source_id"] == "technical_learning"
    ]

    assert payload["article_count"] == 12
    assert len(news_articles) == 11
    assert len(learning_articles) == 1
    assert learning_articles[0]["external_id"] == "learning:lesson_a"
    assert learning_articles[0]["category"] == "technical_learning"
    assert payload["learning"]["lesson_ids"] == ["lesson_a"]
    assert summary["selected_news_articles"] == 11
    assert summary["selected_learning_articles"] == 1
    assert summary["learning"]["news_capacity"] == 11


def test_same_day_rerun_reuses_the_archived_lesson(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    archive_root = tmp_path / "site" / "archive"
    _write_learning_library(config_dir)
    config = _make_config(tmp_path)

    first_path, _ = _process_and_write_ranked_articles(
        config=config,
        articles=_make_news_articles(),
        output_dir=tmp_path / "first-output",
        config_dir=config_dir,
        archive_root=archive_root,
        enable_learning=True,
        now=NOW,
    )
    first_payload = json.loads(first_path.read_text(encoding="utf-8"))
    _write_archive_payload(
        archive_root,
        date="2026-07-31",
        payload=first_payload,
    )

    second_path, second_summary = _process_and_write_ranked_articles(
        config=config,
        articles=_make_news_articles(),
        output_dir=tmp_path / "second-output",
        config_dir=config_dir,
        archive_root=archive_root,
        enable_learning=True,
        now=NOW + timedelta(hours=2),
    )
    second_payload = json.loads(second_path.read_text(encoding="utf-8"))

    assert first_payload["learning"]["lesson_ids"] == ["lesson_a"]
    assert second_payload["learning"]["lesson_ids"] == ["lesson_a"]
    assert (
        second_summary["learning"]["selection"][
            "reused_current_edition"
        ]
        is True
    )


def test_next_day_selects_the_next_lesson(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    archive_root = tmp_path / "site" / "archive"
    _write_learning_library(config_dir)
    config = _make_config(tmp_path)

    first_path, _ = _process_and_write_ranked_articles(
        config=config,
        articles=_make_news_articles(),
        output_dir=tmp_path / "first-output",
        config_dir=config_dir,
        archive_root=archive_root,
        enable_learning=True,
        now=NOW,
    )
    first_payload = json.loads(first_path.read_text(encoding="utf-8"))
    _write_archive_payload(
        archive_root,
        date="2026-07-31",
        payload=first_payload,
    )

    next_day_path, _ = _process_and_write_ranked_articles(
        config=config,
        articles=_make_news_articles(),
        output_dir=tmp_path / "next-day-output",
        config_dir=config_dir,
        archive_root=archive_root,
        enable_learning=True,
        now=NOW + timedelta(days=1),
    )
    next_day_payload = json.loads(
        next_day_path.read_text(encoding="utf-8")
    )

    assert next_day_payload["learning"]["lesson_ids"] == ["lesson_b"]


def test_source_filter_run_does_not_add_learning_article(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_dir = tmp_path / "config"
    _write_learning_library(config_dir)
    config = _make_config(tmp_path)
    articles = _make_news_articles()
    report_time = NOW.isoformat().replace("+00:00", "Z")
    collection_result = CollectionResult(
        started_at=report_time,
        completed_at=report_time,
        duration_seconds=0.1,
        articles=articles,
        reports=(
            SourceReport(
                source_id="linux_source",
                source_name="Linux Source",
                category="linux",
                url="https://example.com/feed.xml",
                status="success",
                started_at=report_time,
                completed_at=report_time,
                duration_seconds=0.1,
                article_count=len(articles),
                http_status=200,
                final_url="https://example.com/feed.xml",
                feed_title="Linux Source",
            ),
        ),
    )

    monkeypatch.setattr(
        main_module,
        "load_project_config",
        lambda _config_dir: config,
    )
    monkeypatch.setattr(
        main_module,
        "collect_feeds",
        lambda _config, sources: collection_result,
    )

    exit_code = main_module.main(
        [
            "--config-dir",
            str(config_dir),
            "--source",
            "linux_source",
            "--json",
        ]
    )

    assert exit_code == 0
    execution_summary = json.loads(capsys.readouterr().out)
    payload = json.loads(
        (tmp_path / "output" / "ranked_articles.json").read_text(
            encoding="utf-8"
        )
    )

    assert "learning" not in payload
    assert payload["article_count"] == 12
    assert all(
        article["source_id"] != "technical_learning"
        for article in payload["articles"]
    )
    assert "selected_learning_articles" not in execution_summary["processing"]
