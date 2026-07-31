from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

import pytest
import requests

from src.content.enricher import (
    ArticleContentEnricher,
    enrich_selected_articles,
)
from src.content.extractor import (
    ArticleContentExtractor,
    ContentExtractionError,
    ExtractedContent,
)
from src.models import Article


class FakeResponse:
    def __init__(
        self,
        *,
        body: bytes = b"",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        url: str = "https://example.com/final",
        chunks: Iterable[bytes] | None = None,
        stream_error: Exception | None = None,
    ) -> None:
        self.body = body
        self.status_code = status_code
        self.headers = headers or {
            "Content-Type": "text/html; charset=utf-8",
        }
        self.url = url
        self.chunks = tuple(chunks) if chunks is not None else None
        self.stream_error = stream_error
        self.closed = False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(
                f"{self.status_code} Client Error"
            )
            error.response = self  # type: ignore[assignment]
            raise error

    def iter_content(
        self,
        chunk_size: int,
    ) -> Iterable[bytes]:
        del chunk_size
        if self.stream_error is not None:
            raise self.stream_error
        if self.chunks is not None:
            yield from self.chunks
            return
        yield self.body

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(
        self,
        outcomes: list[FakeResponse | Exception],
    ) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self) -> None:
        self.closed = True


class StubExtractor:
    def __init__(
        self,
        result: ExtractedContent | Exception,
    ) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def extract(
        self,
        html: str | bytes,
        *,
        base_url: str,
    ) -> ExtractedContent:
        self.calls.append(
            {
                "html": html,
                "base_url": base_url,
            }
        )
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _article(
    *,
    title: str = "PLL Fundamentals",
    url: str = "https://example.com/pll",
) -> Article:
    return Article(
        source_id="example",
        source_name="Example",
        category="technical_learning",
        source_priority=10,
        source_tags=("pll",),
        title=title,
        url=url,
        external_id="example:pll",
        published_at="2026-07-31T00:00:00Z",
        updated_at=None,
        summary="Fallback summary.",
        author="Example Author",
        fetched_at="2026-07-31T01:00:00Z",
    )


def _usable_extracted() -> ExtractedContent:
    return ExtractedContent(
        content_html="<h2>Loop filter</h2><p>Full content.</p>",
        content_text="Loop filter\n\nFull content.",
        status="extracted",
        selector="[itemprop='articleBody']",
        word_count=4,
    )


def _enricher(
    session: FakeSession,
    extractor: StubExtractor | ArticleContentExtractor,
    *,
    timeout_seconds: float = 15.0,
    maximum_download_bytes: int = 5_000_000,
) -> ArticleContentEnricher:
    return ArticleContentEnricher(
        session=session,  # type: ignore[arg-type]
        extractor=extractor,  # type: ignore[arg-type]
        timeout_seconds=timeout_seconds,
        maximum_download_bytes=maximum_download_bytes,
        user_agent="TestAgent/1.0",
    )


def test_enriches_article_and_uses_browser_headers() -> None:
    response = FakeResponse(
        body=b"<html>article</html>",
        url="https://example.com/final-pll",
    )
    session = FakeSession([response])
    extractor = StubExtractor(_usable_extracted())

    result = _enricher(
        session,
        extractor,
        timeout_seconds=12,
    ).enrich([_article()])

    article = result.articles[0]
    record = result.records[0]

    assert article.content_status == "extracted"
    assert article.content_html.startswith("<h2>")
    assert article.content_text == "Loop filter\n\nFull content."
    assert article.has_full_content is True

    assert record.status == "extracted"
    assert record.http_status == 200
    assert record.content_type == "text/html"
    assert record.selector == "[itemprop='articleBody']"
    assert record.word_count == 4
    assert record.error is None
    assert record.content_origin == "web"

    assert extractor.calls == [
        {
            "html": b"<html>article</html>",
            "base_url": "https://example.com/final-pll",
        }
    ]

    request = session.calls[0]
    assert request["timeout"] == 12
    assert request["stream"] is True
    assert request["allow_redirects"] is True
    assert request["headers"]["User-Agent"] == "TestAgent/1.0"
    assert request["headers"]["Referer"] == "https://example.com/"
    assert "text/html" in request["headers"]["Accept"]
    assert response.closed is True


