from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.learning.article import (
    is_learning_article,
    learning_lesson_id_from_article,
    learning_lesson_to_article,
    learning_lessons_to_articles,
)
from src.learning.library import LearningLesson
from src.models import Article


def _lesson(
    *,
    lesson_id: str = "pll_fundamentals",
    order: int = 10,
    track: str = "pll_and_clocking",
    topics: tuple[str, ...] = (
        "pll",
        "clocking",
    ),
) -> LearningLesson:
    return LearningLesson(
        id=lesson_id,
        order=order,
        title="Phase-Locked Loop Fundamentals",
        source_name="Analog Devices",
        url="https://example.com/pll-fundamentals",
        track=track,
        topics=topics,
        difficulty="intermediate",
        estimated_minutes=30,
        summary=(
            "Introduces the main PLL blocks and their closed-loop behavior."
        ),
        why_it_matters=(
            "It provides a structure for debugging lock and clock issues."
        ),
        enabled=True,
    )


def _normal_article() -> Article:
    return Article(
        source_id="example_source",
        source_name="Example Source",
        category="ai",
        source_priority=5,
        source_tags=("example",),
        title="A normal article",
        url="https://example.com/article",
        external_id="article-1",
        published_at="2026-07-31T00:00:00Z",
        updated_at=None,
        summary="Normal article summary.",
        author="Example Author",
        fetched_at="2026-07-31T01:00:00Z",
    )


def test_converts_analog_lesson_to_article() -> None:
    generated_at = datetime(
        2026,
        7,
        31,
        13,
        24,
        tzinfo=timezone(timedelta(hours=7)),
    )

    article = learning_lesson_to_article(
        _lesson(),
        generated_at=generated_at,
    )

    assert article.source_id == "technical_learning"
    assert article.source_name == "Analog Devices"
    assert article.category == "analog_mixed_signal"
    assert article.source_priority == 10
    assert article.title == "Phase-Locked Loop Fundamentals"
    assert article.url == "https://example.com/pll-fundamentals"
    assert article.external_id == "learning:pll_fundamentals"
    assert article.published_at is None
    assert article.updated_at is None
    assert article.author is None
    assert article.fetched_at == "2026-07-31T06:24:00Z"

    assert article.source_tags == (
        "technical_learning",
        "learning_lesson_id:pll_fundamentals",
        "learning_track:pll_and_clocking",
        "difficulty:intermediate",
        "estimated_minutes:30",
        "pll",
        "clocking",
    )

    assert "Why it matters:" in article.summary
    assert "Estimated reading time: 30 minutes." in article.summary
    assert article.summary.endswith("Difficulty: intermediate.")


def test_maps_post_silicon_track_to_test_engineering() -> None:
    article = learning_lesson_to_article(
        _lesson(
            lesson_id="device_validation",
            track="post_silicon_test",
            topics=("validation", "ate"),
        ),
        generated_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    assert article.category == "test_engineering"


def test_converts_multiple_lessons_in_original_order() -> None:
    generated_at = datetime(2026, 7, 31, 6, 0, tzinfo=timezone.utc)
    lessons = (
        _lesson(lesson_id="lesson_b", order=20),
        _lesson(lesson_id="lesson_a", order=10),
    )

    articles = learning_lessons_to_articles(
        lessons,
        generated_at=generated_at,
    )

    assert [article.external_id for article in articles] == [
        "learning:lesson_b",
        "learning:lesson_a",
    ]
    assert {
        article.fetched_at
        for article in articles
    } == {
        "2026-07-31T06:00:00Z",
    }


def test_supports_custom_track_category_mapping() -> None:
    article = learning_lesson_to_article(
        _lesson(track="custom_track"),
        generated_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        category_by_track={
            "custom_track": "custom_category",
        },
    )

    assert article.category == "custom_category"


def test_unknown_track_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="No article category is configured",
    ):
        learning_lesson_to_article(
            _lesson(track="unknown_track"),
        )


@pytest.mark.parametrize(
    "source_priority",
    [
        0,
        11,
        True,
        5.5,
    ],
)
def test_invalid_source_priority_is_rejected(
    source_priority: object,
) -> None:
    with pytest.raises(
        ValueError,
        match="source_priority must be an integer between 1 and 10",
    ):
        learning_lesson_to_article(
            _lesson(),
            source_priority=source_priority,  # type: ignore[arg-type]
        )


def test_recovers_lesson_id_from_external_id_and_tag() -> None:
    article = learning_lesson_to_article(_lesson())

    assert (
        learning_lesson_id_from_article(article)
        == "pll_fundamentals"
    )
    assert is_learning_article(article) is True


def test_recovers_lesson_id_from_tag_only() -> None:
    article = replace(
        _normal_article(),
        external_id=None,
        source_tags=(
            "technical_learning",
            "learning_lesson_id:bandgap_reference_intro",
        ),
    )

    assert (
        learning_lesson_id_from_article(article)
        == "bandgap_reference_intro"
    )
    assert is_learning_article(article) is True


def test_normal_article_is_not_learning_article() -> None:
    article = _normal_article()

    assert learning_lesson_id_from_article(article) is None
    assert is_learning_article(article) is False


def test_conflicting_external_and_tag_lesson_ids_are_rejected() -> None:
    article = replace(
        _normal_article(),
        external_id="learning:lesson_a",
        source_tags=(
            "learning_lesson_id:lesson_b",
        ),
    )

    with pytest.raises(
        ValueError,
        match="conflicting lesson IDs",
    ):
        learning_lesson_id_from_article(article)


def test_multiple_different_lesson_tags_are_rejected() -> None:
    article = replace(
        _normal_article(),
        external_id=None,
        source_tags=(
            "learning_lesson_id:lesson_a",
            "learning_lesson_id:lesson_b",
        ),
    )

    with pytest.raises(
        ValueError,
        match="conflicting lesson IDs",
    ):
        learning_lesson_id_from_article(article)


def test_duplicate_generated_tags_are_removed() -> None:
    article = learning_lesson_to_article(
        _lesson(
            topics=(
                "technical_learning",
                "pll",
                "pll",
            ),
        )
    )

    assert article.source_tags.count("technical_learning") == 1
    assert article.source_tags.count("pll") == 1


def test_naive_generated_at_is_treated_as_utc() -> None:
    article = learning_lesson_to_article(
        _lesson(),
        generated_at=datetime(2026, 7, 31, 6, 24, 30),
    )

    assert article.fetched_at == "2026-07-31T06:24:30Z"
