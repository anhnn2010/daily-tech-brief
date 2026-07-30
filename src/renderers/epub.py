from __future__ import annotations

import re
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.ranking.rule_based import RankedArticle


_EPUB_MIMETYPE = "application/epub+zip"
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class EpubRenderError(ValueError):
    """Raised when an EPUB digest cannot be rendered."""


def render_epub_digest(
    articles: Iterable[RankedArticle],
    profile: dict[str, Any],
    *,
    generated_at: str | datetime,
    project_name: str = "Daily Tech Brief",
) -> bytes:
    """Render selected articles as a deterministic EPUB 3 document.

    The book is organized into one chapter per non-empty category. Article
    URLs remain available as links, but long URLs are never displayed as
    reading text so text-to-speech tools can read the digest naturally.
    """

    if not isinstance(project_name, str) or not project_name.strip():
        raise EpubRenderError("project_name must be a non-empty string")

    normalized_project_name = project_name.strip()
    category_labels = _load_category_labels(profile)
    timezone_name = _load_timezone_name(profile)
    language = _load_language(profile)
    local_timezone = _load_timezone(timezone_name)
    generated_datetime = _parse_datetime(generated_at, "generated_at")
    local_generated_at = generated_datetime.astimezone(local_timezone)
    normalized_articles = tuple(articles)

    grouped_articles: OrderedDict[str, list[RankedArticle]] = OrderedDict(
        (category_id, []) for category_id in category_labels
    )
    for ranked_article in normalized_articles:
        category = ranked_article.article.category
        if category not in grouped_articles:
            grouped_articles[category] = []
            category_labels[category] = _humanize_category(category)
        grouped_articles[category].append(ranked_article)

    non_empty_categories = [
        (category_id, category_labels[category_id], category_articles)
        for category_id, category_articles in grouped_articles.items()
        if category_articles
    ]
    chapter_records = _build_chapter_records(non_empty_categories)

    title_date = (
        f"{local_generated_at.strftime('%B')} "
        f"{local_generated_at.day}, {local_generated_at.year}"
    )
    book_title = f"{normalized_project_name} — {title_date}"
    identifier = _build_identifier(
        normalized_project_name,
        generated_datetime,
    )
    modified_at = _to_epub_modified(generated_datetime)

    files: list[tuple[str, str, int]] = [
        ("mimetype", _EPUB_MIMETYPE, ZIP_STORED),
        (
            "META-INF/container.xml",
            _render_container_xml(),
            ZIP_DEFLATED,
        ),
        (
            "EPUB/styles.css",
            _render_stylesheet(),
            ZIP_DEFLATED,
        ),
        (
            "EPUB/title.xhtml",
            _render_title_page(
                book_title=book_title,
                project_name=normalized_project_name,
                generated_at=local_generated_at,
                timezone_name=timezone_name,
                language=language,
                article_count=len(normalized_articles),
            ),
            ZIP_DEFLATED,
        ),
        (
            "EPUB/nav.xhtml",
            _render_navigation(
                book_title=book_title,
                language=language,
                chapters=chapter_records,
            ),
            ZIP_DEFLATED,
        ),
        (
            "EPUB/toc.ncx",
            _render_ncx(
                book_title=book_title,
                identifier=identifier,
                language=language,
                chapters=chapter_records,
            ),
            ZIP_DEFLATED,
        ),
    ]

    for chapter in chapter_records:
        files.append(
            (
                f"EPUB/{chapter['filename']}",
                _render_category_chapter(
                    category_label=chapter["label"],
                    articles=chapter["articles"],
                    language=language,
                    local_timezone=local_timezone,
                    timezone_name=timezone_name,
                ),
                ZIP_DEFLATED,
            )
        )

    files.append(
        (
            "EPUB/package.opf",
            _render_package_document(
                book_title=book_title,
                project_name=normalized_project_name,
                identifier=identifier,
                language=language,
                modified_at=modified_at,
                chapters=chapter_records,
            ),
            ZIP_DEFLATED,
        )
    )

    archive = BytesIO()
    with ZipFile(archive, mode="w") as epub:
        for path, content, compression in files:
            _write_zip_text(epub, path, content, compression)

    return archive.getvalue()


