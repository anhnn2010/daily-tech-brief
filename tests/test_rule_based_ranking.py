from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.models import Article
from src.ranking.rule_based import rank_articles


NOW = datetime(2026, 7, 30, 3, 0, tzinfo=timezone.utc)


def make_article(
    *,
    title: str = "Example article",
    summary: str = "",
    category: str = "linux",
    source_priority: int = 5,
    source_tags: tuple[str, ...] = (),
    published_at: str | None = "2026-07-30T01:00:00Z",
    updated_at: str | None = None,
    url: str = "https://example.com/article",
) -> Article:
    return Article(
        source_id="example_source",
        source_name="Example Source",
        category=category,
        source_priority=source_priority,
        source_tags=source_tags,
        title=title,
        url=url,
        external_id=None,
        published_at=published_at,
        updated_at=updated_at,
        summary=summary,
        author=None,
        fetched_at="2026-07-30T03:00:00Z",
    )


def make_profile(
    *,
    linux_weight: int = 10,
    high_priority: list[str] | None = None,
    low_priority: list[str] | None = None,
) -> dict[str, object]:
    return {
        "categories": {
            "linux": {
                "label": "Linux",
                "weight": linux_weight,
                "daily_quota": 2,
            },
            "python": {
                "label": "Python",
                "weight": 8,
                "daily_quota": 2,
            },
        },
        "keywords": {
            "high_priority": high_priority or [],
            "low_priority": low_priority or [],
        },
    }


def test_rank_combines_source_category_and_freshness_scores() -> None:
    result = rank_articles(
        [make_article(source_priority=7)],
        make_profile(linux_weight=9),
        now=NOW,
    )

    ranked = result.articles[0]

    assert ranked.score == 42
    assert ranked.category_weight == 9
    assert ranked.freshness_hours == 2.0
    assert ranked.score_reasons == (
        "Source priority 7: +14",
        "Category weight 9: +18",
        "Published within 6 hours: +10",
    )


@pytest.mark.parametrize(
    ("published_at", "expected_score", "expected_hours"),
    [
        ("2026-07-29T21:00:00Z", 40, 6.0),
        ("2026-07-29T15:00:00Z", 38, 12.0),
        ("2026-07-29T03:00:00Z", 36, 24.0),
        ("2026-07-28T15:00:00Z", 34, 36.0),
        ("2026-07-28T03:00:00Z", 32, 48.0),
        ("2026-07-28T02:59:59Z", 30, 48.0),
    ],
)
def test_freshness_uses_expected_score_bands(
    published_at: str,
    expected_score: int,
    expected_hours: float,
) -> None:
    result = rank_articles(
        [make_article(published_at=published_at)],
        make_profile(),
        now=NOW,
    )

    ranked = result.articles[0]

    assert ranked.score == expected_score
    assert ranked.freshness_hours == expected_hours


def test_high_priority_keywords_score_title_before_summary_and_tags() -> None:
    article = make_article(
        title="GitHub Actions adds a new deployment feature",
        summary="This update also improves Jenkins integration.",
        source_tags=("Arch Linux",),
    )
    profile = make_profile(
        high_priority=["github actions", "jenkins", "arch linux"]
    )

    ranked = rank_articles([article], profile, now=NOW).articles[0]

    assert ranked.score == 56
    assert ranked.matched_high_priority_keywords == (
        "github actions",
        "jenkins",
        "arch linux",
    )
    assert "High-priority keyword in title 'github actions': +8" in (
        ranked.score_reasons
    )
    assert "High-priority keyword in summary/tags 'jenkins': +4" in (
        ranked.score_reasons
    )


def test_high_priority_keyword_bonus_is_capped_at_24() -> None:
    article = make_article(
        title="GitHub Actions Jenkins Arch Linux KDE Plasma",
    )
    profile = make_profile(
        high_priority=[
            "github actions",
            "jenkins",
            "arch linux",
            "kde plasma",
        ]
    )

    ranked = rank_articles([article], profile, now=NOW).articles[0]

    assert ranked.score == 64
    assert len(ranked.matched_high_priority_keywords) == 4
    assert "High-priority keyword bonus capped: 32 -> 24" in (
        ranked.score_reasons
    )


def test_low_priority_keyword_penalty_is_capped_at_12() -> None:
    article = make_article(
        title="Celebrity smartphone rumor and gaming deal",
    )
    profile = make_profile(
        low_priority=["celebrity", "smartphone rumor", "gaming deal"]
    )

    ranked = rank_articles([article], profile, now=NOW).articles[0]

    assert ranked.score == 28
    assert ranked.matched_low_priority_keywords == (
        "celebrity",
        "smartphone rumor",
        "gaming deal",
    )
    assert "Low-priority keyword penalty capped: 18 -> 12" in (
        ranked.score_reasons
    )


def test_keyword_matching_respects_word_boundaries() -> None:
    article = make_article(
        title="Maintainers improve the project",
        summary="The maintenance release is available.",
    )
    profile = make_profile(high_priority=["ai"])

    ranked = rank_articles([article], profile, now=NOW).articles[0]

    assert ranked.score == 40
    assert ranked.matched_high_priority_keywords == ()


def test_updated_at_is_used_when_published_at_is_invalid() -> None:
    article = make_article(
        published_at="not-a-date",
        updated_at="2026-07-29T21:00:00Z",
    )

    ranked = rank_articles([article], make_profile(), now=NOW).articles[0]

    assert ranked.freshness_hours == 6.0
    assert ranked.score == 40


def test_articles_are_sorted_by_score_then_recency() -> None:
    higher_score = make_article(
        title="Higher score",
        category="linux",
        source_priority=8,
        published_at="2026-07-29T15:00:00Z",
        url="https://example.com/higher-score",
    )
    newer_tie = make_article(
        title="Newer tie",
        category="python",
        source_priority=7,
        published_at="2026-07-30T01:00:00Z",
        url="https://example.com/newer-tie",
    )
    older_tie = make_article(
        title="Older tie",
        category="python",
        source_priority=7,
        published_at="2026-07-29T23:00:00Z",
        url="https://example.com/older-tie",
    )

    result = rank_articles(
        [older_tie, newer_tie, higher_score],
        make_profile(),
        now=NOW,
    )

    assert [item.article.title for item in result.articles] == [
        "Higher score",
        "Newer tie",
        "Older tie",
    ]


def test_ranking_result_summary_and_serialization() -> None:
    result = rank_articles(
        [make_article(title="Serialized article")],
        make_profile(high_priority=["serialized article"]),
        now=NOW,
    )

    assert result.summary() == {
        "evaluated_at": "2026-07-30T03:00:00Z",
        "total_articles": 1,
        "top_score": 48,
    }

    payload = result.articles[0].to_dict()
    assert payload["title"] == "Serialized article"
    assert payload["score"] == 48
    assert payload["category_weight"] == 10
    assert payload["matched_high_priority_keywords"] == [
        "serialized article"
    ]
    assert isinstance(payload["score_reasons"], list)


def test_missing_article_category_raises_clear_error() -> None:
    article = make_article(category="semiconductor")

    with pytest.raises(
        ValueError,
        match="Article category 'semiconductor' is missing from profile",
    ):
        rank_articles([article], make_profile(), now=NOW)


def test_profile_validation_rejects_invalid_keyword_configuration() -> None:
    profile = make_profile()
    profile["keywords"] = {"high_priority": "jenkins"}

    with pytest.raises(
        ValueError,
        match="keywords.high_priority must be a list",
    ):
        rank_articles([make_article()], profile, now=NOW)
