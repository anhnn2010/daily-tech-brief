from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from html import escape
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.ranking.rule_based import RankedArticle


def render_html_digest(
    articles: Iterable[RankedArticle],
    profile: dict[str, Any],
    *,
    generated_at: str | datetime,
    project_name: str = "Daily Tech Brief",
    include_scores: bool = True,
    epub_href: str | None = None,
) -> str:
    """Render selected ranked articles as a standalone HTML document.

    The generated page has no external CSS, JavaScript, fonts, or image
    dependencies, so it can be opened locally or published through GitHub
    Pages without an additional build step.
    """

    if not isinstance(project_name, str) or not project_name.strip():
        raise ValueError("project_name must be a non-empty string")
    if not isinstance(include_scores, bool):
        raise ValueError("include_scores must be a boolean")
    if epub_href is not None:
        if not isinstance(epub_href, str) or not epub_href.strip():
            raise ValueError(
                "epub_href must be None or a non-empty string"
            )
        epub_href = epub_href.strip()

    category_labels = _load_category_labels(profile)
    timezone_name = _load_timezone_name(profile)
    language = _load_language(profile)
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

    article_count = sum(len(items) for items in grouped_articles.values())
    title_date = (
        f"{local_generated_at.strftime('%B')} "
        f"{local_generated_at.day}, {local_generated_at.year}"
    )
    page_title = f"{project_name.strip()} — {title_date}"
    generated_label = (
        f"{local_generated_at.strftime('%Y-%m-%d %H:%M')} "
        f"{timezone_name}"
    )

    category_navigation = _render_category_navigation(
        grouped_articles,
        category_labels,
    )
    digest_content = _render_digest_content(
        grouped_articles,
        category_labels,
        local_timezone=local_timezone,
        timezone_name=timezone_name,
        include_scores=include_scores,
    )
    edition_actions = _render_edition_actions(epub_href)

    return f"""<!doctype html>
<html lang="{escape(language, quote=True)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{escape(project_name.strip(), quote=True)} personalized technology digest">
  <title>{escape(page_title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --background: #f4f6f8;
      --surface: #ffffff;
      --surface-muted: #f7f8fa;
      --text: #1f2933;
      --muted: #5f6c7b;
      --border: #d8dee6;
      --accent: #2457c5;
      --badge: #edf1f5;
      --shadow: 0 8px 24px rgba(31, 41, 51, 0.08);
    }}

    @media (prefers-color-scheme: dark) {{
      :root {{
        --background: #11151a;
        --surface: #191f26;
        --surface-muted: #202730;
        --text: #edf2f7;
        --muted: #aab6c3;
        --border: #34404c;
        --accent: #8eb0ff;
        --badge: #29333e;
        --shadow: none;
      }}
    }}

    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}

    body {{
      margin: 0;
      background: var(--background);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 16px;
      line-height: 1.65;
    }}

    a {{
      color: var(--accent);
      text-decoration-thickness: 0.08em;
      text-underline-offset: 0.18em;
    }}

    a:hover {{ text-decoration-thickness: 0.14em; }}

    .page {{
      width: min(920px, calc(100% - 32px));
      margin: 0 auto;
      padding: 48px 0 64px;
    }}

    .hero {{ margin-bottom: 28px; }}

    .eyebrow {{
      margin: 0 0 8px;
      color: var(--accent);
      font-size: 0.78rem;
      font-weight: 750;
      letter-spacing: 0.09em;
      text-transform: uppercase;
    }}

    h1 {{
      margin: 0;
      font-size: clamp(2rem, 6vw, 3.3rem);
      line-height: 1.08;
      letter-spacing: -0.035em;
    }}

    .edition-meta {{
      margin: 14px 0 0;
      color: var(--muted);
    }}

    .edition-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 20px 0 0;
    }}

    .download-link {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      border: 1px solid var(--accent);
      border-radius: 10px;
      padding: 8px 14px;
      background: var(--surface);
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
    }}

    .download-link:hover {{
      filter: brightness(1.08);
      text-decoration: none;
    }}

    .category-nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 24px 0 38px;
    }}

    .category-nav a {{
      border: 1px solid var(--border);
      border-radius: 999px;
      background: var(--surface);
      padding: 6px 12px;
      color: var(--text);
      font-size: 0.88rem;
      text-decoration: none;
    }}

    .category-nav a:hover {{
      border-color: var(--accent);
      color: var(--accent);
    }}

    .category-section {{ margin-top: 42px; }}

    .category-heading {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin: 0 0 16px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 10px;
      font-size: 1.45rem;
      line-height: 1.25;
    }}

    .category-count {{
      color: var(--muted);
      font-size: 0.85rem;
      font-weight: 500;
    }}

    .article-card {{
      margin: 0 0 16px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
      padding: 22px;
      box-shadow: var(--shadow);
    }}

    .article-title {{
      margin: 0;
      font-size: 1.18rem;
      line-height: 1.35;
    }}

    .article-title a {{
      color: var(--text);
      text-decoration: none;
    }}

    .article-title a:hover {{
      color: var(--accent);
      text-decoration: underline;
    }}

    .article-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px 14px;
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 0.86rem;
    }}

    .summary {{ margin: 15px 0 0; }}

    .interest-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin: 16px 0 0;
      padding: 0;
      list-style: none;
    }}

    .interest-list li {{
      border-radius: 999px;
      background: var(--badge);
      padding: 4px 9px;
      font-size: 0.78rem;
    }}

    .read-link {{
      display: inline-block;
      margin-top: 17px;
      font-weight: 650;
    }}

    .empty-state {{
      border: 1px dashed var(--border);
      border-radius: 14px;
      background: var(--surface-muted);
      padding: 28px;
      color: var(--muted);
    }}

    .footer {{
      margin-top: 48px;
      border-top: 1px solid var(--border);
      padding-top: 20px;
      color: var(--muted);
      font-size: 0.84rem;
    }}

    @media (max-width: 600px) {{
      .page {{
        width: min(100% - 22px, 920px);
        padding-top: 28px;
      }}

      .article-card {{
        border-radius: 11px;
        padding: 17px;
      }}
    }}

    @media print {{
      :root {{ color-scheme: light; }}
      body {{ background: #ffffff; }}
      .page {{ width: 100%; padding: 0; }}
      .category-nav, .edition-actions {{ display: none; }}
      .article-card {{ break-inside: avoid; box-shadow: none; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <p class="eyebrow">Personalized technology digest</p>
      <h1>{escape(page_title)}</h1>
      <p class="edition-meta">
        Generated at {escape(generated_label)}
        · {article_count} {_pluralize("article", article_count)}
      </p>
{edition_actions}    </header>
{category_navigation}
{digest_content}
    <footer class="footer">
      Generated by {escape(project_name.strip())}. Article titles, summaries,
      and links remain attributed to their original sources.
    </footer>
  </main>
</body>
</html>
"""


