from __future__ import annotations

import json
import zipfile
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
                "version": "0.7.0",
            },
            "runtime": {
                "output_dir": str(tmp_path / "output"),
                "site_dir": str(tmp_path / "site"),
                "lookback_hours": 48,
                "request_timeout_seconds": 20,
                "max_articles": 1,
                "max_summary_chars": 2000,
                "user_agent": "DailyTechBrief/0.7.0",
                "fail_on_source_error": False,
            },
            "features": {
                "fetch_feeds": True,
                "ranking": True,
                "render_markdown": True,
                "render_html": True,
                "render_epub": True,
                "full_content_epub": True,
                "build_site": True,
                "ai_editor": False,
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
        content_html=(
            "<h2>Full Arch Linux details</h2>"
            "<p>Private full-text EPUB content.</p>"
        ),
        content_text="Private full-text EPUB content.",
        content_status="extracted",
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


def test_main_builds_complete_static_site_with_epub(
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

    exit_code = main_module.main(
        [
            "--config-dir",
            str(tmp_path),
            "--json",
        ]
    )

    assert exit_code == 0

    execution_summary = json.loads(capsys.readouterr().out)
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"

    expected_output_files = (
        "raw_articles.json",
        "source_report.json",
        "ranked_articles.json",
        "digest.md",
        "digest.html",
        "digest.epub",
        "digest-full.epub",
    )
    for filename in expected_output_files:
        assert (output_dir / filename).is_file()

    assert (site_dir / "index.html").is_file()
    assert (site_dir / "latest" / "index.html").is_file()
    assert (site_dir / "archive" / "index.html").is_file()
    assert (site_dir / "archive" / "index.json").is_file()
    assert (site_dir / "site.json").is_file()
    assert (site_dir / ".nojekyll").is_file()
    assert 'href="digest-full.epub"' in (
        site_dir / "index.html"
    ).read_text(encoding="utf-8")

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
    assert (archive_dir / "digest.epub").is_file()
    assert (archive_dir / "ranked_articles.json").is_file()
    assert (archive_dir / "source_report.json").is_file()

    assert (site_dir / "digest-full.epub").is_file()
    assert (site_dir / "latest" / "digest-full.epub").is_file()
    assert (archive_dir / "digest-full.epub").is_file()

    output_epub = output_dir / "digest.epub"
    published_epubs = (
        site_dir / "digest.epub",
        site_dir / "latest" / "digest.epub",
        archive_dir / "digest.epub",
    )
    for published_epub in published_epubs:
        assert published_epub.is_file()
        assert published_epub.read_bytes() == output_epub.read_bytes()

    full_epub = output_dir / "digest-full.epub"
    published_full_epubs = (
        site_dir / "digest-full.epub",
        site_dir / "latest" / "digest-full.epub",
        archive_dir / "digest-full.epub",
    )
    for published_full_epub in published_full_epubs:
        assert published_full_epub.is_file()
        assert (
            published_full_epub.read_bytes()
            == full_epub.read_bytes()
        )

    with zipfile.ZipFile(output_epub) as epub_archive:
        assert epub_archive.read("mimetype") == b"application/epub+zip"
        assert "EPUB/nav.xhtml" in epub_archive.namelist()
        assert "EPUB/category-linux.xhtml" in epub_archive.namelist()
        chapter = epub_archive.read("EPUB/category-linux.xhtml").decode(
            "utf-8"
        )
        assert "Arch Linux workflow update" in chapter
        assert "A practical Arch Linux update." in chapter
        assert "Private full-text EPUB content." not in chapter
        assert "Read the original article" not in chapter
        assert "Original source" in chapter

    with zipfile.ZipFile(full_epub) as epub_archive:
        chapter = epub_archive.read("EPUB/category-linux.xhtml").decode(
            "utf-8"
        )
        assert "Private full-text EPUB content." in chapter
        assert 'class="article-content full-content"' in chapter

    rendering = execution_summary["processing"]["rendering"]
    epub_summary = rendering["epub"]
    assert epub_summary["enabled"] is True
    assert epub_summary["path"] == str(output_epub)
    assert epub_summary["article_count"] == 1
    assert epub_summary["size_bytes"] == output_epub.stat().st_size
    assert str(output_epub) in execution_summary["output_paths"]

    assert epub_summary["content_mode"] == "summary"
    assert epub_summary["published_to_site"] is True

    full_epub_summary = rendering["full_epub"]
    assert full_epub_summary["enabled"] is True
    assert full_epub_summary["path"] == str(full_epub)
    assert full_epub_summary["content_mode"] == "full"
    assert full_epub_summary["published_to_site"] is True
    assert str(full_epub) in execution_summary["output_paths"]

    assert site_metadata["project"]["version"] == "0.7.0"
    assert site_metadata["article_count"] == 1
    site_summary = execution_summary["publishing"]["site"]
    assert site_summary["archive_date"] == archive_date
    assert site_summary["article_count"] == 1
    assert str(site_dir / "digest.epub") in site_summary["copied_files"]
    assert str(site_dir / "latest" / "digest.epub") in site_summary[
        "copied_files"
    ]
    assert str(archive_dir / "digest.epub") in site_summary["copied_files"]
    assert str(site_dir / "digest-full.epub") in site_summary["copied_files"]
    assert (
        str(site_dir / "latest" / "digest-full.epub")
        in site_summary["copied_files"]
    )
    assert (
        str(archive_dir / "digest-full.epub")
        in site_summary["copied_files"]
    )

    latest_html = (site_dir / "index.html").read_text(encoding="utf-8")
    assert "Arch Linux workflow update" in latest_html
    assert latest_html == (output_dir / "digest.html").read_text(
        encoding="utf-8"
    )
