from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from src.models import Article, FeedFetchError, Source
from src.providers.router import ProviderRouter


class StubProvider:
    def __init__(
        self,
        result: tuple[list[Article], dict[str, Any]],
    ) -> None:
        self.result = result
        self.calls: list[tuple[Source, datetime]] = []

    def fetch(
        self,
        source: Source,
        fetched_at: datetime,
    ) -> tuple[list[Article], dict[str, Any]]:
        self.calls.append((source, fetched_at))
        return self.result


def make_source(
    *,
    provider: str,
    source_id: str = "example",
) -> Source:
    return Source(
        id=source_id,
        name="Example",
        provider=provider,
        format="rss",
        url="https://example.com/source",
        category="analog_mixed_signal",
        priority=10,
        cadence="daily",
        enabled=True,
        official=True,
        tags=("pll",),
    )


def test_router_uses_feed_provider() -> None:
    fetched_at = datetime(
        2026,
        7,
        31,
        tzinfo=timezone.utc,
    )
    feed = StubProvider(([], {"provider": "feed"}))
    html = StubProvider(([], {"provider": "html"}))
    router = ProviderRouter(
        feed_provider=feed,
        html_index_provider=html,
    )
    source = make_source(provider="feed")

    result = router.fetch(source, fetched_at)

    assert result == ([], {"provider": "feed"})
    assert feed.calls == [(source, fetched_at)]
    assert html.calls == []


def test_router_uses_html_index_provider() -> None:
    fetched_at = datetime(
        2026,
        7,
        31,
        tzinfo=timezone.utc,
    )
    feed = StubProvider(([], {"provider": "feed"}))
    html = StubProvider(([], {"provider": "html"}))
    router = ProviderRouter(
        feed_provider=feed,
        html_index_provider=html,
    )
    source = make_source(
        provider="html_index",
        source_id="all_about_circuits_technical",
    )

    result = router.fetch(source, fetched_at)

    assert result == ([], {"provider": "html"})
    assert html.calls == [(source, fetched_at)]
    assert feed.calls == []


def test_router_rejects_unknown_provider() -> None:
    feed = StubProvider(([], {}))
    html = StubProvider(([], {}))
    router = ProviderRouter(
        feed_provider=feed,
        html_index_provider=html,
    )
    source = make_source(provider="unknown")

    with pytest.raises(
        FeedFetchError,
        match=(
            "Unsupported source provider "
            "'unknown'.*feed, html_index"
        ),
    ):
        router.fetch(
            source,
            datetime.now(timezone.utc),
        )

    assert feed.calls == []
    assert html.calls == []
