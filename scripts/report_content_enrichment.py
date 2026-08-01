from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class ContentReportError(RuntimeError):
    """Raised when content enrichment report data is invalid."""


@dataclass(frozen=True)
class ContentRecord:
    index: int
    source_id: str
    title: str
    url: str
    status: str
    http_status: int | None
    content_type: str | None
    selector: str | None
    word_count: int
    duration_seconds: float
    error: str | None
    content_origin: str

    @property
    def is_problem(self) -> bool:
        return self.status != "extracted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "status": self.status,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "selector": self.selector,
            "word_count": self.word_count,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "content_origin": self.content_origin,
        }


@dataclass(frozen=True)
class ContentReport:
    input_path: Path
    requested: int
    extracted: int
    summary_fallback: int
    fetch_failed: int
    records: tuple[ContentRecord, ...]

    @property
    def extraction_rate(self) -> float:
        if self.requested == 0:
            return 0.0
        return self.extracted / self.requested

    @property
    def origin_counts(self) -> dict[str, int]:
        counts = {
            origin: 0
            for origin in _SUPPORTED_CONTENT_ORIGINS
        }
        for record in self.records:
            counts[record.content_origin] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": str(self.input_path),
            "requested": self.requested,
            "extracted": self.extracted,
            "summary_fallback": self.summary_fallback,
            "fetch_failed": self.fetch_failed,
            "extraction_rate": round(
                self.extraction_rate,
                4,
            ),
            "content_origins": self.origin_counts,
            "records": [
                record.to_dict()
                for record in self.records
            ],
        }


_SUPPORTED_STATUSES = {
    "extracted",
    "summary_fallback",
    "fetch_failed",
}

_SUPPORTED_CONTENT_ORIGINS = {
    "feed",
    "curated",
    "web",
    "summary",
    "none",
    "unknown",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Show full-content extraction results for the "
            "generated Daily Tech Brief EPUB."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("output/ranked_articles.json"),
        help="Path to ranked_articles.json.",
    )
    parser.add_argument(
        "--problems-only",
        action="store_true",
        help=(
            "Show only summary fallbacks and fetch failures."
        ),
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON.",
    )
    output_group.add_argument(
        "--markdown",
        action="store_true",
        help=(
            "Print a Markdown report suitable for "
            "GitHub Actions Job Summary."
        ),
    )
    return parser


def load_content_report(
    path: str | Path,
) -> ContentReport:
    report_path = Path(path)
    payload = _read_json_object(report_path)
    enrichment = _extract_enrichment(payload)

    requested = _require_non_negative_integer(
        enrichment,
        "requested_articles",
    )
    extracted = _require_non_negative_integer(
        enrichment,
        "extracted_articles",
    )
    summary_fallback = _require_non_negative_integer(
        enrichment,
        "summary_fallback_articles",
    )
    fetch_failed = _require_non_negative_integer(
        enrichment,
        "failed_articles",
    )

    if (
        extracted
        + summary_fallback
        + fetch_failed
        != requested
    ):
        raise ContentReportError(
            "Content enrichment counts do not add up "
            "to requested_articles"
        )

    raw_records = enrichment.get("records")
    if not isinstance(raw_records, list):
        raise ContentReportError(
            "content_enrichment.records must be a list"
        )

    if len(raw_records) != requested:
        raise ContentReportError(
            "content_enrichment.records count does not match "
            "requested_articles"
        )

    records = tuple(
        _parse_record(
            item,
            index=index,
        )
        for index, item in enumerate(
            raw_records,
            start=1,
        )
    )

    actual_counts = {
        "extracted": sum(
            record.status == "extracted"
            for record in records
        ),
        "summary_fallback": sum(
            record.status == "summary_fallback"
            for record in records
        ),
        "fetch_failed": sum(
            record.status == "fetch_failed"
            for record in records
        ),
    }

    expected_counts = {
        "extracted": extracted,
        "summary_fallback": summary_fallback,
        "fetch_failed": fetch_failed,
    }

    if actual_counts != expected_counts:
        raise ContentReportError(
            "Content enrichment record statuses do not "
            "match summary counts"
        )

    return ContentReport(
        input_path=report_path,
        requested=requested,
        extracted=extracted,
        summary_fallback=summary_fallback,
        fetch_failed=fetch_failed,
        records=records,
    )


