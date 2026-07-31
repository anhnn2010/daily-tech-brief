from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class VerificationError(RuntimeError):
    """Raised when generated digest artifacts violate the output contract."""


@dataclass(frozen=True)
class VerificationResult:
    total_articles: int
    learning_articles: int
    lesson_ids: tuple[str, ...]
    content_requested: int
    content_extracted: int
    content_fallback: int
    content_failed: int
    archive_file: Path
    checked_epub_copies: tuple[Path, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify Technical Learning and full-text EPUB output after "
            "a complete Daily Tech Brief run."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Generated output directory.",
    )
    parser.add_argument(
        "--site-dir",
        type=Path,
        default=Path("site"),
        help="Generated static site directory.",
    )
    parser.add_argument(
        "--expected-total",
        type=int,
        default=12,
        help="Expected total number of ranked articles.",
    )
    parser.add_argument(
        "--expected-learning",
        type=int,
        default=1,
        help="Expected number of Technical Learning articles.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the verification result as JSON.",
    )
    return parser


def verify_technical_learning_output(
    *,
    output_dir: Path,
    site_dir: Path,
    expected_total: int,
    expected_learning: int,
) -> VerificationResult:
    _validate_expected_count(
        expected_total,
        field="expected_total",
    )
    _validate_expected_count(
        expected_learning,
        field="expected_learning",
    )

    if expected_learning > expected_total:
        raise VerificationError(
            "expected_learning cannot exceed expected_total"
        )

    ranked_path = output_dir / "ranked_articles.json"
    markdown_path = output_dir / "digest.md"
    html_path = output_dir / "digest.html"
    epub_path = output_dir / "digest.epub"

    payload = _read_json_object(ranked_path)
    articles = payload.get("articles")

    if not isinstance(articles, list):
        raise VerificationError(
            f"{ranked_path} must contain an articles list"
        )

    article_count = payload.get("article_count")
    if article_count != len(articles):
        raise VerificationError(
            "ranked_articles.json article_count does not match "
            "the articles list"
        )

    if article_count != expected_total:
        raise VerificationError(
            f"Expected {expected_total} total articles, "
            f"found {article_count}"
        )

    _verify_public_articles_are_summary_only(
        articles,
        source=ranked_path,
    )
    enrichment = _extract_content_enrichment(
        payload,
        expected_total=expected_total,
    )

    learning_articles = [
        article
        for article in articles
        if isinstance(article, dict)
        and article.get("source_id") == "technical_learning"
    ]

    if len(learning_articles) != expected_learning:
        raise VerificationError(
            f"Expected {expected_learning} learning articles, "
            f"found {len(learning_articles)}"
        )

    lesson_ids = _extract_learning_article_ids(
        learning_articles
    )
    metadata_lesson_ids = _extract_payload_lesson_ids(
        payload
    )

    if tuple(metadata_lesson_ids) != tuple(lesson_ids):
        raise VerificationError(
            "Learning lesson IDs in metadata do not match "
            "the learning articles"
        )

    for article in learning_articles:
        if article.get("category") != "technical_learning":
            raise VerificationError(
                "Every learning article must use category "
                "'technical_learning'"
            )

    learning_titles = tuple(
        _require_non_empty_string(
            article.get("title"),
            field="learning article title",
        )
        for article in learning_articles
    )

    markdown = _read_text(markdown_path)
    html = _read_text(html_path)

    if expected_learning:
        _require_contains(
            markdown,
            "## Technical Learning",
            source=markdown_path,
        )
        _require_contains(
            html,
            'id="technical-learning"',
            source=html_path,
        )

        for title in learning_titles:
            _require_contains(
                markdown,
                title,
                source=markdown_path,
            )
            _require_contains(
                html,
                title,
                source=html_path,
            )

    _require_contains(
        html,
        'href="digest.epub"',
        source=html_path,
    )

    _verify_epub(
        epub_path,
        learning_titles=learning_titles,
        require_learning=bool(expected_learning),
        expected_articles=expected_total,
        expected_full_content=enrichment["extracted_articles"],
    )

    site_index = site_dir / "index.html"
    site_html = _read_text(site_index)
    if expected_learning:
        _require_contains(
            site_html,
            'id="technical-learning"',
            source=site_index,
        )

    checked_epub_copies = _verify_epub_copies(
        source_epub=epub_path,
        site_dir=site_dir,
    )

    archive_file = _find_latest_archive_payload(site_dir)
    archive_payload = _read_json_object(archive_file)
    archive_lesson_ids = _extract_payload_lesson_ids(
        archive_payload
    )

    if tuple(archive_lesson_ids) != tuple(lesson_ids):
        raise VerificationError(
            f"{archive_file} contains different learning "
            "lesson IDs"
        )

    return VerificationResult(
        total_articles=article_count,
        learning_articles=len(learning_articles),
        lesson_ids=tuple(lesson_ids),
        content_requested=enrichment["requested_articles"],
        content_extracted=enrichment["extracted_articles"],
        content_fallback=enrichment["summary_fallback_articles"],
        content_failed=enrichment["failed_articles"],
        archive_file=archive_file,
        checked_epub_copies=checked_epub_copies,
    )


