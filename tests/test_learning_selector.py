from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.learning.library import (
    LearningLesson,
    LearningLibrary,
    LearningSelection,
)
from src.learning.selector import (
    LearningSelectionError,
    load_learning_history,
    select_learning_lessons,
)


def _lesson(
    lesson_id: str,
    order: int,
    *,
    enabled: bool = True,
) -> LearningLesson:
    return LearningLesson(
        id=lesson_id,
        order=order,
        title=f"Lesson {lesson_id}",
        source_name="Example Source",
        url=f"https://example.com/{lesson_id}",
        track="analog_foundations",
        topics=("analog", lesson_id),
        difficulty="intermediate",
        estimated_minutes=20,
        summary=f"Summary for {lesson_id}.",
        why_it_matters=f"Why {lesson_id} matters.",
        enabled=enabled,
    )


def _library(
    *,
    daily_count: int = 1,
    enabled: bool = True,
    history_source: str = "site_archive",
) -> LearningLibrary:
    return LearningLibrary(
        schema_version=1,
        selection=LearningSelection(
            enabled=enabled,
            daily_count=daily_count,
            rotation="sequential",
            include_in_max_articles=True,
            history_source=history_source,
            timezone="Asia/Ho_Chi_Minh",
        ),
        lessons=(
            _lesson("lesson_a", 10),
            _lesson("lesson_b", 20),
            _lesson("lesson_c", 30),
        ),
    )


def _write_ranked_articles(
    archive_root: Path,
    date: str,
    payload: dict[str, object],
) -> Path:
    year, month, day = date.split("-")
    directory = archive_root / year / month / day
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "ranked_articles.json"
    path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return path


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_selects_first_lesson_without_history(
    tmp_path: Path,
) -> None:
    result = select_learning_lessons(
        _library(),
        archive_root=tmp_path / "archive",
        now=_utc("2026-07-31T01:00:00"),
    )

    assert result.evaluated_date == "2026-07-31"
    assert [
        lesson.id
        for lesson in result.selected_lessons
    ] == ["lesson_a"]
    assert result.previous_lesson_id is None
    assert result.reused_current_edition is False
    assert result.cycle_reset is False
    assert result.history_entries == ()


