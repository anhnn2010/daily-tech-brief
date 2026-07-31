from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
import requests

from src.models import FeedFetchError, Source
from src.providers.feed import FeedProvider


FIXED_NOW = datetime(
    2026,
    7,
    31,
    4,
    30,
    tzinfo=timezone.utc,
)

RSS_CONTENT = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Analog Engineering</title>
    <item>
      <title>PLL Lock Detection</title>
      <link>https://example.com/pll-lock</link>
      <guid>pll-lock</guid>
      <pubDate>Fri, 31 Jul 2026 03:00:00 GMT</pubDate>
      <description>Practical PLL bring-up notes.</description>
    </item>
  </channel>
</rss>
"""


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        url: str,
        status_code: int = 200,
    ) -> None:
        self.content = content
        self.url = url
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"{self.status_code} error for {self.url}"
            )


class SequenceSession:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if not self.outcomes:
            raise AssertionError("Unexpected extra request")

        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_source() -> Source:
    return Source(
        id="analog_test_feed",
        name="Analog Test Feed",
        provider="feed",
        format="rss",
        url="https://feeds.example.com/analog/rss",
        category="analog_mixed_signal",
        priority=10,
        cadence="daily",
        enabled=True,
        official=True,
        tags=("pll", "calibration"),
    )


def make_provider(
    session: SequenceSession,
    *,
    timeout_seconds: float = 20,
) -> FeedProvider:
    return FeedProvider(
        session=session,
        timeout_seconds=timeout_seconds,
        user_agent="DailyTechBrief-Test/0.7.0",
        max_summary_chars=2000,
    )


def test_timeout_retries_with_browser_headers() -> None:
    source = make_source()
    session = SequenceSession(
        [
            requests.ReadTimeout("first request timed out"),
            FakeResponse(RSS_CONTENT, source.url),
        ]
    )
    provider = make_provider(session)

    articles, metadata = provider.fetch(
        source,
        fetched_at=FIXED_NOW,
    )

    assert len(articles) == 1
    assert articles[0].title == "PLL Lock Detection"
    assert metadata["request_profile"] == (
        "browser_compatible_timeout_retry"
    )
    assert metadata["retry_count"] == 1

    assert len(session.calls) == 2
    first_call, retry_call = session.calls
    assert first_call["timeout"] == 20
    assert first_call["headers"]["User-Agent"] == (
        "DailyTechBrief-Test/0.7.0"
    )

    assert retry_call["timeout"] == 40
    assert retry_call["headers"]["User-Agent"].startswith(
        "Mozilla/5.0"
    )
    assert retry_call["headers"]["Referer"] == (
        "https://feeds.example.com/"
    )
    assert retry_call["headers"]["Cache-Control"] == (
        "no-cache"
    )


def test_timeout_retry_is_capped_at_sixty_seconds() -> None:
    source = make_source()
    session = SequenceSession(
        [
            requests.ConnectTimeout("connection timed out"),
            FakeResponse(RSS_CONTENT, source.url),
        ]
    )
    provider = make_provider(
        session,
        timeout_seconds=40,
    )

    _, metadata = provider.fetch(
        source,
        fetched_at=FIXED_NOW,
    )

    assert session.calls[0]["timeout"] == 40
    assert session.calls[1]["timeout"] == 60
    assert metadata["retry_count"] == 1


def test_second_timeout_is_reported_as_feed_error() -> None:
    source = make_source()
    session = SequenceSession(
        [
            requests.ReadTimeout("first timeout"),
            requests.ReadTimeout("retry timeout"),
        ]
    )
    provider = make_provider(session)

    with pytest.raises(
        FeedFetchError,
        match="retry timeout",
    ):
        provider.fetch(
            source,
            fetched_at=FIXED_NOW,
        )

    assert len(session.calls) == 2
    assert session.calls[1]["timeout"] == 40


def test_forbidden_response_retries_with_same_timeout() -> None:
    source = make_source()
    session = SequenceSession(
        [
            FakeResponse(
                b"forbidden",
                source.url,
                status_code=403,
            ),
            FakeResponse(RSS_CONTENT, source.url),
        ]
    )
    provider = make_provider(session)

    articles, metadata = provider.fetch(
        source,
        fetched_at=FIXED_NOW,
    )

    assert len(articles) == 1
    assert session.calls[0]["timeout"] == 20
    assert session.calls[1]["timeout"] == 20
    assert metadata["request_profile"] == (
        "browser_compatible"
    )
    assert metadata["retry_count"] == 1
