from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


class LearningLibraryError(ValueError):
    """Raised when the technical learning library is invalid."""


@dataclass(frozen=True)
class LearningSelection:
    enabled: bool
    daily_count: int
    rotation: str
    include_in_max_articles: bool
    history_source: str
    timezone: str


@dataclass(frozen=True)
class LearningLesson:
    id: str
    order: int
    title: str
    source_name: str
    url: str
    track: str
    topics: tuple[str, ...]
    difficulty: str
    estimated_minutes: int
    summary: str
    why_it_matters: str
    enabled: bool
    content_html: str = ""


@dataclass(frozen=True)
class LearningLibrary:
    schema_version: int
    selection: LearningSelection
    lessons: tuple[LearningLesson, ...]

    @property
    def enabled_lessons(self) -> tuple[LearningLesson, ...]:
        return tuple(
            lesson
            for lesson in self.lessons
            if lesson.enabled
        )


_REQUIRED_SELECTION_FIELDS = {
    "enabled",
    "daily_count",
    "rotation",
    "include_in_max_articles",
    "history_source",
    "timezone",
}

_REQUIRED_LESSON_FIELDS = {
    "id",
    "order",
    "title",
    "source_name",
    "url",
    "track",
    "topics",
    "difficulty",
    "estimated_minutes",
    "summary",
    "why_it_matters",
    "enabled",
}

_SUPPORTED_ROTATIONS = {
    "sequential",
}

_SUPPORTED_DIFFICULTIES = {
    "beginner",
    "intermediate",
    "advanced",
}


def load_learning_library(
    path: str | Path,
) -> LearningLibrary:
    """Load and validate a technical learning library YAML file."""

    library_path = Path(path)

    try:
        raw = yaml.safe_load(
            library_path.read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise LearningLibraryError(
            f"Learning library not found: {library_path}"
        ) from exc
    except OSError as exc:
        raise LearningLibraryError(
            f"Unable to read learning library "
            f"'{library_path}': {exc}"
        ) from exc
    except yaml.YAMLError as exc:
        raise LearningLibraryError(
            f"Invalid YAML in learning library "
            f"'{library_path}': {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise LearningLibraryError(
            "Learning library root must be a mapping"
        )

    schema_version = raw.get("schema_version")
    if schema_version != 1:
        raise LearningLibraryError(
            "Learning library schema_version must be 1"
        )

    selection = _parse_selection(raw.get("selection"))
    lessons = _parse_lessons(raw.get("lessons"))

    if selection.enabled and not any(
        lesson.enabled
        for lesson in lessons
    ):
        raise LearningLibraryError(
            "Learning selection is enabled but no lessons "
            "are enabled"
        )

    return LearningLibrary(
        schema_version=schema_version,
        selection=selection,
        lessons=tuple(
            sorted(
                lessons,
                key=lambda lesson: (
                    lesson.order,
                    lesson.id,
                ),
            )
        ),
    )


def _parse_selection(
    raw: Any,
) -> LearningSelection:
    if not isinstance(raw, dict):
        raise LearningLibraryError(
            "selection must be a mapping"
        )

    missing = sorted(
        _REQUIRED_SELECTION_FIELDS - raw.keys()
    )
    if missing:
        raise LearningLibraryError(
            "selection is missing required fields: "
            + ", ".join(missing)
        )

    enabled = _require_bool(
        raw,
        "enabled",
        prefix="selection",
    )
    daily_count = _require_int(
        raw,
        "daily_count",
        prefix="selection",
        minimum=0,
    )
    rotation = _require_non_empty_string(
        raw,
        "rotation",
        prefix="selection",
    )
    include_in_max_articles = _require_bool(
        raw,
        "include_in_max_articles",
        prefix="selection",
    )
    history_source = _require_non_empty_string(
        raw,
        "history_source",
        prefix="selection",
    )
    timezone = _require_non_empty_string(
        raw,
        "timezone",
        prefix="selection",
    )

    if enabled and daily_count < 1:
        raise LearningLibraryError(
            "selection.daily_count must be at least 1 "
            "when selection is enabled"
        )

    if rotation not in _SUPPORTED_ROTATIONS:
        supported = ", ".join(
            sorted(_SUPPORTED_ROTATIONS)
        )
        raise LearningLibraryError(
            f"selection.rotation must be one of: "
            f"{supported}"
        )

    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise LearningLibraryError(
            f"selection.timezone is invalid: "
            f"{timezone}"
        ) from exc

    return LearningSelection(
        enabled=enabled,
        daily_count=daily_count,
        rotation=rotation,
        include_in_max_articles=(
            include_in_max_articles
        ),
        history_source=history_source,
        timezone=timezone,
    )


def _parse_lessons(
    raw: Any,
) -> list[LearningLesson]:
    if not isinstance(raw, list):
        raise LearningLibraryError(
            "lessons must be a list"
        )

    if not raw:
        raise LearningLibraryError(
            "lessons must not be empty"
        )

    lessons: list[LearningLesson] = []
    seen_ids: set[str] = set()

    for index, item in enumerate(raw):
        prefix = f"lessons[{index}]"

        if not isinstance(item, dict):
            raise LearningLibraryError(
                f"{prefix} must be a mapping"
            )

        missing = sorted(
            _REQUIRED_LESSON_FIELDS - item.keys()
        )
        if missing:
            raise LearningLibraryError(
                f"{prefix} is missing required fields: "
                + ", ".join(missing)
            )

        lesson = _parse_lesson(
            item,
            prefix=prefix,
        )

        if lesson.id in seen_ids:
            raise LearningLibraryError(
                f"Duplicate lesson id: {lesson.id}"
            )

        seen_ids.add(lesson.id)
        lessons.append(lesson)

    return lessons


def _parse_lesson(
    raw: dict[str, Any],
    *,
    prefix: str,
) -> LearningLesson:
    lesson_id = _require_non_empty_string(
        raw,
        "id",
        prefix=prefix,
    )

    if (
        lesson_id.lower() != lesson_id
        or not lesson_id.replace("_", "").isalnum()
    ):
        raise LearningLibraryError(
            f"{prefix}.id must use lowercase letters, "
            "numbers, and underscores"
        )

    order = _require_int(
        raw,
        "order",
        prefix=prefix,
        minimum=0,
    )
    title = _require_non_empty_string(
        raw,
        "title",
        prefix=prefix,
    )
    source_name = _require_non_empty_string(
        raw,
        "source_name",
        prefix=prefix,
    )
    url = _require_non_empty_string(
        raw,
        "url",
        prefix=prefix,
    )
    track = _require_non_empty_string(
        raw,
        "track",
        prefix=prefix,
    )
    topics = _require_string_list(
        raw,
        "topics",
        prefix=prefix,
    )
    difficulty = _require_non_empty_string(
        raw,
        "difficulty",
        prefix=prefix,
    )
    estimated_minutes = _require_int(
        raw,
        "estimated_minutes",
        prefix=prefix,
        minimum=1,
    )
    summary = _require_non_empty_string(
        raw,
        "summary",
        prefix=prefix,
    )
    why_it_matters = _require_non_empty_string(
        raw,
        "why_it_matters",
        prefix=prefix,
    )
    content_html = _optional_string(
        raw,
        "content_html",
        prefix=prefix,
    )
    enabled = _require_bool(
        raw,
        "enabled",
        prefix=prefix,
    )

    parsed_url = urlparse(url)
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
    ):
        raise LearningLibraryError(
            f"{prefix}.url must be a valid HTTP or HTTPS URL"
        )

    if difficulty not in _SUPPORTED_DIFFICULTIES:
        supported = ", ".join(
            sorted(_SUPPORTED_DIFFICULTIES)
        )
        raise LearningLibraryError(
            f"{prefix}.difficulty must be one of: "
            f"{supported}"
        )

    return LearningLesson(
        id=lesson_id,
        order=order,
        title=title,
        source_name=source_name,
        url=url,
        track=track,
        topics=topics,
        difficulty=difficulty,
        estimated_minutes=estimated_minutes,
        summary=summary,
        why_it_matters=why_it_matters,
        content_html=content_html,
        enabled=enabled,
    )


