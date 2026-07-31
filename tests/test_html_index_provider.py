from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
import requests

from src.models import FeedFetchError, Source
from src.providers.html_index import HtmlIndexProvider


TECHNICAL_INDEX_HTML = b"""<!doctype html>
<html lang="en">
  <head>
    <title>Technical Articles</title>
  </head>
  <body>
    <main>
      <article class="content-card">
        <span class="content-type">Technical Articles</span>
        <h2>
          <a href="/technical-articles/understanding-pll-loop-filters/">
            Understanding PLL Loop Filters &amp; Bandwidth
          </a>
        </h2>
        <p class="author">by Robert Keim July 30, 2026</p>
        <p class="summary">
          Learn how loop-filter components affect PLL bandwidth,
          damping, lock time, and phase-noise performance.
        </p>
      </article>

      <article class="content-card">
        <span class="content-type">Technical Articles</span>
        <h3>
          <a href="https://www.allaboutcircuits.com/technical-articles/adc-clock-jitter/">
            How Clock Jitter Limits ADC Performance
          </a>
        </h3>
        <p class="author">by Bonnie Baker July 29, 2026</p>
        <p class="summary">
          This article connects sampling uncertainty with SNR and ENOB.
        </p>
      </article>

      <article class="content-card">
        <span class="content-type">Projects</span>
        <h2>
          <a href="/projects/build-a-simple-audio-board/">
            Build a Simple Audio Board
          </a>
        </h2>
        <p>by Project Author July 28, 2026</p>
        <p>This project should not be collected.</p>
      </article>

      <article class="content-card duplicate">
        <span class="content-type">Technical Articles</span>
        <h2>
          <a href="/technical-articles/understanding-pll-loop-filters/">
            Duplicate PLL Card
          </a>
        </h2>
        <p>by Duplicate Author July 30, 2026</p>
        <p>This duplicate URL should be ignored.</p>
      </article>
    </main>
  </body>
</html>
"""


EMPTY_INDEX_HTML = b"""<!doctype html>
<html lang="en">
  <body>
    <main>
      <h1>Technical Articles</h1>
      <p>No article cards are available.</p>
    </main>
  </body>
</html>
"""


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        *,
        status_code: int = 200,
        url: str = "https://www.allaboutcircuits.com/technical-articles/",
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.url = url
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}",
                response=self,  # type: ignore[arg-type]
            )


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def make_source(
    *,
    source_id: str = "all_about_circuits_technical",
) -> Source:
    return Source(
        id=source_id,
        name="All About Circuits Technical Articles",
        provider="html_index",
        format="html",
        url="https://www.allaboutcircuits.com/technical-articles/",
        category="analog_mixed_signal",
        priority=10,
        cadence="daily",
        enabled=True,
        official=True,
        tags=(
            "analog",
            "pll",
            "adc",
            "technical_learning",
        ),
    )


def make_provider(
    response: FakeResponse,
    *,
    max_summary_chars: int = 500,
) -> tuple[HtmlIndexProvider, FakeSession]:
    session = FakeSession(response)
    provider = HtmlIndexProvider(
        session=session,  # type: ignore[arg-type]
        timeout_seconds=12,
        user_agent="DailyTechBrief/0.7.0",
        max_summary_chars=max_summary_chars,
    )
    return provider, session


def test_fetch_parses_only_unique_technical_articles() -> None:
    provider, _ = make_provider(
        FakeResponse(TECHNICAL_INDEX_HTML)
    )
    fetched_at = datetime(
        2026,
        7,
        31,
        1,
        30,
        tzinfo=timezone.utc,
    )

    articles, metadata = provider.fetch(
        make_source(),
        fetched_at,
    )

    assert len(articles) == 2
    assert [article.title for article in articles] == [
        "Understanding PLL Loop Filters & Bandwidth",
        "How Clock Jitter Limits ADC Performance",
    ]
    assert all(
        "Build a Simple Audio Board" != article.title
        for article in articles
    )

    pll_article = articles[0]
    assert pll_article.source_id == "all_about_circuits_technical"
    assert pll_article.source_name == (
        "All About Circuits Technical Articles"
    )
    assert pll_article.category == "analog_mixed_signal"
    assert pll_article.source_priority == 10
    assert pll_article.source_tags == (
        "analog",
        "pll",
        "adc",
        "technical_learning",
    )
    assert pll_article.url == (
        "https://www.allaboutcircuits.com/technical-articles/"
        "understanding-pll-loop-filters/"
    )
    assert pll_article.external_id == pll_article.url
    assert pll_article.published_at == "2026-07-30T00:00:00Z"
    assert pll_article.updated_at is None
    assert pll_article.author == "Robert Keim"
    assert pll_article.summary == (
        "Learn how loop-filter components affect PLL bandwidth, "
        "damping, lock time, and phase-noise performance."
    )
    assert pll_article.fetched_at == "2026-07-31T01:30:00Z"

    assert metadata == {
        "http_status": 200,
        "final_url": (
            "https://www.allaboutcircuits.com/technical-articles/"
        ),
        "content_type": "text/html; charset=utf-8",
        "request_profile": "browser_compatible",
        "retry_count": 0,
        "parser": "all_about_circuits_technical",
        "warning": None,
    }


def test_fetch_uses_browser_compatible_request_headers() -> None:
    provider, session = make_provider(
        FakeResponse(TECHNICAL_INDEX_HTML)
    )

    provider.fetch(
        make_source(),
        datetime.now(timezone.utc),
    )

    assert len(session.calls) == 1
    request = session.calls[0]
    assert request["url"] == (
        "https://www.allaboutcircuits.com/technical-articles/"
    )
    assert request["timeout"] == 12

    headers = request["headers"]
    assert headers["User-Agent"] == "DailyTechBrief/0.7.0"
    assert "text/html" in headers["Accept"]
    assert headers["Accept-Language"] == "en-US,en;q=0.9"
    assert headers["Referer"] == (
        "https://www.allaboutcircuits.com/"
    )


def test_summary_is_normalized_and_truncated() -> None:
    provider, _ = make_provider(
        FakeResponse(TECHNICAL_INDEX_HTML),
        max_summary_chars=48,
    )

    articles, _ = provider.fetch(
        make_source(),
        datetime.now(timezone.utc),
    )

    assert articles[0].summary == (
        "Learn how loop-filter components affect PLL ban…"
    )
    assert len(articles[0].summary) == 48


def test_empty_index_returns_warning() -> None:
    provider, _ = make_provider(
        FakeResponse(EMPTY_INDEX_HTML)
    )

    articles, metadata = provider.fetch(
        make_source(),
        datetime.now(timezone.utc),
    )

    assert articles == []
    assert metadata["warning"] == (
        "HTML index returned no technical articles"
    )


def test_unsupported_html_index_source_is_rejected() -> None:
    provider, session = make_provider(
        FakeResponse(TECHNICAL_INDEX_HTML)
    )

    with pytest.raises(
        FeedFetchError,
        match="Unsupported HTML index source: unknown_source",
    ):
        provider.fetch(
            make_source(source_id="unknown_source"),
            datetime.now(timezone.utc),
        )

    assert session.calls == []


def test_http_error_is_wrapped_as_feed_fetch_error() -> None:
    provider, _ = make_provider(
        FakeResponse(
            b"Service unavailable",
            status_code=503,
        )
    )

    with pytest.raises(
        FeedFetchError,
        match="HTTP 503",
    ):
        provider.fetch(
            make_source(),
            datetime.now(timezone.utc),
        )
