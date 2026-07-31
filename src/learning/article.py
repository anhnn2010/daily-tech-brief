from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping

from src.content.extractor import (
    ArticleContentExtractor,
    ContentExtractionError,
)
from src.learning.library import LearningLesson
from src.models import Article


LEARNING_EXTERNAL_ID_PREFIX = "learning:"
LEARNING_LESSON_TAG_PREFIX = "learning_lesson_id:"

DEFAULT_CATEGORY_BY_TRACK: dict[str, str] = {
    "analog_foundations": "technical_learning",
    "pll_and_clocking": "technical_learning",
    "data_converters": "technical_learning",
    "post_silicon_test": "technical_learning",
}


def learning_lesson_to_article(
    lesson: LearningLesson,
    *,
    generated_at: datetime | None = None,
    source_priority: int = 10,
    category_by_track: Mapping[str, str] | None = None,
) -> Article:
    """Convert one technical learning lesson into a normal article.

    Learning articles intentionally have no publication timestamp. This keeps
    them outside normal freshness assumptions while still allowing the current
    Markdown, HTML, and EPUB renderers to display them.
    """

    if (
        not isinstance(source_priority, int)
        or isinstance(source_priority, bool)
        or not 1 <= source_priority <= 10
    ):
        raise ValueError(
            "source_priority must be an integer between 1 and 10"
        )

    categories = (
        DEFAULT_CATEGORY_BY_TRACK
        if category_by_track is None
        else category_by_track
    )
    category = categories.get(lesson.track)
    if not isinstance(category, str) or not category.strip():
        raise ValueError(
            "No article category is configured for learning track "
            f"'{lesson.track}'"
        )

    evaluated_at = _normalize_datetime(
        generated_at or datetime.now(timezone.utc)
    )
    tags = _build_source_tags(lesson)

    curated_html, curated_text = _build_curated_content(lesson)

    return Article(
        source_id="technical_learning",
        source_name=lesson.source_name,
        category=category.strip(),
        source_priority=source_priority,
        source_tags=tags,
        title=lesson.title,
        url=lesson.url,
        external_id=(
            f"{LEARNING_EXTERNAL_ID_PREFIX}{lesson.id}"
        ),
        published_at=None,
        updated_at=None,
        summary=_build_summary(lesson),
        author=None,
        fetched_at=_to_iso(evaluated_at),
        content_html=curated_html,
        content_text=curated_text,
        content_status=(
            "extracted"
            if curated_html or curated_text
            else "not_requested"
        ),
    )


def learning_lessons_to_articles(
    lessons: Iterable[LearningLesson],
    *,
    generated_at: datetime | None = None,
    source_priority: int = 10,
    category_by_track: Mapping[str, str] | None = None,
) -> tuple[Article, ...]:
    """Convert selected technical lessons while preserving their order."""

    evaluated_at = _normalize_datetime(
        generated_at or datetime.now(timezone.utc)
    )

    return tuple(
        learning_lesson_to_article(
            lesson,
            generated_at=evaluated_at,
            source_priority=source_priority,
            category_by_track=category_by_track,
        )
        for lesson in lessons
    )


def is_learning_article(article: Article) -> bool:
    """Return whether an article was created from the learning library."""

    return (
        learning_lesson_id_from_article(article)
        is not None
    )


def learning_lesson_id_from_article(
    article: Article,
) -> str | None:
    """Recover a learning lesson ID from stable article metadata."""

    external_id = article.external_id
    external_lesson_id: str | None = None

    if (
        isinstance(external_id, str)
        and external_id.startswith(
            LEARNING_EXTERNAL_ID_PREFIX
        )
    ):
        candidate = external_id[
            len(LEARNING_EXTERNAL_ID_PREFIX):
        ].strip()
        external_lesson_id = candidate or None

    tagged_lesson_ids = [
        tag[len(LEARNING_LESSON_TAG_PREFIX):].strip()
        for tag in article.source_tags
        if tag.startswith(LEARNING_LESSON_TAG_PREFIX)
        and tag[len(LEARNING_LESSON_TAG_PREFIX):].strip()
    ]
    tagged_lesson_id = (
        tagged_lesson_ids[0]
        if tagged_lesson_ids
        else None
    )

    if (
        len(set(tagged_lesson_ids)) > 1
        or (
            external_lesson_id is not None
            and tagged_lesson_id is not None
            and external_lesson_id != tagged_lesson_id
        )
    ):
        raise ValueError(
            "Learning article metadata contains conflicting "
            "lesson IDs"
        )

    return external_lesson_id or tagged_lesson_id


def _build_curated_content(
    lesson: LearningLesson,
) -> tuple[str, str]:
    """Sanitize optional lesson content for private EPUB rendering."""

    content_html = lesson.content_html.strip()
    if not content_html:
        return "", ""

    extractor = ArticleContentExtractor(
        minimum_text_chars=1,
        maximum_text_chars=120_000,
    )

    try:
        extracted = extractor.extract(
            (
                '<article>'
                '<div itemprop="articleBody">'
                f'{content_html}'
                '</div>'
                '</article>'
            ),
            base_url=lesson.url,
        )
    except ContentExtractionError as exc:
        raise ValueError(
            "Invalid curated content for learning lesson "
            f"'{lesson.id}': {exc}"
        ) from exc

    if not extracted.is_usable:
        raise ValueError(
            "Curated content for learning lesson "
            f"'{lesson.id}' is empty after sanitization"
        )

    return (
        extracted.content_html,
        extracted.content_text,
    )


def _build_source_tags(
    lesson: LearningLesson,
) -> tuple[str, ...]:
    values = (
        "technical_learning",
        f"{LEARNING_LESSON_TAG_PREFIX}{lesson.id}",
        f"learning_track:{lesson.track}",
        f"difficulty:{lesson.difficulty}",
        f"estimated_minutes:{lesson.estimated_minutes}",
        *(
            ("learning_content:curated",)
            if lesson.content_html.strip()
            else ()
        ),
        *lesson.topics,
    )
    return tuple(dict.fromkeys(values))


def _build_summary(
    lesson: LearningLesson,
) -> str:
    return " ".join(
        (
            lesson.summary.strip(),
            "Why it matters:",
            lesson.why_it_matters.strip(),
            "Estimated reading time:",
            f"{lesson.estimated_minutes} minutes.",
            "Difficulty:",
            f"{lesson.difficulty}.",
        )
    )


def _normalize_datetime(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_iso(value: datetime) -> str:
    return value.replace(
        microsecond=0,
    ).isoformat().replace(
        "+00:00",
        "Z",
    )
