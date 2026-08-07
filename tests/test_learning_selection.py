from __future__ import annotations

from src.learning.discovery import score_learning_article
from src.learning.selection import select_diverse_candidates
from src.models import Article


def _make_candidate(
    *,
    title: str,
    source_id: str,
    category: str,
    url: str,
    source_priority: int = 9,
    source_tags: tuple[str, ...] = (
        "learning_candidate",
        "tutorials",
    ),
):
    article = Article(
        source_id=source_id,
        source_name=source_id,
        category=category,
        source_priority=source_priority,
        source_tags=source_tags,
        title=title,
        url=url,
        external_id=url,
        published_at="2026-08-07T08:00:00Z",
        updated_at=None,
        summary="A practical tutorial and guide.",
        author=None,
        fetched_at="2026-08-07T09:00:00Z",
    )
    return score_learning_article(article)


def test_selection_keeps_highest_ranked_candidates() -> None:
    lower = _make_candidate(
        title="Python Tutorial",
        source_id="source_a",
        category="python",
        url="https://example.com/lower",
        source_priority=8,
    )
    higher = _make_candidate(
        title="Python Tutorial Guide",
        source_id="source_b",
        category="python",
        url="https://example.com/higher",
        source_priority=10,
    )

    result = select_diverse_candidates(
        (lower, higher),
        maximum_selected=2,
    )

    assert result.selected == (higher, lower)


def test_selection_limits_candidates_per_source() -> None:
    candidates = tuple(
        _make_candidate(
            title=f"Python Tutorial {index}",
            source_id="large_source",
            category="python",
            url=f"https://example.com/source-{index}",
        )
        for index in range(5)
    )

    result = select_diverse_candidates(
        candidates,
        maximum_selected=20,
        max_per_source=3,
        max_per_track=20,
    )

    assert len(result.selected) == 3
    assert all(
        candidate.article.source_id == "large_source"
        for candidate in result.selected
    )
    assert result.skipped_source_limit == 2
    assert result.skipped_track_limit == 0


def test_selection_limits_candidates_per_track() -> None:
    candidates = tuple(
        _make_candidate(
            title=f"Python Tutorial {index}",
            source_id=f"source_{index}",
            category="python",
            url=f"https://example.com/track-{index}",
        )
        for index in range(6)
    )

    result = select_diverse_candidates(
        candidates,
        maximum_selected=20,
        max_per_source=20,
        max_per_track=4,
    )

    assert len(result.selected) == 4
    assert all(
        candidate.track == "software_engineering"
        for candidate in result.selected
    )
    assert result.skipped_source_limit == 0
    assert result.skipped_track_limit == 2


def test_selection_allows_multiple_sources_and_tracks() -> None:
    candidates = (
        _make_candidate(
            title="Pytest Tutorial",
            source_id="pythontest",
            category="test_engineering",
            url="https://example.com/pytest",
            source_tags=(
                "learning_candidate",
                "tutorials",
                "pytest",
            ),
        ),
        _make_candidate(
            title="GitHub Actions Tutorial",
            source_id="earthly",
            category="automation_ci",
            url="https://example.com/actions",
        ),
        _make_candidate(
            title="Bash Tutorial",
            source_id="julia_evans",
            category="linux",
            url="https://example.com/bash",
            source_tags=(
                "learning_candidate",
                "tutorials",
                "shell_script",
            ),
        ),
        _make_candidate(
            title="FastAPI Tutorial",
            source_id="testdriven",
            category="python",
            url="https://example.com/fastapi",
        ),
    )

    result = select_diverse_candidates(
        candidates,
        maximum_selected=4,
        max_per_source=1,
        max_per_track=1,
    )

    assert len(result.selected) == 4
    assert {
        candidate.article.source_id
        for candidate in result.selected
    } == {
        "pythontest",
        "earthly",
        "julia_evans",
        "testdriven",
    }


def test_source_limit_is_checked_before_track_limit() -> None:
    candidates = (
        _make_candidate(
            title="Python Tutorial A",
            source_id="same_source",
            category="python",
            url="https://example.com/a",
        ),
        _make_candidate(
            title="Python Tutorial B",
            source_id="same_source",
            category="python",
            url="https://example.com/b",
        ),
        _make_candidate(
            title="Python Tutorial C",
            source_id="other_source",
            category="python",
            url="https://example.com/c",
        ),
    )

    result = select_diverse_candidates(
        candidates,
        maximum_selected=10,
        max_per_source=1,
        max_per_track=1,
    )

    assert len(result.selected) == 1
    assert result.skipped_source_limit == 1
    assert result.skipped_track_limit == 1


def test_selection_stops_at_maximum_selected() -> None:
    candidates = tuple(
        _make_candidate(
            title=f"Guide {index}",
            source_id=f"source_{index}",
            category="open_source",
            url=f"https://example.com/item-{index}",
        )
        for index in range(10)
    )

    result = select_diverse_candidates(
        candidates,
        maximum_selected=3,
        max_per_source=10,
        max_per_track=10,
    )

    assert len(result.selected) == 3


def test_empty_input_returns_empty_selection() -> None:
    result = select_diverse_candidates(())

    assert result.selected == ()
    assert result.top is None
    assert result.skipped_source_limit == 0
    assert result.skipped_track_limit == 0


def test_top_returns_first_selected_candidate() -> None:
    first = _make_candidate(
        title="Pytest Tutorial Guide",
        source_id="source_a",
        category="test_engineering",
        url="https://example.com/first",
        source_priority=10,
        source_tags=(
            "learning_candidate",
            "tutorials",
            "pytest",
        ),
    )
    second = _make_candidate(
        title="Python Tutorial",
        source_id="source_b",
        category="python",
        url="https://example.com/second",
        source_priority=8,
    )

    result = select_diverse_candidates(
        (second, first),
        maximum_selected=2,
    )

    assert result.top == result.selected[0]
    assert result.top == first


def test_invalid_selection_limits_are_rejected() -> None:
    candidate = _make_candidate(
        title="Python Tutorial",
        source_id="source",
        category="python",
        url="https://example.com/article",
    )

    invalid_cases = (
        (
            {"maximum_selected": 0},
            "maximum_selected must be greater than zero",
        ),
        (
            {"max_per_source": 0},
            "max_per_source must be greater than zero",
        ),
        (
            {"max_per_track": 0},
            "max_per_track must be greater than zero",
        ),
    )

    for kwargs, expected_message in invalid_cases:
        try:
            select_diverse_candidates(
                (candidate,),
                **kwargs,
            )
        except ValueError as exc:
            assert str(exc) == expected_message
        else:
            raise AssertionError(
                f"Invalid selection arguments were accepted: {kwargs}"
            )
