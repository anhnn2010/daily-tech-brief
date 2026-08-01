from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_LIBRARY_PATH = (
    _PROJECT_ROOT
    / "config"
    / "learning_library.yml"
)

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.learning.library import (
    LearningLibraryError,
    load_learning_library,
)


class LearningCoverageError(RuntimeError):
    """Raised when curated learning coverage cannot be reported."""


@dataclass(frozen=True)
class LessonCoverage:
    index: int
    lesson_id: str
    order: int
    title: str
    track: str
    difficulty: str
    estimated_minutes: int
    enabled: bool
    curated: bool
    content_characters: int

    @property
    def status(self) -> str:
        if not self.enabled:
            return "disabled"
        if self.curated:
            return "curated"
        return "needs_web"

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "id": self.lesson_id,
            "order": self.order,
            "title": self.title,
            "track": self.track,
            "difficulty": self.difficulty,
            "estimated_minutes": self.estimated_minutes,
            "enabled": self.enabled,
            "curated": self.curated,
            "status": self.status,
            "content_characters": self.content_characters,
        }


@dataclass(frozen=True)
class LearningCoverageReport:
    input_path: Path
    total_lessons: int
    enabled_lessons: int
    curated_enabled_lessons: int
    uncurated_enabled_lessons: int
    curated_reading_minutes: int
    uncurated_reading_minutes: int
    records: tuple[LessonCoverage, ...]

    @property
    def coverage_rate(self) -> float:
        if self.enabled_lessons == 0:
            return 0.0
        return self.curated_enabled_lessons / self.enabled_lessons

    @property
    def next_uncurated_lesson(self) -> LessonCoverage | None:
        return next(
            (
                record
                for record in self.records
                if record.enabled and not record.curated
            ),
            None,
        )

    def to_dict(self) -> dict[str, Any]:
        next_lesson = self.next_uncurated_lesson
        return {
            "input_path": str(self.input_path),
            "total_lessons": self.total_lessons,
            "enabled_lessons": self.enabled_lessons,
            "curated_enabled_lessons": self.curated_enabled_lessons,
            "uncurated_enabled_lessons": self.uncurated_enabled_lessons,
            "coverage_rate": round(self.coverage_rate, 4),
            "curated_reading_minutes": self.curated_reading_minutes,
            "uncurated_reading_minutes": self.uncurated_reading_minutes,
            "next_uncurated_lesson_id": (
                next_lesson.lesson_id
                if next_lesson is not None
                else None
            ),
            "records": [
                record.to_dict()
                for record in self.records
            ],
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Report how many Technical Learning lessons have "
            "curated offline content."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=_DEFAULT_LIBRARY_PATH,
        help=(
            "Path to the Technical Learning library YAML. "
            "Defaults to config/learning_library.yml in the "
            "project root."
        ),
    )
    parser.add_argument(
        "--uncurated-only",
        action="store_true",
        help="Show only enabled lessons that still depend on web content.",
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
        help="Print a Markdown report suitable for GitHub Actions.",
    )
    return parser


def load_learning_coverage(
    path: str | Path,
) -> LearningCoverageReport:
    library_path = Path(path)

    try:
        library = load_learning_library(library_path)
    except LearningLibraryError as exc:
        raise LearningCoverageError(str(exc)) from exc

    records = tuple(
        LessonCoverage(
            index=index,
            lesson_id=lesson.id,
            order=lesson.order,
            title=lesson.title,
            track=lesson.track,
            difficulty=lesson.difficulty,
            estimated_minutes=lesson.estimated_minutes,
            enabled=lesson.enabled,
            curated=bool(lesson.content_html.strip()),
            content_characters=len(lesson.content_html.strip()),
        )
        for index, lesson in enumerate(
            library.lessons,
            start=1,
        )
    )

    enabled_records = tuple(
        record
        for record in records
        if record.enabled
    )
    curated_records = tuple(
        record
        for record in enabled_records
        if record.curated
    )
    uncurated_records = tuple(
        record
        for record in enabled_records
        if not record.curated
    )

    return LearningCoverageReport(
        input_path=library_path,
        total_lessons=len(records),
        enabled_lessons=len(enabled_records),
        curated_enabled_lessons=len(curated_records),
        uncurated_enabled_lessons=len(uncurated_records),
        curated_reading_minutes=sum(
            record.estimated_minutes
            for record in curated_records
        ),
        uncurated_reading_minutes=sum(
            record.estimated_minutes
            for record in uncurated_records
        ),
        records=records,
    )


