from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

from src.models import Article, FeedFetchError, Source


_WHITESPACE_RE = re.compile(r"\s+")


class FeedProvider:
    """Download and normalize RSS 1.0, RSS 2.0, or Atom feeds."""

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

    def fetch(
        self,
        source: Source,
        fetched_at: datetime,
    ) -> tuple[list[Article], dict[str, Any]]:
        try:
            response = self._session.get(
                source.url,
                timeout=self._timeout_seconds,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": (
                        "application/rss+xml, application/atom+xml, "
                        "application/xml, text/xml;q=0.9, */*;q=0.5"
                    ),
                },
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise FeedFetchError(str(exc)) from exc

        try:
            parsed = _parse_feed(response.content)
        except ET.ParseError as exc:
            raise FeedFetchError(f"Invalid XML: {exc}") from exc
        except ValueError as exc:
            raise FeedFetchError(str(exc)) from exc

        articles = [
            _build_article(
                source=source,
                entry=entry,
                fetched_at=fetched_at,
                max_summary_chars=self._max_summary_chars,
            )
            for entry in parsed.entries
        ]

        metadata = {
            "http_status": response.status_code,
            "final_url": response.url,
            "feed_title": parsed.title,
            "warning": "Feed returned no entries" if not articles else None,
        }
        return articles, metadata


class ParsedFeed:
    def __init__(self, title: str | None, entries: list[dict[str, str | None]]) -> None:
        self.title = title
        self.entries = entries


def _parse_feed(content: bytes) -> ParsedFeed:
    root = ET.fromstring(content)
    root_name = _local_name(root.tag).lower()

    if root_name == "feed":
        return _parse_atom(root)
    if root_name == "rss":
        return _parse_rss2(root)
    if root_name == "rdf":
        return _parse_rss1(root)

    raise ValueError(f"Unsupported feed root element: {root_name}")


def _parse_rss2(root: ET.Element) -> ParsedFeed:
    channel = _first_child(root, "channel")
    if channel is None:
        raise ValueError("RSS feed is missing the channel element")

    title = _element_text(_first_child(channel, "title")) or None
    entries = [_parse_rss_item(item) for item in _children(channel, "item")]
    return ParsedFeed(title=title, entries=entries)


def _parse_rss1(root: ET.Element) -> ParsedFeed:
    channel = _first_child(root, "channel")
    title = _element_text(_first_child(channel, "title")) if channel is not None else ""
    entries = [_parse_rss_item(item) for item in _children(root, "item")]
    return ParsedFeed(title=title or None, entries=entries)


def _parse_rss_item(item: ET.Element) -> dict[str, str | None]:
    summary_element = _first_present_child(
        item,
        "encoded",
        "description",
        "summary",
    )
    published = (
        _element_text(_first_child(item, "pubDate"))
        or _element_text(_first_child(item, "date"))
        or _element_text(_first_child(item, "published"))
    )
    updated = _element_text(_first_child(item, "updated"))
    author = (
        _element_text(_first_child(item, "author"))
        or _element_text(_first_child(item, "creator"))
    )
    return {
        "title": _element_text(_first_child(item, "title")),
        "url": _element_text(_first_child(item, "link")),
        "external_id": (
            _element_text(_first_child(item, "guid"))
            or _element_text(_first_child(item, "id"))
        ),
        "published": published,
        "updated": updated,
        "summary": _element_content(summary_element),
        "author": author,
    }


def _parse_atom(root: ET.Element) -> ParsedFeed:
    title = _element_text(_first_child(root, "title")) or None
    entries = [_parse_atom_entry(entry) for entry in _children(root, "entry")]
    return ParsedFeed(title=title, entries=entries)


def _parse_atom_entry(entry: ET.Element) -> dict[str, str | None]:
    summary_element = _first_present_child(entry, "summary", "content")
    author_element = _first_child(entry, "author")
    author = None
    if author_element is not None:
        author = _element_text(_first_child(author_element, "name")) or _element_text(
            author_element
        )

    return {
        "title": _element_text(_first_child(entry, "title")),
        "url": _atom_link(entry),
        "external_id": _element_text(_first_child(entry, "id")),
        "published": _element_text(_first_child(entry, "published")),
        "updated": _element_text(_first_child(entry, "updated")),
        "summary": _element_content(summary_element),
        "author": author,
    }


def _atom_link(entry: ET.Element) -> str:
    fallback = ""
    for link in _children(entry, "link"):
        href = str(link.attrib.get("href", "")).strip()
        rel = str(link.attrib.get("rel", "alternate")).strip()
        if not href:
            continue
        if rel in {"alternate", ""}:
            return href
        if not fallback:
            fallback = href
    return fallback


def _build_article(
    source: Source,
    entry: dict[str, str | None],
    fetched_at: datetime,
    max_summary_chars: int,
) -> Article:
    title = _clean_text(entry.get("title") or "") or "Untitled"
    url = _clean_text(entry.get("url") or "")
    summary = _clean_html(entry.get("summary") or "")
    if max_summary_chars > 0 and len(summary) > max_summary_chars:
        summary = summary[: max_summary_chars - 1].rstrip() + "…"

    return Article(
        source_id=source.id,
        source_name=source.name,
        category=source.category,
        source_priority=source.priority,
        source_tags=source.tags,
        title=title,
        url=url,
        external_id=_optional_text(entry.get("external_id") or url),
        published_at=_parse_datetime(entry.get("published")),
        updated_at=_parse_datetime(entry.get("updated")),
        summary=summary,
        author=_optional_text(entry.get("author")),
        fetched_at=_to_iso(fetched_at),
    )


def _children(element: ET.Element, name: str) -> Iterable[ET.Element]:
    return (child for child in element if _local_name(child.tag) == name)


def _first_child(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    return next(_children(element, name), None)



def _first_present_child(
    element: ET.Element | None,
    *names: str,
) -> ET.Element | None:
    for name in names:
        child = _first_child(element, name)
        if child is not None:
            return child
    return None

def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return _clean_text(" ".join(element.itertext()))


def _element_content(element: ET.Element | None) -> str:
    if element is None:
        return ""
    if len(element) == 0:
        return element.text or ""

    parts: list[str] = []
    if element.text:
        parts.append(element.text)
    parts.extend(ET.tostring(child, encoding="unicode") for child in element)
    return " ".join(parts)


def _parse_datetime(value: str | None) -> str | None:
    if not value:
        return None

    text = value.strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _to_iso(parsed)


def _clean_html(value: str) -> str:
    if not value:
        return ""
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return _clean_text(text)


def _clean_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", unescape(value)).strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _clean_text(str(value))
    return text or None


def _to_iso(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")
