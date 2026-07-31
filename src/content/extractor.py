from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment, Tag


class ContentExtractionError(ValueError):
    """Raised when article HTML cannot be processed."""


@dataclass(frozen=True)
class ExtractedContent:
    content_html: str
    content_text: str
    status: str
    selector: str | None
    word_count: int

    @property
    def is_usable(self) -> bool:
        return self.status == "extracted"


_CANDIDATE_SELECTORS = (
    "[itemprop='articleBody']",
    "article [data-component='text-block']",
    "article .article-content",
    "article .article-body",
    "article .post-content",
    "article .entry-content",
    ".article-content",
    ".article-body",
    ".post-content",
    ".entry-content",
    ".story-body",
    ".content-body",
    "article",
    "main",
)

_DROP_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "canvas",
    "iframe",
    "form",
    "button",
    "input",
    "select",
    "textarea",
    "nav",
    "footer",
    "aside",
}

_ALLOWED_TAGS = {
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "br",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "strong",
    "b",
    "em",
    "i",
    "a",
    "hr",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
    "figure",
    "figcaption",
    "sup",
    "sub",
    "kbd",
    "samp",
    "var",
}

_BLOCK_TAGS = {
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "li",
    "blockquote",
    "pre",
    "figcaption",
    "caption",
    "tr",
}

_SUSPICIOUS_PATTERN = re.compile(
    r"(?:^|[-_])("
    r"ad|ads|advert|advertisement|banner|breadcrumb|"
    r"cookie|comment|comments|footer|header-nav|"
    r"newsletter|paywall|popup|promo|recommend|"
    r"related|share|sharing|sidebar|social|sponsor|"
    r"subscribe|subscription|toc|toolbar"
    r")(?:$|[-_])",
    re.IGNORECASE,
)

_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


class ArticleContentExtractor:
    """Extract readable, text-first article content from an HTML document."""

    def __init__(
        self,
        *,
        minimum_text_chars: int = 400,
        maximum_text_chars: int = 120_000,
    ) -> None:
        if (
            not isinstance(minimum_text_chars, int)
            or isinstance(minimum_text_chars, bool)
            or minimum_text_chars < 1
        ):
            raise ValueError(
                "minimum_text_chars must be a positive integer"
            )

        if (
            not isinstance(maximum_text_chars, int)
            or isinstance(maximum_text_chars, bool)
            or maximum_text_chars < minimum_text_chars
        ):
            raise ValueError(
                "maximum_text_chars must be an integer greater than "
                "or equal to minimum_text_chars"
            )

        self._minimum_text_chars = minimum_text_chars
        self._maximum_text_chars = maximum_text_chars

    def extract(
        self,
        html: str | bytes,
        *,
        base_url: str,
    ) -> ExtractedContent:
        """Return sanitized article HTML and plain text.

        The extractor intentionally keeps text, headings, lists, tables,
        quotes, code blocks, and reference links. Images are excluded because
        an offline EPUB must download and package image files separately.
        """

        markup = _normalize_markup(html)
        normalized_base_url = _validate_base_url(base_url)

        soup = BeautifulSoup(markup, "html.parser")
        _remove_comments(soup)
        _remove_global_noise(soup)

        candidate, selector = _select_best_candidate(
            soup,
            minimum_text_chars=self._minimum_text_chars,
        )
        if candidate is None:
            return ExtractedContent(
                content_html="",
                content_text="",
                status="insufficient_content",
                selector=None,
                word_count=0,
            )

        fragment = BeautifulSoup(
            str(candidate),
            "html.parser",
        )
        root = fragment.body or fragment
        _remove_global_noise(root)
        _sanitize_fragment(
            root,
            base_url=normalized_base_url,
        )

        content_text = _extract_plain_text(root)
        content_text = content_text[
            : self._maximum_text_chars
        ].rstrip()

        if len(content_text) < self._minimum_text_chars:
            return ExtractedContent(
                content_html="",
                content_text=content_text,
                status="insufficient_content",
                selector=selector,
                word_count=_word_count(content_text),
            )

        content_html = _extract_clean_html(root)

        return ExtractedContent(
            content_html=content_html,
            content_text=content_text,
            status="extracted",
            selector=selector,
            word_count=_word_count(content_text),
        )


def _normalize_markup(
    html: str | bytes,
) -> str:
    if isinstance(html, bytes):
        return html.decode(
            "utf-8",
            errors="replace",
        )

    if not isinstance(html, str):
        raise ContentExtractionError(
            "html must be a string or bytes"
        )

    if not html.strip():
        raise ContentExtractionError(
            "html must not be empty"
        )

    return html


