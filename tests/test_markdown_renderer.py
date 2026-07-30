from __future__ import annotations

from src.models import Article
from src.ranking.rule_based import RankedArticle
from src.renderers.markdown import render_markdown_digest


def make_profile() -> dict[str, object]:
    return {
        "profile": {
            "name": "personal-tech-profile",
            "language": "en",
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "categories": {
            "linux": {
                "label": "Linux",
                "weight": 10,
                "daily_quota": 2,
            },
            "python": {
                "label": "Python",
                "weight": 10,
                "daily_quota": 1,
            },
            "ebook": {
                "label": "Ebook",
                "weight": 9,
                "daily_quota": 1,
            },
        },
    }


def make_ranked_article(
    *,
    title: str = "Example article",
    category: str = "linux",
    source_name: str = "Example Source",
    url: str = "https://example.com/article",
    summary: str = "Example summary.",
    published_at: str | None = "2026-07-30T02:00:00Z",
    updated_at: str | None = None,
    score: int = 50,
    matched_keywords: tuple[str, ...] = (),
) -> RankedArticle:
    article = Article(
        source_id="example_source",
        source_name=source_name,
        category=category,
        source_priority=10,
        source_tags=(),
        title=title,
        url=url,
        external_id=None,
        published_at=published_at,
        updated_at=updated_at,
        summary=summary,
        author=None,
        fetched_at="2026-07-30T04:00:00Z",
    )
    return RankedArticle(
        article=article,
        score=score,
        category_weight=10,
        freshness_hours=2.0,
        matched_high_priority_keywords=matched_keywords,
        matched_low_priority_keywords=(),
        score_reasons=(),
    )


def test_renderer_groups_articles_using_profile_category_order() -> None:
    markdown = render_markdown_digest(
        [
            make_ranked_article(
                title="Python article",
                category="python",
                url="https://example.com/python",
            ),
            make_ranked_article(
                title="Linux article",
                category="linux",
                url="https://example.com/linux",
            ),
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert markdown.index("## Linux") < markdown.index("## Python")
    assert "## Ebook" not in markdown


def test_renderer_converts_generated_and_published_times_to_profile_timezone() -> None:
    markdown = render_markdown_digest(
        [make_ranked_article()],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert "# Daily Tech Brief — July 30, 2026" in markdown
    assert "> Generated at 2026-07-30 11:00 Asia/Ho_Chi_Minh" in markdown
    assert "**Published:** 2026-07-30 09:00 Asia/Ho_Chi_Minh" in markdown


def test_renderer_escapes_markdown_in_project_article_and_source_names() -> None:
    markdown = render_markdown_digest(
        [
            make_ranked_article(
                title="Python [3.14] *preview*",
                source_name="Source_Name",
            )
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
        project_name="Daily *Tech* Brief",
    )

    assert "# Daily \\*Tech\\* Brief — July 30, 2026" in markdown
    assert "### [Python \\[3.14\\] \\*preview\\*]" in markdown
    assert "**Source:** Source\\_Name" in markdown


def test_renderer_normalizes_summary_and_shows_matched_interests() -> None:
    markdown = render_markdown_digest(
        [
            make_ranked_article(
                summary="First line.\n\nSecond   line.",
                matched_keywords=("arch linux", "kde plasma"),
            )
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert "First line. Second line." in markdown
    assert "**Matched interests:** `arch linux`, `kde plasma`" in markdown


def test_renderer_omits_empty_summary_invalid_date_and_score_when_disabled() -> None:
    markdown = render_markdown_digest(
        [
            make_ranked_article(
                summary="   ",
                published_at="not-a-date",
                updated_at=None,
            )
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
        include_scores=False,
    )

    assert "**Published:**" not in markdown
    assert "**Score:**" not in markdown
    assert "Example summary" not in markdown
    assert "[Read the original article]" in markdown


def test_renderer_uses_updated_at_when_published_at_is_missing() -> None:
    markdown = render_markdown_digest(
        [
            make_ranked_article(
                published_at=None,
                updated_at="2026-07-29T23:30:00Z",
            )
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert "**Published:** 2026-07-30 06:30 Asia/Ho_Chi_Minh" in markdown


def test_renderer_humanizes_category_missing_from_profile() -> None:
    markdown = render_markdown_digest(
        [make_ranked_article(category="test_engineering")],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert "## Test Engineering" in markdown


def test_renderer_returns_readable_empty_digest() -> None:
    markdown = render_markdown_digest(
        [],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert "# Daily Tech Brief — July 30, 2026" in markdown
    assert "No articles were selected for this edition." in markdown
    assert "## Linux" not in markdown


def test_renderer_accepts_naive_generated_datetime_as_utc() -> None:
    markdown = render_markdown_digest(
        [make_ranked_article()],
        make_profile(),
        generated_at="2026-07-30T04:00:00",
    )

    assert "> Generated at 2026-07-30 11:00 Asia/Ho_Chi_Minh" in markdown


def test_renderer_rejects_invalid_options_and_profile() -> None:
    try:
        render_markdown_digest(
            [],
            make_profile(),
            generated_at="invalid",
        )
    except ValueError as exc:
        assert "generated_at must be a valid ISO datetime" in str(exc)
    else:
        raise AssertionError("Expected invalid generated_at to fail")

    try:
        render_markdown_digest(
            [],
            make_profile(),
            generated_at="2026-07-30T04:00:00Z",
            include_scores="yes",  # type: ignore[arg-type]
        )
    except ValueError as exc:
        assert "include_scores must be a boolean" in str(exc)
    else:
        raise AssertionError("Expected invalid include_scores to fail")
