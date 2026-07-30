from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from src.models import Article


@dataclass(frozen=True)
class TimeFilterResult:
    """Articles grouped by their publication time status."""

    evaluated_at: str
    cutoff_at: str
    future_limit_at: str
    articles: tuple[Article, ...]
    too_old_articles: tuple[Article, ...]
    future_articles: tuple[Article, ...]
    missing_date_articles: tuple[Article, ...]
    invalid_date_articles: tuple[Article, ...]

    @property
    def total_articles(self) -> int:
        return (
            len(self.articles)
            + len(self.too_old_articles)
            + len(self.future_articles)
            + len(self.missing_date_articles)
            + len(self.invalid_date_articles)
        )

    @property
    def kept_articles(self) -> int:
        return len(self.articles)

    def summary(self) -> dict[str, int | str]:
        """Return JSON-friendly counters for logs and reports."""

        return {
            "evaluated_at": self.evaluated_at,
            "cutoff_at": self.cutoff_at,
            "future_limit_at": self.future_limit_at,
            "total_articles": self.total_articles,
            "kept_articles": self.kept_articles,
            "too_old_articles": len(self.too_old_articles),
            "future_articles": len(self.future_articles),
            "missing_date_articles": len(self.missing_date_articles),
            "invalid_date_articles": len(self.invalid_date_articles),
        }


def filter_articles_by_time(
    articles: Iterable[Article],
    lookback_hours: float,
    *,
    now: datetime | None = None,
    future_tolerance_minutes: float = 15,
) -> TimeFilterResult:
    """Group articles according to the configured publication-time window.

    ``published_at`` is preferred because an old article should not become new
    merely because its feed entry was edited. ``updated_at`` is used when the
    publication date is missing or invalid.

    Naive datetimes are interpreted as UTC. Articles exactly on the cutoff are
    retained. Articles slightly ahead of the current time are also retained up
    to ``future_tolerance_minutes`` to tolerate clock differences between feed
    publishers and the machine running the collector.
    """

    _validate_positive_number("lookback_hours", lookback_hours)
    _validate_non_negative_number(
        "future_tolerance_minutes",
        future_tolerance_minutes,
    )

    evaluated_at = _normalize_datetime(now or datetime.now(timezone.utc))
    cutoff_at = evaluated_at - timedelta(hours=float(lookback_hours))
    future_limit_at = evaluated_at + timedelta(
        minutes=float(future_tolerance_minutes)
    )

    kept: list[Article] = []
    too_old: list[Article] = []
    future: list[Article] = []
    missing_date: list[Article] = []
    invalid_date: list[Article] = []

    for article in articles:
        article_date, date_status = _resolve_article_datetime(article)

        if date_status == "missing":
            missing_date.append(article)
            continue

        if date_status == "invalid" or article_date is None:
            invalid_date.append(article)
            continue

        if article_date < cutoff_at:
            too_old.append(article)
            continue

        if article_date > future_limit_at:
            future.append(article)
            continue

        kept.append(article)

    return TimeFilterResult(
        evaluated_at=_to_iso(evaluated_at),
        cutoff_at=_to_iso(cutoff_at),
        future_limit_at=_to_iso(future_limit_at),
        articles=tuple(kept),
        too_old_articles=tuple(too_old),
        future_articles=tuple(future),
        missing_date_articles=tuple(missing_date),
        invalid_date_articles=tuple(invalid_date),
    )


def _resolve_article_datetime(article: Article) -> tuple[datetime | None, str]:
    candidates = [article.published_at, article.updated_at]
    has_date_value = False

    for candidate in candidates:
        if candidate is None or not candidate.strip():
            continue

        has_date_value = True
        parsed = _parse_iso_datetime(candidate)
        if parsed is not None:
            return parsed, "valid"

    if has_date_value:
        return None, "invalid"
    return None, "missing"


def _parse_iso_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None

    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    return _normalize_datetime(parsed)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_iso(value: datetime) -> str:
    normalized = _normalize_datetime(value).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _validate_positive_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be a number greater than zero")


def _validate_non_negative_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} must be a non-negative number")
