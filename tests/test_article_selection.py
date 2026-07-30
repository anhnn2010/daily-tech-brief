from __future__ import annotations

import pytest

from src.models import Article
from src.ranking.rule_based import RankedArticle
from src.ranking.selection import select_articles_by_category_quota


def make_ranked_article(
    title: str,
    category: str,
    score: int,
) -> RankedArticle:
    article = Article(
        source_id=f"{category}_source",
        source_name=f"{category.title()} Source",
        category=category,
        source_priority=5,
        source_tags=(),
        title=title,
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        external_id=None,
        published_at="2026-07-30T01:00:00Z",
        updated_at=None,
        summary="",
        author=None,
        fetched_at="2026-07-30T03:00:00Z",
    )
    return RankedArticle(
        article=article,
        score=score,
        category_weight=10,
        freshness_hours=2.0,
        matched_high_priority_keywords=(),
        matched_low_priority_keywords=(),
        score_reasons=(),
    )


def make_profile() -> dict[str, object]:
    return {
        "categories": {
            "ai": {
                "label": "AI",
                "weight": 10,
                "daily_quota": 1,
            },
            "linux": {
                "label": "Linux",
                "weight": 10,
                "daily_quota": 1,
            },
            "python": {
                "label": "Python",
                "weight": 9,
                "daily_quota": 1,
            },
            "hardware": {
                "label": "Hardware",
                "weight": 5,
                "daily_quota": 0,
            },
        }
    }


def test_selection_respects_quotas_then_fills_unused_slots() -> None:
    ranked = [
        make_ranked_article("AI one", "ai", 100),
        make_ranked_article("AI two", "ai", 95),
        make_ranked_article("Linux one", "linux", 90),
        make_ranked_article("Python one", "python", 85),
        make_ranked_article("Linux two", "linux", 80),
    ]

    result = select_articles_by_category_quota(
        ranked,
        make_profile(),
        max_articles=4,
    )

    assert [item.article.title for item in result.articles] == [
        "AI one",
        "AI two",
        "Linux one",
        "Python one",
    ]
    assert result.selected_within_quota == 3
    assert result.selected_from_overflow == 1
    assert result.category_counts == {
        "ai": 2,
        "linux": 1,
        "python": 1,
        "hardware": 0,
    }
    assert [item.article.title for item in result.deferred_articles] == [
        "Linux two"
    ]


def test_selection_can_leave_unused_slots_when_overflow_is_disabled() -> None:
    ranked = [
        make_ranked_article("AI one", "ai", 100),
        make_ranked_article("AI two", "ai", 95),
        make_ranked_article("Linux one", "linux", 90),
    ]

    result = select_articles_by_category_quota(
        ranked,
        make_profile(),
        max_articles=4,
        fill_unused_slots=False,
    )

    assert [item.article.title for item in result.articles] == [
        "AI one",
        "Linux one",
    ]
    assert result.selected_from_overflow == 0
    assert result.deferred_count == 1


def test_zero_quota_category_is_never_selected() -> None:
    ranked = [
        make_ranked_article("Hardware one", "hardware", 120),
        make_ranked_article("AI one", "ai", 100),
        make_ranked_article("Hardware two", "hardware", 95),
    ]

    result = select_articles_by_category_quota(
        ranked,
        make_profile(),
        max_articles=3,
    )

    assert [item.article.title for item in result.articles] == ["AI one"]
    assert result.category_counts["hardware"] == 0
    assert [item.article.title for item in result.deferred_articles] == [
        "Hardware one",
        "Hardware two",
    ]


def test_selection_stops_at_global_article_limit() -> None:
    ranked = [
        make_ranked_article("AI one", "ai", 100),
        make_ranked_article("Linux one", "linux", 90),
        make_ranked_article("Python one", "python", 80),
    ]

    result = select_articles_by_category_quota(
        ranked,
        make_profile(),
        max_articles=2,
    )

    assert [item.article.title for item in result.articles] == [
        "AI one",
        "Linux one",
    ]
    assert result.deferred_count == 1


def test_selection_accepts_a_generator() -> None:
    ranked = (
        make_ranked_article(title, category, score)
        for title, category, score in [
            ("AI one", "ai", 100),
            ("Linux one", "linux", 90),
        ]
    )

    result = select_articles_by_category_quota(
        ranked,
        make_profile(),
        max_articles=2,
    )

    assert result.available_articles == 2
    assert result.selected_articles == 2


def test_selection_summary_reports_counts_and_quotas() -> None:
    result = select_articles_by_category_quota(
        [
            make_ranked_article("AI one", "ai", 100),
            make_ranked_article("AI two", "ai", 95),
            make_ranked_article("Linux one", "linux", 90),
        ],
        make_profile(),
        max_articles=3,
    )

    assert result.summary() == {
        "requested_max_articles": 3,
        "available_articles": 3,
        "selected_articles": 3,
        "deferred_articles": 0,
        "selected_within_quota": 2,
        "selected_from_overflow": 1,
        "category_quotas": {
            "ai": 1,
            "linux": 1,
            "python": 1,
            "hardware": 0,
        },
        "category_counts": {
            "ai": 2,
            "linux": 1,
            "python": 0,
            "hardware": 0,
        },
    }


def test_missing_article_category_raises_clear_error() -> None:
    ranked = [make_ranked_article("Chip article", "semiconductor", 100)]

    with pytest.raises(
        ValueError,
        match="Article category 'semiconductor' is missing from profile",
    ):
        select_articles_by_category_quota(
            ranked,
            make_profile(),
            max_articles=1,
        )


@pytest.mark.parametrize("max_articles", [0, -1, True, 1.5])
def test_invalid_max_articles_is_rejected(max_articles: object) -> None:
    with pytest.raises(
        ValueError,
        match="max_articles must be a positive integer",
    ):
        select_articles_by_category_quota(
            [],
            make_profile(),
            max_articles=max_articles,  # type: ignore[arg-type]
        )


def test_invalid_fill_unused_slots_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="fill_unused_slots must be a boolean",
    ):
        select_articles_by_category_quota(
            [],
            make_profile(),
            max_articles=1,
            fill_unused_slots="yes",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("daily_quota", [-1, 1.5, True, None])
def test_invalid_daily_quota_is_rejected(daily_quota: object) -> None:
    profile = make_profile()
    profile["categories"]["ai"]["daily_quota"] = daily_quota  # type: ignore[index]

    with pytest.raises(
        ValueError,
        match=(
            "Category 'ai' daily_quota must be a non-negative integer"
        ),
    ):
        select_articles_by_category_quota(
            [],
            profile,
            max_articles=1,
        )
