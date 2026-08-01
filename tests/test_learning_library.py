from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.learning.library import (
    LearningLibraryError,
    load_learning_library,
)


def _valid_library() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "selection": {
            "enabled": True,
            "daily_count": 1,
            "rotation": "sequential",
            "include_in_max_articles": True,
            "history_source": "site_archive",
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "lessons": [
            {
                "id": "lesson_b",
                "order": 20,
                "title": "Lesson B",
                "source_name": "Example Source",
                "url": "https://example.com/lesson-b",
                "track": "analog_foundations",
                "topics": [
                    "biasing",
                    "current_mirror",
                ],
                "difficulty": "intermediate",
                "estimated_minutes": 20,
                "summary": "A useful technical summary.",
                "why_it_matters": (
                    "This lesson supports practical validation work."
                ),
                "enabled": True,
            },
            {
                "id": "lesson_a",
                "order": 10,
                "title": "Lesson A",
                "source_name": "Example Source",
                "url": "https://example.com/lesson-a",
                "track": "pll_and_clocking",
                "topics": [
                    "pll",
                    "clocking",
                ],
                "difficulty": "advanced",
                "estimated_minutes": 30,
                "summary": "Another useful technical summary.",
                "why_it_matters": (
                    "This lesson supports clock-debug workflows."
                ),
                "enabled": False,
            },
        ],
    }


def _write_library(
    tmp_path: Path,
    data: Any,
) -> Path:
    path = tmp_path / "learning_library.yml"
    path.write_text(
        yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return path


def test_loads_bundled_learning_library() -> None:
    library = load_learning_library(
        "config/learning_library.yml"
    )

    assert library.schema_version == 1
    assert library.selection.enabled is True
    assert library.selection.daily_count == 1
    assert library.selection.rotation == "sequential"
    assert library.selection.timezone == "Asia/Ho_Chi_Minh"

    assert len(library.lessons) == 16
    assert len(library.enabled_lessons) == 16
    assert library.lessons[0].id == "current_mirror_types"
    assert library.lessons[-1].id == "shmoo_and_silent_errors"
    current_mirror = library.lessons[0]
    bandgap = library.lessons[1]
    voltage_reference = library.lessons[2]

    assert current_mirror.id == "current_mirror_types"
    assert len(current_mirror.content_html) > 8_000
    assert "Why current mirrors matter" in (
        current_mirror.content_html
    )

    assert bandgap.id == "bandgap_reference_intro"
    assert len(bandgap.content_html) > 8_000
    assert "Why a stable reference matters" in (
        bandgap.content_html
    )

    assert (
        voltage_reference.id
        == "voltage_reference_fundamentals"
    )
    assert len(voltage_reference.content_html) > 8_000
    assert "What a voltage reference is" in (
        voltage_reference.content_html
    )

    tracks = {
        lesson.track
        for lesson in library.enabled_lessons
    }
    assert {
        "analog_foundations",
        "pll_and_clocking",
        "data_converters",
        "post_silicon_test",
    } <= tracks


def test_sorts_lessons_and_filters_disabled(
    tmp_path: Path,
) -> None:
    path = _write_library(
        tmp_path,
        _valid_library(),
    )

    library = load_learning_library(path)

    assert [
        lesson.id
        for lesson in library.lessons
    ] == [
        "lesson_a",
        "lesson_b",
    ]
    assert [
        lesson.id
        for lesson in library.enabled_lessons
    ] == [
        "lesson_b",
    ]


def test_content_html_is_optional_and_defaults_to_empty(
    tmp_path: Path,
) -> None:
    path = _write_library(
        tmp_path,
        _valid_library(),
    )

    library = load_learning_library(path)

    assert all(
        lesson.content_html == ""
        for lesson in library.lessons
    )


def test_loads_optional_curated_content(
    tmp_path: Path,
) -> None:
    data = _valid_library()
    data["lessons"][0]["content_html"] = (
        "<h2>Current mirror</h2>"
        "<p>A curated offline lesson.</p>"
    )
    path = _write_library(tmp_path, data)

    library = load_learning_library(path)
    lesson = next(
        lesson
        for lesson in library.lessons
        if lesson.id == "lesson_b"
    )

    assert lesson.content_html.startswith(
        "<h2>Current mirror</h2>"
    )
    assert "curated offline lesson" in lesson.content_html


def test_non_string_curated_content_is_rejected(
    tmp_path: Path,
) -> None:
    data = _valid_library()
    data["lessons"][0]["content_html"] = [
        "paragraph one",
        "paragraph two",
    ]
    path = _write_library(tmp_path, data)

    with pytest.raises(
        LearningLibraryError,
        match=r"lessons\[0\]\.content_html must be a string",
    ):
        load_learning_library(path)


def test_missing_library_file_is_rejected(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.yml"

    with pytest.raises(
        LearningLibraryError,
        match="Learning library not found",
    ):
        load_learning_library(missing)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "schema_version",
            2,
            "schema_version must be 1",
        ),
        (
            "selection.daily_count",
            0,
            "daily_count must be at least 1",
        ),
        (
            "selection.rotation",
            "random",
            "rotation must be one of",
        ),
        (
            "selection.timezone",
            "Invalid/Timezone",
            "timezone is invalid",
        ),
    ],
)
def test_invalid_library_settings_are_rejected(
    tmp_path: Path,
    field: str,
    value: Any,
    message: str,
) -> None:
    data = _valid_library()

    if "." in field:
        section, key = field.split(".", maxsplit=1)
        data[section][key] = value
    else:
        data[field] = value

    path = _write_library(tmp_path, data)

    with pytest.raises(
        LearningLibraryError,
        match=message,
    ):
        load_learning_library(path)