def _validate_base_url(
    base_url: str,
) -> str:
    if not isinstance(base_url, str) or not base_url.strip():
        raise ContentExtractionError(
            "base_url must be a non-empty string"
        )

    normalized = base_url.strip()
    parsed = urlparse(normalized)

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
    ):
        raise ContentExtractionError(
            "base_url must be a valid HTTP or HTTPS URL"
        )

    return normalized


def _remove_comments(
    root: BeautifulSoup | Tag,
) -> None:
    for comment in root.find_all(
        string=lambda value: isinstance(value, Comment)
    ):
        comment.extract()


def _remove_global_noise(
    root: BeautifulSoup | Tag,
) -> None:
    for tag_name in _DROP_TAGS:
        for tag in list(root.find_all(tag_name)):
            if _is_live_tag(tag):
                tag.decompose()

    for tag in list(root.find_all(True)):
        if not _is_live_tag(tag):
            continue
        if _is_suspicious(tag):
            tag.decompose()


def _is_live_tag(
    tag: Tag,
) -> bool:
    """Return whether BeautifulSoup has not decomposed the tag."""

    return (
        tag.name is not None
        and tag.attrs is not None
    )


def _is_suspicious(
    tag: Tag,
) -> bool:
    if not _is_live_tag(tag):
        return False

    values: list[str] = []

    tag_id = tag.get("id")
    if isinstance(tag_id, str):
        values.append(tag_id)

    classes = tag.get("class")
    if isinstance(classes, list):
        values.extend(str(item) for item in classes)

    role = tag.get("role")
    if isinstance(role, str):
        values.append(role)

    aria_label = tag.get("aria-label")
    if isinstance(aria_label, str):
        values.append(aria_label)

    combined = " ".join(values)
    return bool(
        combined
        and _SUSPICIOUS_PATTERN.search(combined)
    )


def _select_best_candidate(
    soup: BeautifulSoup,
    *,
    minimum_text_chars: int,
) -> tuple[Tag | None, str | None]:
    all_candidates: list[tuple[float, int, Tag, str]] = []
    seen: set[int] = set()

    for selector_index, selector in enumerate(
        _CANDIDATE_SELECTORS
    ):
        selector_candidates: list[tuple[float, Tag]] = []

        for candidate in soup.select(selector):
            identity = id(candidate)
            if identity in seen:
                continue

            seen.add(identity)
            score = _score_candidate(candidate)
            all_candidates.append(
                (
                    score,
                    -selector_index,
                    candidate,
                    selector,
                )
            )

            text_length = len(
                _clean_inline_text(
                    candidate.get_text(
                        " ",
                        strip=True,
                    )
                )
            )
            if text_length >= minimum_text_chars:
                selector_candidates.append(
                    (score, candidate)
                )

        if selector_candidates:
            _, candidate = max(
                selector_candidates,
                key=lambda item: item[0],
            )
            return candidate, selector

    if not all_candidates:
        body = soup.body
        if body is None:
            return None, None
        return body, "body"

    _, _, candidate, selector = max(
        all_candidates,
        key=lambda item: (
            item[0],
            item[1],
        ),
    )
    return candidate, selector


def _score_candidate(
    candidate: Tag,
) -> float:
    text = _clean_inline_text(
        candidate.get_text(
            " ",
            strip=True,
        )
    )

    if not text:
        return float("-inf")

    text_length = len(text)
    paragraph_count = len(candidate.find_all("p"))
    heading_count = len(
        candidate.find_all(
            ["h2", "h3", "h4", "h5", "h6"]
        )
    )
    list_item_count = len(candidate.find_all("li"))
    code_block_count = len(candidate.find_all("pre"))
    table_row_count = len(candidate.find_all("tr"))

    link_text_length = sum(
        len(
            _clean_inline_text(
                link.get_text(
                    " ",
                    strip=True,
                )
            )
        )
        for link in candidate.find_all("a")
    )
    link_density = (
        link_text_length / text_length
        if text_length
        else 1.0
    )

    return (
        text_length
        + paragraph_count * 120
        + heading_count * 40
        + list_item_count * 20
        + code_block_count * 100
        + table_row_count * 15
        - text_length * link_density * 0.8
    )


