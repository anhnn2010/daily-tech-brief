from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import src.main as main_module
from src.collector import CollectionResult
from src.config_loader import ProjectConfig
from src.models import Article, Source, SourceReport


def make_config(tmp_path: Path) -> ProjectConfig:
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
            },
            "keywords": {
                "high_priority": ["arch linux"],
                "low_priority": [],
            },
        },
        settings={
            "project": {
                "name": "Daily Tech Brief",
                "version": "0.6.0",
            },
            "runtime": {
                "output_dir": str(tmp_path / "output"),
                "site_dir": str(tmp_path / "site"),
                "lookback_hours": 48,
                "request_timeout_seconds": 20,
                "max_articles": 1,
                "max_summary_chars": 2000,
                "user_agent": "DailyTechBrief/0.6.0",
                "fail_on_source_error": False,
            },
            "features": {
                "fetch_feeds": True,
                "ranking": True,
                "render_markdown": True,
                "render_html": True,
                "build_site": True,
                "ai_editor": False,
                "epub": False,
            },
        },
    )


def make_collection_result() -> CollectionResult:
    collected_at = datetime.now(timezone.utc).replace(microsecond=0)
    published_at = collected_at - timedelta(hours=1)

    article = Article(
        source_id="linux_source",
        source_name="Linux Source",
        category="linux",
        source_priority=10,
        source_tags=("linux",),
        title="Arch Linux workflow update",
        url="https://example.com/arch-linux-update",
        external_id=None,
        published_at=published_at.isoformat().replace("+00:00", "Z"),
        updated_at=None,
        summary="A practical Arch Linux update.",
        author="Example Author",
        fetched_at=collected_at.isoformat().replace("+00:00", "Z"),
    )
    report = SourceReport(
        source_id="linux_source",
        source_name="Linux Source",
        category="linux",
        url="https://example.com/feed.xml",
        status="success",
        started_at=collected_at.isoformat().replace("+00:00", "Z"),
        completed_at=collected_at.isoformat().replace("+00:00", "Z"),
        duration_seconds=0.1,
        article_count=1,
        http_status=200,
        final_url="https://example.com/feed.xml",
        feed_title="Linux Source",
    )

    return CollectionResult(
        started_at=collected_at.isoformat().replace("+00:00", "Z"),
        completed_at=collected_at.isoformat().replace("+00:00", "Z"),
        duration_seconds=0.1,
        articles=(article,),
        reports=(report,),
    )


def test_main_builds_complete_static_site(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config = make_config(tmp_path)
    collection_result = make_collection_result()

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

    exit_code = main_module.main(["--json"])

    assert exit_code == 0

    execution_summary = json.loads(capsys.readouterr().out)
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"

    assert (output_dir / "raw_articles.json").is_file()
    assert (output_dir / "source_report.json").is_file()
    assert (output_dir / "ranked_articles.json").is_file()
    assert (output_dir / "digest.md").is_file()
    assert (output_dir / "digest.html").is_file()

    assert (site_dir / "index.html").is_file()
    assert (site_dir / "latest" / "index.html").is_file()
    assert (site_dir / "archive" / "index.html").is_file()
    assert (site_dir / "archive" / "index.json").is_file()
    assert (site_dir / "site.json").is_file()
    assert (site_dir / ".nojekyll").is_file()

    site_metadata = json.loads(
        (site_dir / "site.json").read_text(encoding="utf-8")
    )
    archive_date = site_metadata["archive_date"]
    archive_dir = (
        site_dir
        / "archive"
        / archive_date[0:4]
        / archive_date[5:7]
        / archive_date[8:10]
    )

    assert (archive_dir / "index.html").is_file()
    assert (archive_dir / "digest.md").is_file()
    assert (archive_dir / "ranked_articles.json").is_file()
    assert (archive_dir / "source_report.json").is_file()

    assert site_metadata["project"]["version"] == "0.6.0"
    assert site_metadata["article_count"] == 1
    assert execution_summary["publishing"]["site"]["archive_date"] == archive_date
    assert execution_summary["publishing"]["site"]["article_count"] == 1

    latest_html = (site_dir / "index.html").read_text(encoding="utf-8")
    assert "Arch Linux workflow update" in latest_html
    assert latest_html == (output_dir / "digest.html").read_text(
        encoding="utf-8"
    )
