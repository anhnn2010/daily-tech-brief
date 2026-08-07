from __future__ import annotations

from datetime import datetime, timezone

from src.learning.discovery import score_learning_article
from src.learning.state_update import merge_candidate_articles
from src.learning.store import LearningState
from src.models import Article


NOW = datetime(
    2026,
    8,
    7,
    11,
    30,
    tzinfo=timezone.utc,
)

LATER = datetime(
    2026,
    8,
    8,
    11,
    30,
    tzinfo=timezone.utc,
)


def _make_candidate(
    *,
    title: str = "Pytest Tutorial",
    url: str = "https://example.com/pytest-tutorial",
    source_id: str = "example_source",
    source_name: str = "Example Source",
    category: str = "test_engineering",
    source_priority: int = 9,
    source_tags: tuple[str, ...] = (
        "learning_candidate",
        "tutorials",
        "pytest",
    ),
    summary: str = "A practical pytest testing guide.",
):
    article = Article(
        source_id=source_id,
        source_name=source_name,
        category=category,
        source_priority=source_priority,
        source_tags=source_tags,
        title=title,
        url=url,
        external_id=url,
        published_at="2026-08-07T08:00:00Z",
        updated_at=None,
        summary=summary,
        author=None,
        fetched_at="2026-08-07T09:00:00Z",
    )
    return score_learning_article(article)


def test_new_candidate_is_added_to_empty_state() -> None:
    candidate = _make_candidate()

    updated = merge_candidate_articles(
        LearningState.empty(),
        (candidate,),
        now=NOW,
    )

    assert len(updated.candidate_articles) == 1

    record = updated.candidate_articles[0]
    assert record["id"] == candidate.id
    assert record["canonical_url"] == candidate.canonical_url
    assert record["status"] == "candidate"
    assert record["first_seen_at"] == "2026-08-07T11:30:00Z"
    assert record["last_seen_at"] == "2026-08-07T11:30:00Z"


def test_rediscovered_candidate_keeps_first_seen_and_refreshes_last_seen() -> None:
    candidate = _make_candidate()
    first_state = merge_candidate_articles(
        LearningState.empty(),
        (candidate,),
        now=NOW,
    )

    updated = merge_candidate_articles(
        first_state,
        (candidate,),
        now=LATER,
    )

    assert len(updated.candidate_articles) == 1

    record = updated.candidate_articles[0]
    assert record["first_seen_at"] == "2026-08-07T11:30:00Z"
    assert record["last_seen_at"] == "2026-08-08T11:30:00Z"


def test_rediscovered_candidate_refreshes_mutable_metadata() -> None:
    original = _make_candidate(
        title="Pytest Tutorial",
        summary="A practical pytest testing guide.",
        source_priority=8,
    )
    first_state = merge_candidate_articles(
        LearningState.empty(),
        (original,),
        now=NOW,
    )

    refreshed = _make_candidate(
        title="Pytest Tutorial Updated",
        summary=(
            "A deep dive and best practices guide for pytest "
            "testing and debugging."
        ),
        source_priority=10,
    )

    updated = merge_candidate_articles(
        first_state,
        (refreshed,),
        now=LATER,
    )

    record = updated.candidate_articles[0]

    assert record["title"] == "Pytest Tutorial Updated"
    assert record["score"] == refreshed.score
    assert record["positive_signals"] == list(
        refreshed.positive_signals
    )
    assert record["first_seen_at"] == "2026-08-07T11:30:00Z"
    assert record["last_seen_at"] == "2026-08-08T11:30:00Z"


def test_existing_candidate_not_seen_today_is_preserved() -> None:
    candidate = _make_candidate()
    first_state = merge_candidate_articles(
        LearningState.empty(),
        (candidate,),
        now=NOW,
    )

    updated = merge_candidate_articles(
        first_state,
        (),
        now=LATER,
    )

    assert updated.candidate_articles == first_state.candidate_articles


def test_new_candidates_are_placed_before_older_candidates() -> None:
    old_candidate = _make_candidate(
        title="Old Tutorial",
        url="https://example.com/old",
    )
    first_state = merge_candidate_articles(
        LearningState.empty(),
        (old_candidate,),
        now=NOW,
    )

    new_candidate = _make_candidate(
        title="New Tutorial",
        url="https://example.com/new",
    )

    updated = merge_candidate_articles(
        first_state,
        (new_candidate,),
        now=LATER,
    )

    assert [
        record["title"]
        for record in updated.candidate_articles
    ] == [
        "New Tutorial",
        "Old Tutorial",
    ]