def _render_edition_actions(epub_href: str | None) -> str:
    if epub_href is None:
        return ""

    return f'''      <p class="edition-actions">
        <a class="download-link" href="{escape(epub_href, quote=True)}" download>
          Download EPUB
        </a>
      </p>
'''


def _render_category_navigation(
    grouped_articles: OrderedDict[str, list[RankedArticle]],
    category_labels: dict[str, str],
) -> str:
    links: list[str] = []

    for category, category_articles in grouped_articles.items():
        if not category_articles:
            continue

        anchor = _category_anchor(category)
        label = category_labels[category]
        links.append(
            f'      <a href="#{escape(anchor, quote=True)}">'
            f"{escape(label)} ({len(category_articles)})</a>"
        )

    if not links:
        return ""

    return (
        '    <nav class="category-nav" aria-label="Digest categories">\n'
        + "\n".join(links)
        + "\n    </nav>"
    )


def _render_digest_content(
    grouped_articles: OrderedDict[str, list[RankedArticle]],
    category_labels: dict[str, str],
    *,
    local_timezone: ZoneInfo,
    timezone_name: str,
    include_scores: bool,
) -> str:
    sections: list[str] = []

    for category, category_articles in grouped_articles.items():
        if not category_articles:
            continue

        label = category_labels[category]
        article_cards = "\n".join(
            _render_article_card(
                ranked_article,
                local_timezone=local_timezone,
                timezone_name=timezone_name,
                include_scores=include_scores,
            )
            for ranked_article in category_articles
        )

        sections.append(
            f'''    <section class="category-section" id="{escape(_category_anchor(category), quote=True)}">
      <h2 class="category-heading">
        <span>{escape(label)}</span>
        <span class="category-count">
          {len(category_articles)} {_pluralize("article", len(category_articles))}
        </span>
      </h2>
{article_cards}
    </section>'''
        )

    if sections:
        return "\n".join(sections)

    return '''    <section class="empty-state">
      No articles were selected for this edition.
    </section>'''