def _build_chapter_records(
    categories: list[tuple[str, str, list[RankedArticle]]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    used_slugs: set[str] = set()

    for index, (category_id, label, articles) in enumerate(categories, start=1):
        base_slug = _slugify(category_id) or f"category-{index}"
        slug = base_slug
        suffix = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        used_slugs.add(slug)

        records.append(
            {
                "id": f"chapter-{index}",
                "filename": f"category-{slug}.xhtml",
                "label": label,
                "articles": tuple(articles),
            }
        )

    return records


def _render_container_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _render_package_document(
    *,
    book_title: str,
    project_name: str,
    identifier: str,
    language: str,
    modified_at: str,
    chapters: list[dict[str, Any]],
) -> str:
    manifest_items = [
        (
            '    <item id="nav" href="nav.xhtml" '
            'media-type="application/xhtml+xml" properties="nav"/>'
        ),
        (
            '    <item id="ncx" href="toc.ncx" '
            'media-type="application/x-dtbncx+xml"/>'
        ),
        '    <item id="style" href="styles.css" media-type="text/css"/>',
        (
            '    <item id="title-page" href="title.xhtml" '
            'media-type="application/xhtml+xml"/>'
        ),
    ]
    spine_items = ['    <itemref idref="title-page"/>']

    for chapter in chapters:
        manifest_items.append(
            "    <item "
            f'id="{escape(chapter["id"], quote=True)}" '
            f'href="{escape(chapter["filename"], quote=True)}" '
            'media-type="application/xhtml+xml"/>'
        )
        spine_items.append(
            f'    <itemref idref="{escape(chapter["id"], quote=True)}"/>'
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id" xml:lang="{escape(language, quote=True)}" prefix="schema: http://schema.org/">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">{escape(identifier)}</dc:identifier>
    <dc:title>{escape(book_title)}</dc:title>
    <dc:creator>{escape(project_name)}</dc:creator>
    <dc:language>{escape(language)}</dc:language>
    <meta property="dcterms:modified">{escape(modified_at)}</meta>
    <meta property="schema:accessMode">textual</meta>
    <meta property="schema:accessModeSufficient">textual</meta>
    <meta property="schema:accessibilityFeature">tableOfContents</meta>
    <meta property="schema:accessibilityFeature">readingOrder</meta>
    <meta property="schema:accessibilityHazard">none</meta>
  </metadata>
  <manifest>
{chr(10).join(manifest_items)}
  </manifest>
  <spine toc="ncx" page-progression-direction="ltr">
{chr(10).join(spine_items)}
  </spine>
</package>
"""


def _render_title_page(
    *,
    book_title: str,
    project_name: str,
    generated_at: datetime,
    timezone_name: str,
    language: str,
    article_count: int,
) -> str:
    article_label = "article" if article_count == 1 else "articles"
    generated_label = escape(generated_at.strftime("%Y-%m-%d %H:%M"))
    timezone_label = escape(timezone_name)
    return _wrap_xhtml(
        title=book_title,
        language=language,
        body=f"""
  <section class="title-page" epub:type="titlepage">
    <p class="eyebrow">{escape(project_name)}</p>
    <h1>{escape(book_title)}</h1>
    <p>Generated at {generated_label} {timezone_label}.</p>
    <p>{article_count} {article_label} selected for this edition.</p>
  </section>""",
    )


def _render_navigation(
    *,
    book_title: str,
    language: str,
    chapters: list[dict[str, Any]],
) -> str:
    chapter_items: list[str] = []
    for chapter in chapters:
        article_items = []
        for index, ranked_article in enumerate(chapter["articles"], start=1):
            article_items.append(
                "          <li><a "
                f'href="{escape(chapter["filename"], quote=True)}#article-{index}">'
                f"{escape(ranked_article.article.title)}</a></li>"
            )

        nested_articles = ""
        if article_items:
            nested_articles = "\n        <ol>\n" + "\n".join(article_items) + "\n        </ol>"

        chapter_items.append(
            "      <li><a "
            f'href="{escape(chapter["filename"], quote=True)}">'
            f"{escape(chapter['label'])}</a>{nested_articles}</li>"
        )

    if not chapter_items:
        chapter_items.append(
            '      <li><a href="title.xhtml">Edition information</a></li>'
        )

    body = f"""
  <nav epub:type="toc" id="toc">
    <h1>Contents</h1>
    <ol>
      <li><a href="title.xhtml">{escape(book_title)}</a></li>
{chr(10).join(chapter_items)}
    </ol>
  </nav>
  <nav epub:type="landmarks" hidden="hidden">
    <h2>Landmarks</h2>
    <ol>
      <li><a epub:type="titlepage" href="title.xhtml">Title page</a></li>
      <li><a epub:type="toc" href="nav.xhtml">Table of contents</a></li>
    </ol>
  </nav>"""
    return _wrap_xhtml(
        title=f"Contents — {book_title}",
        language=language,
        body=body,
    )


def _render_ncx(
    *,
    book_title: str,
    identifier: str,
    language: str,
    chapters: list[dict[str, Any]],
) -> str:
    nav_points = [
        """    <navPoint id="nav-title" playOrder="1">
      <navLabel><text>{title}</text></navLabel>
      <content src="title.xhtml"/>
    </navPoint>""".format(title=escape(book_title))
    ]

    play_order = 2
    for chapter in chapters:
        chapter_play_order = play_order
        play_order += 1
        child_points: list[str] = []
        for index, ranked_article in enumerate(chapter["articles"], start=1):
            child_points.append(
                f"""      <navPoint id="nav-{escape(chapter['id'], quote=True)}-article-{index}" playOrder="{play_order}">
        <navLabel><text>{escape(ranked_article.article.title)}</text></navLabel>
        <content src="{escape(chapter['filename'], quote=True)}#article-{index}"/>
      </navPoint>"""
            )
            play_order += 1

        nav_points.append(
            f"""    <navPoint id="nav-{escape(chapter['id'], quote=True)}" playOrder="{chapter_play_order}">
      <navLabel><text>{escape(chapter['label'])}</text></navLabel>
      <content src="{escape(chapter['filename'], quote=True)}"/>
{chr(10).join(child_points)}
    </navPoint>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="{escape(language, quote=True)}">
  <head>
    <meta name="dtb:uid" content="{escape(identifier, quote=True)}"/>
    <meta name="dtb:depth" content="2"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{escape(book_title)}</text></docTitle>
  <navMap>
{chr(10).join(nav_points)}
  </navMap>
</ncx>
"""


def _render_category_chapter(
    *,
    category_label: str,
    articles: tuple[RankedArticle, ...],
    language: str,
    local_timezone: ZoneInfo,
    timezone_name: str,
) -> str:
    article_sections: list[str] = []

    for index, ranked_article in enumerate(articles, start=1):
        article = ranked_article.article
        metadata_parts = [f"Source: {article.source_name}."]

        published_label = _format_article_datetime(
            article.published_at or article.updated_at,
            local_timezone,
            timezone_name,
        )
        if published_label is not None:
            metadata_parts.append(f"Published: {published_label}.")
        if article.author:
            metadata_parts.append(f"Author: {article.author.strip()}.")

        summary = _normalize_summary(article.summary)
        summary_html = (
            f"\n      <p class=\"summary\">{escape(summary)}</p>"
            if summary
            else ""
        )
        original_link = ""
        if article.url.strip():
            original_link = (
                "\n      <p class=\"original-link\"><a "
                f'href="{escape(article.url.strip(), quote=True)}">'
                "Read the original article</a>.</p>"
            )

        article_sections.append(
            f"""    <article id="article-{index}">
      <h2>{escape(article.title.strip() or 'Untitled')}</h2>
      <p class="metadata">{escape(' '.join(metadata_parts))}</p>{summary_html}{original_link}
    </article>"""
        )

    body = f"""
  <section epub:type="chapter">
    <h1>{escape(category_label)}</h1>
{chr(10).join(article_sections)}
  </section>"""
    return _wrap_xhtml(
        title=category_label,
        language=language,
        body=body,
    )


def _wrap_xhtml(*, title: str, language: str, body: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{escape(language, quote=True)}" lang="{escape(language, quote=True)}">
<head>
  <meta charset="UTF-8"/>
  <title>{escape(title)}</title>
  <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>{body}
</body>
</html>
"""


def _render_stylesheet() -> str:
    return """body {
  font-family: serif;
  line-height: 1.55;
  margin: 5%;
}

h1,
h2 {
  line-height: 1.2;
}

h1 {
  margin-bottom: 1.2em;
}

article {
  break-inside: avoid;
  margin-bottom: 2.5em;
}

.metadata,
.eyebrow {
  font-size: 0.9em;
  font-weight: bold;
}

.summary {
  margin-top: 0.8em;
}

.original-link {
  margin-top: 0.8em;
}

.title-page {
  margin-top: 20%;
  text-align: center;
}
"""


def _write_zip_text(
    archive: ZipFile,
    path: str,
    content: str,
    compression: int,
) -> None:
    zip_info = ZipInfo(path, date_time=_FIXED_ZIP_TIMESTAMP)
    zip_info.compress_type = compression
    zip_info.create_system = 3
    zip_info.external_attr = 0o100644 << 16
    archive.writestr(zip_info, content.encode("utf-8"))


def _load_category_labels(profile: dict[str, Any]) -> dict[str, str]:
    categories = profile.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise EpubRenderError(
            "profile must contain a non-empty 'categories' mapping"
        )

    labels: dict[str, str] = {}
    for category_id, category_data in categories.items():
        if not isinstance(category_id, str) or not category_id.strip():
            raise EpubRenderError(
                "profile category ids must be non-empty strings"
            )
        if not isinstance(category_data, dict):
            raise EpubRenderError(
                f"Category '{category_id}' must be a mapping"
            )

        label = category_data.get("label")
        if not isinstance(label, str) or not label.strip():
            raise EpubRenderError(
                f"Category '{category_id}' label must be a non-empty string"
            )
        labels[category_id] = label.strip()

    return labels


def _load_timezone_name(profile: dict[str, Any]) -> str:
    profile_data = profile.get("profile")
    if not isinstance(profile_data, dict):
        raise EpubRenderError("profile must contain a 'profile' mapping")

    timezone_name = profile_data.get("timezone")
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise EpubRenderError(
            "profile.profile.timezone must be a non-empty string"
        )
    return timezone_name.strip()


def _load_language(profile: dict[str, Any]) -> str:
    profile_data = profile.get("profile")
    if not isinstance(profile_data, dict):
        raise EpubRenderError("profile must contain a 'profile' mapping")

    language = profile_data.get("language")
    if not isinstance(language, str) or not language.strip():
        raise EpubRenderError(
            "profile.profile.language must be a non-empty string"
        )
    return language.strip()


def _load_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise EpubRenderError(
            f"Unknown timezone '{timezone_name}'"
        ) from exc


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
            raise EpubRenderError(
                f"{field_name} must be an ISO 8601 datetime"
            ) from exc
    else:
        raise EpubRenderError(
            f"{field_name} must be a datetime or ISO 8601 string"
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
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
    except EpubRenderError:
        return None

    local_value = parsed.astimezone(local_timezone)
    return f"{local_value.strftime('%Y-%m-%d %H:%M')} {timezone_name}"


def _build_identifier(project_name: str, generated_at: datetime) -> str:
    normalized_time = generated_at.astimezone(timezone.utc).isoformat()
    value = f"{project_name}|{normalized_time}"
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, value)}"


def _to_epub_modified(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_summary(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def _slugify(value: str) -> str:
    return _SLUG_RE.sub("-", value.casefold()).strip("-")


def _humanize_category(category: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", category.replace("_", " ")).strip()
    return normalized.title() or "Other"