def render_text_report(
    report: LearningCoverageReport,
    *,
    uncurated_only: bool = False,
) -> str:
    next_lesson = report.next_uncurated_lesson
    lines = [
        "Technical Learning curated coverage",
        f"- Input:                    {report.input_path}",
        f"- Total lessons:            {report.total_lessons}",
        f"- Enabled lessons:          {report.enabled_lessons}",
        f"- Curated offline lessons:  {report.curated_enabled_lessons}",
        f"- Lessons needing web:      {report.uncurated_enabled_lessons}",
        (
            "- Curated coverage:         "
            f"{report.coverage_rate * 100:.1f}%"
        ),
        (
            "- Curated reading time:     "
            f"{report.curated_reading_minutes} min"
        ),
        (
            "- Web-dependent time:       "
            f"{report.uncurated_reading_minutes} min"
        ),
        (
            "- Next lesson to curate:    "
            + (
                next_lesson.lesson_id
                if next_lesson is not None
                else "none"
            )
        ),
        "",
    ]

    records = _selected_records(
        report,
        uncurated_only=uncurated_only,
    )
    if not records:
        lines.append("No matching lessons.")
        return "\n".join(lines)

    for record in records:
        lines.extend(
            [
                (
                    f"[{record.index:02d}] "
                    f"{record.status.upper()} "
                    f"| {record.estimated_minutes} min "
                    f"| {record.content_characters} chars"
                ),
                f"     {record.title}",
                f"     id:         {record.lesson_id}",
                f"     track:      {record.track}",
                f"     difficulty: {record.difficulty}",
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def render_markdown_report(
    report: LearningCoverageReport,
    *,
    uncurated_only: bool = False,
) -> str:
    next_lesson = report.next_uncurated_lesson
    lines = [
        "## Technical Learning coverage",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Enabled lessons | {report.enabled_lessons} |",
        (
            "| Curated offline lessons | "
            f"{report.curated_enabled_lessons} |"
        ),
        (
            "| Lessons needing web | "
            f"{report.uncurated_enabled_lessons} |"
        ),
        (
            "| Curated coverage | "
            f"{report.coverage_rate * 100:.1f}% |"
        ),
        (
            "| Curated reading time | "
            f"{report.curated_reading_minutes} min |"
        ),
        (
            "| Web-dependent reading time | "
            f"{report.uncurated_reading_minutes} min |"
        ),
        "",
        (
            "Next lesson to curate: `"
            + (
                next_lesson.lesson_id
                if next_lesson is not None
                else "none"
            )
            + "`"
        ),
        "",
        "| # | Status | Lesson | Track | Level | Minutes | Characters |",
        "|---:|---|---|---|---|---:|---:|",
    ]

    records = _selected_records(
        report,
        uncurated_only=uncurated_only,
    )
    if not records:
        lines.append("| - | - | No matching lessons | - | - | - | - |")
        return "\n".join(lines)

    for record in records:
        lines.append(
            "| "
            f"{record.index} | "
            f"{record.status} | "
            f"{_escape_markdown(record.title)} | "
            f"{_escape_markdown(record.track)} | "
            f"{_escape_markdown(record.difficulty)} | "
            f"{record.estimated_minutes} | "
            f"{record.content_characters} |"
        )

    return "\n".join(lines)


def _selected_records(
    report: LearningCoverageReport,
    *,
    uncurated_only: bool,
) -> tuple[LessonCoverage, ...]:
    records: Iterable[LessonCoverage] = report.records
    if uncurated_only:
        records = (
            record
            for record in records
            if record.enabled and not record.curated
        )
    return tuple(records)


def _escape_markdown(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        report = load_learning_coverage(args.input)
    except LearningCoverageError as exc:
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
                f"Learning coverage report failed: {exc}",
                file=sys.stderr,
            )
        return 1

    if args.json:
        payload = report.to_dict()
        if args.uncurated_only:
            payload["records"] = [
                record.to_dict()
                for record in report.records
                if record.enabled and not record.curated
            ]
        payload["status"] = "passed"
        print(json.dumps(payload, indent=2))
    elif args.markdown:
        print(
            render_markdown_report(
                report,
                uncurated_only=args.uncurated_only,
            )
        )
    else:
        print(
            render_text_report(
                report,
                uncurated_only=args.uncurated_only,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
