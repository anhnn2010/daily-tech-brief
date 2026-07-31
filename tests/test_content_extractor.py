from __future__ import annotations

import pytest

from src.content.extractor import (
    ArticleContentExtractor,
    ContentExtractionError,
)


def _long_paragraph(label: str, repeat: int = 16) -> str:
    sentence = (
        f"{label} explains the circuit behavior, measurement setup, "
        "trade-offs, and practical debugging considerations. "
    )
    return sentence * repeat


def test_extracts_article_body_and_removes_page_noise() -> None:
    html = f"""
    <html>
      <body>
        <nav>Home Products Documentation</nav>
        <main>
          <article>
            <h1>PLL Fundamentals</h1>
            <div class="article-body" itemprop="articleBody">
              <h2>Introduction</h2>
              <p>{_long_paragraph("A phase-locked loop")}</p>
              <div class="advertisement">Buy this product now</div>
              <aside>Sidebar newsletter</aside>
              <div class="related-posts">Related articles</div>
              <ul>
                <li>Phase-frequency detector</li>
                <li>Charge pump</li>
                <li>Loop filter</li>
              </ul>
            </div>
          </article>
        </main>
        <footer>Copyright and site links</footer>
      </body>
    </html>
    """

    result = ArticleContentExtractor().extract(
        html,
        base_url="https://example.com/articles/pll",
    )

    assert result.status == "extracted"
    assert result.is_usable is True
    assert result.selector == "[itemprop='articleBody']"
    assert result.word_count > 100

    assert "Introduction" in result.content_text
    assert "Phase-frequency detector" in result.content_text
    assert "Charge pump" in result.content_text
    assert "Loop filter" in result.content_text

    assert "PLL Fundamentals" not in result.content_text
    assert "Home Products Documentation" not in result.content_text
    assert "Buy this product now" not in result.content_text
    assert "Sidebar newsletter" not in result.content_text
    assert "Related articles" not in result.content_text
    assert "Copyright and site links" not in result.content_text

    assert "<h2>Introduction</h2>" in result.content_html
    assert "advertisement" not in result.content_html
    assert "related-posts" not in result.content_html


def test_nested_noise_elements_do_not_crash_after_parent_decompose() -> None:
    html = f"""
    <html>
      <body>
        <main>
          <div class="sidebar">
            <div class="related-posts">Related content</div>
            <aside>Nested sidebar</aside>
          </div>

          <article>
            <div itemprop="articleBody">
              <h2>Stable extraction</h2>
              <p>{_long_paragraph("The valid article body")}</p>
            </div>
          </article>
        </main>
      </body>
    </html>
    """

    result = ArticleContentExtractor().extract(
        html,
        base_url="https://example.com/articles/stable",
    )

    assert result.status == "extracted"
    assert result.selector == "[itemprop='articleBody']"
    assert "Stable extraction" in result.content_text
    assert "Related content" not in result.content_text
    assert "Nested sidebar" not in result.content_text


def test_layout_sidebar_class_does_not_remove_main_article() -> None:
    html = f"""
    <html>
      <body>
        <main class="changelog-layout has-sidebar">
          <section class="changelog-entry">
            <p>{_long_paragraph("Self-repository actions", repeat=7)}</p>
            <p>{_long_paragraph("The new syntax", repeat=7)}</p>
            <p>{_long_paragraph("Commit pinning", repeat=7)}</p>
            <p>{_long_paragraph("Runner compatibility", repeat=7)}</p>
          </section>

          <div class="related-posts">Related changelog posts</div>
          <div class="social-share">Share this update</div>
        </main>
      </body>
    </html>
    """

    result = ArticleContentExtractor().extract(
        html,
        base_url=(
            "https://github.blog/changelog/"
            "2026-07-30-example/"
        ),
    )

    assert result.status == "extracted"
    assert result.selector == "main"
    assert "Self-repository actions" in result.content_text
    assert "Runner compatibility" in result.content_text
    assert "Related changelog posts" not in result.content_text
    assert "Share this update" not in result.content_text