def _render_article_card(
    ranked_article: RankedArticle,
    *,
    local_timezone: ZoneInfo,
    timezone_name: str,
    include_scores: bool,
) -> str:
    article = ranked_article.article
    metadata = [f"<span>{escape(article.source_name)}</span>"]

    source_datetime = article.published_at or article.updated_at
    published_label = _format_article_datetime(
        source_datetime,
        local_timezone,
        timezone_name,
    )
    if published_label is not None:
        metadata.append(
            f'<time datetime="{escape(source_datetime or "", quote=True)}">'
            f"{escape(published_label)}</time>"
        )

    if include_scores:
        metadata.append(f"<span>Score {ranked_article.score}</span>")

    summary = _normalize_summary(article.summary)
    summary_html = (
        f'      <p class="summary">{escape(summary)}</p>\n'
        if summary
        else ""
    )

    interest_html = ""
    if ranked_article.matched_high_priority_keywords:
        items = "\n".join(
            f"        <li>{escape(keyword)}</li>"
            for keyword in ranked_article.matched_high_priority_keywords
        )
        interest_html = (
            '      <ul class="interest-list" aria-label="Matched interests">\n'
            f"{items}\n"
            "      </ul>\n"
        )

    article_url = article.url.strip()
    return f'''      <article class="article-card">
        <h3 class="article-title">
          <a href="{escape(article_url, quote=True)}">{escape(article.title.strip())}</a>
        </h3>
        <p class="article-meta">
          {''.join(metadata)}
        </p>
{summary_html}{interest_html}        <a class="read-link" href="{escape(article_url, quote=True)}">
          Read the original article →
        </a>
      </article>'''


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


def _load_profile_data(profile: dict[str, Any]) -> dict[str, Any]:
    profile_data = profile.get("profile")
    if not isinstance(profile_data, dict):
        raise ValueError("profile must contain a 'profile' mapping")
    return profile_data


def _load_timezone_name(profile: dict[str, Any]) -> str:
    timezone_name = _load_profile_data(profile).get("timezone")
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError("profile.profile.timezone must be a non-empty string")
    return timezone_name.strip()


def _load_language(profile: dict[str, Any]) -> str:
    language = _load_profile_data(profile).get("language", "en")
    if not isinstance(language, str) or not language.strip():
        raise ValueError("profile.profile.language must be a non-empty string")
    return language.strip()


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
            raise ValueError(
                f"{field_name} must be a valid ISO datetime"
            ) from exc
    else:
        raise ValueError(
            f"{field_name} must be a datetime or ISO datetime string"
        )

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


def _humanize_category(category: str) -> str:
    return category.replace("_", " ").strip().title() or "Other"


def _category_anchor(category: str) -> str:
    normalized = "".join(
        character if character.isalnum() else "-"
        for character in category.casefold()
    )
    return "-".join(part for part in normalized.split("-") if part) or "other"


def _pluralize(noun: str, count: int) -> str:
    return noun if count == 1 else f"{noun}s"
