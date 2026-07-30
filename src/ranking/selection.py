from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from src.ranking.rule_based import RankedArticle


@dataclass(frozen=True)
class SelectionResult:
    """Ranked articles selected with soft per-category quotas."""

    requested_max_articles: int
    available_articles: int
    articles: tuple[RankedArticle, ...]
    deferred_articles: tuple[RankedArticle, ...]
    category_quotas: dict[str, int]
    category_counts: dict[str, int]
    selected_within_quota: int
    selected_from_overflow: int

    @property
    def selected_articles(self) -> int:
        return len(self.articles)

    @property
    def deferred_count(self) -> int:
        return len(self.deferred_articles)

    def summary(self) -> dict[str, Any]:
        return {
            "requested_max_articles": self.requested_max_articles,
            "available_articles": self.available_articles,
            "selected_articles": self.selected_articles,
            "deferred_articles": self.deferred_count,
            "selected_within_quota": self.selected_within_quota,
            "selected_from_overflow": self.selected_from_overflow,
            "category_quotas": dict(self.category_quotas),
            "category_counts": dict(self.category_counts),
        }


def select_articles_by_category_quota(
    ranked_articles: Iterable[RankedArticle],
    profile: dict[str, Any],
    *,
    max_articles: int,
    fill_unused_slots: bool = True,
) -> SelectionResult:
    """Select top-ranked articles while limiting category concentration.

    The first pass respects each category's ``daily_quota``. If fewer than
    ``max_articles`` are selected, an optional second pass fills unused slots
    from the highest-ranked deferred articles.

    A category with ``daily_quota: 0`` is excluded from selection entirely.
    """

    if (
        not isinstance(max_articles, int)
        or isinstance(max_articles, bool)
        or max_articles <= 0
    ):
        raise ValueError("max_articles must be a positive integer")

    if not isinstance(fill_unused_slots, bool):
        raise ValueError("fill_unused_slots must be a boolean")

    category_quotas = _load_category_quotas(profile)
    ranked = tuple(ranked_articles)

    category_counts = {
        category_id: 0
        for category_id in category_quotas
    }

    selected_primary: list[tuple[int, RankedArticle]] = []
    overflow: list[tuple[int, RankedArticle]] = []

    for rank_index, ranked_article in enumerate(ranked):
        category = ranked_article.article.category
        if category not in category_quotas:
            raise ValueError(
                f"Article category '{category}' is missing from profile"
            )

        quota = category_quotas[category]
        if quota <= 0:
            overflow.append((rank_index, ranked_article))
            continue

        if (
            len(selected_primary) < max_articles
            and category_counts[category] < quota
        ):
            selected_primary.append((rank_index, ranked_article))
            category_counts[category] += 1
        else:
            overflow.append((rank_index, ranked_article))

    selected_overflow: list[tuple[int, RankedArticle]] = []
    if fill_unused_slots and len(selected_primary) < max_articles:
        remaining_slots = max_articles - len(selected_primary)

        for rank_index, ranked_article in overflow:
            category = ranked_article.article.category

            # A zero quota explicitly disables the category.
            if category_quotas[category] <= 0:
                continue

            selected_overflow.append((rank_index, ranked_article))
            category_counts[category] += 1

            if len(selected_overflow) >= remaining_slots:
                break

    selected_entries = selected_primary + selected_overflow
    selected_entries.sort(key=lambda item: item[0])

    selected_indexes = {
        rank_index
        for rank_index, _ in selected_entries
    }

    deferred_articles = tuple(
        ranked_article
        for rank_index, ranked_article in enumerate(ranked)
        if rank_index not in selected_indexes
    )

    return SelectionResult(
        requested_max_articles=max_articles,
        available_articles=len(ranked),
        articles=tuple(
            ranked_article
            for _, ranked_article in selected_entries
        ),
        deferred_articles=deferred_articles,
        category_quotas=category_quotas,
        category_counts=category_counts,
        selected_within_quota=len(selected_primary),
        selected_from_overflow=len(selected_overflow),
    )


def _load_category_quotas(
    profile: dict[str, Any],
) -> dict[str, int]:
    categories = profile.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise ValueError(
            "profile must contain a non-empty 'categories' mapping"
        )

    quotas: dict[str, int] = {}
    for category_id, category_data in categories.items():
        if not isinstance(category_id, str) or not category_id.strip():
            raise ValueError(
                "profile category ids must be non-empty strings"
            )
        if not isinstance(category_data, dict):
            raise ValueError(
                f"Category '{category_id}' must be a mapping"
            )

        daily_quota = category_data.get("daily_quota")
        if (
            not isinstance(daily_quota, int)
            or isinstance(daily_quota, bool)
            or daily_quota < 0
        ):
            raise ValueError(
                f"Category '{category_id}' daily_quota "
                "must be a non-negative integer"
            )

        quotas[category_id] = daily_quota

    return quotas