def test_timeout_and_http_error_use_available_summary() -> None:
    session = FakeSession(
        [
            requests.ReadTimeout("slow site"),
            FakeResponse(status_code=403),
        ]
    )
    extractor = StubExtractor(_usable_extracted())

    result = _enricher(session, extractor).enrich(
        [
            _article(title="Timeout"),
            _article(title="Forbidden"),
        ]
    )

    assert [article.content_status for article in result.articles] == [
        "summary_fallback",
        "summary_fallback",
    ]
    assert [record.status for record in result.records] == [
        "summary_fallback",
        "summary_fallback",
    ]
    assert [record.word_count for record in result.records] == [
        2,
        2,
    ]
    assert [record.content_origin for record in result.records] == [
        "summary",
        "summary",
    ]
    assert "slow site" in (result.records[0].error or "")
    assert "403 Client Error" in (result.records[1].error or "")
    assert extractor.calls == []


def test_request_error_without_summary_remains_fetch_failed() -> None:
    session = FakeSession(
        [requests.ConnectTimeout("offline")]
    )
    extractor = StubExtractor(_usable_extracted())
    article = replace(_article(), summary="")

    result = _enricher(session, extractor).enrich([article])

    assert result.articles[0].content_status == "fetch_failed"
    assert result.records[0].status == "fetch_failed"
    assert result.records[0].content_origin == "none"
    assert "offline" in (result.records[0].error or "")
    assert extractor.calls == []


def test_unsupported_content_type_uses_summary_fallback() -> None:
    response = FakeResponse(
        body=b"%PDF",
        headers={"Content-Type": "application/pdf"},
    )
    session = FakeSession([response])
    extractor = StubExtractor(_usable_extracted())

    result = _enricher(session, extractor).enrich([_article()])

    assert result.articles[0].content_status == "summary_fallback"
    assert result.articles[0].has_full_content is False
    assert result.records[0].content_type == "application/pdf"
    assert "Unsupported article content type" in (
        result.records[0].error or ""
    )
    assert response.closed is True
    assert extractor.calls == []


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            FakeResponse(
                headers={
                    "Content-Type": "text/html",
                    "Content-Length": "5001",
                },
            ),
            "exceeds maximum download size",
        ),
        (
            FakeResponse(
                headers={"Content-Type": "text/html"},
                chunks=(b"a" * 600, b"b" * 600),
            ),
            "exceeds maximum download size",
        ),
        (
            FakeResponse(
                headers={"Content-Type": "text/html"},
                chunks=(),
            ),
            "response body is empty",
        ),
    ],
)
def test_invalid_response_body_uses_summary_fallback(
    response: FakeResponse,
    message: str,
) -> None:
    session = FakeSession([response])
    extractor = StubExtractor(_usable_extracted())

    result = _enricher(
        session,
        extractor,
        maximum_download_bytes=1000,
    ).enrich([_article()])

    assert result.articles[0].content_status == "summary_fallback"
    assert message in (result.records[0].error or "")
    assert response.closed is True
    assert extractor.calls == []


def test_insufficient_extraction_uses_summary_fallback() -> None:
    response = FakeResponse(body=b"<html>short</html>")
    session = FakeSession([response])
    extractor = StubExtractor(
        ExtractedContent(
            content_html="",
            content_text="Short text",
            status="insufficient_content",
            selector="article",
            word_count=2,
        )
    )

    article = replace(
        _article(),
        summary="Readable fallback summary for offline use.",
    )
    result = _enricher(session, extractor).enrich([article])

    assert result.articles[0].content_status == "summary_fallback"
    assert result.records[0].selector == "article"
    assert result.records[0].word_count == 6
    assert "too short" in (result.records[0].error or "")


def test_extractor_error_uses_summary_fallback() -> None:
    response = FakeResponse(body=b"<html>bad</html>")
    session = FakeSession([response])
    extractor = StubExtractor(
        ContentExtractionError("invalid article markup")
    )

    result = _enricher(session, extractor).enrich([_article()])

    assert result.articles[0].content_status == "summary_fallback"
    assert result.records[0].error == "invalid article markup"


def test_unexpected_extractor_error_uses_summary_fallback() -> None:
    response = FakeResponse(body=b"<html>broken</html>")
    session = FakeSession([response])
    extractor = StubExtractor(RuntimeError("parser bug"))

    result = _enricher(session, extractor).enrich([_article()])

    assert result.articles[0].content_status == "summary_fallback"
    assert result.records[0].status == "summary_fallback"
    assert result.records[0].word_count == 2
    assert result.records[0].error == (
        "Unexpected content extraction error: parser bug"
    )
    assert response.closed is True


