from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from src.models import Article


@dataclass(frozen=True)
class RankedArticle:
    """An article plus its explainable rule-based ranking result."""

    article: Article
    score: int
    category_weight: int
    freshness_hours: float | None
    matched_high_priority_keywords: tuple[str, ...]
    matched_low_priority_keywords: tuple[str, ...]
    score_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = self.article.to_dict()
        payload.update(
            {
                "score": self.score,
                "category_weight": self.category_weight,
                "freshness_hours": self.freshness_hours,
                "matched_high_priority_keywords": list(
                    self.matched_high_priority_keywords
                ),
                "matched_low_priority_keywords": list(
                    self.matched_low_priority_keywords
                ),
                "score_reasons": list(self.score_reasons),
            }
        )
        return payload


@dataclass(frozen=True)
class RankingResult:
    """Articles sorted from the highest to the lowest relevance score."""

    evaluated_at: str
    articles: tuple[RankedArticle, ...]

    @property
    def total_articles(self) -> int:
        return len(self.articles)

    @property
    def top_score(self) -> int | None:
        if not self.articles:
            return None
        return self.articles[0].score

    def summary(self) -> dict[str, int | str | None]:
        return {
            "evaluated_at": self.evaluated_at,
            "total_articles": self.total_articles,
            "top_score": self.top_score,
        }


def rank_articles(
    articles: Iterable[Article],
    profile: dict[str, Any],
    *,
    now: datetime | None = None,
) -> RankingResult:
    """Rank articles using source, category, freshness, and keyword signals.

    The score intentionally uses simple rules so every ranking decision can be
    shown in reports and reviewed without an AI model.
    """

    categories = _load_categories(profile)
    high_priority_keywords, low_priority_keywords = _load_keywords(profile)
    evaluated_at = _normalize_datetime(now or datetime.now(timezone.utc))

    ranked_articles: list[RankedArticle] = []
    for article in articles:
        category_data = categories.get(article.category)
        if category_data is None:
            raise ValueError(
                f"Article category '{article.category}' is missing from profile"
            )

        category_weight = _validate_weight(
            category_data.get("weight"),
            f"Category '{article.category}' weight",
        )

        ranked_articles.append(
            _rank_article(
                article=article,
                category_weight=category_weight,
                high_priority_keywords=high_priority_keywords,
                low_priority_keywords=low_priority_keywords,
                evaluated_at=evaluated_at,
            )
        )

    ranked_articles.sort(key=_ranking_sort_key)
    return RankingResult(
        evaluated_at=_to_iso(evaluated_at),
        articles=tuple(ranked_articles),
    )


def _rank_article(
    article: Article,
    category_weight: int,
    high_priority_keywords: tuple[str, ...],
    low_priority_keywords: tuple[str, ...],
    evaluated_at: datetime,
) -> RankedArticle:
    score = 0
    reasons: list[str] = []

    source_score = article.source_priority * 2
    score += source_score
    reasons.append(
        f"Source priority {article.source_priority}: +{source_score}"
    )

    category_score = category_weight * 2
    score += category_score
    reasons.append(f"Category weight {category_weight}: +{category_score}")

    freshness_seconds = _calculate_freshness_seconds(article, evaluated_at)
    freshness_score, freshness_reason = _score_freshness(freshness_seconds)
    freshness_hours = (
        round(freshness_seconds / 3600, 3)
        if freshness_seconds is not None
        else None
    )
    score += freshness_score
    if freshness_reason is not None:
        reasons.append(freshness_reason)

    title_text = article.title.casefold()
    supporting_text = " ".join(
        [article.summary, *article.source_tags]
    ).casefold()

    matched_high: list[str] = []
    high_keyword_score = 0
    for keyword in high_priority_keywords:
        if _contains_keyword(title_text, keyword):
            matched_high.append(keyword)
            high_keyword_score += 8
            reasons.append(
                f"High-priority keyword in title '{keyword}': +8"
            )
        elif _contains_keyword(supporting_text, keyword):
            matched_high.append(keyword)
            high_keyword_score += 4
            reasons.append(
                f"High-priority keyword in summary/tags '{keyword}': +4"
            )

    if high_keyword_score > 24:
        reasons.append(
            f"High-priority keyword bonus capped: {high_keyword_score} -> 24"
        )
        high_keyword_score = 24
    score += high_keyword_score

    combined_text = f"{title_text} {supporting_text}"
    matched_low: list[str] = []
    low_keyword_penalty = 0
    for keyword in low_priority_keywords:
        if _contains_keyword(combined_text, keyword):
            matched_low.append(keyword)
            low_keyword_penalty += 6
            reasons.append(f"Low-priority keyword '{keyword}': -6")

    if low_keyword_penalty > 12:
        reasons.append(
            f"Low-priority keyword penalty capped: {low_keyword_penalty} -> 12"
        )
        low_keyword_penalty = 12
    score -= low_keyword_penalty

    return RankedArticle(
        article=article,
        score=max(score, 0),
        category_weight=category_weight,
        freshness_hours=freshness_hours,
        matched_high_priority_keywords=tuple(matched_high),
        matched_low_priority_keywords=tuple(matched_low),
        score_reasons=tuple(reasons),
    )