def render_text_report(
    report: ContentReport,
    *,
    problems_only: bool = False,
) -> str:
    records: Iterable[ContentRecord] = report.records
    if problems_only:
        records = (
            record
            for record in records
            if record.is_problem
        )

    selected_records = tuple(records)
    origins = report.origin_counts
    lines = [
        "Full-content EPUB report",
        f"- Input:             {report.input_path}",
        f"- Requested:         {report.requested}",
        f"- Extracted:         {report.extracted}",
        f"- Summary fallback:  {report.summary_fallback}",
        f"- Fetch failed:      {report.fetch_failed}",
        (
            "- Extraction rate:  "
            f"{report.extraction_rate * 100:.1f}%"
        ),
        f"- From feed:         {origins['feed']}",
        f"- From web:          {origins['web']}",
        f"- Curated lessons:   {origins['curated']}",
        f"- Summary only:      {origins['summary']}",
        f"- No readable text:  {origins['none']}",
        "",
    ]

    if origins["unknown"]:
        lines.insert(
            -1,
            f"- Unknown origin:    {origins['unknown']}",
        )

    if not selected_records:
        lines.append(
            "No matching article records."
            if problems_only
            else "No article records."
        )
        return "\n".join(lines)

    for record in selected_records:
        lines.extend(
            _render_record(record)
        )

    return "\n".join(lines).rstrip()


def render_markdown_report(
    report: ContentReport,
    *,
    problems_only: bool = False,
) -> str:
    """Render a compact report for GitHub Actions Job Summary."""

    origins = report.origin_counts
    records = tuple(
        record
        for record in report.records
        if not problems_only or record.is_problem
    )

    lines = [
        "## Full-content EPUB",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Requested articles | {report.requested} |",
        f"| Full content extracted | {report.extracted} |",
        f"| Summary fallbacks | {report.summary_fallback} |",
        f"| Fetch failures | {report.fetch_failed} |",
        (
            "| Extraction rate | "
            f"{report.extraction_rate * 100:.1f}% |"
        ),
        "",
        "### Content origin",
        "",
        "| Origin | Articles |",
        "|---|---:|",
        f"| RSS or Atom feed | {origins['feed']} |",
        f"| Web page extraction | {origins['web']} |",
        f"| Curated learning | {origins['curated']} |",
        f"| Summary only | {origins['summary']} |",
        f"| No readable text | {origins['none']} |",
    ]

    if origins["unknown"]:
        lines.append(
            f"| Unknown | {origins['unknown']} |"
        )

    section_title = (
        "### Articles using fallback"
        if problems_only
        else "### Article details"
    )
    lines.extend(
        [
            "",
            section_title,
            "",
        ]
    )

    if not records:
        lines.append(
            "No articles require fallback."
            if problems_only
            else "No article records."
        )
        return "\n".join(lines)

    lines.extend(
        [
            (
                "| # | Status | Origin | Source | Article | "
                "Words | HTTP | Detail |"
            ),
            "|---:|---|---|---|---|---:|---:|---|",
        ]
    )

    for record in records:
        status = {
            "extracted": "Extracted",
            "summary_fallback": "Fallback",
            "fetch_failed": "Failed",
        }[record.status]
        http_status = (
            str(record.http_status)
            if record.http_status is not None
            else "—"
        )
        detail = record.error or record.selector or "—"
        title = _markdown_link(
            record.title,
            record.url,
        )
        lines.append(
            "| "
            f"{record.index} | "
            f"{status} | "
            f"{_escape_markdown_table(record.content_origin)} | "
            f"{_escape_markdown_table(record.source_id)} | "
            f"{title} | "
            f"{record.word_count} | "
            f"{http_status} | "
            f"{_escape_markdown_table(detail)} |"
        )

    return "\n".join(lines)


def _markdown_link(
    label: str,
    url: str,
) -> str:
    escaped_label = _escape_markdown_table(label).replace(
        "]",
        "\\]",
    )
    escaped_url = url.replace(
        ")",
        "%29",
    )
    return f"[{escaped_label}]({escaped_url})"


def _escape_markdown_table(
    value: str,
) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _render_record(
    record: ContentRecord,
) -> list[str]:
    status_label = {
        "extracted": "EXTRACTED",
        "summary_fallback": "FALLBACK",
        "fetch_failed": "FAILED",
    }[record.status]

    http_status = (
        str(record.http_status)
        if record.http_status is not None
        else "-"
    )
    selector = record.selector or "-"
    content_type = record.content_type or "-"
    error = record.error or "-"

    return [
        (
            f"[{record.index:02d}] {status_label} "
            f"| words={record.word_count} "
            f"| origin={record.content_origin} "
            f"| time={record.duration_seconds:.3f}s "
            f"| http={http_status}"
        ),
        f"     {record.title}",
        f"     source:   {record.source_id}",
        f"     selector: {selector}",
        f"     type:     {content_type}",
        f"     error:    {error}",
        f"     url:      {record.url}",
        "",
    ]


def _extract_enrichment(
    payload: dict[str, Any],
) -> dict[str, Any]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ContentReportError(
            "ranked_articles.json summary must be an object"
        )

    nested_processing = summary.get("processing")
    if nested_processing is None:
        processing = summary
    elif isinstance(nested_processing, dict):
        processing = nested_processing
    else:
        raise ContentReportError(
            "ranked_articles.json summary.processing "
            "must be an object"
        )

    enrichment = processing.get("content_enrichment")
    if not isinstance(enrichment, dict):
        raise ContentReportError(
            "ranked_articles.json does not contain "
            "content enrichment data"
        )

    return enrichment