def _require_bool(
    data: dict[str, Any],
    field: str,
    *,
    prefix: str,
) -> bool:
    value = data.get(field)
    if not isinstance(value, bool):
        raise LearningLibraryError(
            f"{prefix}.{field} must be a boolean"
        )
    return value


def _require_int(
    data: dict[str, Any],
    field: str,
    *,
    prefix: str,
    minimum: int,
) -> int:
    value = data.get(field)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
    ):
        raise LearningLibraryError(
            f"{prefix}.{field} must be an integer"
        )
    if value < minimum:
        raise LearningLibraryError(
            f"{prefix}.{field} must be at least "
            f"{minimum}"
        )
    return value


def _require_non_empty_string(
    data: dict[str, Any],
    field: str,
    *,
    prefix: str,
) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LearningLibraryError(
            f"{prefix}.{field} must be a non-empty string"
        )
    return value.strip()


def _optional_string(
    data: dict[str, Any],
    field: str,
    *,
    prefix: str,
) -> str:
    value = data.get(field, "")

    if value is None:
        return ""

    if not isinstance(value, str):
        raise LearningLibraryError(
            f"{prefix}.{field} must be a string"
        )

    return value.strip()


def _require_string_list(
    data: dict[str, Any],
    field: str,
    *,
    prefix: str,
) -> tuple[str, ...]:
    value = data.get(field)
    if not isinstance(value, list) or not value:
        raise LearningLibraryError(
            f"{prefix}.{field} must be a non-empty list"
        )

    items: list[str] = []
    seen: set[str] = set()

    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise LearningLibraryError(
                f"{prefix}.{field}[{index}] must be "
                "a non-empty string"
            )

        normalized = item.strip()
        if normalized in seen:
            raise LearningLibraryError(
                f"{prefix}.{field} contains duplicate "
                f"value: {normalized}"
            )

        seen.add(normalized)
        items.append(normalized)

    return tuple(items)
