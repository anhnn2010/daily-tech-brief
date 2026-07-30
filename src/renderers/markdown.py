from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.ranking.rule_based import RankedArticle


def render_markdown_digest(
    articles: Iterable[RankedArticle],
    profile: dict[str, Any],
    *,
    generated_at: str | datetime,
    project_name: str = "Daily Tech Brief",
    include_scores: bool = True,
) -> str:
    """Render selected ranked articles as a readable Markdown digest.

    Articles are grouped using the category order and labels from the profile.
    Empty categories are omitted, while article order inside each category is
    preserved from the ranking and selection pipeline.
    """

    if not isinstance(project_name, str) or not project_name.strip():
        raise ValueError("project_name must be a non-empty string")
    if not isinstance(include_scores, bool):
        raise ValueError("include_scores must be a boolean")

    category_labels = _load_category_labels(profile)
    timezone_name = _load_timezone_name(profile)
    local_timezone = _load_timezone(timezone_name)
    generated_datetime = _parse_datetime(generated_at, "generated_at")
    local_generated_at = generated_datetime.astimezone(local_timezone)

    grouped_articles: OrderedDict[str, list[RankedArticle]] = OrderedDict(
        (category_id, []) for category_id in category_labels
    )

    for ranked_article in articles:
        category = ranked_article.article.category
        if category not in grouped_articles:
            grouped_articles[category] = []
            category_labels[category] = _humanize_category(category)
        grouped_articles[category].append(ranked_article)

    title_date = (
        f"{local_generated_at.strftime('%B')} "
        f"{local_generated_at.day}, {local_generated_at.year}"
    )
    lines = [
        f"# {_escape_markdown_text(project_name.strip())} — {title_date}",
        "",
        (
            f"> Generated at {local_generated_at.strftime('%Y-%m-%d %H:%M')} "
            f"{timezone_name}"
        ),
        "",
    ]

    article_count = sum(len(items) for items in grouped_articles.values())
    if article_count == 0:
        lines.extend(
            [
                "No articles were selected for this edition.",
                "",
            ]
        )
        return "\n".join(lines)

    for category, category_articles in grouped_articles.items():
        if not category_articles:
            continue

        lines.extend(
            [
                f"## {_escape_markdown_text(category_labels[category])}",
                "",
            ]
        )

        for ranked_article in category_articles:
            article = ranked_article.article
            title = _escape_markdown_text(article.title.strip())
            article_url = article.url.strip()

            lines.append(f"### [{title}](<{article_url}>)")
            lines.append("")

            metadata = [f"**Source:** {_escape_markdown_text(article.source_name)}"]
            published_label = _format_article_datetime(
                article.published_at or article.updated_at,
                local_timezone,
                timezone_name,
            )
            if published_label is not None:
                metadata.append(f"**Published:** {published_label}")
            if include_scores:
                metadata.append(f"**Score:** {ranked_article.score}")

            lines.append(" · ".join(metadata))
            lines.append("")

            summary = _normalize_summary(article.summary)
            if summary:
                lines.append(summary)
                lines.append("")

            matched_keywords = ranked_article.matched_high_priority_keywords
            if matched_keywords:
                keywords = ", ".join(
                    f"`{keyword}`" for keyword in matched_keywords
                )
                lines.append(f"**Matched interests:** {keywords}")
                lines.append("")

            lines.extend(["[Read the original article](<" + article_url + ">)", ""])

    return "\n".join(lines).rstrip() + "\n"


def _load_category_labels(profile: dict[str, Any]) -> dict[str, str]:
    categories = profile.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise ValueError(
            "profile must contain a non-empty 'categories' mapping"
        )

    labels: dict[str, str] = {}
    for category_id, category_data in categories.items():
        if not isinstance(category_id, str) or not category_id.strip():
            raise ValueError("profile category ids must be non-empty strings")
        if not isinstance(category_data, dict):
            raise ValueError(f"Category '{category_id}' must be a mapping")

        label = category_data.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(
                f"Category '{category_id}' label must be a non-empty string"
            )
        labels[category_id] = label.strip()

    return labels


def _load_timezone_name(profile: dict[str, Any]) -> str:
    profile_data = profile.get("profile")
    if not isinstance(profile_data, dict):
        raise ValueError("profile must contain a 'profile' mapping")

    timezone_name = profile_data.get("timezone")
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError("profile.profile.timezone must be a non-empty string")
    return timezone_name.strip()


def _load_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone '{timezone_name}'") from exc


def _parse_datetime(value: str | datetime, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        normalized = value.strip()
        if normalized.endswith(("Z", "z")):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a valid ISO datetime") from exc
    else:
        raise ValueError(f"{field_name} must be a datetime or ISO datetime string")

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_article_datetime(
    value: str | None,
    local_timezone: ZoneInfo,
    timezone_name: str,
) -> str | None:
    if value is None or not value.strip():
        return None

    try:
        parsed = _parse_datetime(value, "article datetime")
    except ValueError:
        return None

    local_datetime = parsed.astimezone(local_timezone)
    return (
        f"{local_datetime.strftime('%Y-%m-%d %H:%M')} "
        f"{timezone_name}"
    )


def _normalize_summary(value: str) -> str:
    return " ".join(value.split())


def _escape_markdown_text(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for character in ("[", "]", "*", "_", "`", "#"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def _humanize_category(category: str) -> str:
    return category.replace("_", " ").strip().title() or "Other"