def test_rediscovered_candidate_moves_to_front() -> None:
    first = _make_candidate(
        title="First Tutorial",
        url="https://example.com/first",
    )
    second = _make_candidate(
        title="Second Tutorial",
        url="https://example.com/second",
    )

    initial = merge_candidate_articles(
        LearningState.empty(),
        (first, second),
        now=NOW,
    )

    updated = merge_candidate_articles(
        initial,
        (second,),
        now=LATER,
    )

    assert [
        record["title"]
        for record in updated.candidate_articles
    ] == [
        "Second Tutorial",
        "First Tutorial",
    ]


def test_used_candidate_is_removed_by_id() -> None:
    candidate = _make_candidate()
    state_with_candidate = merge_candidate_articles(
        LearningState.empty(),
        (candidate,),
        now=NOW,
    )

    state_with_used = LearningState(
        schema_version=state_with_candidate.schema_version,
        updated_at=state_with_candidate.updated_at,
        candidate_articles=state_with_candidate.candidate_articles,
        used_articles=(
            {
                "id": candidate.id,
                "canonical_url": candidate.canonical_url,
                "used_at": "2026-08-08T07:00:00Z",
            },
        ),
        candidate_sources=(),
    )

    updated = merge_candidate_articles(
        state_with_used,
        (),
        now=LATER,
    )

    assert updated.candidate_articles == ()


def test_used_candidate_is_removed_by_canonical_url() -> None:
    candidate = _make_candidate(
        url=(
            "https://example.com/tutorial"
            "?utm_source=digest"
        )
    )
    state_with_candidate = merge_candidate_articles(
        LearningState.empty(),
        (candidate,),
        now=NOW,
    )

    state_with_used = LearningState(
        schema_version=1,
        updated_at=None,
        candidate_articles=state_with_candidate.candidate_articles,
        used_articles=(
            {
                "url": (
                    "https://example.com/tutorial"
                    "?utm_source=old"
                ),
                "used_at": "2026-08-08T07:00:00Z",
            },
        ),
        candidate_sources=(),
    )

    updated = merge_candidate_articles(
        state_with_used,
        (),
        now=LATER,
    )

    assert updated.candidate_articles == ()


def test_incoming_candidate_already_used_is_not_added() -> None:
    candidate = _make_candidate()

    state = LearningState(
        schema_version=1,
        updated_at=None,
        candidate_articles=(),
        used_articles=(
            {
                "id": candidate.id,
                "canonical_url": candidate.canonical_url,
            },
        ),
        candidate_sources=(),
    )

    updated = merge_candidate_articles(
        state,
        (candidate,),
        now=NOW,
    )

    assert updated.candidate_articles == ()


def test_duplicate_incoming_candidate_is_merged_once() -> None:
    candidate = _make_candidate()

    updated = merge_candidate_articles(
        LearningState.empty(),
        (candidate, candidate),
        now=NOW,
    )

    assert len(updated.candidate_articles) == 1
    assert updated.candidate_articles[0]["id"] == candidate.id


def test_existing_record_without_canonical_url_is_normalized() -> None:
    candidate = _make_candidate(
        url=(
            "https://example.com/tutorial"
            "?utm_source=newsletter"
        )
    )

    existing_state = LearningState(
        schema_version=1,
        updated_at=None,
        candidate_articles=(
            {
                "title": "Existing Tutorial",
                "url": (
                    "https://example.com/tutorial"
                    "?utm_source=old"
                ),
                "status": "candidate",
                "first_seen_at": "2026-08-01T00:00:00Z",
            },
        ),
        used_articles=(),
        candidate_sources=(),
    )

    updated = merge_candidate_articles(
        existing_state,
        (candidate,),
        now=NOW,
    )

    assert len(updated.candidate_articles) == 1

    record = updated.candidate_articles[0]
    assert record["id"] == candidate.id
    assert record["canonical_url"] == candidate.canonical_url
    assert record["first_seen_at"] == "2026-08-01T00:00:00Z"


def test_other_state_sections_are_preserved() -> None:
    candidate = _make_candidate()

    state = LearningState(
        schema_version=1,
        updated_at="2026-08-06T00:00:00Z",
        candidate_articles=(),
        used_articles=(
            {
                "id": "used-article",
            },
        ),
        candidate_sources=(
            {
                "id": "candidate-source",
                "status": "probation",
            },
        ),
    )

    updated = merge_candidate_articles(
        state,
        (candidate,),
        now=NOW,
    )

    assert updated.schema_version == state.schema_version
    assert updated.updated_at == state.updated_at
    assert updated.used_articles == state.used_articles
    assert updated.candidate_sources == state.candidate_sources


def test_naive_datetime_is_rejected() -> None:
    candidate = _make_candidate()

    try:
        merge_candidate_articles(
            LearningState.empty(),
            (candidate,),
            now=datetime(2026, 8, 7, 11, 30),
        )
    except ValueError as exc:
        assert str(exc) == "now must include a timezone"
    else:
        raise AssertionError("naive datetime was accepted")