def _extract_content_enrichment(
    payload: dict[str, Any],
    *,
    expected_total: int,
) -> dict[str, int]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise VerificationError(
            "ranked_articles.json summary must be an object"
        )

    nested_processing = summary.get("processing")
    if nested_processing is None:
        processing = summary
    elif isinstance(nested_processing, dict):
        processing = nested_processing
    else:
        raise VerificationError(
            "ranked_articles.json summary.processing must be an object"
        )

    enrichment = processing.get("content_enrichment")
    if not isinstance(enrichment, dict):
        raise VerificationError(
            "Full-content EPUB enrichment summary is missing"
        )

    fields = (
        "requested_articles",
        "extracted_articles",
        "summary_fallback_articles",
        "failed_articles",
    )
    counts = {
        field: _require_non_negative_integer(
            enrichment.get(field),
            field=f"content_enrichment.{field}",
        )
        for field in fields
    }

    if counts["requested_articles"] != expected_total:
        raise VerificationError(
            "Full-content enrichment did not request every "
            "selected article"
        )

    completed = (
        counts["extracted_articles"]
        + counts["summary_fallback_articles"]
        + counts["failed_articles"]
    )
    if completed != counts["requested_articles"]:
        raise VerificationError(
            "Full-content enrichment counts do not add up"
        )

    records = enrichment.get("records")
    if not isinstance(records, list):
        raise VerificationError(
            "content_enrichment.records must be a list"
        )
    if len(records) != counts["requested_articles"]:
        raise VerificationError(
            "content_enrichment.records does not match "
            "requested_articles"
        )

    status_counts = {
        "extracted": 0,
        "summary_fallback": 0,
        "fetch_failed": 0,
    }
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise VerificationError(
                f"content_enrichment.records[{index}] must be an object"
            )
        status = record.get("status")
        if status not in status_counts:
            raise VerificationError(
                f"content_enrichment.records[{index}].status "
                "is invalid"
            )
        status_counts[status] += 1

    expected_status_counts = {
        "extracted": counts["extracted_articles"],
        "summary_fallback": counts["summary_fallback_articles"],
        "fetch_failed": counts["failed_articles"],
    }
    if status_counts != expected_status_counts:
        raise VerificationError(
            "Full-content enrichment record statuses do not "
            "match the summary counts"
        )

    return counts


def _verify_public_articles_are_summary_only(
    articles: list[Any],
    *,
    source: Path,
) -> None:
    for index, article in enumerate(articles):
        if not isinstance(article, dict):
            raise VerificationError(
                f"{source} articles[{index}] must be an object"
            )

        if str(article.get("content_html") or "").strip():
            raise VerificationError(
                f"{source} publicly exposes full article HTML"
            )
        if str(article.get("content_text") or "").strip():
            raise VerificationError(
                f"{source} publicly exposes full article text"
            )

        status = article.get("content_status", "not_requested")
        if status != "not_requested":
            raise VerificationError(
                f"{source} public article content_status must be "
                "'not_requested'"
            )


