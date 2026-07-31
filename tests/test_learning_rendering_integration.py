from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from src.learning.article import learning_lesson_to_article
from src.learning.library import LearningLesson
from src.models import Article
from src.ranking.rule_based import RankedArticle
from src.renderers.epub import render_epub_digest
from src.renderers.html import render_html_digest
from src.renderers.markdown import render_markdown_digest


GENERATED_AT = "2026-07-31T06:00:00Z"


def _profile() -> dict[str, object]:
    return {
        "profile": {
            "name": "technical-learning-profile",
            "language": "en",
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "categories": {
            "linux": {
                "label": "Linux",
                "weight": 10,
                "daily_quota": 11,
            },
            "technical_learning": {
                "label": "Technical Learning",
                "weight": 10,
                "daily_quota": 0,
            },
        },
    }


def _ranked_news_article() -> RankedArticle:
    article = Article(
        source_id="linux_source",
        source_name="Linux Source",
        category="linux",
        source_priority=10,
        source_tags=("linux",),
        title="Linux automation article",
        url="https://example.com/linux-automation",
        external_id="linux-automation",
        published_at="2026-07-31T04:00:00Z",
        updated_at=None,
        summary="A practical Linux automation article.",
        author="Example Author",
        fetched_at=GENERATED_AT,
    )
    return RankedArticle(
        article=article,
        score=80,
        category_weight=10,
        freshness_hours=2.0,
        matched_high_priority_keywords=("linux",),
        matched_low_priority_keywords=(),
        score_reasons=(),
    )


def _ranked_learning_article() -> RankedArticle:
    lesson = LearningLesson(
        id="pll_fundamentals",
        order=10,
        title="Phase-Locked Loop Fundamentals",
        source_name="Analog Devices",
        url="https://example.com/pll-fundamentals",
        track="pll_and_clocking",
        topics=("pll", "clocking", "phase_noise"),
        difficulty="intermediate",
        estimated_minutes=30,
        summary=(
            "Introduces the main PLL blocks and their closed-loop behavior."
        ),
        why_it_matters=(
            "This knowledge supports clock bring-up, lock debug, and jitter "
            "analysis."
        ),
        enabled=True,
    )
    article = learning_lesson_to_article(
        lesson,
        generated_at=None,
    )
    return RankedArticle(
        article=article,
        score=100,
        category_weight=10,
        freshness_hours=None,
        matched_high_priority_keywords=("pll", "phase noise"),
        matched_low_priority_keywords=(),
        score_reasons=(),
    )


def test_learning_section_is_rendered_in_markdown_html_and_epub() -> None:
    articles = (
        _ranked_learning_article(),
        _ranked_news_article(),
    )
    profile = _profile()

    markdown = render_markdown_digest(
        articles,
        profile,
        generated_at=GENERATED_AT,
    )
    html = render_html_digest(
        articles,
        profile,
        generated_at=GENERATED_AT,
        epub_href="digest.epub",
    )
    epub_bytes = render_epub_digest(
        articles,
        profile,
        generated_at=GENERATED_AT,
    )

    assert markdown.index("## Linux") < markdown.index(
        "## Technical Learning"
    )
    assert "Phase-Locked Loop Fundamentals" in markdown
    assert "Why it matters:" in markdown
    assert "Estimated reading time: 30 minutes." in markdown

    assert html.index('id="linux"') < html.index(
        'id="technical-learning"'
    )
    assert 'href="#technical-learning"' in html
    assert "Technical Learning (1)" in html
    assert "Phase-Locked Loop Fundamentals" in html
    assert 'href="digest.epub"' in html

    with ZipFile(BytesIO(epub_bytes)) as epub:
        names = set(epub.namelist())
        navigation = epub.read("EPUB/nav.xhtml").decode("utf-8")
        chapter = epub.read(
            "EPUB/category-technical-learning.xhtml"
        ).decode("utf-8")

    assert "EPUB/category-technical-learning.xhtml" in names
    assert "Technical Learning" in navigation
    assert "Phase-Locked Loop Fundamentals" in navigation
    assert "Phase-Locked Loop Fundamentals" in chapter
    assert "Why it matters:" in chapter
    assert "Estimated reading time: 30 minutes." in chapter


def test_renderers_omit_empty_technical_learning_section() -> None:
    articles = (_ranked_news_article(),)
    profile = _profile()

    markdown = render_markdown_digest(
        articles,
        profile,
        generated_at=GENERATED_AT,
    )
    html = render_html_digest(
        articles,
        profile,
        generated_at=GENERATED_AT,
    )
    epub_bytes = render_epub_digest(
        articles,
        profile,
        generated_at=GENERATED_AT,
    )

    assert "## Technical Learning" not in markdown
    assert 'id="technical-learning"' not in html

    with ZipFile(BytesIO(epub_bytes)) as epub:
        names = set(epub.namelist())
        navigation = epub.read("EPUB/nav.xhtml").decode("utf-8")

    assert "EPUB/category-technical-learning.xhtml" not in names
    assert "Technical Learning" not in navigation
