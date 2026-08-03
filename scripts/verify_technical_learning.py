from __future__ import annotations

import argparse
import json
import sys
import zipfile
import xml.etree.ElementTree as ET
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
    content_feed: int
    content_web: int
    content_curated: int
    content_summary: int
    content_none: int
    public_epub_path: Path
    full_epub_path: Path
    archive_file: Path
    checked_epub_copies: tuple[Path, ...]
    opds_catalog_path: Path
    opds_book_path: Path
    opds_edition_count: int


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
        help=(
            "Maximum allowed number of ranked articles. "
            "The generated digest may contain fewer articles."
        ),
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
    public_epub_path = output_dir / "digest.epub"
    full_epub_path = output_dir / "digest-full.epub"

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

    if article_count > expected_total:
        raise VerificationError(
            f"Expected at most {expected_total} total articles, "
            f"found {article_count}"
        )

    _verify_public_articles_are_summary_only(
        articles,
        source=ranked_path,
    )
    enrichment = _extract_content_enrichment(
        payload,
        expected_total=article_count,
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

    _verify_learning_content_origins(
        enrichment["records"],
        learning_articles=learning_articles,
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
        'href="digest-full.epub"',
        source=html_path,
    )

    _verify_epub(
        public_epub_path,
        learning_titles=learning_titles,
        require_learning=bool(expected_learning),
        expected_articles=article_count,
        expected_full_content=0,
    )
    _verify_epub(
        full_epub_path,
        learning_titles=learning_titles,
        require_learning=bool(expected_learning),
        expected_articles=article_count,
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

    checked_public_epub_copies = _verify_epub_copies(
        source_epub=public_epub_path,
        site_dir=site_dir,
        published_name="digest.epub",
    )
    checked_full_epub_copies = _verify_epub_copies(
        source_epub=full_epub_path,
        site_dir=site_dir,
        published_name="digest-full.epub",
    )
    checked_epub_copies = (
        checked_public_epub_copies
        + checked_full_epub_copies
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

    archive_enrichment = _extract_content_enrichment(
        archive_payload,
        expected_total=article_count,
    )
    _verify_archive_enrichment_matches(
        current=enrichment,
        archived=archive_enrichment,
        archive_file=archive_file,
    )

    (
        opds_catalog_path,
        opds_book_path,
        opds_edition_count,
    ) = _verify_opds_catalog(
        site_dir=site_dir,
        full_epub_path=full_epub_path,
        archive_file=archive_file,
    )

    origins = enrichment["content_origins"]

    return VerificationResult(
        total_articles=article_count,
        learning_articles=len(learning_articles),
        lesson_ids=tuple(lesson_ids),
        content_requested=enrichment["requested_articles"],
        content_extracted=enrichment["extracted_articles"],
        content_fallback=enrichment["summary_fallback_articles"],
        content_failed=enrichment["failed_articles"],
        content_feed=origins["feed"],
        content_web=origins["web"],
        content_curated=origins["curated"],
        content_summary=origins["summary"],
        content_none=origins["none"],
        public_epub_path=public_epub_path,
        full_epub_path=full_epub_path,
        archive_file=archive_file,
        checked_epub_copies=checked_epub_copies,
        opds_catalog_path=opds_catalog_path,
        opds_book_path=opds_book_path,
        opds_edition_count=opds_edition_count,
    )


def _verify_opds_catalog(
    *,
    site_dir: Path,
    full_epub_path: Path,
    archive_file: Path,
) -> tuple[Path, Path, int]:
    catalog_path = site_dir / "opds" / "catalog.xml"
    _require_file(catalog_path)

    archive_root = site_dir / "archive"
    try:
        relative_archive = archive_file.parent.relative_to(
            archive_root
        )
    except ValueError as exc:
        raise VerificationError(
            f"Archive payload is outside {archive_root}: "
            f"{archive_file}"
        ) from exc

    if len(relative_archive.parts) != 3:
        raise VerificationError(
            "Archive payload path must use YYYY/MM/DD"
        )

    edition_date = "-".join(relative_archive.parts)
    expected_href = (
        "books/"
        f"daily-tech-brief-{edition_date}.epub"
    )
    expected_book = catalog_path.parent / expected_href
    _require_file(expected_book)

    if expected_book.read_bytes() != full_epub_path.read_bytes():
        raise VerificationError(
            f"{expected_book} does not match {full_epub_path}"
        )

    try:
        root = ET.parse(catalog_path).getroot()
    except ET.ParseError as exc:
        raise VerificationError(
            f"{catalog_path} contains invalid XML: {exc}"
        ) from exc

    atom = "{http://www.w3.org/2005/Atom}"
    if root.tag != f"{atom}feed":
        raise VerificationError(
            f"{catalog_path} root element must be an Atom feed"
        )

    self_links = [
        link
        for link in root.findall(f"{atom}link")
        if link.get("rel") == "self"
    ]
    if len(self_links) != 1:
        raise VerificationError(
            f"{catalog_path} must contain exactly one self link"
        )

    expected_feed_type = (
        "application/atom+xml;"
        "profile=opds-catalog;kind=acquisition"
    )
    if self_links[0].get("type") != expected_feed_type:
        raise VerificationError(
            f"{catalog_path} self link has an invalid media type"
        )

    entries = root.findall(f"{atom}entry")
    if not entries:
        raise VerificationError(
            f"{catalog_path} does not contain any OPDS editions"
        )

    matching_entries = []
    for entry in entries:
        acquisition_links = [
            link
            for link in entry.findall(f"{atom}link")
            if (
                link.get("rel")
                == "http://opds-spec.org/acquisition"
            )
        ]
        for link in acquisition_links:
            if link.get("href") == expected_href:
                matching_entries.append((entry, link))

    if len(matching_entries) != 1:
        raise VerificationError(
            f"{catalog_path} must contain exactly one acquisition "
            f"entry for {edition_date}"
        )

    entry, acquisition = matching_entries[0]
    if acquisition.get("type") != "application/epub+zip":
        raise VerificationError(
            f"{catalog_path} acquisition link has an invalid "
            "EPUB media type"
        )

    entry_id = entry.findtext(f"{atom}id", default="").strip()
    if entry_id != (
        f"urn:daily-tech-brief:edition:{edition_date}"
    ):
        raise VerificationError(
            f"{catalog_path} contains an invalid edition ID "
            f"for {edition_date}"
        )

    return catalog_path, expected_book, len(entries)


def _extract_content_enrichment(
    payload: dict[str, Any],
    *,
    expected_total: int,
) -> dict[str, Any]:
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
    origin_counts = {
        "feed": 0,
        "web": 0,
        "curated": 0,
        "summary": 0,
        "none": 0,
    }
    allowed_origins_by_status = {
        "extracted": {"feed", "web", "curated"},
        "summary_fallback": {"summary"},
        "fetch_failed": {"none"},
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

        origin = record.get("content_origin")
        if origin == "unknown":
            raise VerificationError(
                f"content_enrichment.records[{index}].content_origin "
                "must not be 'unknown'"
            )
        if origin not in origin_counts:
            raise VerificationError(
                f"content_enrichment.records[{index}].content_origin "
                "is invalid or missing"
            )
        if origin not in allowed_origins_by_status[status]:
            raise VerificationError(
                f"content_enrichment.records[{index}] has incompatible "
                "status and content_origin"
            )

        status_counts[status] += 1
        origin_counts[origin] += 1

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

    if sum(origin_counts.values()) != counts["requested_articles"]:
        raise VerificationError(
            "Full-content enrichment origins do not add up"
        )

    counts["content_origins"] = origin_counts
    counts["records"] = records
    return counts


def _verify_learning_content_origins(
    records: list[dict[str, Any]],
    *,
    learning_articles: list[dict[str, Any]],
) -> None:
    learning_records = [
        record
        for record in records
        if record.get("source_id") == "technical_learning"
    ]

    if len(learning_records) != len(learning_articles):
        raise VerificationError(
            "Technical Learning enrichment records do not match "
            "the selected learning articles"
        )

    curated_by_title: dict[str, bool] = {}
    for article in learning_articles:
        title = _require_non_empty_string(
            article.get("title"),
            field="Technical Learning article title",
        )
        source_tags = article.get("source_tags", [])
        if not isinstance(source_tags, list) or not all(
            isinstance(tag, str)
            for tag in source_tags
        ):
            raise VerificationError(
                "Technical Learning source_tags must be a list "
                "of strings"
            )
        curated_by_title[title] = (
            "learning_content:curated" in source_tags
        )

    record_titles = {
        _require_non_empty_string(
            record.get("title"),
            field="Technical Learning enrichment title",
        )
        for record in learning_records
    }
    if record_titles != set(curated_by_title):
        raise VerificationError(
            "Technical Learning enrichment titles do not match "
            "the selected learning articles"
        )

    for record in learning_records:
        title = _require_non_empty_string(
            record.get("title"),
            field="Technical Learning enrichment title",
        )
        status = record.get("status")
        origin = record.get("content_origin")
        expects_curated = curated_by_title[title]

        if expects_curated:
            if status != "extracted":
                raise VerificationError(
                    "Curated Technical Learning content must be "
                    "extracted"
                )
            if origin != "curated":
                raise VerificationError(
                    "Curated Technical Learning content must use "
                    "curated origin"
                )
            continue

        if origin == "curated":
            raise VerificationError(
                "Technical Learning content without the curated "
                "tag must not use curated origin"
            )
        if status == "fetch_failed":
            raise VerificationError(
                "Technical Learning must provide full content or "
                "a summary fallback"
            )


def _verify_archive_enrichment_matches(
    *,
    current: dict[str, Any],
    archived: dict[str, Any],
    archive_file: Path,
) -> None:
    fields = (
        "requested_articles",
        "extracted_articles",
        "summary_fallback_articles",
        "failed_articles",
        "content_origins",
    )

    for field in fields:
        if current[field] != archived[field]:
            raise VerificationError(
                f"{archive_file} contains different content "
                "enrichment data"
            )


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
    published_name: str,
) -> tuple[Path, ...]:
    source_bytes = source_epub.read_bytes()
    candidates = (
        site_dir / published_name,
        site_dir / "latest" / published_name,
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
            f"No published site copy of {published_name} was found"
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
            "content_origins": {
                "feed": result.content_feed,
                "web": result.content_web,
                "curated": result.content_curated,
                "summary": result.content_summary,
                "none": result.content_none,
            },
        },
        "public_epub": str(result.public_epub_path),
        "full_epub": str(result.full_epub_path),
        "archive_file": str(result.archive_file),
        "checked_epub_copies": [
            str(path)
            for path in result.checked_epub_copies
        ],
        "opds": {
            "catalog": str(result.opds_catalog_path),
            "latest_book": str(result.opds_book_path),
            "edition_count": result.opds_edition_count,
        },
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
            "- Content origins:     "
            f"feed={result.content_feed}, "
            f"web={result.content_web}, "
            f"curated={result.content_curated}, "
            f"summary={result.content_summary}, "
            f"none={result.content_none}"
        )
        print(
            f"- Public EPUB:         "
            f"{result.public_epub_path}"
        )
        print(
            f"- Full EPUB:           "
            f"{result.full_epub_path}"
        )
        print(
            f"- Archive payload:     "
            f"{result.archive_file}"
        )
        for path in result.checked_epub_copies:
            print(
                f"- Published EPUB matched: "
                f"{path}"
            )
        print(
            f"- OPDS catalog:        "
            f"{result.opds_catalog_path}"
        )
        print(
            f"- OPDS latest book:    "
            f"{result.opds_book_path}"
        )
        print(
            f"- OPDS editions:       "
            f"{result.opds_edition_count}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
