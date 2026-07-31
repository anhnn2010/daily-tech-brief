from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import requests

from src.config_loader import ProjectConfig
from src.models import Article, FeedFetchError, Source, SourceReport
from src.providers.feed import FeedProvider
from src.providers.html_index import HtmlIndexProvider
from src.providers.router import ProviderRouter


@dataclass(frozen=True)
class CollectionResult:
    started_at: str
    completed_at: str
    duration_seconds: float
    articles: tuple[Article, ...]
    reports: tuple[SourceReport, ...]

    @property
    def fetched_sources(self) -> int:
        return sum(
            report.status != "failed"
            for report in self.reports
        )

    @property
    def successful_sources(self) -> int:
        return sum(
            report.status == "success"
            for report in self.reports
        )

    @property
    def failed_sources(self) -> int:
        return sum(
            report.status == "failed"
            for report in self.reports
        )

    @property
    def warning_sources(self) -> int:
        return sum(
            report.status == "warning"
            for report in self.reports
        )

    def summary(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "total_sources": len(self.reports),
            "fetched_sources": self.fetched_sources,
            "successful_sources": self.successful_sources,
            "warning_sources": self.warning_sources,
            "failed_sources": self.failed_sources,
            "article_count": len(self.articles),
        }


def collect_feeds(
    config: ProjectConfig,
    sources: Iterable[Source] | None = None,
    session: requests.Session | None = None,
    now: datetime | None = None,
) -> CollectionResult:
    """Collect articles from every configured source provider."""

    selected_sources = (
        config.enabled_sources
        if sources is None
        else tuple(sources)
    )
    runtime = config.settings["runtime"]
    session = session or requests.Session()

    common_provider_options = {
        "session": session,
        "timeout_seconds": float(
            runtime["request_timeout_seconds"]
        ),
        "user_agent": str(runtime["user_agent"]),
        "max_summary_chars": int(
            runtime["max_summary_chars"]
        ),
    }
    provider = ProviderRouter(
        feed_provider=FeedProvider(
            **common_provider_options,
        ),
        html_index_provider=HtmlIndexProvider(
            **common_provider_options,
        ),
    )

    started = now or datetime.now(timezone.utc)
    total_started = perf_counter()
    articles: list[Article] = []
    reports: list[SourceReport] = []

    for source in selected_sources:
        source_started_at = datetime.now(timezone.utc)
        source_timer = perf_counter()

        try:
            source_articles, metadata = provider.fetch(
                source,
                fetched_at=started,
            )
            warning = metadata.get("warning")
            if not source_articles and not warning:
                warning = "Source returned no articles"

            status = "warning" if warning else "success"
            articles.extend(source_articles)
            report = SourceReport(
                source_id=source.id,
                source_name=source.name,
                category=source.category,
                url=source.url,
                status=status,
                started_at=_to_iso(source_started_at),
                completed_at=_to_iso(
                    datetime.now(timezone.utc)
                ),
                duration_seconds=round(
                    perf_counter() - source_timer,
                    3,
                ),
                article_count=len(source_articles),
                http_status=metadata.get("http_status"),
                final_url=metadata.get("final_url"),
                feed_title=metadata.get("feed_title"),
                warning=warning,
            )
        except FeedFetchError as exc:
            report = SourceReport(
                source_id=source.id,
                source_name=source.name,
                category=source.category,
                url=source.url,
                status="failed",
                started_at=_to_iso(source_started_at),
                completed_at=_to_iso(
                    datetime.now(timezone.utc)
                ),
                duration_seconds=round(
                    perf_counter() - source_timer,
                    3,
                ),
                article_count=0,
                error=str(exc),
            )

        reports.append(report)

    completed = datetime.now(timezone.utc)
    return CollectionResult(
        started_at=_to_iso(started),
        completed_at=_to_iso(completed),
        duration_seconds=round(
            perf_counter() - total_started,
            3,
        ),
        articles=tuple(articles),
        reports=tuple(reports),
    )


def write_collection_outputs(
    result: CollectionResult,
    output_dir: Path,
    project: dict[str, Any],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_articles_path = output_dir / "raw_articles.json"
    source_report_path = output_dir / "source_report.json"

    articles_payload = {
        "schema_version": 1,
        "project": project,
        "generated_at": result.completed_at,
        "article_count": len(result.articles),
        "articles": [
            _public_article_dict(article)
            for article in result.articles
        ],
    }
    report_payload = {
        "schema_version": 1,
        "project": project,
        "generated_at": result.completed_at,
        "summary": result.summary(),
        "sources": [
            report.to_dict()
            for report in result.reports
        ],
    }

    _write_json_atomic(
        raw_articles_path,
        articles_payload,
    )
    _write_json_atomic(
        source_report_path,
        report_payload,
    )
    return raw_articles_path, source_report_path


def _public_article_dict(
    article: Article,
) -> dict[str, Any]:
    """Serialize collection metadata without private full article content."""

    data = article.to_dict()
    data["content_html"] = ""
    data["content_text"] = ""
    data["content_status"] = "not_requested"
    return data


def _write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )
    temporary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _to_iso(value: datetime) -> str:
    normalized = (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
    )
    return normalized.isoformat().replace(
        "+00:00",
        "Z",
    )