def test_invalid_article_url_skips_request() -> None:
    session = FakeSession([])
    extractor = StubExtractor(_usable_extracted())

    result = _enricher(session, extractor).enrich(
        [_article(url="file:///tmp/article.html")]
    )

    assert result.articles[0].content_status == "summary_fallback"
    assert "valid HTTP or HTTPS URL" in (
        result.records[0].error or ""
    )
    assert session.calls == []
    assert extractor.calls == []


def test_existing_content_is_preserved_without_request() -> None:
    original = replace(
        _article(),
        content_html="<p>Feed full content.</p>",
        content_text="Feed full content.",
        content_status="feed_content",
    )
    session = FakeSession([])
    extractor = StubExtractor(_usable_extracted())

    result = _enricher(session, extractor).enrich([original])

    assert result.articles == (original,)
    assert result.records[0].status == "feed_content"
    assert result.records[0].word_count == 3
    assert session.calls == []
    assert extractor.calls == []


def test_preserves_input_order_and_summarizes_statuses() -> None:
    session = FakeSession(
        [
            FakeResponse(body=b"<html>one</html>"),
            requests.ConnectTimeout("offline"),
            FakeResponse(
                body=b"binary",
                headers={"Content-Type": "application/octet-stream"},
            ),
        ]
    )
    extractor = StubExtractor(_usable_extracted())
    articles = [
        _article(title="One"),
        _article(title="Two"),
        _article(title="Three"),
    ]

    result = _enricher(session, extractor).enrich(articles)

    assert [article.title for article in result.articles] == [
        "One",
        "Two",
        "Three",
    ]
    assert result.requested_count == 3
    assert result.extracted_count == 1
    assert result.fallback_count == 2
    assert result.failed_count == 0

    summary = result.summary()
    assert summary["requested_articles"] == 3
    assert summary["extracted_articles"] == 1
    assert summary["summary_fallback_articles"] == 2
    assert summary["failed_articles"] == 0
    assert len(summary["records"]) == 3


def test_streaming_request_error_uses_available_summary() -> None:
    response = FakeResponse(
        headers={"Content-Type": "text/html"},
        stream_error=requests.exceptions.ChunkedEncodingError(
            "connection interrupted"
        ),
    )
    session = FakeSession([response])
    extractor = StubExtractor(_usable_extracted())

    result = _enricher(session, extractor).enrich([_article()])

    assert result.articles[0].content_status == "summary_fallback"
    assert result.records[0].status == "summary_fallback"
    assert "connection interrupted" in (
        result.records[0].error or ""
    )
    assert response.closed is True


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"maximum_download_bytes": 0}, "maximum_download_bytes"),
        ({"maximum_download_bytes": True}, "maximum_download_bytes"),
        ({"user_agent": ""}, "user_agent"),
    ],
)
def test_constructor_rejects_invalid_options(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ArticleContentEnricher(
            session=FakeSession([]),  # type: ignore[arg-type]
            extractor=StubExtractor(  # type: ignore[arg-type]
                _usable_extracted()
            ),
            **kwargs,
        )


def test_wrapper_keeps_external_session_open() -> None:
    response = FakeResponse(body=b"<html>article</html>")
    session = FakeSession([response])
    extractor = StubExtractor(_usable_extracted())

    result = enrich_selected_articles(
        [_article()],
        session=session,  # type: ignore[arg-type]
        extractor=extractor,  # type: ignore[arg-type]
    )

    assert result.extracted_count == 1
    assert session.closed is False


def test_preloaded_content_reports_feed_and_curated_origins() -> None:
    feed_article = replace(
        _article(title="Feed content"),
        content_html="<p>Full feed article body.</p>",
        content_text="Full feed article body.",
        content_status="extracted",
    )
    curated_article = replace(
        _article(title="Curated lesson"),
        source_tags=(
            "technical_learning",
            "learning_content:curated",
        ),
        content_html="<p>Curated offline lesson.</p>",
        content_text="Curated offline lesson.",
        content_status="extracted",
    )
    session = FakeSession([])
    extractor = StubExtractor(_usable_extracted())

    result = _enricher(session, extractor).enrich(
        [feed_article, curated_article]
    )

    assert [
        record.content_origin
        for record in result.records
    ] == [
        "feed",
        "curated",
    ]
    assert [record.http_status for record in result.records] == [
        None,
        None,
    ]
    assert session.calls == []
    assert extractor.calls == []
