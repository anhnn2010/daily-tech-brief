from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.models import Source
from src.providers.feed import FeedProvider


FIXED_NOW = datetime(
    2026,
    7,
    31,
    4,
    30,
    tzinfo=timezone.utc,
)

FULL_BODY = " ".join(
    [
        "Current mirrors distribute stable bias currents across analog blocks."
    ]
    * 12
)


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        url: str,
    ) -> None:
        self.content = content
        self.url = url
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None


class SingleResponseSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def _source(*, format_name: str = "rss") -> Source:
    return Source(
        id="analog_feed",
        name="Analog Feed",
        provider="feed",
        format=format_name,
        url="https://feeds.example.com/analog.xml",
        category="semiconductor",
        priority=10,
        cadence="daily",
        enabled=True,
        official=True,
        tags=("analog", "biasing"),
    )


def _provider(
    content: bytes,
    *,
    format_name: str = "rss",
) -> FeedProvider:
    source = _source(format_name=format_name)
    session = SingleResponseSession(
        FakeResponse(content, source.url)
    )
    return FeedProvider(
        session=session,
        timeout_seconds=20,
        user_agent="DailyTechBrief-Test/0.7.0",
        max_summary_chars=2_000,
    )


def test_rss_content_encoded_is_kept_as_private_full_body() -> None:
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss
      version="2.0"
      xmlns:content="http://purl.org/rss/1.0/modules/content/"
    >
      <channel>
        <title>Analog Engineering</title>
        <item>
          <title>Current Mirror Validation</title>
          <link>https://example.com/articles/current-mirror</link>
          <guid>current-mirror</guid>
          <pubDate>Fri, 31 Jul 2026 03:00:00 GMT</pubDate>
          <description>Short public summary.</description>
          <content:encoded><![CDATA[
            <h2>Current mirror validation</h2>
            <p>{FULL_BODY}</p>
            <p><a href="/measurements">Measurement guide</a></p>
          ]]></content:encoded>
        </item>
      </channel>
    </rss>
    """.encode()

    articles, _ = _provider(content).fetch(
        _source(),
        fetched_at=FIXED_NOW,
    )

    article = articles[0]
    assert article.summary == "Short public summary."
    assert article.content_status == "extracted"
    assert article.has_full_content is True
    assert "Current mirror validation" in article.content_text
    assert "stable bias currents" in article.content_text
    assert (
        'href="https://example.com/measurements"'
        in article.content_html
    )


def test_atom_content_is_kept_separate_from_public_summary() -> None:
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Analog Engineering</title>
      <entry>
        <title>PLL Charge Pump Matching</title>
        <id>tag:example.com,2026:charge-pump</id>
        <link
          rel="alternate"
          href="https://example.com/articles/charge-pump"
        />
        <published>2026-07-31T03:00:00Z</published>
        <summary>Short Atom summary.</summary>
        <content type="html"><![CDATA[
          <h2>Charge pump matching</h2>
          <p>{FULL_BODY}</p>
        ]]></content>
      </entry>
    </feed>
    """.encode()

    articles, _ = _provider(
        content,
        format_name="atom",
    ).fetch(
        _source(format_name="atom"),
        fetched_at=FIXED_NOW,
    )

    article = articles[0]
    assert article.summary == "Short Atom summary."
    assert article.content_status == "extracted"
    assert "Charge pump matching" in article.content_text
    assert "stable bias currents" in article.content_text


def test_description_only_feed_does_not_claim_full_content() -> None:
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
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

    articles, _ = _provider(content).fetch(
        _source(),
        fetched_at=FIXED_NOW,
    )

    article = articles[0]
    assert article.summary == "Practical PLL bring-up notes."
    assert article.content_html == ""
    assert article.content_text == ""
    assert article.content_status == "not_requested"
    assert article.has_full_content is False


def test_short_explicit_feed_content_falls_back_to_web_enrichment() -> None:
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss
      version="2.0"
      xmlns:content="http://purl.org/rss/1.0/modules/content/"
    >
      <channel>
        <title>Analog Engineering</title>
        <item>
          <title>Short Feed Body</title>
          <link>https://example.com/short</link>
          <description>Useful public summary.</description>
          <content:encoded><![CDATA[
            <p>Too short to count as a full article.</p>
          ]]></content:encoded>
        </item>
      </channel>
    </rss>
    """

    articles, _ = _provider(content).fetch(
        _source(),
        fetched_at=FIXED_NOW,
    )

    article = articles[0]
    assert article.summary == "Useful public summary."
    assert article.content_status == "not_requested"
    assert article.has_full_content is False
