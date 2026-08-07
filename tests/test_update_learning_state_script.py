from __future__ import annotations

import json
from pathlib import Path

from scripts.update_learning_state import (
    load_raw_articles,
    update_learning_state,
)
from src.learning.store import LearningState, LearningStateStore


def _write_raw_articles(path: Path) -> None:
    payload = {
        "schema_version": 1,
        "generated_at": "2026-08-07T10:00:00Z",
        "articles": [
            {
                "source_id": "pythontest_blog",
                "source_name": "PythonTest",
                "category": "test_engineering",
                "source_priority": 10,
                "source_tags": [
                    "learning_candidate",
                    "tutorials",
                    "pytest",
                ],
                "title": "Pytest Fixtures Tutorial",
                "url": "https://example.com/pytest-fixtures/",
                "external_id": "pytest-fixtures",
                "published_at": "2026-08-07T08:00:00Z",
                "updated_at": None,
                "summary": (
                    "A practical guide to pytest fixtures, "
                    "testing, and debugging."
                ),
                "author": "Example Author",
                "fetched_at": "2026-08-07T09:00:00Z",
                "content_html": "",
                "content_text": "",
                "content_status": "not_requested",
            },
            {
                "source_id": "earthly_blog",
                "source_name": "Earthly Blog",
                "category": "automation_ci",
                "source_priority": 9,
                "source_tags": [
                    "learning_candidate",
                    "tutorials",
                    "ci",
                ],
                "title": "GitHub Actions CI/CD Guide",
                "url": "https://example.com/github-actions/",
                "external_id": "github-actions",
                "published_at": "2026-08-07T07:00:00Z",
                "updated_at": None,
                "summary": (
                    "A tutorial for GitHub Actions build automation "
                    "and CI/CD pipelines."
                ),
                "author": None,
                "fetched_at": "2026-08-07T09:00:00Z",
                "content_html": "",
                "content_text": "",
                "content_status": "not_requested",
            },
            {
                "source_id": "company_news",
                "source_name": "Company News",
                "category": "open_source",
                "source_priority": 5,
                "source_tags": [],
                "title": "Quarterly Earnings Announcement",
                "url": "https://example.com/earnings/",
                "external_id": "earnings",
                "published_at": "2026-08-07T06:00:00Z",
                "updated_at": None,
                "summary": "Quarterly earnings announcement.",
                "author": None,
                "fetched_at": "2026-08-07T09:00:00Z",
                "content_html": "",
                "content_text": "",
                "content_status": "not_requested",
            },
        ],
    }

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_load_raw_articles_builds_article_objects(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "raw_articles.json"
    _write_raw_articles(input_path)

    articles = load_raw_articles(input_path)

    assert len(articles) == 3
    assert articles[0].source_id == "pythontest_blog"
    assert articles[0].title == "Pytest Fixtures Tutorial"
    assert articles[0].source_tags == (
        "learning_candidate",
        "tutorials",
        "pytest",
    )


def test_dry_run_does_not_create_state_file(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "raw_articles.json"
    state_path = tmp_path / "learning_state.json"
    _write_raw_articles(input_path)

    articles = load_raw_articles(input_path)

    summary = update_learning_state(
        articles=articles,
        state_path=state_path,
        minimum_score=12,
        limit=20,
        max_per_source=3,
        max_per_track=4,
        dry_run=True,
    )

    assert summary["input_articles"] == 3
    assert summary["selected_candidate_count"] == 2
    assert summary["new_candidate_count"] == 2
    assert summary["persisted_candidate_count"] == 2
    assert summary["dry_run"] is True
    assert summary["updated_at"] is None
    assert not state_path.exists()


def test_real_run_creates_learning_state(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "raw_articles.json"
    state_path = tmp_path / "learning_state.json"
    _write_raw_articles(input_path)

    articles = load_raw_articles(input_path)

    summary = update_learning_state(
        articles=articles,
        state_path=state_path,
        minimum_score=12,
        limit=20,
        max_per_source=3,
        max_per_track=4,
        dry_run=False,
    )

    assert state_path.is_file()
    assert summary["previous_candidate_count"] == 0
    assert summary["new_candidate_count"] == 2
    assert summary["removed_candidate_count"] == 0
    assert summary["persisted_candidate_count"] == 2
    assert summary["updated_at"] is not None

    state = LearningStateStore(state_path).load()

    assert len(state.candidate_articles) == 2
    assert {
        record["title"]
        for record in state.candidate_articles
    } == {
        "Pytest Fixtures Tutorial",
        "GitHub Actions CI/CD Guide",
    }


def test_second_run_does_not_duplicate_candidates(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "raw_articles.json"
    state_path = tmp_path / "learning_state.json"
    _write_raw_articles(input_path)

    articles = load_raw_articles(input_path)

    first = update_learning_state(
        articles=articles,
        state_path=state_path,
        minimum_score=12,
        limit=20,
        max_per_source=3,
        max_per_track=4,
        dry_run=False,
    )
    second = update_learning_state(
        articles=articles,
        state_path=state_path,
        minimum_score=12,
        limit=20,
        max_per_source=3,
        max_per_track=4,
        dry_run=False,
    )

    assert first["new_candidate_count"] == 2
    assert second["previous_candidate_count"] == 2
    assert second["new_candidate_count"] == 0
    assert second["persisted_candidate_count"] == 2

    state = LearningStateStore(state_path).load()

    assert len(state.candidate_articles) == 2


def test_used_article_is_not_reintroduced(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "raw_articles.json"
    state_path = tmp_path / "learning_state.json"
    _write_raw_articles(input_path)

    articles = load_raw_articles(input_path)

    update_learning_state(
        articles=articles,
        state_path=state_path,
        minimum_score=12,
        limit=20,
        max_per_source=3,
        max_per_track=4,
        dry_run=False,
    )

    store = LearningStateStore(state_path)
    state = store.load()

    used_record = dict(state.candidate_articles[0])
    used_record["status"] = "used"
    used_record["used_at"] = "2026-08-07T12:00:00Z"

    state_with_used = LearningState(
        schema_version=state.schema_version,
        updated_at=state.updated_at,
        candidate_articles=state.candidate_articles,
        used_articles=(used_record,),
        candidate_sources=state.candidate_sources,
    )
    store.save(state_with_used)

    summary = update_learning_state(
        articles=articles,
        state_path=state_path,
        minimum_score=12,
        limit=20,
        max_per_source=3,
        max_per_track=4,
        dry_run=False,
    )

    updated = store.load()

    assert summary["skipped_used_count"] == 1
    assert len(updated.used_articles) == 1
    assert len(updated.candidate_articles) == 1
    assert used_record["id"] not in {
        record["id"]
        for record in updated.candidate_articles
    }


def test_selection_limits_are_applied_before_persistence(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "raw_articles.json"
    state_path = tmp_path / "learning_state.json"

    payload = {
        "schema_version": 1,
        "articles": [],
    }

    for index in range(5):
        payload["articles"].append(
            {
                "source_id": "large_source",
                "source_name": "Large Source",
                "category": "test_engineering",
                "source_priority": 10,
                "source_tags": [
                    "learning_candidate",
                    "tutorials",
                    "pytest",
                ],
                "title": f"Pytest Tutorial {index}",
                "url": f"https://example.com/tutorial-{index}/",
                "external_id": f"tutorial-{index}",
                "published_at": "2026-08-07T08:00:00Z",
                "updated_at": None,
                "summary": "A practical pytest testing guide.",
                "author": None,
                "fetched_at": "2026-08-07T09:00:00Z",
                "content_html": "",
                "content_text": "",
                "content_status": "not_requested",
            }
        )

    input_path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    articles = load_raw_articles(input_path)

    summary = update_learning_state(
        articles=articles,
        state_path=state_path,
        minimum_score=12,
        limit=20,
        max_per_source=2,
        max_per_track=4,
        dry_run=False,
    )

    state = LearningStateStore(state_path).load()

    assert summary["discovered_candidate_count"] == 5
    assert summary["selected_candidate_count"] == 2
    assert summary["persisted_candidate_count"] == 2
    assert summary["skipped_source_limit"] == 3
    assert len(state.candidate_articles) == 2