def test_duplicate_lesson_ids_are_rejected(
    tmp_path: Path,
) -> None:
    data = _valid_library()
    duplicate = deepcopy(data["lessons"][0])
    duplicate["order"] = 30
    data["lessons"].append(duplicate)

    path = _write_library(tmp_path, data)

    with pytest.raises(
        LearningLibraryError,
        match="Duplicate lesson id: lesson_b",
    ):
        load_learning_library(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "id",
            "Lesson With Spaces",
            "id must use lowercase letters",
        ),
        (
            "url",
            "not-a-url",
            "url must be a valid HTTP or HTTPS URL",
        ),
        (
            "difficulty",
            "expert",
            "difficulty must be one of",
        ),
        (
            "estimated_minutes",
            0,
            "estimated_minutes must be at least 1",
        ),
        (
            "enabled",
            1,
            "enabled must be a boolean",
        ),
    ],
)
def test_invalid_lesson_fields_are_rejected(
    tmp_path: Path,
    field: str,
    value: Any,
    message: str,
) -> None:
    data = _valid_library()
    data["lessons"][0][field] = value

    path = _write_library(tmp_path, data)

    with pytest.raises(
        LearningLibraryError,
        match=message,
    ):
        load_learning_library(path)


def test_duplicate_topics_are_rejected(
    tmp_path: Path,
) -> None:
    data = _valid_library()
    data["lessons"][0]["topics"] = [
        "pll",
        "pll",
    ]

    path = _write_library(tmp_path, data)

    with pytest.raises(
        LearningLibraryError,
        match="contains duplicate value: pll",
    ):
        load_learning_library(path)


def test_enabled_selection_requires_enabled_lesson(
    tmp_path: Path,
) -> None:
    data = _valid_library()

    for lesson in data["lessons"]:
        lesson["enabled"] = False

    path = _write_library(tmp_path, data)

    with pytest.raises(
        LearningLibraryError,
        match="no lessons are enabled",
    ):
        load_learning_library(path)


def test_disabled_selection_allows_zero_daily_count(
    tmp_path: Path,
) -> None:
    data = _valid_library()
    data["selection"]["enabled"] = False
    data["selection"]["daily_count"] = 0

    for lesson in data["lessons"]:
        lesson["enabled"] = False

    path = _write_library(tmp_path, data)
    library = load_learning_library(path)

    assert library.selection.enabled is False
    assert library.selection.daily_count == 0
    assert library.enabled_lessons == ()