def _score_freshness(
    freshness_seconds: float | None,
) -> tuple[int, str | None]:
    if freshness_seconds is None:
        return 0, None
    if freshness_seconds <= 6 * 3600:
        return 10, "Published within 6 hours: +10"
    if freshness_seconds <= 12 * 3600:
        return 8, "Published within 12 hours: +8"
    if freshness_seconds <= 24 * 3600:
        return 6, "Published within 24 hours: +6"
    if freshness_seconds <= 36 * 3600:
        return 4, "Published within 36 hours: +4"
    if freshness_seconds <= 48 * 3600:
        return 2, "Published within 48 hours: +2"
    return 0, None


def _calculate_freshness_seconds(
    article: Article,
    evaluated_at: datetime,
) -> float | None:
    article_datetime = _resolve_article_datetime(article)
    if article_datetime is None:
        return None

    age_seconds = (evaluated_at - article_datetime).total_seconds()
    return max(age_seconds, 0.0)


def _resolve_article_datetime(article: Article) -> datetime | None:
    for value in (article.published_at, article.updated_at):
        if value is None or not value.strip():
            continue

        parsed = _parse_iso_datetime(value)
        if parsed is not None:
            return parsed

    return None


def _parse_iso_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    return _normalize_datetime(parsed)


def _contains_keyword(text: str, keyword: str) -> bool:
    normalized_keyword = keyword.strip().casefold()
    if not normalized_keyword:
        return False

    pattern = rf"(?<!\w){re.escape(normalized_keyword)}(?!\w)"
    return re.search(pattern, text) is not None


def _load_categories(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    categories = profile.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise ValueError("profile must contain a non-empty 'categories' mapping")

    normalized_categories: dict[str, dict[str, Any]] = {}
    for category_id, category_data in categories.items():
        if not isinstance(category_id, str) or not category_id.strip():
            raise ValueError("profile category ids must be non-empty strings")
        if not isinstance(category_data, dict):
            raise ValueError(f"Category '{category_id}' must be a mapping")
        normalized_categories[category_id] = category_data

    return normalized_categories


def _load_keywords(
    profile: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    keywords = profile.get("keywords", {})
    if not isinstance(keywords, dict):
        raise ValueError("profile 'keywords' must be a mapping")

    high_priority = _normalize_keyword_list(
        keywords.get("high_priority", []),
        "keywords.high_priority",
    )
    low_priority = _normalize_keyword_list(
        keywords.get("low_priority", []),
        "keywords.low_priority",
    )
    return high_priority, low_priority


def _normalize_keyword_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{name} must contain non-empty strings")

        keyword = item.strip().casefold()
        if keyword not in seen:
            normalized.append(keyword)
            seen.add(keyword)

    return tuple(normalized)


def _validate_weight(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10:
        raise ValueError(f"{name} must be an integer from 1 to 10")
    return value


def _ranking_sort_key(ranked_article: RankedArticle) -> tuple[Any, ...]:
    article_datetime = _resolve_article_datetime(ranked_article.article)
    timestamp = (
        article_datetime.timestamp()
        if article_datetime is not None
        else float("-inf")
    )
    return (
        -ranked_article.score,
        -timestamp,
        -ranked_article.article.source_priority,
        ranked_article.article.title.casefold(),
        ranked_article.article.url,
    )


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_iso(value: datetime) -> str:
    normalized = _normalize_datetime(value).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")
