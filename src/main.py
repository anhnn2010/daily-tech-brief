from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from src.collector import collect_feeds, write_collection_outputs
from src.config_loader import ProjectConfig, load_project_config
from src.content.enricher import enrich_selected_articles
from src.filters.deduplicate import deduplicate_articles
from src.filters.time_filter import filter_articles_by_time
from src.learning.pipeline import prepare_learning_edition
from src.models import Article, ConfigError, Source
from src.publishing.site_builder import build_static_site
from src.ranking.rule_based import RankedArticle, rank_articles
from src.ranking.selection import select_articles_by_category_quota
from src.renderers.epub import render_epub_digest
from src.renderers.html import render_html_digest
from src.renderers.markdown import render_markdown_digest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and rank RSS and Atom feeds for Daily Tech Brief."
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config"),
        help="Directory containing sources.yml, profile.yml, and settings.yml",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Override runtime.output_dir from settings.yml",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="SOURCE_ID",
        help="Fetch only this enabled source; may be specified multiple times",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate configuration without fetching feeds",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the validation or execution summary as JSON",
    )
    return parser


def create_config_summary(config: ProjectConfig) -> dict[str, object]:
    categories: dict[str, list[dict[str, object]]] = defaultdict(list)
    for source in config.enabled_sources:
        categories[source.category].append(
            {
                "id": source.id,
                "name": source.name,
                "priority": source.priority,
                "cadence": source.cadence,
                "format": source.format,
            }
        )

    for category_sources in categories.values():
        category_sources.sort(
            key=lambda source: (-int(source["priority"]), str(source["name"]))
        )

    return {
        "project": config.settings["project"],
        "total_sources": len(config.sources),
        "enabled_sources": len(config.enabled_sources),
        "categories": dict(sorted(categories.items())),
    }


def print_config_summary(summary: dict[str, object]) -> None:
    project = summary["project"]
    assert isinstance(project, dict)

    print(f"{project['name']} v{project['version']}")
    print(f"Configured sources: {summary['total_sources']}")
    print(f"Enabled sources:    {summary['enabled_sources']}")

    categories = summary["categories"]
    assert isinstance(categories, dict)
    for category, sources in categories.items():
        print(f"\n{category}:")
        for source in sources:
            print(
                f"  - {source['name']} "
                f"(priority={source['priority']}, cadence={source['cadence']}, "
                f"format={source['format']})"
            )


def _select_sources(config: ProjectConfig, source_ids: list[str]) -> tuple[Source, ...]:
    if not source_ids:
        return config.enabled_sources

    enabled_by_id = {source.id: source for source in config.enabled_sources}
    unknown = sorted(set(source_ids) - enabled_by_id.keys())
    if unknown:
        raise ConfigError(
            "Unknown or disabled source ids: " + ", ".join(unknown)
        )
    return tuple(enabled_by_id[source_id] for source_id in dict.fromkeys(source_ids))


def _strip_article_content(
    article: Article,
) -> Article:
    """Return a public-safe article without full body content."""

    if (
        not article.content_html
        and not article.content_text
        and article.content_status == "not_requested"
    ):
        return article

    return replace(
        article,
        content_html="",
        content_text="",
        content_status="not_requested",
    )


def _public_ranked_articles(
    ranked_articles: tuple[RankedArticle, ...],
) -> tuple[RankedArticle, ...]:
    """Remove private EPUB content from public render and JSON payloads."""

    return tuple(
        replace(
            ranked_article,
            article=_strip_article_content(
                ranked_article.article
            ),
        )
        for ranked_article in ranked_articles
    )


def _enrich_ranked_articles_for_epub(
    ranked_articles: tuple[RankedArticle, ...],
    runtime: dict[str, Any],
) -> tuple[tuple[RankedArticle, ...], dict[str, Any]]:
    """Fetch full text for EPUB without changing public digest payloads."""

    if not ranked_articles:
        return (), {
            "requested_articles": 0,
            "extracted_articles": 0,
            "summary_fallback_articles": 0,
            "failed_articles": 0,
            "content_origins": {
                "feed": 0,
                "web": 0,
                "curated": 0,
                "summary": 0,
                "none": 0,
                "unknown": 0,
            },
            "records": [],
        }

    result = enrich_selected_articles(
        (ranked.article for ranked in ranked_articles),
        timeout_seconds=float(
            runtime.get("content_timeout_seconds", 15.0)
        ),
        maximum_download_bytes=int(
            runtime.get(
                "content_max_download_bytes",
                5_000_000,
            )
        ),
    )

    enriched_ranked_articles = tuple(
        replace(
            ranked_article,
            article=enriched_article,
        )
        for ranked_article, enriched_article in zip(
            ranked_articles,
            result.articles,
            strict=True,
        )
    )

    return enriched_ranked_articles, result.summary()