def test_selects_lesson_after_previous_day(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    _write_ranked_articles(
        archive_root,
        "2026-07-30",
        {
            "learning": {
                "lesson_ids": ["lesson_a"],
            }
        },
    )

    result = select_learning_lessons(
        _library(),
        archive_root=archive_root,
        now=_utc("2026-07-31T01:00:00"),
    )

    assert result.previous_lesson_id == "lesson_a"
    assert result.selected_lessons[0].id == "lesson_b"
    assert result.reused_current_edition is False
    assert result.cycle_reset is False


def test_same_day_rerun_reuses_archived_lesson(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    _write_ranked_articles(
        archive_root,
        "2026-07-30",
        {"learning_lesson_ids": ["lesson_a"]},
    )
    _write_ranked_articles(
        archive_root,
        "2026-07-31",
        {
            "articles": [
                {
                    "learning_lesson_id": "lesson_b",
                }
            ]
        },
    )

    result = select_learning_lessons(
        _library(),
        archive_root=archive_root,
        now=_utc("2026-07-31T08:00:00"),
    )

    assert result.previous_lesson_id == "lesson_a"
    assert result.selected_lessons[0].id == "lesson_b"
    assert result.reused_current_edition is True
    assert result.cycle_reset is False


def test_wraps_to_first_lesson_after_last_lesson(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    _write_ranked_articles(
        archive_root,
        "2026-07-30",
        {
            "learning": {
                "lesson_ids": ["lesson_c"],
            }
        },
    )

    result = select_learning_lessons(
        _library(),
        archive_root=archive_root,
        now=_utc("2026-07-31T01:00:00"),
    )

    assert result.previous_lesson_id == "lesson_c"
    assert result.selected_lessons[0].id == "lesson_a"
    assert result.cycle_reset is True


def test_selects_multiple_lessons_across_cycle_boundary(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    _write_ranked_articles(
        archive_root,
        "2026-07-30",
        {"learning_lesson_ids": ["lesson_b"]},
    )

    result = select_learning_lessons(
        _library(daily_count=2),
        archive_root=archive_root,
        now=_utc("2026-07-31T01:00:00"),
    )

    assert [
        lesson.id
        for lesson in result.selected_lessons
    ] == ["lesson_c", "lesson_a"]
    assert result.cycle_reset is True


def test_disabled_selection_returns_no_lessons(
    tmp_path: Path,
) -> None:
    result = select_learning_lessons(
        _library(enabled=False, daily_count=0),
        archive_root=tmp_path / "archive",
        now=_utc("2026-07-31T01:00:00"),
    )

    assert result.requested_lessons == 0
    assert result.available_lessons == 3
    assert result.selected_lessons == ()
    assert result.reused_current_edition is False


def test_rejects_unsupported_history_source(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        LearningSelectionError,
        match="Unsupported learning history source",
    ):
        select_learning_lessons(
            _library(history_source="database"),
            archive_root=tmp_path / "archive",
            now=_utc("2026-07-31T01:00:00"),
        )


def test_rejects_daily_count_above_enabled_lessons(
    tmp_path: Path,
) -> None:
    library = _library(daily_count=3)
    library = replace(
        library,
        lessons=(
            library.lessons[0],
            replace(library.lessons[1], enabled=False),
            replace(library.lessons[2], enabled=False),
        ),
    )

    with pytest.raises(
        LearningSelectionError,
        match="daily_count must not exceed",
    ):
        select_learning_lessons(
            library,
            archive_root=tmp_path / "archive",
            now=_utc("2026-07-31T01:00:00"),
        )


def test_loads_history_from_archive_manifest(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    ranked_path = _write_ranked_articles(
        archive_root,
        "2026-07-30",
        {
            "learning": {
                "lessons": [
                    {"id": "lesson_a"},
                    {"lesson_id": "lesson_b"},
                ]
            }
        },
    )
    relative_edition = ranked_path.parent.relative_to(
        archive_root
    )
    (archive_root / "index.json").write_text(
        json.dumps(
            {
                "editions": [
                    {
                        "date": "2026-07-30",
                        "path": str(relative_edition),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    history = load_learning_history(archive_root)

    assert len(history) == 1
    assert history[0].date == "2026-07-30"
    assert history[0].lesson_ids == (
        "lesson_a",
        "lesson_b",
    )
    assert history[0].ranked_articles_path == ranked_path


def test_discovers_history_when_manifest_is_missing(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    _write_ranked_articles(
        archive_root,
        "2026-07-29",
        {
            "learning_lesson_ids": [
                "lesson_a",
                "lesson_a",
            ],
            "learning": {
                "lesson_ids": ["lesson_b"],
            },
            "articles": [
                {
                    "learning_lesson_id": "lesson_c",
                }
            ],
        },
    )

    history = load_learning_history(archive_root)

    assert len(history) == 1
    assert history[0].lesson_ids == (
        "lesson_a",
        "lesson_b",
        "lesson_c",
    )


def test_ignores_corrupt_and_unrelated_history_files(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    corrupt_path = (
        archive_root
        / "2026"
        / "07"
        / "29"
        / "ranked_articles.json"
    )
    corrupt_path.parent.mkdir(parents=True)
    corrupt_path.write_text("{not-json", encoding="utf-8")

    _write_ranked_articles(
        archive_root,
        "2026-07-30",
        {"articles": [{"title": "Regular article"}]},
    )

    assert load_learning_history(archive_root) == ()


def test_uses_local_timezone_for_evaluated_date(
    tmp_path: Path,
) -> None:
    result = select_learning_lessons(
        _library(),
        archive_root=tmp_path / "archive",
        now=_utc("2026-07-30T18:30:00"),
    )

    assert result.evaluated_date == "2026-07-31"


def test_summary_reports_selected_ids_and_history_count(
    tmp_path: Path,
) -> None:
    archive_root = tmp_path / "archive"
    _write_ranked_articles(
        archive_root,
        "2026-07-30",
        {"learning_lesson_ids": ["lesson_a"]},
    )

    result = select_learning_lessons(
        _library(),
        archive_root=archive_root,
        now=_utc("2026-07-31T01:00:00"),
    )

    assert result.summary() == {
        "evaluated_date": "2026-07-31",
        "requested_lessons": 1,
        "available_lessons": 3,
        "selected_lessons": 1,
        "selected_lesson_ids": ["lesson_b"],
        "previous_lesson_id": "lesson_a",
        "reused_current_edition": False,
        "cycle_reset": False,
        "history_entries": 1,
    }
