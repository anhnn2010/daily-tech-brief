from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.learning.store import (
    LEARNING_STATE_SCHEMA_VERSION,
    LearningState,
    LearningStateStore,
    LearningStateStoreError,
)


NOW = datetime(
    2026,
    8,
    7,
    10,
    30,
    tzinfo=timezone.utc,
)


def test_missing_state_file_returns_empty_state(
    tmp_path: Path,
) -> None:
    store = LearningStateStore(
        tmp_path / "learning_state.json"
    )

    state = store.load()

    assert state == LearningState.empty()
    assert state.schema_version == LEARNING_STATE_SCHEMA_VERSION
    assert state.updated_at is None
    assert state.candidate_articles == ()
    assert state.used_articles == ()
    assert state.candidate_sources == ()


def test_save_and_load_round_trip(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning-data" / "learning_state.json"
    store = LearningStateStore(path)
    state = LearningState(
        schema_version=LEARNING_STATE_SCHEMA_VERSION,
        updated_at=None,
        candidate_articles=(
            {
                "id": "article-1",
                "title": "Bash Error Handling",
                "score": 18,
                "status": "candidate",
            },
        ),
        used_articles=(
            {
                "id": "article-old",
                "used_date": "2026-08-06",
            },
        ),
        candidate_sources=(
            {
                "id": "example_source",
                "status": "probation",
            },
        ),
    )

    persisted = store.save(
        state,
        now=NOW,
    )
    loaded = store.load()

    assert persisted.updated_at == "2026-08-07T10:30:00Z"
    assert loaded == persisted
    assert path.is_file()


def test_saved_json_has_expected_top_level_shape(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning_state.json"
    store = LearningStateStore(path)

    store.save(
        LearningState.empty(),
        now=NOW,
    )

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert payload == {
        "schema_version": 1,
        "updated_at": "2026-08-07T10:30:00Z",
        "candidate_articles": [],
        "used_articles": [],
        "candidate_sources": [],
    }


def test_save_creates_parent_directory(
    tmp_path: Path,
) -> None:
    path = (
        tmp_path
        / "nested"
        / "learning-data"
        / "learning_state.json"
    )
    store = LearningStateStore(path)

    store.save(
        LearningState.empty(),
        now=NOW,
    )

    assert path.is_file()


def test_save_normalizes_timestamp_to_utc(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning_state.json"
    store = LearningStateStore(path)
    local_time = datetime.fromisoformat(
        "2026-08-07T17:30:00+07:00"
    )

    persisted = store.save(
        LearningState.empty(),
        now=local_time,
    )

    assert persisted.updated_at == "2026-08-07T10:30:00Z"


def test_load_normalizes_existing_timestamp_to_utc(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning_state.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "2026-08-07T17:30:00+07:00",
                "candidate_articles": [],
                "used_articles": [],
                "candidate_sources": [],
            }
        ),
        encoding="utf-8",
    )

    state = LearningStateStore(path).load()

    assert state.updated_at == "2026-08-07T10:30:00Z"


def test_invalid_json_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning_state.json"
    path.write_text(
        "{invalid-json",
        encoding="utf-8",
    )

    with pytest.raises(
        LearningStateStoreError,
        match="invalid JSON",
    ):
        LearningStateStore(path).load()


def test_unsupported_schema_version_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning_state.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "updated_at": None,
                "candidate_articles": [],
                "used_articles": [],
                "candidate_sources": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        LearningStateStoreError,
        match="Unsupported learning state schema_version",
    ):
        LearningStateStore(path).load()


@pytest.mark.parametrize(
    "field",
    (
        "candidate_articles",
        "used_articles",
        "candidate_sources",
    ),
)
def test_state_lists_must_be_lists(
    tmp_path: Path,
    field: str,
) -> None:
    payload = {
        "schema_version": 1,
        "updated_at": None,
        "candidate_articles": [],
        "used_articles": [],
        "candidate_sources": [],
    }
    payload[field] = {}

    path = tmp_path / "learning_state.json"
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(
        LearningStateStoreError,
        match=rf"{field} must be a list",
    ):
        LearningStateStore(path).load()


@pytest.mark.parametrize(
    "field",
    (
        "candidate_articles",
        "used_articles",
        "candidate_sources",
    ),
)
def test_state_list_items_must_be_objects(
    tmp_path: Path,
    field: str,
) -> None:
    payload = {
        "schema_version": 1,
        "updated_at": None,
        "candidate_articles": [],
        "used_articles": [],
        "candidate_sources": [],
    }
    payload[field] = ["invalid-record"]

    path = tmp_path / "learning_state.json"
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(
        LearningStateStoreError,
        match=rf"{field}\[0\] must be an object",
    ):
        LearningStateStore(path).load()


@pytest.mark.parametrize(
    "updated_at",
    (
        "",
        "not-a-timestamp",
        "2026-08-07T10:30:00",
    ),
)
def test_invalid_updated_at_is_rejected(
    tmp_path: Path,
    updated_at: str,
) -> None:
    path = tmp_path / "learning_state.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": updated_at,
                "candidate_articles": [],
                "used_articles": [],
                "candidate_sources": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(LearningStateStoreError):
        LearningStateStore(path).load()


def test_save_rejects_naive_datetime(
    tmp_path: Path,
) -> None:
    store = LearningStateStore(
        tmp_path / "learning_state.json"
    )

    with pytest.raises(
        LearningStateStoreError,
        match="now must include a timezone",
    ):
        store.save(
            LearningState.empty(),
            now=datetime(2026, 8, 7, 10, 30),
        )


def test_save_rejects_non_state_value(
    tmp_path: Path,
) -> None:
    store = LearningStateStore(
        tmp_path / "learning_state.json"
    )

    with pytest.raises(
        LearningStateStoreError,
        match="state must be a LearningState instance",
    ):
        store.save(  # type: ignore[arg-type]
            {"schema_version": 1}
        )


def test_save_replaces_existing_file_without_leaving_tmp(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning_state.json"
    store = LearningStateStore(path)

    store.save(
        LearningState.empty(),
        now=NOW,
    )

    updated_state = LearningState(
        schema_version=1,
        updated_at=None,
        candidate_articles=(
            {
                "id": "article-2",
                "status": "candidate",
            },
        ),
        used_articles=(),
        candidate_sources=(),
    )

    store.save(
        updated_state,
        now=NOW,
    )

    loaded = store.load()
    temporary_path = path.with_name(
        f".{path.name}.tmp"
    )

    assert loaded.candidate_articles == (
        {
            "id": "article-2",
            "status": "candidate",
        },
    )
    assert not temporary_path.exists()
