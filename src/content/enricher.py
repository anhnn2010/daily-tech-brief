from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from time import monotonic
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

from src.content.extractor import (
    ArticleContentExtractor,
    ContentExtractionError,
)
from src.models import Article


_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)

_HTML_ACCEPT = (
    "text/html, application/xhtml+xml;q=0.9, "
    "application/xml;q=0.8, */*;q=0.5"
)

_ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}

_CONTENT_STATUS_EXTRACTED = "extracted"
_CONTENT_STATUS_SUMMARY_FALLBACK = "summary_fallback"
_CONTENT_STATUS_FETCH_FAILED = "fetch_failed"
_CONTENT_STATUS_NOT_REQUESTED = "not_requested"


@dataclass(frozen=True)
class ContentEnrichmentRecord:
    source_id: str
    title: str
    url: str
    status: str
    http_status: int | None
    content_type: str | None
    selector: str | None
    word_count: int
    duration_seconds: float
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContentEnrichmentResult:
    articles: tuple[Article, ...]
    records: tuple[ContentEnrichmentRecord, ...]

    @property
    def requested_count(self) -> int:
        return len(self.records)

    @property
    def extracted_count(self) -> int:
        return sum(
            record.status == _CONTENT_STATUS_EXTRACTED
            for record in self.records
        )

    @property
    def fallback_count(self) -> int:
        return sum(
            record.status == _CONTENT_STATUS_SUMMARY_FALLBACK
            for record in self.records
        )

    @property
    def failed_count(self) -> int:
        return sum(
            record.status == _CONTENT_STATUS_FETCH_FAILED
            for record in self.records
        )

    def summary(self) -> dict[str, Any]:
        return {
            "requested_articles": self.requested_count,
            "extracted_articles": self.extracted_count,
            "summary_fallback_articles": self.fallback_count,
            "failed_articles": self.failed_count,
            "records": [
                record.to_dict()
                for record in self.records
            ],
        }


class ArticleContentEnricher:
    """Fetch and extract readable content for selected articles only."""

    def __init__(
        self,
        *,
        session: requests.Session,
        extractor: ArticleContentExtractor,
        timeout_seconds: float = 15.0,
        maximum_download_bytes: int = 5_000_000,
        user_agent: str = _BROWSER_USER_AGENT,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero"
            )

        if (
            not isinstance(maximum_download_bytes, int)
            or isinstance(maximum_download_bytes, bool)
            or maximum_download_bytes < 1
        ):
            raise ValueError(
                "maximum_download_bytes must be a positive integer"
            )

        if not isinstance(user_agent, str) or not user_agent.strip():
            raise ValueError(
                "user_agent must be a non-empty string"
            )

        self._session = session
        self._extractor = extractor
        self._timeout_seconds = timeout_seconds
        self._maximum_download_bytes = maximum_download_bytes
        self._user_agent = user_agent.strip()

    def enrich(
        self,
        articles: Iterable[Article],
    ) -> ContentEnrichmentResult:
        """Enrich articles in input order without failing the whole edition."""

        enriched_articles: list[Article] = []
        records: list[ContentEnrichmentRecord] = []

        for article in articles:
            enriched_article, record = self._enrich_one(article)
            enriched_articles.append(enriched_article)
            records.append(record)

        return ContentEnrichmentResult(
            articles=tuple(enriched_articles),
            records=tuple(records),
        )

    def _enrich_one(
        self,
        article: Article,
    ) -> tuple[Article, ContentEnrichmentRecord]:
        started = monotonic()

        if article.has_full_content:
            return (
                article,
                ContentEnrichmentRecord(
                    source_id=article.source_id,
                    title=article.title,
                    url=article.url,
                    status=article.content_status,
                    http_status=None,
                    content_type=None,
                    selector=None,
                    word_count=_word_count(
                        article.content_text
                    ),
                    duration_seconds=_duration(started),
                    error=None,
                ),
            )

        if not _is_http_url(article.url):
            return self._fallback(
                article,
                started=started,
                error="Article URL is not a valid HTTP or HTTPS URL",
            )

        response: requests.Response | None = None

        try:
            response = self._session.get(
                article.url,
                timeout=self._timeout_seconds,
                headers=self._headers(article.url),
                stream=True,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            http_status = (
                response.status_code
                if response is not None
                else None
            )
            content_type = (
                _normalize_content_type(
                    response.headers.get("Content-Type")
                )
                if response is not None
                else None
            )
            if response is not None:
                response.close()

            return self._fetch_failed(
                article,
                started=started,
                error=str(exc),
                http_status=http_status,
                content_type=content_type,
            )

        content_type = _normalize_content_type(
            response.headers.get("Content-Type")
        )

        if (
            content_type is not None
            and content_type not in _ALLOWED_CONTENT_TYPES
        ):
            response.close()
            return self._fallback(
                article,
                started=started,
                http_status=response.status_code,
                content_type=content_type,
                error=(
                    "Unsupported article content type: "
                    f"{content_type}"
                ),
            )

        try:
            body = _read_limited_body(
                response,
                maximum_bytes=self._maximum_download_bytes,
            )
        except requests.RequestException as exc:
            return self._fetch_failed(
                article,
                started=started,
                error=str(exc),
                http_status=response.status_code,
                content_type=content_type,
            )
        except ValueError as exc:
            return self._fallback(
                article,
                started=started,
                http_status=response.status_code,
                content_type=content_type,
                error=str(exc),
            )
        finally:
            response.close()

        try:
            extracted = self._extractor.extract(
                body,
                base_url=response.url or article.url,
            )
        except ContentExtractionError as exc:
            return self._fallback(
                article,
                started=started,
                http_status=response.status_code,
                content_type=content_type,
                error=str(exc),
            )

        if not extracted.is_usable:
            return self._fallback(
                article,
                started=started,
                http_status=response.status_code,
                content_type=content_type,
                selector=extracted.selector,
                word_count=extracted.word_count,
                error=(
                    "Readable article content was too short "
                    "after extraction"
                ),
            )

        enriched_article = replace(
            article,
            content_html=extracted.content_html,
            content_text=extracted.content_text,
            content_status=_CONTENT_STATUS_EXTRACTED,
        )

        return (
            enriched_article,
            ContentEnrichmentRecord(
                source_id=article.source_id,
                title=article.title,
                url=article.url,
                status=_CONTENT_STATUS_EXTRACTED,
                http_status=response.status_code,
                content_type=content_type,
                selector=extracted.selector,
                word_count=extracted.word_count,
                duration_seconds=_duration(started),
                error=None,
            ),
        )

    def _headers(
        self,
        url: str,
    ) -> dict[str, str]:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}/"

        return {
            "User-Agent": self._user_agent,
            "Accept": _HTML_ACCEPT,
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": origin,
        }

    def _fallback(
        self,
        article: Article,
        *,
        started: float,
        error: str,
        http_status: int | None = None,
        content_type: str | None = None,
        selector: str | None = None,
        word_count: int = 0,
    ) -> tuple[Article, ContentEnrichmentRecord]:
        fallback_article = replace(
            article,
            content_html="",
            content_text="",
            content_status=_CONTENT_STATUS_SUMMARY_FALLBACK,
        )

        return (
            fallback_article,
            ContentEnrichmentRecord(
                source_id=article.source_id,
                title=article.title,
                url=article.url,
                status=_CONTENT_STATUS_SUMMARY_FALLBACK,
                http_status=http_status,
                content_type=content_type,
                selector=selector,
                word_count=word_count,
                duration_seconds=_duration(started),
                error=error,
            ),
        )

    def _fetch_failed(
        self,
        article: Article,
        *,
        started: float,
        error: str,
        http_status: int | None = None,
        content_type: str | None = None,
    ) -> tuple[Article, ContentEnrichmentRecord]:
        failed_article = replace(
            article,
            content_html="",
            content_text="",
            content_status=_CONTENT_STATUS_FETCH_FAILED,
        )

        return (
            failed_article,
            ContentEnrichmentRecord(
                source_id=article.source_id,
                title=article.title,
                url=article.url,
                status=_CONTENT_STATUS_FETCH_FAILED,
                http_status=http_status,
                content_type=content_type,
                selector=None,
                word_count=0,
                duration_seconds=_duration(started),
                error=error,
            ),
        )


