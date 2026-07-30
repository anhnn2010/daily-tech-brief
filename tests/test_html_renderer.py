from __future__ import annotations

import pytest

from src.models import Article
from src.ranking.rule_based import RankedArticle
from src.renderers.html import render_html_digest


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


def test_renderer_creates_standalone_responsive_html() -> None:
    html = render_html_digest(
        [make_ranked_article()],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert html.startswith("<!doctype html>")
    assert '<meta name="viewport"' in html
    assert "@media (prefers-color-scheme: dark)" in html
    assert "@media (max-width: 600px)" in html
    assert "@media print" in html
    assert "<script" not in html
    assert "https://cdn" not in html
    assert "Download EPUB" not in html
    assert 'class="edition-actions"' not in html



def test_renderer_adds_relative_epub_download_action() -> None:
    html = render_html_digest(
        [make_ranked_article()],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
        epub_href="digest.epub",
    )

    assert '<p class="edition-actions">' in html
    assert (
        '<a class="download-link" href="digest.epub" download>'
        in html
    )
    assert "Download EPUB" in html
    assert "min-height: 42px" in html
    assert ".category-nav, .edition-actions { display: none; }" in html


def test_renderer_escapes_epub_download_href() -> None:
    html = render_html_digest(
        [make_ranked_article()],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
        epub_href='digest.epub?edition=1&name="daily"',
    )

    assert (
        'href="digest.epub?edition=1&amp;name=&quot;daily&quot;"'
        in html
    )
    assert 'href="digest.epub?edition=1&name="daily""' not in html

def test_renderer_groups_articles_in_profile_category_order() -> None:
    html = render_html_digest(
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

    assert html.index('id="linux"') < html.index('id="python"')
    assert 'href="#linux">Linux (1)</a>' in html
    assert 'href="#python">Python (1)</a>' in html
    assert 'href="#ebook"' not in html


def test_renderer_converts_times_to_profile_timezone() -> None:
    html = render_html_digest(
        [make_ranked_article()],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert "Daily Tech Brief — July 30, 2026" in html
    assert "Generated at 2026-07-30 11:00 Asia/Ho_Chi_Minh" in html
    assert "2026-07-30 09:00 Asia/Ho_Chi_Minh" in html
    assert 'datetime="2026-07-30T02:00:00Z"' in html


def test_renderer_escapes_untrusted_feed_content_and_urls() -> None:
    html = render_html_digest(
        [
            make_ranked_article(
                title='Linux <Update> & "News"',
                source_name="Source <One> & Co",
                url="https://example.com/article?a=1&b=2",
                summary="Use <script>alert('x')</script> & continue.",
                matched_keywords=("linux <kernel>",),
            )
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
        project_name="Daily <Tech> & Brief",
    )

    assert "Linux &lt;Update&gt; &amp; &quot;News&quot;" in html
    assert "Source &lt;One&gt; &amp; Co" in html
    assert "Use &lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; &amp; continue." in html
    assert 'href="https://example.com/article?a=1&amp;b=2"' in html
    assert "linux &lt;kernel&gt;" in html
    assert "Daily &lt;Tech&gt; &amp; Brief" in html
    assert "<script>alert" not in html


def test_renderer_normalizes_summary_and_shows_matched_interests() -> None:
    html = render_html_digest(
        [
            make_ranked_article(
                summary="First line.\n\n   Second line.",
                matched_keywords=("arch linux", "kde plasma"),
            )
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert '<p class="summary">First line. Second line.</p>' in html
    assert '<ul class="interest-list" aria-label="Matched interests">' in html
    assert "<li>arch linux</li>" in html
    assert "<li>kde plasma</li>" in html


def test_renderer_can_hide_scores_and_omit_empty_summary() -> None:
    html = render_html_digest(
        [make_ranked_article(summary="   ", score=77)],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
        include_scores=False,
    )

    assert "Score 77" not in html
    assert '<p class="summary">' not in html
    assert "Read the original article →" in html


def test_renderer_falls_back_to_updated_at_and_ignores_invalid_date() -> None:
    fallback_html = render_html_digest(
        [
            make_ranked_article(
                published_at=None,
                updated_at="2026-07-30T03:00:00Z",
            )
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )
    invalid_html = render_html_digest(
        [
            make_ranked_article(
                published_at="not-a-date",
                updated_at="2026-07-30T03:00:00Z",
            )
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert "2026-07-30 10:00 Asia/Ho_Chi_Minh" in fallback_html
    assert 'datetime="2026-07-30T03:00:00Z"' in fallback_html
    assert "2026-07-30 10:00 Asia/Ho_Chi_Minh" not in invalid_html
    assert "not-a-date" not in invalid_html


def test_renderer_humanizes_category_missing_from_profile() -> None:
    html = render_html_digest(
        [make_ranked_article(category="developer_tools")],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert 'href="#developer-tools">Developer Tools (1)</a>' in html
    assert 'id="developer-tools"' in html
    assert "<span>Developer Tools</span>" in html


def test_renderer_handles_empty_digest() -> None:
    html = render_html_digest(
        [],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    assert "0 articles" in html
    assert "No articles were selected for this edition." in html
    assert '<nav class="category-nav"' not in html
    assert '<article class="article-card">' not in html


@pytest.mark.parametrize(
    ("kwargs", "error_message"),
    [
        ({"project_name": "   "}, "project_name must be a non-empty string"),
        ({"include_scores": "yes"}, "include_scores must be a boolean"),
        (
            {"epub_href": ""},
            "epub_href must be None or a non-empty string",
        ),
        (
            {"epub_href": "   "},
            "epub_href must be None or a non-empty string",
        ),
        (
            {"epub_href": 123},
            "epub_href must be None or a non-empty string",
        ),
        ({"generated_at": "invalid"}, "generated_at must be a valid ISO datetime"),
    ],
)
def test_renderer_validates_options(
    kwargs: dict[str, object],
    error_message: str,
) -> None:
    options = {
        "generated_at": "2026-07-30T04:00:00Z",
        **kwargs,
    }

    with pytest.raises(ValueError, match=error_message):
        render_html_digest(
            [make_ranked_article()],
            make_profile(),
            **options,
        )


def test_renderer_validates_profile_timezone_language_and_categories() -> None:
    invalid_timezone = make_profile()
    invalid_timezone["profile"]["timezone"] = "Unknown/Timezone"  # type: ignore[index]

    invalid_language = make_profile()
    invalid_language["profile"]["language"] = ""  # type: ignore[index]

    invalid_categories = make_profile()
    invalid_categories["categories"] = {}

    with pytest.raises(ValueError, match="Unknown timezone"):
        render_html_digest(
            [],
            invalid_timezone,
            generated_at="2026-07-30T04:00:00Z",
        )

    with pytest.raises(ValueError, match="language must be a non-empty string"):
        render_html_digest(
            [],
            invalid_language,
            generated_at="2026-07-30T04:00:00Z",
        )

    with pytest.raises(ValueError, match="non-empty 'categories' mapping"):
        render_html_digest(
            [],
            invalid_categories,
            generated_at="2026-07-30T04:00:00Z",
        )
