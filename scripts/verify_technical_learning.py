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
    archive_file: Path
    checked_epub_copies: tuple[Path, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify Technical Learning output after a full Daily Tech Brief run."
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
        archive_file=archive_file,
        checked_epub_copies=checked_epub_copies,
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

            if require_learning and chapter not in names:
                raise VerificationError(
                    f"{path} is missing {chapter}"
                )

            if require_learning:
                chapter_text = archive.read(
                    chapter
                ).decode("utf-8")

                for title in learning_titles:
                    _require_contains(
                        chapter_text,
                        title,
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


def _validate_expected_count(
    value: int,
    *,
    field: str,
) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise VerificationError(
            f"{field} must be a non-negative integer"
        )


def _result_payload(
    result: VerificationResult,
) -> dict[str, Any]:
    return {
        "status": "passed",
        "total_articles": result.total_articles,
        "learning_articles": result.learning_articles,
        "lesson_ids": list(result.lesson_ids),
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
        print("Technical Learning verification passed")
        print(
            f"- Total articles:    "
            f"{result.total_articles}"
        )
        print(
            f"- Learning articles: "
            f"{result.learning_articles}"
        )
        print(
            "- Lesson IDs:        "
            + (
                ", ".join(result.lesson_ids)
                if result.lesson_ids
                else "none"
            )
        )
        print(
            f"- Archive payload:   "
            f"{result.archive_file}"
        )
        for path in result.checked_epub_copies:
            print(f"- EPUB copy matched: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