def _parse_record(
    raw: Any,
    *,
    index: int,
) -> ContentRecord:
    if not isinstance(raw, dict):
        raise ContentReportError(
            f"content_enrichment.records[{index - 1}] "
            "must be an object"
        )

    status = _require_non_empty_string(
        raw.get("status"),
        field=(
            f"content_enrichment.records[{index - 1}].status"
        ),
    )
    if status not in _SUPPORTED_STATUSES:
        raise ContentReportError(
            f"Unsupported content status: {status}"
        )

    return ContentRecord(
        index=index,
        source_id=_require_non_empty_string(
            raw.get("source_id"),
            field=(
                f"content_enrichment.records[{index - 1}]"
                ".source_id"
            ),
        ),
        title=_require_non_empty_string(
            raw.get("title"),
            field=(
                f"content_enrichment.records[{index - 1}]"
                ".title"
            ),
        ),
        url=_require_non_empty_string(
            raw.get("url"),
            field=(
                f"content_enrichment.records[{index - 1}]"
                ".url"
            ),
        ),
        status=status,
        http_status=_optional_integer(
            raw.get("http_status"),
            field=(
                f"content_enrichment.records[{index - 1}]"
                ".http_status"
            ),
        ),
        content_type=_optional_string(
            raw.get("content_type"),
        ),
        selector=_optional_string(
            raw.get("selector"),
        ),
        word_count=_require_non_negative_value(
            raw.get("word_count"),
            field=(
                f"content_enrichment.records[{index - 1}]"
                ".word_count"
            ),
            expected_type=int,
        ),
        duration_seconds=float(
            _require_non_negative_value(
                raw.get("duration_seconds"),
                field=(
                    f"content_enrichment.records[{index - 1}]"
                    ".duration_seconds"
                ),
                expected_type=(int, float),
            )
        ),
        error=_optional_string(
            raw.get("error"),
        ),
        content_origin=_parse_content_origin(
            raw.get("content_origin"),
            status=status,
            http_status=_optional_integer(
                raw.get("http_status"),
                field=(
                    f"content_enrichment.records[{index - 1}]"
                    ".http_status"
                ),
            ),
        ),
    )



def _parse_content_origin(
    value: Any,
    *,
    status: str,
    http_status: int | None,
) -> str:
    if value is None:
        if status == "summary_fallback":
            return "summary"
        if status == "fetch_failed":
            return "none"
        if http_status is not None:
            return "web"
        return "unknown"

    if not isinstance(value, str):
        raise ContentReportError(
            "content_origin must be a string or null"
        )

    normalized = value.strip().lower()
    if normalized not in _SUPPORTED_CONTENT_ORIGINS:
        raise ContentReportError(
            f"Unsupported content origin: {normalized}"
        )

    return normalized


def _read_json_object(
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        raise ContentReportError(
            f"Input file not found: {path}"
        )

    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except OSError as exc:
        raise ContentReportError(
            f"Unable to read {path}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ContentReportError(
            f"{path} contains invalid JSON: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise ContentReportError(
            f"{path} must contain a JSON object"
        )

    return value


def _require_non_negative_integer(
    data: dict[str, Any],
    field: str,
) -> int:
    value = data.get(field)
    return int(
        _require_non_negative_value(
            value,
            field=f"content_enrichment.{field}",
            expected_type=int,
        )
    )


def _require_non_negative_value(
    value: Any,
    *,
    field: str,
    expected_type: type | tuple[type, ...],
) -> int | float:
    if (
        not isinstance(value, expected_type)
        or isinstance(value, bool)
        or value < 0
    ):
        raise ContentReportError(
            f"{field} must be a non-negative number"
        )
    return value


def _require_non_empty_string(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContentReportError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _optional_string(
    value: Any,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContentReportError(
            "Optional report text must be a string"
        )
    normalized = value.strip()
    return normalized or None


def _optional_integer(
    value: Any,
    *,
    field: str,
) -> int | None:
    if value is None:
        return None
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
    ):
        raise ContentReportError(
            f"{field} must be an integer or null"
        )
    return value


def main(
    argv: list[str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)

    try:
        report = load_content_report(args.input)
    except ContentReportError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": str(exc),
                    },
                    indent=2,
                )
            )
        else:
            print(
                f"Content report failed: {exc}",
                file=sys.stderr,
            )
        return 1

    if args.json:
        payload = report.to_dict()
        if args.problems_only:
            payload["records"] = [
                record.to_dict()
                for record in report.records
                if record.is_problem
            ]
        payload["status"] = "passed"
        print(
            json.dumps(
                payload,
                indent=2,
            )
        )
    elif args.markdown:
        print(
            render_markdown_report(
                report,
                problems_only=args.problems_only,
            )
        )
    else:
        print(
            render_text_report(
                report,
                problems_only=args.problems_only,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