def _sanitize_fragment(
    root: BeautifulSoup | Tag,
    *,
    base_url: str,
) -> None:
    for h1 in list(root.find_all("h1")):
        if _is_live_tag(h1):
            h1.decompose()

    for tag in list(root.find_all(True)):
        if not _is_live_tag(tag):
            continue

        if tag.name in _DROP_TAGS:
            tag.decompose()
            continue

        if _is_suspicious(tag):
            tag.decompose()
            continue

        if tag.name == "img":
            tag.decompose()
            continue

        if tag.name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue

        _sanitize_attributes(
            tag,
            base_url=base_url,
        )

    _remove_empty_elements(root)


def _sanitize_attributes(
    tag: Tag,
    *,
    base_url: str,
) -> None:
    if tag.name == "a":
        href = tag.get("href")
        title = tag.get("title")
        tag.attrs = {}

        if isinstance(href, str):
            absolute = urljoin(
                base_url,
                unescape(href.strip()),
            )
            parsed = urlparse(absolute)
            if (
                parsed.scheme in {"http", "https"}
                and parsed.netloc
            ):
                tag["href"] = absolute

        if isinstance(title, str) and title.strip():
            tag["title"] = _clean_inline_text(title)
        return

    if tag.name in {"th", "td"}:
        colspan = tag.get("colspan")
        rowspan = tag.get("rowspan")
        tag.attrs = {}

        if (
            isinstance(colspan, str)
            and colspan.isdigit()
        ):
            tag["colspan"] = colspan

        if (
            isinstance(rowspan, str)
            and rowspan.isdigit()
        ):
            tag["rowspan"] = rowspan
        return

    tag.attrs = {}


def _remove_empty_elements(
    root: BeautifulSoup | Tag,
) -> None:
    removable = {
        "p",
        "li",
        "blockquote",
        "figcaption",
        "caption",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }

    changed = True
    while changed:
        changed = False

        for tag in list(root.find_all(removable)):
            if not _is_live_tag(tag):
                continue

            text = _clean_inline_text(
                tag.get_text(
                    " ",
                    strip=True,
                )
            )
            if text:
                continue

            if tag.find(["code", "br"]):
                continue

            tag.decompose()
            changed = True


def _extract_plain_text(
    root: BeautifulSoup | Tag,
) -> str:
    parts: list[str] = []

    for tag in root.find_all(_BLOCK_TAGS):
        if any(
            parent.name in _BLOCK_TAGS
            for parent in tag.parents
            if isinstance(parent, Tag)
            and parent is not root
        ):
            continue

        if tag.name == "pre":
            text = tag.get_text(
                "\n",
                strip=True,
            )
        elif tag.name == "tr":
            cells = [
                _clean_inline_text(
                    cell.get_text(
                        " ",
                        strip=True,
                    )
                )
                for cell in tag.find_all(
                    ["th", "td"],
                    recursive=False,
                )
            ]
            text = " | ".join(
                cell
                for cell in cells
                if cell
            )
        else:
            text = _clean_inline_text(
                tag.get_text(
                    " ",
                    strip=True,
                )
            )

        if text:
            parts.append(text)

    if not parts:
        fallback = _clean_inline_text(
            root.get_text(
                " ",
                strip=True,
            )
        )
        parts.append(fallback)

    text = "\n\n".join(
        part
        for part in parts
        if part
    )
    text = _WHITESPACE_RE.sub(
        " ",
        text,
    )
    text = text.replace(" \n", "\n")
    text = _BLANK_LINES_RE.sub(
        "\n\n",
        text,
    )
    return text.strip()


def _extract_clean_html(
    root: BeautifulSoup | Tag,
) -> str:
    container = BeautifulSoup(
        "<div></div>",
        "html.parser",
    ).div

    if container is None:
        raise ContentExtractionError(
            "Unable to create sanitized content container"
        )

    for child in list(root.contents):
        if isinstance(child, Tag):
            container.append(child.extract())
            continue

        text = _clean_inline_text(str(child))
        if text:
            paragraph = BeautifulSoup(
                "<p></p>",
                "html.parser",
            ).p
            if paragraph is not None:
                paragraph.string = text
                container.append(paragraph)

    return container.decode_contents(
        formatter="html",
    ).strip()


def _clean_inline_text(
    value: str,
) -> str:
    return _WHITESPACE_RE.sub(
        " ",
        unescape(value),
    ).strip()


def _word_count(
    text: str,
) -> int:
    return len(
        [
            word
            for word in re.split(r"\s+", text.strip())
            if word
        ]
    )
