from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup, Tag

from src.models import Article, FeedFetchError, Source


_WHITESPACE_RE = re.compile(r"\s+")
_DATE_RE = re.compile(
    r"\b("
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
    r")\s+\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)
_BY_RE = re.compile(
    r"\bby\s+(.+?)(?:\s{2,}|$)",
    re.IGNORECASE,
)

_HTML_ACCEPT = (
    "text/html, application/xhtml+xml, "
    "application/xml;q=0.9, */*;q=0.5"
)
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)


class HtmlIndexProvider:
    """Download and normalize supported technical-article index pages."""

    def __init__(
        self,
        session: requests.Session,
        timeout_seconds: float,
        user_agent: str,
        max_summary_chars: int,
    ) -> None:
        self._session = session
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent
        self._max_summary_chars = max_summary_chars
        self._parsers: dict[
            str,
            Callable[[Source, bytes, datetime, int], list[Article]],
        ] = {
            "all_about_circuits_technical": (
                _parse_all_about_circuits_articles
            ),
        }

    def fetch(
        self,
        source: Source,
        fetched_at: datetime,
    ) -> tuple[list[Article], dict[str, Any]]:
        parser = self._parsers.get(source.id)
        if parser is None:
            raise FeedFetchError(
                "Unsupported HTML index source: "
                f"{source.id}"
            )

        response = self._request(source)
        articles = parser(
            source,
            response.content,
            fetched_at,
            self._max_summary_chars,
        )

        metadata = {
            "http_status": response.status_code,
            "final_url": response.url,
            "content_type": response.headers.get(
                "Content-Type"
            ),
            "request_profile": "browser_compatible",
            "retry_count": 0,
            "parser": source.id,
            "warning": (
                "HTML index returned no technical articles"
                if not articles
                else None
            ),
        }
        return articles, metadata

    def _request(self, source: Source) -> requests.Response:
        try:
            response = self._session.get(
                source.url,
                timeout=self._timeout_seconds,
                headers=self._headers(source.url),
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise FeedFetchError(str(exc)) from exc

    def _headers(self, url: str) -> dict[str, str]:
        parsed_url = urlsplit(url)
        origin = (
            f"{parsed_url.scheme}://{parsed_url.netloc}/"
        )
        return {
            "User-Agent": (
                self._user_agent.strip()
                or _BROWSER_USER_AGENT
            ),
            "Accept": _HTML_ACCEPT,
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": origin,
        }


def _parse_all_about_circuits_articles(
    source: Source,
    content: bytes,
    fetched_at: datetime,
    max_summary_chars: int,
) -> list[Article]:
    soup = BeautifulSoup(content, "html.parser")
    root = soup.select_one("main") or soup
    articles: list[Article] = []
    seen_urls: set[str] = set()

    for heading in root.find_all(["h2", "h3"]):
        title = _clean_text(
            heading.get_text(" ", strip=True)
        )
        if not title or title == "Latest Technical Articles":
            continue

        link = _heading_link(heading)
        if link is None:
            continue

        href = _clean_text(link.get("href", ""))
        if not href:
            continue

        container = _find_article_container(heading)
        if container is None:
            continue

        container_text = _clean_text(
            container.get_text(" ", strip=True)
        )
        if not _is_technical_article(container_text):
            continue

        url = urljoin(source.url, href)
        if url in seen_urls:
            continue

        published_at = _extract_published_at(
            container_text
        )
        summary = _extract_summary(
            container,
            title=title,
            max_summary_chars=max_summary_chars,
        )
        author = _extract_author(container_text)

        articles.append(
            Article(
                source_id=source.id,
                source_name=source.name,
                category=source.category,
                source_priority=source.priority,
                source_tags=source.tags,
                title=title,
                url=url,
                external_id=url,
                published_at=published_at,
                updated_at=None,
                summary=summary,
                author=author,
                fetched_at=_to_iso(fetched_at),
            )
        )
        seen_urls.add(url)

    return articles


def _heading_link(heading: Tag) -> Tag | None:
    direct = heading.find("a", href=True)
    if isinstance(direct, Tag):
        return direct

    parent_link = heading.find_parent("a", href=True)
    if isinstance(parent_link, Tag):
        return parent_link

    return None


def _find_article_container(
    heading: Tag,
) -> Tag | None:
    current: Tag | None = heading

    for _ in range(8):
        parent = current.parent
        if not isinstance(parent, Tag):
            return None

        current = parent
        text = _clean_text(
            current.get_text(" ", strip=True)
        )
        has_date = _DATE_RE.search(text) is not None
        has_type = (
            "Technical Articles" in text
            or "Projects" in text
        )

        if has_date and has_type:
            return current

        if current.name == "main":
            break

    return None


def _is_technical_article(container_text: str) -> bool:
    if "Technical Articles" not in container_text:
        return False

    technical_position = container_text.find(
        "Technical Articles"
    )
    project_position = container_text.find("Projects")

    return (
        project_position < 0
        or technical_position < project_position
    )


def _extract_published_at(
    container_text: str,
) -> str | None:
    match = _DATE_RE.search(container_text)
    if match is None:
        return None

    raw_date = match.group(0)
    for date_format in (
        "%b %d, %Y",
        "%B %d, %Y",
    ):
        try:
            parsed = datetime.strptime(
                raw_date,
                date_format,
            ).replace(tzinfo=timezone.utc)
            return _to_iso(parsed)
        except ValueError:
            continue

    return None


def _extract_author(
    container_text: str,
) -> str | None:
    match = _BY_RE.search(container_text)
    if match is None:
        return None

    author = _clean_text(match.group(1))
    author = _DATE_RE.split(author, maxsplit=1)[0]
    author = _clean_text(author).rstrip(" |\t·•-–—:")
    return author or None


def _extract_summary(
    container: Tag,
    *,
    title: str,
    max_summary_chars: int,
) -> str:
    candidates: list[str] = []

    for paragraph in container.find_all("p"):
        text = _clean_text(
            paragraph.get_text(" ", strip=True)
        )
        if not text or text == title:
            continue
        candidates.append(text)

    if not candidates:
        return ""

    summary = max(candidates, key=len)
    if (
        max_summary_chars > 0
        and len(summary) > max_summary_chars
    ):
        summary = (
            summary[: max_summary_chars - 1].rstrip()
            + "…"
        )
    return summary


def _clean_text(value: str) -> str:
    return _WHITESPACE_RE.sub(
        " ",
        unescape(str(value)),
    ).strip()


def _to_iso(value: datetime) -> str:
    normalized = (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
    )
    return normalized.isoformat().replace(
        "+00:00",
        "Z",
    )
