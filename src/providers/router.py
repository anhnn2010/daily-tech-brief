from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from src.models import Article, FeedFetchError, Source


class ArticleProvider(Protocol):
    """Common contract implemented by article source providers."""

    def fetch(
        self,
        source: Source,
        fetched_at: datetime,
    ) -> tuple[list[Article], dict[str, Any]]:
        ...


class ProviderRouter:
    """Route a source to the provider declared in sources.yml."""

    def __init__(
        self,
        *,
        feed_provider: ArticleProvider,
        html_index_provider: ArticleProvider,
    ) -> None:
        self._providers: dict[str, ArticleProvider] = {
            "feed": feed_provider,
            "html_index": html_index_provider,
        }

    def fetch(
        self,
        source: Source,
        fetched_at: datetime,
    ) -> tuple[list[Article], dict[str, Any]]:
        provider = self._providers.get(source.provider)

        if provider is None:
            supported = ", ".join(sorted(self._providers))
            raise FeedFetchError(
                "Unsupported source provider "
                f"'{source.provider}' for source "
                f"'{source.id}'. Supported providers: "
                f"{supported}"
            )

        return provider.fetch(source, fetched_at)
