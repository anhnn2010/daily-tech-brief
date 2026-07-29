from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.collector import collect_feeds, write_collection_outputs
from src.config_loader import ProjectConfig
from src.models import Source


FIXTURES = Path(__file__).parent / "fixtures"
FIXED_NOW = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        url: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.content = content
        self.url = url
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/xml"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error for {self.url}")


class FakeSession:
    def __init__(self, outcomes: dict[str, Any]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        outcome = self.outcomes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_source(source_id: str, url: str, feed_format: str = "rss") -> Source:
    return Source(
        id=source_id,
        name=source_id.replace("_", " ").title(),
        provider="feed",
        format=feed_format,
        url=url,
        category="python",
        priority=10,
        cadence="daily",
        enabled=True,
        official=True,
        tags=("test",),
    )


def make_config(sources: tuple[Source, ...]) -> ProjectConfig:
    return ProjectConfig(
        sources=sources,
        profile={"categories": {"python": {"weight": 10, "daily_quota": 2}}},
        settings={
            "project": {"name": "Test Brief", "version": "0.2.0"},
            "runtime": {
                "request_timeout_seconds": 5,
                "user_agent": "DailyTechBrief-Test/0.2.0",
                "max_summary_chars": 2000,
                "fail_on_source_error": False,
            },
            "features": {"fetch_feeds": True},
        },
    )


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_collects_and_normalizes_rss_feed() -> None:
    source = make_source("sample_rss", "https://feeds.test/rss")
    session = FakeSession(
        {
            source.url: FakeResponse(
                fixture_bytes("sample_rss.xml"),
                source.url,
            )
        }
    )

    result = collect_feeds(make_config((source,)), session=session, now=FIXED_NOW)

    assert result.failed_sources == 0
    assert len(result.articles) == 1
    article = result.articles[0]
    assert article.title == "Python & Automation"
    assert article.url == "https://example.com/python-automation"
    assert article.summary == "A useful article."
    assert article.author == "Example Author"
    assert article.published_at == "2026-07-29T08:00:00Z"
    assert article.fetched_at == "2026-07-29T12:00:00Z"


def test_collects_and_normalizes_atom_feed() -> None:
    source = make_source(
        "sample_atom",
        "https://feeds.test/atom",
        feed_format="atom",
    )
    session = FakeSession(
        {
            source.url: FakeResponse(
                fixture_bytes("sample_atom.xml"),
                source.url,
            )
        }
    )

    result = collect_feeds(make_config((source,)), session=session, now=FIXED_NOW)

    article = result.articles[0]
    assert article.title == "Linux Release"
    assert article.url == "https://example.org/linux-release"
    assert article.summary == "New release details."
    assert article.updated_at == "2026-07-29T09:00:00Z"


def test_source_failure_does_not_stop_other_sources() -> None:
    good = make_source("good_feed", "https://feeds.test/good")
    bad = make_source("bad_feed", "https://feeds.test/bad")
    session = FakeSession(
        {
            good.url: FakeResponse(fixture_bytes("sample_rss.xml"), good.url),
            bad.url: requests.Timeout("request timed out"),
        }
    )

    result = collect_feeds(make_config((good, bad)), session=session, now=FIXED_NOW)

    assert len(result.articles) == 1
    assert result.fetched_sources == 1
    assert result.successful_sources == 1
    assert result.failed_sources == 1
    failed_report = next(report for report in result.reports if report.status == "failed")
    assert failed_report.source_id == "bad_feed"
    assert "request timed out" in (failed_report.error or "")


def test_http_error_is_recorded_as_source_failure() -> None:
    source = make_source("missing_feed", "https://feeds.test/missing")
    session = FakeSession(
        {source.url: FakeResponse(b"not found", source.url, status_code=404)}
    )

    result = collect_feeds(make_config((source,)), session=session, now=FIXED_NOW)

    assert result.failed_sources == 1
    assert "404 error" in (result.reports[0].error or "")


def test_request_uses_timeout_and_user_agent() -> None:
    source = make_source("sample_rss", "https://feeds.test/rss")
    session = FakeSession(
        {source.url: FakeResponse(fixture_bytes("sample_rss.xml"), source.url)}
    )

    collect_feeds(make_config((source,)), session=session, now=FIXED_NOW)

    call = session.calls[0]
    assert call["timeout"] == 5.0
    assert call["headers"]["User-Agent"] == "DailyTechBrief-Test/0.2.0"


def test_writes_raw_articles_and_source_report(tmp_path: Path) -> None:
    source = make_source("sample_rss", "https://feeds.test/rss")
    session = FakeSession(
        {source.url: FakeResponse(fixture_bytes("sample_rss.xml"), source.url)}
    )
    result = collect_feeds(make_config((source,)), session=session, now=FIXED_NOW)

    raw_path, report_path = write_collection_outputs(
        result,
        output_dir=tmp_path,
        project={"name": "Test Brief", "version": "0.2.0"},
    )

    raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    assert raw_data["article_count"] == 1
    assert raw_data["articles"][0]["source_tags"] == ["test"]
    assert report_data["summary"]["successful_sources"] == 1
    assert report_data["sources"][0]["feed_title"] == "Example RSS"
