from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from src.learning.library import (
    LearningLesson,
    LearningLibrary,
)


class LearningSelectionError(ValueError):
    """Raised when technical learning selection cannot be completed."""


@dataclass(frozen=True)
class LearningHistoryEntry:
    """Learning lessons recorded for one archived digest edition."""

    date: str
    lesson_ids: tuple[str, ...]
    ranked_articles_path: Path


@dataclass(frozen=True)
class LearningSelectionResult:
    """Technical lessons selected for the current local calendar date."""

    evaluated_date: str
    requested_lessons: int
    available_lessons: int
    selected_lessons: tuple[LearningLesson, ...]
    previous_lesson_id: str | None
    reused_current_edition: bool
    cycle_reset: bool
    history_entries: tuple[LearningHistoryEntry, ...]

    @property
    def selected_count(self) -> int:
        return len(self.selected_lessons)

    def summary(self) -> dict[str, Any]:
        return {
            "evaluated_date": self.evaluated_date,
            "requested_lessons": self.requested_lessons,
            "available_lessons": self.available_lessons,
            "selected_lessons": self.selected_count,
            "selected_lesson_ids": [
                lesson.id
                for lesson in self.selected_lessons
            ],
            "previous_lesson_id": self.previous_lesson_id,
            "reused_current_edition": self.reused_current_edition,
            "cycle_reset": self.cycle_reset,
            "history_entries": len(self.history_entries),
        }


def select_learning_lessons(
    library: LearningLibrary,
    *,
    archive_root: str | Path,
    now: datetime | None = None,
) -> LearningSelectionResult:
    """Select sequential technical lessons using archived digest history.

    A rerun on the same local calendar date reuses that date's archived
    lessons. A new date starts after the most recently archived lesson and
    wraps to the beginning after the final enabled lesson.
    """

    selection = library.selection
    evaluated_date = _local_date(
        now=now,
        timezone_name=selection.timezone,
    )
    history = load_learning_history(archive_root)
    enabled_lessons = library.enabled_lessons

    if not selection.enabled:
        return LearningSelectionResult(
            evaluated_date=evaluated_date,
            requested_lessons=selection.daily_count,
            available_lessons=len(enabled_lessons),
            selected_lessons=(),
            previous_lesson_id=None,
            reused_current_edition=False,
            cycle_reset=False,
            history_entries=history,
        )

    if selection.history_source != "site_archive":
        raise LearningSelectionError(
            "Unsupported learning history source: "
            f"{selection.history_source}"
        )

    if not enabled_lessons:
        raise LearningSelectionError(
            "No enabled technical learning lessons are available"
        )

    if selection.daily_count > len(enabled_lessons):
        raise LearningSelectionError(
            "selection.daily_count must not exceed the number "
            "of enabled lessons"
        )

    lessons_by_id = {
        lesson.id: lesson
        for lesson in enabled_lessons
    }

    current_entry = _latest_entry_for_date(
        history,
        evaluated_date,
    )
    if current_entry is not None:
        current_lessons = tuple(
            lessons_by_id[lesson_id]
            for lesson_id in current_entry.lesson_ids
            if lesson_id in lessons_by_id
        )
        if len(current_lessons) >= selection.daily_count:
            selected = current_lessons[: selection.daily_count]
            previous_lesson_id = _previous_lesson_id(
                history,
                before_date=evaluated_date,
                valid_ids=lessons_by_id,
            )
            return LearningSelectionResult(
                evaluated_date=evaluated_date,
                requested_lessons=selection.daily_count,
                available_lessons=len(enabled_lessons),
                selected_lessons=selected,
                previous_lesson_id=previous_lesson_id,
                reused_current_edition=True,
                cycle_reset=False,
                history_entries=history,
            )

    previous_lesson_id = _previous_lesson_id(
        history,
        before_date=evaluated_date,
        valid_ids=lessons_by_id,
    )
    selected, cycle_reset = _select_after_previous(
        enabled_lessons,
        previous_lesson_id=previous_lesson_id,
        count=selection.daily_count,
    )

    return LearningSelectionResult(
        evaluated_date=evaluated_date,
        requested_lessons=selection.daily_count,
        available_lessons=len(enabled_lessons),
        selected_lessons=selected,
        previous_lesson_id=previous_lesson_id,
        reused_current_edition=False,
        cycle_reset=cycle_reset,
        history_entries=history,
    )


def load_learning_history(
    archive_root: str | Path,
) -> tuple[LearningHistoryEntry, ...]:
    """Load learning lesson IDs from archived ranked article payloads."""

    root = Path(archive_root)
    if not root.is_dir():
        return ()

    candidates = _archive_candidates(root)
    entries: list[LearningHistoryEntry] = []

    for date, ranked_path in candidates:
        payload = _read_json_object(ranked_path)
        if payload is None:
            continue

        lesson_ids = _extract_lesson_ids(payload)
        if not lesson_ids:
            continue

        resolved_date = date or _date_from_payload(payload)
        if resolved_date is None:
            continue

        entries.append(
            LearningHistoryEntry(
                date=resolved_date,
                lesson_ids=lesson_ids,
                ranked_articles_path=ranked_path,
            )
        )

    entries.sort(
        key=lambda entry: (
            entry.date,
            str(entry.ranked_articles_path),
        )
    )
    return tuple(entries)


