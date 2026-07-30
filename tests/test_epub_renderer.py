from __future__ import annotations

from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZIP_STORED, ZipFile

import pytest

from src.models import Article
from src.ranking.rule_based import RankedArticle
from src.renderers.epub import EpubRenderError, render_epub_digest


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
    url: str = "https://example.com/article?utm_source=test&item=1",
    summary: str = "Example summary.",
    published_at: str | None = "2026-07-30T02:00:00Z",
    updated_at: str | None = None,
    author: str | None = None,
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
        author=author,
        fetched_at="2026-07-30T04:00:00Z",
    )
    return RankedArticle(
        article=article,
        score=score,
        category_weight=10,
        freshness_hours=2.0,
        matched_high_priority_keywords=matched_keywords,
        matched_low_priority_keywords=(),
        score_reasons=("Ranking detail that must not be spoken.",),
    )


def open_epub(epub_bytes: bytes) -> ZipFile:
    return ZipFile(BytesIO(epub_bytes))


def read_text(epub: ZipFile, path: str) -> str:
    return epub.read(path).decode("utf-8")


def assert_well_formed_xml(epub: ZipFile, path: str) -> None:
    ElementTree.fromstring(epub.read(path))


def test_renderer_creates_valid_epub_archive_structure() -> None:
    epub_bytes = render_epub_digest(
        [make_ranked_article()],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    with open_epub(epub_bytes) as epub:
        names = epub.namelist()
        mimetype_info = epub.getinfo("mimetype")

        assert names[0] == "mimetype"
        assert mimetype_info.compress_type == ZIP_STORED
        assert read_text(epub, "mimetype") == "application/epub+zip"
        assert "META-INF/container.xml" in names
        assert "EPUB/package.opf" in names
        assert "EPUB/nav.xhtml" in names
        assert "EPUB/toc.ncx" in names
        assert "EPUB/styles.css" in names
        assert "EPUB/title.xhtml" in names
        assert "EPUB/category-linux.xhtml" in names


def test_renderer_generates_well_formed_xml_and_xhtml() -> None:
    epub_bytes = render_epub_digest(
        [make_ranked_article()],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    with open_epub(epub_bytes) as epub:
        for path in (
            "META-INF/container.xml",
            "EPUB/package.opf",
            "EPUB/nav.xhtml",
            "EPUB/toc.ncx",
            "EPUB/title.xhtml",
            "EPUB/category-linux.xhtml",
        ):
            assert_well_formed_xml(epub, path)


def test_renderer_writes_epub_metadata_and_local_generation_time() -> None:
    epub_bytes = render_epub_digest(
        [make_ranked_article()],
        make_profile(),
        generated_at="2026-07-30T04:00:00.987654Z",
        project_name="Daily Tech Brief",
    )

    with open_epub(epub_bytes) as epub:
        package = read_text(epub, "EPUB/package.opf")
        title_page = read_text(epub, "EPUB/title.xhtml")

        assert "Daily Tech Brief — July 30, 2026" in package
        assert "<dc:creator>Daily Tech Brief</dc:creator>" in package
        assert "<dc:language>en</dc:language>" in package
        assert "2026-07-30T04:00:00Z" in package
        assert "urn:uuid:" in package
        assert "Generated at 2026-07-30 11:00 Asia/Ho_Chi_Minh." in title_page
        assert "1 article selected for this edition." in title_page


def test_renderer_groups_chapters_in_profile_order_and_builds_navigation() -> None:
    epub_bytes = render_epub_digest(
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

    with open_epub(epub_bytes) as epub:
        package = read_text(epub, "EPUB/package.opf")
        navigation = read_text(epub, "EPUB/nav.xhtml")
        ncx = read_text(epub, "EPUB/toc.ncx")

        assert package.index("category-linux.xhtml") < package.index(
            "category-python.xhtml"
        )
        assert navigation.index(">Linux</a>") < navigation.index(">Python</a>")
        assert "category-linux.xhtml#article-1" in navigation
        assert "category-python.xhtml#article-1" in navigation
        assert "Linux article" in navigation
        assert "Python article" in navigation
        assert "Linux article" in ncx
        assert "Python article" in ncx
        assert "category-ebook.xhtml" not in package


def test_renderer_preserves_unicode_and_escapes_feed_content() -> None:
    epub_bytes = render_epub_digest(
        [
            make_ranked_article(
                title='KOReader đọc tiếng Việt <tốt> & "mượt"',
                source_name="Nguồn <Một> & Co",
                summary="Hỗ trợ TTS, EPUB và chữ Việt: ă â ê ô ơ ư đ.",
                author="Nguyễn Văn A & Team",
                url="https://example.com/read?a=1&b=2",
            )
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    with open_epub(epub_bytes) as epub:
        chapter = read_text(epub, "EPUB/category-linux.xhtml")
        navigation = read_text(epub, "EPUB/nav.xhtml")

        assert "KOReader đọc tiếng Việt &lt;tốt&gt; &amp; &quot;mượt&quot;" in chapter
        assert "Nguồn &lt;Một&gt; &amp; Co" in chapter
        assert "ă â ê ô ơ ư đ" in chapter
        assert "Nguyễn Văn A &amp; Team" in chapter
        assert 'href="https://example.com/read?a=1&amp;b=2"' in chapter
        assert "KOReader đọc tiếng Việt &lt;tốt&gt; &amp; &quot;mượt&quot;" in navigation
        assert_well_formed_xml(epub, "EPUB/category-linux.xhtml")


def test_renderer_keeps_long_url_out_of_spoken_text() -> None:
    long_url = (
        "https://example.com/a/very/long/path/that/should/not/be/read/aloud"
        "?utm_source=daily-tech-brief&tracking=1234567890"
    )
    epub_bytes = render_epub_digest(
        [
            make_ranked_article(
                url=long_url,
                score=99,
                matched_keywords=("koreader", "text to speech"),
            )
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    with open_epub(epub_bytes) as epub:
        chapter = read_text(epub, "EPUB/category-linux.xhtml")
        visible_text = " ".join(
            text.strip()
            for text in ElementTree.fromstring(chapter).itertext()
            if text.strip()
        )

        assert long_url not in visible_text
        assert "Read the original article" in visible_text
        assert "Score 99" not in visible_text
        assert "koreader" not in visible_text
        assert "text to speech" not in visible_text
        assert "Ranking detail that must not be spoken." not in visible_text
        assert long_url.replace("&", "&amp;") in chapter


def test_renderer_normalizes_summary_and_formats_article_metadata() -> None:
    epub_bytes = render_epub_digest(
        [
            make_ranked_article(
                summary="First line.\n\n   Second   line.",
                published_at=None,
                updated_at="2026-07-29T23:30:00Z",
                author=" Example Author ",
            )
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    with open_epub(epub_bytes) as epub:
        chapter = read_text(epub, "EPUB/category-linux.xhtml")

        assert "Source: Example Source." in chapter
        assert "Published: 2026-07-30 06:30 Asia/Ho_Chi_Minh." in chapter
        assert "Author: Example Author." in chapter
        assert '<p class="summary">First line. Second line.</p>' in chapter


def test_renderer_humanizes_unknown_category_and_handles_slug_collision() -> None:
    epub_bytes = render_epub_digest(
        [
            make_ranked_article(
                title="First tool article",
                category="developer_tools",
            ),
            make_ranked_article(
                title="Second tool article",
                category="developer-tools",
            ),
        ],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    with open_epub(epub_bytes) as epub:
        names = epub.namelist()
        navigation = read_text(epub, "EPUB/nav.xhtml")

        assert "EPUB/category-developer-tools.xhtml" in names
        assert "EPUB/category-developer-tools-2.xhtml" in names
        assert "Developer Tools</a>" in navigation
        assert "Developer-Tools</a>" in navigation


def test_renderer_handles_empty_digest() -> None:
    epub_bytes = render_epub_digest(
        [],
        make_profile(),
        generated_at="2026-07-30T04:00:00Z",
    )

    with open_epub(epub_bytes) as epub:
        package = read_text(epub, "EPUB/package.opf")
        navigation = read_text(epub, "EPUB/nav.xhtml")
        title_page = read_text(epub, "EPUB/title.xhtml")

        assert "category-" not in package
        assert 'href="title.xhtml">Edition information</a>' in navigation
        assert "0 articles selected for this edition." in title_page


def test_renderer_is_deterministic_for_identical_input() -> None:
    arguments = {
        "articles": [make_ranked_article()],
        "profile": make_profile(),
        "generated_at": "2026-07-30T04:00:00Z",
        "project_name": "Daily Tech Brief",
    }

    first = render_epub_digest(**arguments)
    second = render_epub_digest(**arguments)

    assert first == second


@pytest.mark.parametrize(
    ("articles", "profile", "generated_at", "project_name", "message"),
    [
        (
            [],
            make_profile(),
            "2026-07-30T04:00:00Z",
            "   ",
            "project_name must be a non-empty string",
        ),
        (
            [],
            make_profile(),
            "invalid",
            "Daily Tech Brief",
            "generated_at must be an ISO 8601 datetime",
        ),
        (
            [],
            {"profile": {"language": "en", "timezone": "UTC"}},
            "2026-07-30T04:00:00Z",
            "Daily Tech Brief",
            "profile must contain a non-empty 'categories' mapping",
        ),
        (
            [],
            {
                "profile": {"language": "en", "timezone": "Mars/Olympus"},
                "categories": {"linux": {"label": "Linux"}},
            },
            "2026-07-30T04:00:00Z",
            "Daily Tech Brief",
            "Unknown timezone 'Mars/Olympus'",
        ),
    ],
)
def test_renderer_rejects_invalid_options_and_profile(
    articles: list[RankedArticle],
    profile: dict[str, object],
    generated_at: str,
    project_name: str,
    message: str,
) -> None:
    with pytest.raises(EpubRenderError, match=message):
        render_epub_digest(
            articles,
            profile,
            generated_at=generated_at,
            project_name=project_name,
        )
