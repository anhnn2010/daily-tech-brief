from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.learning.article import (
    learning_lesson_id_from_article,
    learning_lessons_to_articles,
)
from src.learning.library import (
    LearningLibraryError,
    load_learning_library,
)
from src.learning.selector import (
    LearningSelectionError,
    LearningSelectionResult,
    select_learning_lessons,
)
from src.ranking.rule_based import (
    RankedArticle,
    rank_articles,
)


@dataclass(frozen=True)
class LearningEditionPlan:
    """Selected learning articles and the remaining news capacity."""

    library_path: Path
    available: bool
    enabled: bool
    include_in_max_articles: bool
    max_articles: int
    news_capacity: int
    selected_articles: tuple[RankedArticle, ...]
    selection_result: LearningSelectionResult | None

    @property
    def selected_count(self) -> int:
        return len(self.selected_articles)

    @property
    def selected_lesson_ids(self) -> tuple[str, ...]:
        lesson_ids: list[str] = []
        for ranked_article in self.selected_articles:
            lesson_id = learning_lesson_id_from_article(
                ranked_article.article
            )
            if lesson_id is not None:
                lesson_ids.append(lesson_id)
        return tuple(lesson_ids)

    def combine(
        self,
        news_articles: Iterable[RankedArticle],
    ) -> tuple[RankedArticle, ...]:
        """Combine selected news and learning articles deterministically."""

        news = tuple(news_articles)

        if self.include_in_max_articles:
            news = news[: self.news_capacity]
        else:
            news = news[: self.max_articles]

        return news + self.selected_articles

    def summary(
        self,
        *,
        news_article_count: int | None = None,
        final_article_count: int | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "library_path": str(self.library_path),
            "available": self.available,
            "enabled": self.enabled,
            "include_in_max_articles": self.include_in_max_articles,
            "max_articles": self.max_articles,
            "news_capacity": self.news_capacity,
            "selected_lessons": self.selected_count,
            "selected_lesson_ids": list(
                self.selected_lesson_ids
            ),
        }

        if self.selection_result is not None:
            result["selection"] = (
                self.selection_result.summary()
            )

        if news_article_count is not None:
            result["news_articles"] = news_article_count

        if final_article_count is not None:
            result["final_articles"] = final_article_count

        return result

    def payload(self) -> dict[str, Any]:
        """Return archive metadata consumed by the rotation selector."""

        lessons: list[dict[str, Any]] = []

        for ranked_article in self.selected_articles:
            article = ranked_article.article
            lesson_id = learning_lesson_id_from_article(
                article
            )
            if lesson_id is None:
                continue

            lessons.append(
                {
                    "id": lesson_id,
                    "title": article.title,
                    "source_name": article.source_name,
                    "category": article.category,
                    "url": article.url,
                }
            )

        return {
            "enabled": self.enabled,
            "lesson_ids": list(self.selected_lesson_ids),
            "lessons": lessons,
        }


def prepare_learning_edition(
    *,
    profile: dict[str, Any],
    config_dir: str | Path,
    archive_root: str | Path,
    max_articles: int,
    now: datetime | None = None,
    library_filename: str = "learning_library.yml",
) -> LearningEditionPlan:
    """Load, rotate, convert, and rank technical learning lessons.

    The learning library is optional for backward compatibility. When the
    configured YAML file does not exist, the returned plan leaves all article
    capacity available for normal news.
    """

    if (
        not isinstance(max_articles, int)
        or isinstance(max_articles, bool)
        or max_articles < 0
    ):
        raise ValueError(
            "max_articles must be a non-negative integer"
        )

    if (
        not isinstance(library_filename, str)
        or not library_filename.strip()
    ):
        raise ValueError(
            "library_filename must be a non-empty string"
        )

    evaluated_at = _normalize_datetime(
        now or datetime.now(timezone.utc)
    )
    library_path = (
        Path(config_dir)
        / library_filename.strip()
    )

    if not library_path.is_file():
        return LearningEditionPlan(
            library_path=library_path,
            available=False,
            enabled=False,
            include_in_max_articles=True,
            max_articles=max_articles,
            news_capacity=max_articles,
            selected_articles=(),
            selection_result=None,
        )

    try:
        library = load_learning_library(library_path)
        selection_result = select_learning_lessons(
            library,
            archive_root=archive_root,
            now=evaluated_at,
        )
    except (
        LearningLibraryError,
        LearningSelectionError,
    ):
        raise

    selected_articles = _rank_selected_lessons(
        selection_result=selection_result,
        profile=profile,
        evaluated_at=evaluated_at,
    )
    include_in_max_articles = (
        library.selection.include_in_max_articles
    )

    if (
        include_in_max_articles
        and len(selected_articles) > max_articles
    ):
        raise ValueError(
            "Selected learning lessons exceed runtime.max_articles"
        )

    news_capacity = (
        max_articles - len(selected_articles)
        if include_in_max_articles
        else max_articles
    )

    return LearningEditionPlan(
        library_path=library_path,
        available=True,
        enabled=library.selection.enabled,
        include_in_max_articles=include_in_max_articles,
        max_articles=max_articles,
        news_capacity=news_capacity,
        selected_articles=selected_articles,
        selection_result=selection_result,
    )


def _rank_selected_lessons(
    *,
    selection_result: LearningSelectionResult,
    profile: dict[str, Any],
    evaluated_at: datetime,
) -> tuple[RankedArticle, ...]:
    learning_articles = learning_lessons_to_articles(
        selection_result.selected_lessons,
        generated_at=evaluated_at,
    )

    if not learning_articles:
        return ()

    ranking_result = rank_articles(
        learning_articles,
        profile,
        now=evaluated_at,
    )
    ranked_by_lesson_id: dict[str, RankedArticle] = {}

    for ranked_article in ranking_result.articles:
        lesson_id = learning_lesson_id_from_article(
            ranked_article.article
        )
        if lesson_id is None:
            raise ValueError(
                "Ranked learning article is missing its lesson ID"
            )
        ranked_by_lesson_id[lesson_id] = ranked_article

    ordered: list[RankedArticle] = []
    for lesson in selection_result.selected_lessons:
        ranked_article = ranked_by_lesson_id.get(lesson.id)
        if ranked_article is None:
            raise ValueError(
                "Ranked learning article was not produced for "
                f"lesson '{lesson.id}'"
            )
        ordered.append(ranked_article)

    return tuple(ordered)


def _normalize_datetime(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
