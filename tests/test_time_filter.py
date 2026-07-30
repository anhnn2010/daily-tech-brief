from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.filters.time_filter import filter_articles_by_time
from src.models import Article


NOW = datetime(2026, 7, 30, 2, 0, tzinfo=timezone.utc)


def make_article(
    title: str,
    *,
    published_at: str | None = None,
    updated_at: str | None = None,
) -> Article:
    return Article(
        source_id="example_source",
        source_name="Example Source",
        category="python",
        source_priority=8,
        source_tags=("python",),
        title=title,
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        external_id=None,
        published_at=published_at,
        updated_at=updated_at,
        summary="Example summary",
        author=None,
        fetched_at="2026-07-30T02:00:00Z",
    )


def test_keeps_articles_inside_window_and_on_cutoff() -> None:
    recent = make_article(
        "Recent article",
        published_at="2026-07-30T01:30:00Z",
    )
    on_cutoff = make_article(
        "Cutoff article",
        published_at="2026-07-28T02:00:00Z",
    )
    too_old = make_article(
        "Old article",
        published_at="2026-07-28T01:59:59Z",
    )

    result = filter_articles_by_time(
        [recent, on_cutoff, too_old],
        lookback_hours=48,
        now=NOW,
    )

    assert result.articles == (recent, on_cutoff)
    assert result.too_old_articles == (too_old,)
    assert result.kept_articles == 2
    assert result.total_articles == 3
    assert result.cutoff_at == "2026-07-28T02:00:00Z"


def test_normalizes_timezone_aware_and_naive_dates_to_utc() -> None:
    timezone_aware = make_article(
        "Timezone-aware article",
        published_at="2026-07-28T09:00:00+07:00",
    )
    naive_utc = make_article(
        "Naive UTC article",
        published_at="2026-07-28T02:00:00",
    )

    result = filter_articles_by_time(
        [timezone_aware, naive_utc],
        lookback_hours=48,
        now=NOW,
    )

    assert result.articles == (timezone_aware, naive_utc)
    assert result.too_old_articles == ()


def test_groups_articles_beyond_future_tolerance() -> None:
    tolerated = make_article(
        "Tolerated future article",
        published_at="2026-07-30T02:15:00Z",
    )
    too_far_ahead = make_article(
        "Future article",
        published_at="2026-07-30T02:15:01Z",
    )

    result = filter_articles_by_time(
        [tolerated, too_far_ahead],
        lookback_hours=48,
        now=NOW,
        future_tolerance_minutes=15,
    )

    assert result.articles == (tolerated,)
    assert result.future_articles == (too_far_ahead,)
    assert result.future_limit_at == "2026-07-30T02:15:00Z"


def test_uses_updated_at_when_published_at_is_missing_or_invalid() -> None:
    missing_published = make_article(
        "Missing published date",
        updated_at="2026-07-30T01:00:00Z",
    )
    invalid_published = make_article(
        "Invalid published date",
        published_at="not-a-date",
        updated_at="2026-07-30T00:30:00Z",
    )

    result = filter_articles_by_time(
        [missing_published, invalid_published],
        lookback_hours=48,
        now=NOW,
    )

    assert result.articles == (missing_published, invalid_published)
    assert result.invalid_date_articles == ()


def test_groups_missing_and_invalid_dates_separately() -> None:
    missing = make_article("Missing date")
    invalid = make_article(
        "Invalid date",
        published_at="not-a-date",
        updated_at="still-not-a-date",
    )

    result = filter_articles_by_time(
        [missing, invalid],
        lookback_hours=48,
        now=NOW,
    )

    assert result.missing_date_articles == (missing,)
    assert result.invalid_date_articles == (invalid,)
    assert result.articles == ()
    assert result.summary() == {
        "evaluated_at": "2026-07-30T02:00:00Z",
        "cutoff_at": "2026-07-28T02:00:00Z",
        "future_limit_at": "2026-07-30T02:15:00Z",
        "total_articles": 2,
        "kept_articles": 0,
        "too_old_articles": 0,
        "future_articles": 0,
        "missing_date_articles": 1,
        "invalid_date_articles": 1,
    }


@pytest.mark.parametrize(
    ("lookback_hours", "future_tolerance_minutes", "message"),
    [
        (0, 15, "lookback_hours"),
        (-1, 15, "lookback_hours"),
        (48, -1, "future_tolerance_minutes"),
    ],
)
def test_rejects_invalid_filter_settings(
    lookback_hours: float,
    future_tolerance_minutes: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        filter_articles_by_time(
            [],
            lookback_hours=lookback_hours,
            now=NOW,
            future_tolerance_minutes=future_tolerance_minutes,
        )