def _process_and_write_ranked_articles(
    config: ProjectConfig,
    articles: tuple[Article, ...],
    output_dir: Path,
    *,
    config_dir: Path | None = None,
    archive_root: Path | None = None,
    enable_learning: bool = False,
    now: datetime | None = None,
) -> tuple[Path, dict[str, Any]]:
    runtime = config.settings["runtime"]
    evaluated_at = _normalize_datetime(now or datetime.now(timezone.utc))

    time_result = filter_articles_by_time(
        articles,
        lookback_hours=float(runtime["lookback_hours"]),
        now=evaluated_at,
    )
    deduplication_result = deduplicate_articles(time_result.articles)
    ranking_result = rank_articles(
        deduplication_result.articles,
        config.profile,
        now=evaluated_at,
    )

    max_articles = int(runtime["max_articles"])
    learning_plan = None
    news_capacity = max_articles

    if enable_learning:
        resolved_config_dir = config_dir or Path("config")
        resolved_archive_root = archive_root or (
            Path(str(runtime.get("site_dir", "site")))
            / "archive"
        )
        learning_plan = prepare_learning_edition(
            profile=config.profile,
            config_dir=resolved_config_dir,
            archive_root=resolved_archive_root,
            max_articles=max_articles,
            now=evaluated_at,
        )
        news_capacity = learning_plan.news_capacity

    selection_result = select_articles_by_category_quota(
        ranking_result.articles,
        config.profile,
        max_articles=news_capacity,
    )
    news_articles = selection_result.articles
    selected_articles = (
        learning_plan.combine(news_articles)
        if learning_plan is not None
        else news_articles
    )
    ranked_articles_path = output_dir / "ranked_articles.json"

    processing_summary: dict[str, Any] = {
        "evaluated_at": ranking_result.evaluated_at,
        "lookback_hours": float(runtime["lookback_hours"]),
        "max_articles": max_articles,
        "time_filter": time_result.summary(),
        "deduplication": deduplication_result.summary(),
        "ranking": ranking_result.summary(),
        "selection": selection_result.summary(),
        "selected_articles": len(selected_articles),
    }

    if learning_plan is not None:
        processing_summary["selected_news_articles"] = len(
            news_articles
        )
        processing_summary["selected_learning_articles"] = (
            learning_plan.selected_count
        )
        processing_summary["learning"] = learning_plan.summary(
            news_article_count=len(news_articles),
            final_article_count=len(selected_articles),
        )
    features = config.settings["features"]
    rendering_summary: dict[str, dict[str, Any]] = {}
    public_articles = _public_ranked_articles(
        selected_articles
    )
    epub_articles = selected_articles

    if (
        features.get("render_epub", False)
        and features.get("full_content_epub", False)
    ):
        (
            epub_articles,
            content_enrichment_summary,
        ) = _enrich_ranked_articles_for_epub(
            selected_articles,
            runtime,
        )
        processing_summary["content_enrichment"] = (
            content_enrichment_summary
        )

    if features.get("render_markdown", False):
        markdown_path = output_dir / "digest.md"
        markdown_content = render_markdown_digest(
            public_articles,
            config.profile,
            generated_at=ranking_result.evaluated_at,
            project_name=str(config.settings["project"]["name"]),
        )
        _write_text_atomic(markdown_path, markdown_content)
        rendering_summary["markdown"] = {
            "enabled": True,
            "path": str(markdown_path),
            "article_count": len(selected_articles),
        }
    else:
        rendering_summary["markdown"] = {"enabled": False}

    if features.get("render_html", False):
        html_path = output_dir / "digest.html"
        html_content = render_html_digest(
            public_articles,
            config.profile,
            generated_at=ranking_result.evaluated_at,
            project_name=str(config.settings["project"]["name"]),
            epub_href=(
                (
                    "digest-full.epub"
                    if features.get("full_content_epub", False)
                    else "digest.epub"
                )
                if features.get("render_epub", False)
                else None
            ),
        )
        _write_text_atomic(html_path, html_content)
        rendering_summary["html"] = {
            "enabled": True,
            "path": str(html_path),
            "article_count": len(selected_articles),
        }
    else:
        rendering_summary["html"] = {"enabled": False}

    if "render_epub" in features:
        if features.get("render_epub", False):
            public_epub_path = output_dir / "digest.epub"
            public_epub_content = render_epub_digest(
                public_articles,
                config.profile,
                generated_at=ranking_result.evaluated_at,
                project_name=str(config.settings["project"]["name"]),
            )
            _write_bytes_atomic(
                public_epub_path,
                public_epub_content,
            )
            rendering_summary["epub"] = {
                "enabled": True,
                "path": str(public_epub_path),
                "article_count": len(selected_articles),
                "size_bytes": len(public_epub_content),
                "content_mode": "summary",
                "published_to_site": True,
            }

            if features.get("full_content_epub", False):
                full_epub_path = output_dir / "digest-full.epub"
                full_epub_content = render_epub_digest(
                    epub_articles,
                    config.profile,
                    generated_at=ranking_result.evaluated_at,
                    project_name=str(
                        config.settings["project"]["name"]
                    ),
                )
                _write_bytes_atomic(
                    full_epub_path,
                    full_epub_content,
                )
                rendering_summary["full_epub"] = {
                    "enabled": True,
                    "path": str(full_epub_path),
                    "article_count": len(selected_articles),
                    "size_bytes": len(full_epub_content),
                    "content_mode": "full",
                    "published_to_site": True,
                }
            else:
                rendering_summary["full_epub"] = {
                    "enabled": False
                }
        else:
            rendering_summary["epub"] = {"enabled": False}
            rendering_summary["full_epub"] = {
                "enabled": False
            }

    processing_summary["rendering"] = rendering_summary
    payload = {
        "schema_version": 1,
        "project": config.settings["project"],
        "generated_at": ranking_result.evaluated_at,
        "summary": processing_summary,
        "article_count": len(selected_articles),
        "articles": [
            article.to_dict()
            for article in public_articles
        ],
    }
    if learning_plan is not None:
        payload["learning"] = learning_plan.payload()
    _write_json_atomic(ranked_articles_path, payload)

    return ranked_articles_path, processing_summary


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_bytes(content)
    temporary_path.replace(path)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _print_execution_summary(summary: dict[str, Any]) -> None:
    print(f"Fetched sources: {summary['fetched_sources']}/{summary['total_sources']}")
    print(f"Warning sources: {summary['warning_sources']}")
    print(f"Failed sources:  {summary['failed_sources']}")
    print(f"Fetched articles: {summary['article_count']}")

    processing = summary.get("processing")
    if isinstance(processing, dict):
        time_filter = processing["time_filter"]
        deduplication = processing["deduplication"]
        print(f"Articles within lookback: {time_filter['kept_articles']}")
        print(f"Unique articles:          {deduplication['unique_articles']}")
        print(f"Selected articles:        {processing['selected_articles']}")

        learning = processing.get("learning")
        if isinstance(learning, dict):
            print(
                "Selected news articles:   "
                f"{processing['selected_news_articles']}"
            )
            print(
                "Selected learning items:  "
                f"{processing['selected_learning_articles']}"
            )

            lesson_ids = learning.get(
                "selected_lesson_ids",
                [],
            )
            if isinstance(lesson_ids, list) and lesson_ids:
                print(
                    "Learning lesson IDs:     "
                    + ", ".join(str(item) for item in lesson_ids)
                )

        enrichment = processing.get("content_enrichment")
        if isinstance(enrichment, dict):
            print(
                "Full content extracted:  "
                f"{enrichment['extracted_articles']}/"
                f"{enrichment['requested_articles']}"
            )
            print(
                "Summary fallbacks:       "
                f"{enrichment['summary_fallback_articles']}"
            )
            print(
                "Content fetch failures:  "
                f"{enrichment['failed_articles']}"
            )

            content_origins = enrichment.get(
                "content_origins"
            )
            if isinstance(content_origins, dict):
                origin_order = (
                    "feed",
                    "web",
                    "curated",
                    "summary",
                    "none",
                )
                origin_parts = [
                    f"{origin}={int(content_origins.get(origin, 0))}"
                    for origin in origin_order
                ]

                unknown_count = int(
                    content_origins.get("unknown", 0)
                )
                if unknown_count > 0:
                    origin_parts.append(
                        f"unknown={unknown_count}"
                    )

                print(
                    "Content origins:         "
                    + ", ".join(origin_parts)
                )

        selection = processing.get("selection")
        if isinstance(selection, dict):
            print(
                "Selected within quota:    "
                f"{selection['selected_within_quota']}"
            )
            print(
                "Selected from overflow:   "
                f"{selection['selected_from_overflow']}"
            )

            category_counts = selection.get("category_counts", {})
            if isinstance(category_counts, dict):
                selected_categories = [
                    f"{category}={count}"
                    for category, count in sorted(category_counts.items())
                    if int(count) > 0
                ]
                if selected_categories:
                    print(
                        "Selected by category:    "
                        + ", ".join(selected_categories)
                    )

    print("\nOutput:")
    for path in summary["output_paths"]:
        print(f"- {path}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_project_config(args.config_dir)
        selected_sources = _select_sources(config, args.source)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.validate_only:
        summary = create_config_summary(config)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print_config_summary(summary)
        return 0

    if not config.settings["features"]["fetch_feeds"]:
        print(
            "Configuration error: features.fetch_feeds is disabled",
            file=sys.stderr,
        )
        return 2

    result = collect_feeds(config, sources=selected_sources)
    runtime = config.settings["runtime"]
    output_dir = args.output_dir or Path(runtime["output_dir"])
    site_dir = Path(str(runtime.get("site_dir", "site")))
    raw_path, report_path = write_collection_outputs(
        result=result,
        output_dir=output_dir,
        project=config.settings["project"],
    )

    summary = result.summary()
    output_paths = [str(raw_path), str(report_path)]

    if config.settings["features"]["ranking"]:
        try:
            ranked_path, processing_summary = _process_and_write_ranked_articles(
                config=config,
                articles=result.articles,
                output_dir=output_dir,
                config_dir=args.config_dir,
                archive_root=site_dir / "archive",
                enable_learning=not bool(args.source),
            )
        except ValueError as exc:
            print(f"Processing error: {exc}", file=sys.stderr)
            return 2

        summary["processing"] = processing_summary
        output_paths.append(str(ranked_path))

        rendering = processing_summary.get("rendering", {})
        if isinstance(rendering, dict):
            for renderer_name in (
                "markdown",
                "html",
                "epub",
                "full_epub",
            ):
                renderer_summary = rendering.get(renderer_name)
                if (
                    isinstance(renderer_summary, dict)
                    and renderer_summary.get("enabled")
                    and isinstance(renderer_summary.get("path"), str)
                ):
                    output_paths.append(renderer_summary["path"])

    if config.settings["features"].get("build_site", False):
        if not config.settings["features"].get("ranking", False):
            print(
                "Publishing error: features.build_site requires ranking",
                file=sys.stderr,
            )
            return 2

        timezone_name = str(
            config.profile["profile"].get("timezone", "UTC")
        )

        try:
            site_result = build_static_site(
                output_dir=output_dir,
                site_dir=site_dir,
                timezone_name=timezone_name,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Publishing error: {exc}", file=sys.stderr)
            return 2

        summary["publishing"] = {
            "site": site_result.summary(),
        }
        output_paths.extend(
            [
                str(site_result.index_path),
                str(site_result.archive_index_path),
                str(site_result.archive_manifest_path),
                str(site_result.site_dir / "site.json"),
            ]
        )

    summary["output_paths"] = output_paths

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        _print_execution_summary(summary)

        failed = [report for report in result.reports if report.status == "failed"]
        if failed:
            print("\nFailed source details:")
            for report in failed:
                print(f"- {report.source_id}: {report.error}")

    fail_on_source_error = config.settings["runtime"]["fail_on_source_error"]
    if result.failed_sources == len(result.reports):
        return 1
    if fail_on_source_error and result.failed_sources:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