def enrich_selected_articles(
    articles: Iterable[Article],
    *,
    session: requests.Session | None = None,
    extractor: ArticleContentExtractor | None = None,
    timeout_seconds: float = 15.0,
    maximum_download_bytes: int = 5_000_000,
    user_agent: str = _BROWSER_USER_AGENT,
) -> ContentEnrichmentResult:
    """Convenience wrapper for enriching selected articles."""

    owned_session = session is None
    active_session = session or requests.Session()

    try:
        enricher = ArticleContentEnricher(
            session=active_session,
            extractor=extractor or ArticleContentExtractor(),
            timeout_seconds=timeout_seconds,
            maximum_download_bytes=maximum_download_bytes,
            user_agent=user_agent,
        )
        return enricher.enrich(articles)
    finally:
        if owned_session:
            active_session.close()


def _read_limited_body(
    response: requests.Response,
    *,
    maximum_bytes: int,
) -> bytes:
    content_length = response.headers.get("Content-Length")

    if (
        isinstance(content_length, str)
        and content_length.isdigit()
        and int(content_length) > maximum_bytes
    ):
        raise ValueError(
            "Article response exceeds maximum download size"
        )

    chunks: list[bytes] = []
    total = 0

    for chunk in response.iter_content(
        chunk_size=64 * 1024,
    ):
        if not chunk:
            continue

        total += len(chunk)
        if total > maximum_bytes:
            raise ValueError(
                "Article response exceeds maximum download size"
            )

        chunks.append(chunk)

    if not chunks:
        raise ValueError(
            "Article response body is empty"
        )

    return b"".join(chunks)


def _normalize_content_type(
    value: str | None,
) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    return value.split(
        ";",
        maxsplit=1,
    )[0].strip().lower()


def _is_http_url(
    value: str,
) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False

    parsed = urlparse(value.strip())
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
    )


def _duration(
    started: float,
) -> float:
    return round(
        max(0.0, monotonic() - started),
        3,
    )


def _word_count(
    value: str,
) -> int:
    return len(
        [
            item
            for item in value.split()
            if item
        ]
    )