def _archive_candidates(
    archive_root: Path,
) -> tuple[tuple[str | None, Path], ...]:
    manifest_candidates = _candidates_from_manifest(
        archive_root,
    )
    if manifest_candidates:
        return manifest_candidates

    discovered: list[tuple[str | None, Path]] = []
    for ranked_path in archive_root.rglob(
        "ranked_articles.json"
    ):
        discovered.append(
            (
                _date_from_archive_path(
                    archive_root,
                    ranked_path,
                ),
                ranked_path,
            )
        )

    discovered.sort(key=lambda item: str(item[1]))
    return tuple(discovered)


def _candidates_from_manifest(
    archive_root: Path,
) -> tuple[tuple[str | None, Path], ...]:
    manifest = _read_json_object(
        archive_root / "index.json"
    )
    if manifest is None:
        return ()

    editions = manifest.get("editions")
    if not isinstance(editions, list):
        return ()

    candidates: list[tuple[str | None, Path]] = []
    seen_paths: set[Path] = set()

    for edition in editions:
        if not isinstance(edition, dict):
            continue

        relative_path = edition.get("path")
        if not isinstance(relative_path, str):
            continue

        ranked_path = (
            archive_root
            / relative_path
            / "ranked_articles.json"
        )
        if ranked_path in seen_paths or not ranked_path.is_file():
            continue

        date = edition.get("date")
        normalized_date = (
            date.strip()
            if isinstance(date, str) and date.strip()
            else None
        )
        seen_paths.add(ranked_path)
        candidates.append((normalized_date, ranked_path))

    return tuple(candidates)


def _extract_lesson_ids(
    payload: dict[str, Any],
) -> tuple[str, ...]:
    lesson_ids: list[str] = []

    _append_string_ids(
        lesson_ids,
        payload.get("learning_lesson_ids"),
    )

    learning = payload.get("learning")
    if isinstance(learning, dict):
        _append_string_ids(
            lesson_ids,
            learning.get("lesson_ids"),
        )

        lessons = learning.get("lessons")
        if isinstance(lessons, list):
            for lesson in lessons:
                if not isinstance(lesson, dict):
                    continue
                _append_optional_id(
                    lesson_ids,
                    lesson.get("id")
                    or lesson.get("lesson_id"),
                )

    articles = payload.get("articles")
    if isinstance(articles, list):
        for article in articles:
            if not isinstance(article, dict):
                continue
            _append_optional_id(
                lesson_ids,
                article.get("learning_lesson_id"),
            )

    return tuple(dict.fromkeys(lesson_ids))


def _append_string_ids(
    destination: list[str],
    value: Any,
) -> None:
    if not isinstance(value, list):
        return

    for item in value:
        _append_optional_id(destination, item)


def _append_optional_id(
    destination: list[str],
    value: Any,
) -> None:
    if isinstance(value, str) and value.strip():
        destination.append(value.strip())


def _previous_lesson_id(
    history: Iterable[LearningHistoryEntry],
    *,
    before_date: str,
    valid_ids: dict[str, LearningLesson],
) -> str | None:
    previous_entries = [
        entry
        for entry in history
        if entry.date < before_date
    ]

    for entry in reversed(previous_entries):
        for lesson_id in reversed(entry.lesson_ids):
            if lesson_id in valid_ids:
                return lesson_id

    return None


def _latest_entry_for_date(
    history: Iterable[LearningHistoryEntry],
    date: str,
) -> LearningHistoryEntry | None:
    matches = [
        entry
        for entry in history
        if entry.date == date
    ]
    return matches[-1] if matches else None


def _select_after_previous(
    lessons: tuple[LearningLesson, ...],
    *,
    previous_lesson_id: str | None,
    count: int,
) -> tuple[tuple[LearningLesson, ...], bool]:
    start_index = 0
    if previous_lesson_id is not None:
        previous_index = next(
            index
            for index, lesson in enumerate(lessons)
            if lesson.id == previous_lesson_id
        )
        start_index = (previous_index + 1) % len(lessons)

    selected = tuple(
        lessons[(start_index + offset) % len(lessons)]
        for offset in range(count)
    )
    cycle_reset = (
        previous_lesson_id is not None
        and (
            start_index == 0
            or start_index + count > len(lessons)
        )
    )
    return selected, cycle_reset


def _local_date(
    *,
    now: datetime | None,
    timezone_name: str,
) -> str:
    local_timezone = ZoneInfo(timezone_name)
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(local_timezone).date().isoformat()


def _date_from_archive_path(
    archive_root: Path,
    ranked_path: Path,
) -> str | None:
    try:
        relative = ranked_path.relative_to(archive_root)
    except ValueError:
        return None

    parts = relative.parts
    if len(parts) < 4:
        return None

    year, month, day = parts[-4:-1]
    candidate = f"{year}-{month}-{day}"
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return None
    return candidate


def _date_from_payload(
    payload: dict[str, Any],
) -> str | None:
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str):
        return None

    try:
        parsed = datetime.fromisoformat(
            generated_at.strip().replace("Z", "+00:00")
        )
    except ValueError:
        return None

    return parsed.date().isoformat()


def _read_json_object(
    path: Path,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None