def _extract_learning_article_ids(
    articles: Iterable[dict[str, Any]],
) -> list[str]:
    lesson_ids: list[str] = []

    for article in articles:
        external_id = _require_non_empty_string(
            article.get("external_id"),
            field="learning article external_id",
        )
        prefix = "learning:"
        if not external_id.startswith(prefix):
            raise VerificationError(
                "Learning article external_id must start with "
                f"'{prefix}'"
            )

        lesson_id = external_id[len(prefix):].strip()
        if not lesson_id:
            raise VerificationError(
                "Learning article external_id has an empty lesson ID"
            )

        lesson_ids.append(lesson_id)

    if len(set(lesson_ids)) != len(lesson_ids):
        raise VerificationError(
            "Learning article lesson IDs must be unique"
        )

    return lesson_ids


def _extract_payload_lesson_ids(
    payload: dict[str, Any],
) -> list[str]:
    learning = payload.get("learning")

    if learning is None:
        return []

    if not isinstance(learning, dict):
        raise VerificationError(
            "ranked_articles.json learning must be an object"
        )

    lesson_ids = learning.get("lesson_ids")
    if not isinstance(lesson_ids, list):
        raise VerificationError(
            "ranked_articles.json learning.lesson_ids "
            "must be a list"
        )

    normalized: list[str] = []
    for index, lesson_id in enumerate(lesson_ids):
        normalized.append(
            _require_non_empty_string(
                lesson_id,
                field=f"learning.lesson_ids[{index}]",
            )
        )

    return normalized


def _verify_epub(
    path: Path,
    *,
    learning_titles: tuple[str, ...],
    require_learning: bool,
    expected_articles: int,
    expected_full_content: int,
) -> None:
    _require_file(path)

    try:
        with zipfile.ZipFile(path) as archive:
            broken_member = archive.testzip()
            if broken_member is not None:
                raise VerificationError(
                    f"{path} contains a corrupt member: "
                    f"{broken_member}"
                )

            names = set(archive.namelist())
            chapter = "EPUB/category-technical-learning.xhtml"
            stylesheet_name = "EPUB/styles.css"

            if require_learning and chapter not in names:
                raise VerificationError(
                    f"{path} is missing {chapter}"
                )
            if stylesheet_name not in names:
                raise VerificationError(
                    f"{path} is missing {stylesheet_name}"
                )

            category_names = sorted(
                name
                for name in names
                if name.startswith("EPUB/category-")
                and name.endswith(".xhtml")
            )
            chapters = [
                archive.read(name).decode("utf-8")
                for name in category_names
            ]
            combined = "\n".join(chapters)

            if require_learning:
                learning_chapter = archive.read(
                    chapter
                ).decode("utf-8")
                for title in learning_titles:
                    _require_contains(
                        learning_chapter,
                        title,
                        source=path,
                    )

            if "Read the original article" in combined:
                raise VerificationError(
                    f"{path} still contains the legacy read-more link"
                )

            original_source_count = combined.count(
                ">Original source</a>"
            )
            if original_source_count != expected_articles:
                raise VerificationError(
                    f"{path} contains {original_source_count} Original "
                    f"source links; expected {expected_articles}"
                )

            full_content_count = combined.count(
                'class="article-content full-content'
            )
            if full_content_count != expected_full_content:
                raise VerificationError(
                    f"{path} contains {full_content_count} full-content "
                    f"articles; expected {expected_full_content}"
                )

            stylesheet = archive.read(
                stylesheet_name
            ).decode("utf-8")
            for required_rule in (
                "article + article",
                "break-before: page;",
                "page-break-before: always;",
                "break-inside: auto;",
                "page-break-inside: auto;",
            ):
                _require_contains(
                    stylesheet,
                    required_rule,
                    source=path,
                )
    except zipfile.BadZipFile as exc:
        raise VerificationError(
            f"{path} is not a valid EPUB ZIP archive"
        ) from exc