def test_keeps_reading_structure_and_normalizes_links() -> None:
    html = f"""
    <article>
      <div class="entry-content">
        <h2>Measurement sequence</h2>
        <p>{_long_paragraph("The measurement sequence")}</p>
        <blockquote>Measure twice and compare the setup.</blockquote>
        <pre><code>for voltage in sweep:\n    measure(voltage)</code></pre>
        <table class="data-table" style="color:red">
          <caption>Characterization points</caption>
          <thead>
            <tr><th colspan="2">Condition</th></tr>
          </thead>
          <tbody>
            <tr><td>Voltage</td><td>0.8 V</td></tr>
          </tbody>
        </table>
        <p>
          Read the
          <a href="/references/pll" class="tracked" onclick="alert(1)">
            reference note
          </a>.
        </p>
        <img src="/images/diagram.png" alt="PLL diagram">
      </div>
    </article>
    """

    result = ArticleContentExtractor().extract(
        html,
        base_url="https://example.com/articles/current",
    )

    assert result.status == "extracted"
    assert "Measurement sequence" in result.content_text
    assert "Measure twice" in result.content_text
    assert "for voltage in sweep" in result.content_text
    assert "Condition" in result.content_text
    assert "Voltage | 0.8 V" in result.content_text

    assert '<a href="https://example.com/references/pll">' in (
        result.content_html
    )
    assert "onclick" not in result.content_html
    assert "class=" not in result.content_html
    assert "style=" not in result.content_html
    assert "<img" not in result.content_html
    assert '<th colspan="2">Condition</th>' in result.content_html


def test_selects_the_content_rich_candidate() -> None:
    html = f"""
    <html>
      <body>
        <main>
          <section class="article-content">
            <p>Short teaser.</p>
          </section>

          <article>
            <div class="post-content">
              <h2>Detailed explanation</h2>
              <p>{_long_paragraph("The detailed article")}</p>
              <p>{_long_paragraph("The second section")}</p>
            </div>
          </article>
        </main>
      </body>
    </html>
    """

    result = ArticleContentExtractor().extract(
        html,
        base_url="https://example.com/detailed",
    )

    assert result.status == "extracted"
    assert result.selector == "article .post-content"
    assert "Detailed explanation" in result.content_text
    assert "The second section" in result.content_text
    assert "Short teaser" not in result.content_text


def test_returns_insufficient_content_for_short_page() -> None:
    html = """
    <html>
      <body>
        <article>
          <p>Only a short announcement.</p>
        </article>
      </body>
    </html>
    """

    result = ArticleContentExtractor(
        minimum_text_chars=100,
    ).extract(
        html,
        base_url="https://example.com/short",
    )

    assert result.status == "insufficient_content"
    assert result.is_usable is False
    assert result.content_html == ""
    assert result.content_text == "Only a short announcement."
    assert result.word_count == 4


def test_limits_plain_text_length() -> None:
    html = f"""
    <article>
      <div class="article-content">
        <p>{_long_paragraph("Long article", repeat=60)}</p>
      </div>
    </article>
    """

    result = ArticleContentExtractor(
        minimum_text_chars=100,
        maximum_text_chars=500,
    ).extract(
        html,
        base_url="https://example.com/long",
    )

    assert result.status == "extracted"
    assert len(result.content_text) <= 500
    assert result.content_text.startswith("Long article")


@pytest.mark.parametrize(
    ("html", "base_url", "message"),
    [
        ("", "https://example.com", "html must not be empty"),
        (123, "https://example.com", "html must be a string or bytes"),
        ("<article>Text</article>", "", "base_url must be a non-empty string"),
        (
            "<article>Text</article>",
            "not-a-url",
            "base_url must be a valid HTTP or HTTPS URL",
        ),
    ],
)
def test_invalid_input_is_rejected(
    html: object,
    base_url: str,
    message: str,
) -> None:
    with pytest.raises(
        ContentExtractionError,
        match=message,
    ):
        ArticleContentExtractor(
            minimum_text_chars=1,
        ).extract(
            html,  # type: ignore[arg-type]
            base_url=base_url,
        )


@pytest.mark.parametrize(
    ("minimum", "maximum", "message"),
    [
        (0, 100, "minimum_text_chars must be a positive integer"),
        (100, 99, "maximum_text_chars must be an integer"),
        (True, 100, "minimum_text_chars must be a positive integer"),
    ],
)
def test_invalid_limits_are_rejected(
    minimum: int,
    maximum: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ArticleContentExtractor(
            minimum_text_chars=minimum,
            maximum_text_chars=maximum,
        )
