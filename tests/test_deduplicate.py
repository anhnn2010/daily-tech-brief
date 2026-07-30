from __future__ import annotations

from src.filters.deduplicate import deduplicate_articles, normalize_article_url
from src.models import Article


def make_article(
    *,
    url: str,
    title: str = "Example article",
    source_id: str = "example",
    source_name: str = "Example Source",
    source_priority: int = 5,
    published_at: str | None = "2026-07-30T01:00:00+00:00",
    updated_at: str | None = None,
    summary: str = "A useful summary.",
    author: str | None = None,
) -> Article:
    return Article(
        source_id=source_id,
        source_name=source_name,
        category="python",
        source_priority=source_priority,
        source_tags=("python",),
        title=title,
        url=url,
        external_id=None,
        published_at=published_at,
        updated_at=updated_at,
        summary=summary,
        author=author,
        fetched_at="2026-07-30T02:00:00+00:00",
    )


def test_normalize_url_removes_tracking_fragment_and_default_port() -> None:
    url = (
        "HTTPS://Example.COM:443/articles/python/"
        "?utm_source=rss&fbclid=tracking#comments"
    )

    assert normalize_article_url(url) == "https://example.com/articles/python"


def test_normalize_url_preserves_and_sorts_meaningful_query_parameters() -> None:
    url = "https://example.com/search/?page=2&category=linux&page=1&utm_medium=feed"

    assert (
        normalize_article_url(url)
        == "https://example.com/search?category=linux&page=1&page=2"
    )


def test_normalize_url_keeps_root_path_and_non_default_port() -> None:
    assert normalize_article_url("http://Example.com:8080/") == "http://example.com:8080/"


def test_normalize_url_rejects_empty_relative_and_unsupported_urls() -> None:
    assert normalize_article_url("") is None
    assert normalize_article_url("/relative/article") is None
    assert normalize_article_url("ftp://example.com/article") is None
    assert normalize_article_url("https://example.com:invalid/article") is None


def test_deduplicate_articles_groups_equivalent_urls() -> None:
    first = make_article(
        url="https://example.com/article/?utm_source=rss",
        title="First copy",
    )
    duplicate = make_article(
        url="https://EXAMPLE.com:443/article#section",
        title="Second copy",
    )

    result = deduplicate_articles([first, duplicate])

    assert result.articles == (first,)
    assert result.duplicate_articles == (duplicate,)
    assert result.invalid_url_articles == ()
    assert len(result.duplicate_groups) == 1
    assert result.duplicate_groups[0].canonical_url == "https://example.com/article"
    assert result.duplicate_groups[0].kept_article is first
    assert result.duplicate_groups[0].duplicate_articles == (duplicate,)


def test_deduplicate_articles_keeps_the_more_complete_record() -> None:
    incomplete = make_article(
        url="https://example.com/article?utm_campaign=daily",
        source_id="low_priority",
        source_priority=3,
        published_at=None,
        summary="",
        author=None,
    )
    complete = make_article(
        url="https://example.com/article",
        source_id="high_priority",
        source_priority=9,
        published_at="2026-07-30T01:00:00+00:00",
        updated_at="2026-07-30T01:30:00+00:00",
        summary="A longer and more useful summary of the same article.",
        author="Example Author",
    )

    result = deduplicate_articles([incomplete, complete])

    assert result.articles == (complete,)
    assert result.duplicate_articles == (incomplete,)
    assert result.duplicate_groups[0].kept_article is complete


def test_deduplicate_articles_preserves_first_canonical_group_order() -> None:
    first_group_initial = make_article(
        url="https://example.com/first?utm_source=rss",
        title="Incomplete first article",
        published_at=None,
        summary="",
    )
    second_group = make_article(
        url="https://example.com/second",
        title="Second article",
    )
    first_group_better = make_article(
        url="https://example.com/first",
        title="Complete first article",
        summary="A complete summary.",
    )

    result = deduplicate_articles(
        [first_group_initial, second_group, first_group_better]
    )

    assert result.articles == (first_group_better, second_group)


def test_deduplicate_articles_separates_invalid_urls_and_reports_counts() -> None:
    valid = make_article(url="https://example.com/article")
    duplicate = make_article(url="https://example.com/article?gclid=tracking")
    invalid = make_article(url="not-a-url")

    result = deduplicate_articles([valid, duplicate, invalid])

    assert result.articles == (valid,)
    assert result.duplicate_articles == (duplicate,)
    assert result.invalid_url_articles == (invalid,)
    assert result.summary() == {
        "total_articles": 3,
        "unique_articles": 1,
        "duplicate_articles": 1,
        "invalid_url_articles": 1,
        "duplicate_groups": 1,
    }