def _verify_epub_copies(
    *,
    source_epub: Path,
    site_dir: Path,
) -> tuple[Path, ...]:
    source_bytes = source_epub.read_bytes()
    candidates = (
        site_dir / "digest.epub",
        site_dir / "latest" / "digest.epub",
    )
    checked: list[Path] = []

    for candidate in candidates:
        if not candidate.is_file():
            continue

        if candidate.read_bytes() != source_bytes:
            raise VerificationError(
                f"{candidate} does not match {source_epub}"
            )
        checked.append(candidate)

    if not checked:
        raise VerificationError(
            "No published site EPUB copy was found"
        )

    return tuple(checked)


def _find_latest_archive_payload(
    site_dir: Path,
) -> Path:
    archive_root = site_dir / "archive"
    candidates = [
        path
        for path in archive_root.rglob(
            "ranked_articles.json"
        )
        if path.is_file()
    ]

    if not candidates:
        raise VerificationError(
            "No archived ranked_articles.json was found"
        )

    return max(
        candidates,
        key=lambda path: (
            path.parent.as_posix(),
            path.stat().st_mtime_ns,
        ),
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    text = _read_text(path)

    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VerificationError(
            f"{path} contains invalid JSON: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise VerificationError(
            f"{path} must contain a JSON object"
        )

    return value


def _read_text(path: Path) -> str:
    _require_file(path)

    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VerificationError(
            f"Unable to read {path}: {exc}"
        ) from exc


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise VerificationError(
            f"Required file not found: {path}"
        )


def _require_contains(
    content: str,
    expected: str,
    *,
    source: Path,
) -> None:
    if expected not in content:
        raise VerificationError(
            f"{source} does not contain: {expected}"
        )


def _require_non_empty_string(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VerificationError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_non_negative_integer(
    value: Any,
    *,
    field: str,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise VerificationError(
            f"{field} must be a non-negative integer"
        )
    return value


def _validate_expected_count(
    value: int,
    *,
    field: str,
) -> None:
    _require_non_negative_integer(
        value,
        field=field,
    )


def _result_payload(
    result: VerificationResult,
) -> dict[str, Any]:
    return {
        "status": "passed",
        "total_articles": result.total_articles,
        "learning_articles": result.learning_articles,
        "lesson_ids": list(result.lesson_ids),
        "content_enrichment": {
            "requested": result.content_requested,
            "extracted": result.content_extracted,
            "summary_fallback": result.content_fallback,
            "fetch_failed": result.content_failed,
        },
        "archive_file": str(result.archive_file),
        "checked_epub_copies": [
            str(path)
            for path in result.checked_epub_copies
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        result = verify_technical_learning_output(
            output_dir=args.output_dir,
            site_dir=args.site_dir,
            expected_total=args.expected_total,
            expected_learning=args.expected_learning,
        )
    except VerificationError as exc:
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
                f"Verification failed: {exc}",
                file=sys.stderr,
            )
        return 1

    payload = _result_payload(result)

    if args.json:
        print(
            json.dumps(
                payload,
                indent=2,
            )
        )
    else:
        print(
            "Technical Learning and full-text EPUB "
            "verification passed"
        )
        print(
            f"- Total articles:      "
            f"{result.total_articles}"
        )
        print(
            f"- Learning articles:   "
            f"{result.learning_articles}"
        )
        print(
            "- Lesson IDs:          "
            + (
                ", ".join(result.lesson_ids)
                if result.lesson_ids
                else "none"
            )
        )
        print(
            f"- Content extracted:   "
            f"{result.content_extracted}/"
            f"{result.content_requested}"
        )
        print(
            f"- Summary fallbacks:   "
            f"{result.content_fallback}"
        )
        print(
            f"- Content fetch fails: "
            f"{result.content_failed}"
        )
        print(
            f"- Archive payload:     "
            f"{result.archive_file}"
        )
        for path in result.checked_epub_copies:
            print(f"- EPUB copy matched:   {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
