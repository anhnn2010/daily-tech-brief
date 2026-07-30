from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.models import Article


_TRACKING_QUERY_PARAMETERS = {
    "_hsenc",
    "_hsmi",
    "dclid",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "oly_anon_id",
    "oly_enc_id",
    "rb_clickid",
    "s_cid",
    "vero_conv",
    "vero_id",
}


@dataclass(frozen=True)
class DuplicateGroup:
    """Articles that resolve to the same canonical URL."""

    canonical_url: str
    kept_article: Article
    duplicate_articles: tuple[Article, ...]


@dataclass(frozen=True)
class DeduplicationResult:
    """Unique articles plus records excluded during URL deduplication."""

    articles: tuple[Article, ...]
    duplicate_articles: tuple[Article, ...]
    invalid_url_articles: tuple[Article, ...]
    duplicate_groups: tuple[DuplicateGroup, ...]

    @property
    def total_articles(self) -> int:
        return (
            len(self.articles)
            + len(self.duplicate_articles)
            + len(self.invalid_url_articles)
        )

    @property
    def unique_articles(self) -> int:
        return len(self.articles)

    def summary(self) -> dict[str, int]:
        """Return JSON-friendly counters for logs and reports."""

        return {
            "total_articles": self.total_articles,
            "unique_articles": self.unique_articles,
            "duplicate_articles": len(self.duplicate_articles),
            "invalid_url_articles": len(self.invalid_url_articles),
            "duplicate_groups": len(self.duplicate_groups),
        }


def deduplicate_articles(articles: Iterable[Article]) -> DeduplicationResult:
    """Remove duplicate articles by comparing their canonical URLs.

    Articles with invalid HTTP(S) URLs are excluded from the unique result and
    returned separately. When several records point to the same canonical URL,
    the most complete record is retained. Input order is preserved according to
    the first appearance of each canonical URL.
    """

    grouped_articles: dict[str, list[Article]] = {}
    canonical_order: list[str] = []
    invalid_url_articles: list[Article] = []

    for article in articles:
        canonical_url = normalize_article_url(article.url)
        if canonical_url is None:
            invalid_url_articles.append(article)
            continue

        if canonical_url not in grouped_articles:
            grouped_articles[canonical_url] = []
            canonical_order.append(canonical_url)

        grouped_articles[canonical_url].append(article)

    unique_articles: list[Article] = []
    duplicate_articles: list[Article] = []
    duplicate_groups: list[DuplicateGroup] = []

    for canonical_url in canonical_order:
        group = grouped_articles[canonical_url]
        kept_article = _select_best_article(group)
        removed_articles = tuple(
            article for article in group if article is not kept_article
        )

        unique_articles.append(kept_article)
        duplicate_articles.extend(removed_articles)

        if removed_articles:
            duplicate_groups.append(
                DuplicateGroup(
                    canonical_url=canonical_url,
                    kept_article=kept_article,
                    duplicate_articles=removed_articles,
                )
            )

    return DeduplicationResult(
        articles=tuple(unique_articles),
        duplicate_articles=tuple(duplicate_articles),
        invalid_url_articles=tuple(invalid_url_articles),
        duplicate_groups=tuple(duplicate_groups),
    )


def normalize_article_url(url: str) -> str | None:
    """Return a stable HTTP(S) URL suitable for duplicate comparison.

    The normalization removes fragments and common analytics parameters,
    lowercases the scheme and host, removes default ports, sorts remaining
    query parameters, and removes a non-root trailing slash.
    """

    candidate = url.strip()
    if not candidate:
        return None

    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname
    if scheme not in {"http", "https"} or hostname is None:
        return None

    normalized_host = hostname.lower().rstrip(".")
    if not normalized_host:
        return None

    if ":" in normalized_host and not normalized_host.startswith("["):
        normalized_host = f"[{normalized_host}]"

    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    netloc = normalized_host if port is None or default_port else f"{normalized_host}:{port}"

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_parameter(key)
    ]
    query_items.sort(key=lambda item: (item[0].lower(), item[0], item[1]))
    query = urlencode(query_items, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def _is_tracking_parameter(name: str) -> bool:
    normalized = name.strip().lower()
    return normalized.startswith("utm_") or normalized in _TRACKING_QUERY_PARAMETERS


def _select_best_article(articles: list[Article]) -> Article:
    return max(articles, key=_article_quality)


def _article_quality(article: Article) -> tuple[int, int, int, int, int, int]:
    summary = article.summary.strip()
    return (
        int(bool(article.published_at and article.published_at.strip())),
        int(bool(article.updated_at and article.updated_at.strip())),
        int(bool(summary)),
        min(len(summary), 4000),
        int(bool(article.author and article.author.strip())),
        article.source_priority,
    )
