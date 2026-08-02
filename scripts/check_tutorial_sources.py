from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collector import collect_feeds
from src.config_loader import load_project_config
from src.models import SourceReport


TUTORIAL_SOURCE_IDS = (
    "automation_panda",
    "pythontest_blog",
    "testdriven_io",
    "pybites_blog",
    "zyte_blog",
    "earthly_blog",
    "circleci_blog",
    "julia_evans_blog",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch the tutorial-oriented sources and report whether "
            "their feeds are usable by the current collector."
        )
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=PROJECT_ROOT / "config",
        help="Project configuration directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON instead of a table.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the JSON report to this path.",
    )
    return parser


def _report_to_dict(report: SourceReport) -> dict[str, Any]:
    return {
        "source_id": report.source_id,
        "source_name": report.source_name,
        "category": report.category,
        "status": report.status,
        "article_count": report.article_count,
        "http_status": report.http_status,
        "duration_seconds": report.duration_seconds,
        "feed_title": report.feed_title,
        "final_url": report.final_url,
        "warning": report.warning,
        "error": report.error,
    }


def _build_payload(
    reports: Sequence[SourceReport],
) -> dict[str, Any]:
    source_payload = [
        _report_to_dict(report)
        for report in reports
    ]

    return {
        "schema_version": 1,
        "summary": {
            "total_sources": len(reports),
            "successful_sources": sum(
                report.status == "success"
                for report in reports
            ),
            "warning_sources": sum(
                report.status == "warning"
                for report in reports
            ),
            "failed_sources": sum(
                report.status == "failed"
                for report in reports
            ),
            "article_count": sum(
                report.article_count
                for report in reports
            ),
        },
        "sources": source_payload,
    }


def _display_value(value: object | None) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def _print_table(payload: dict[str, Any]) -> None:
    rows = payload["sources"]
    headers = (
        "Source",
        "Status",
        "HTTP",
        "Articles",
        "Seconds",
        "Details",
    )

    table_rows: list[tuple[str, ...]] = []
    for row in rows:
        details = (
            row["error"]
            or row["warning"]
            or row["feed_title"]
            or ""
        )
        table_rows.append(
            (
                str(row["source_id"]),
                str(row["status"]).upper(),
                _display_value(row["http_status"]),
                str(row["article_count"]),
                str(row["duration_seconds"]),
                _display_value(details),
            )
        )

    widths = [
        max(
            len(headers[index]),
            *(
                len(row[index])
                for row in table_rows
            ),
        )
        for index in range(len(headers))
    ]

    def format_row(row: Sequence[str]) -> str:
        return " | ".join(
            value.ljust(widths[index])
            for index, value in enumerate(row)
        )

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in table_rows:
        print(format_row(row))

    summary = payload["summary"]
    print()
    print(
        "Summary: "
        f"{summary['successful_sources']} success, "
        f"{summary['warning_sources']} warning, "
        f"{summary['failed_sources']} failed, "
        f"{summary['article_count']} articles"
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
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


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    config = load_project_config(args.config_dir)
    sources_by_id = {
        source.id: source
        for source in config.sources
    }

    missing_ids = [
        source_id
        for source_id in TUTORIAL_SOURCE_IDS
        if source_id not in sources_by_id
    ]
    if missing_ids:
        print(
            "Missing tutorial sources: "
            + ", ".join(missing_ids),
            file=sys.stderr,
        )
        return 2

    disabled_ids = [
        source_id
        for source_id in TUTORIAL_SOURCE_IDS
        if not sources_by_id[source_id].enabled
    ]
    if disabled_ids:
        print(
            "Disabled tutorial sources: "
            + ", ".join(disabled_ids),
            file=sys.stderr,
        )
        return 2

    selected_sources = tuple(
        sources_by_id[source_id]
        for source_id in TUTORIAL_SOURCE_IDS
    )
    result = collect_feeds(
        config,
        sources=selected_sources,
    )
    payload = _build_payload(result.reports)

    if args.output is not None:
        _write_json(args.output, payload)

    if args.json:
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_table(payload)

    return (
        1
        if payload["summary"]["failed_sources"] > 0
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
