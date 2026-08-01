from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.verify_technical_learning import (
    VerificationError,
    main,
    verify_technical_learning_output,
)


def _write_epub(
    path: Path,
    *,
    title: str = "Phase-Locked Loop Fundamentals",
    legacy_link: bool = False,
    include_page_breaks: bool = True,
    full_content_count: int = 2,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    source_label = (
        "Read the original article"
        if legacy_link
        else "Original source"
    )
    stylesheet = "article { break-inside: auto; page-break-inside: auto; }"
    if include_page_breaks:
        stylesheet += (
            "\narticle + article { break-before: page; "
            "page-break-before: always; }"
        )

    linux_full_content_count = max(
        0,
        full_content_count - 1,
    )
    linux_articles: list[str] = []
    for index in range(11):
        body_class = (
            ' class="article-content full-content"'
            if index < linux_full_content_count
            else ""
        )
        body = (
            f"<div{body_class}><p>Linux body {index}</p></div>"
            if body_class
            else f'<p class="summary">Linux summary {index}</p>'
        )
        linux_articles.append(
            "<article>"
            f"<h2>Linux article {index}</h2>"
            f"{body}"
            f'<p><a href="https://example.com/linux-{index}">'
            f"{source_label}</a></p>"
            "</article>"
        )

    learning_body = (
        '<div class="article-content full-content">'
        '<p>Curated learning body</p></div>'
        if full_content_count > 0
        else '<p class="summary">Learning summary</p>'
    )
    learning_article = (
        "<article>"
        f"<h2>{title}</h2>"
        f"{learning_body}"
        '<p><a href="https://example.com/pll">'
        f"{source_label}</a></p>"
        "</article>"
    )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("EPUB/styles.css", stylesheet)
        archive.writestr(
            "EPUB/category-linux.xhtml",
            "<html><body>" + "".join(linux_articles) + "</body></html>",
        )
        archive.writestr(
            "EPUB/category-technical-learning.xhtml",
            "<html><body><h1>Technical Learning</h1>"
            + learning_article
            + "</body></html>",
        )


def _content_enrichment() -> dict[str, object]:
    records: list[dict[str, object]] = []

    for index in range(11):
        if index == 0:
            status = "extracted"
            origin = "web"
        elif index < 9:
            status = "summary_fallback"
            origin = "summary"
        else:
            status = "fetch_failed"
            origin = "none"

        records.append(
            {
                "source_id": f"source-{index}",
                "title": f"Article {index}",
                "url": f"https://example.com/{index}",
                "status": status,
                "content_origin": origin,
            }
        )

    records.append(
        {
            "source_id": "technical_learning",
            "title": "Phase-Locked Loop Fundamentals",
            "url": "https://example.com/pll",
            "status": "extracted",
            "content_origin": "curated",
        }
    )

    return {
        "requested_articles": 12,
        "extracted_articles": 2,
        "summary_fallback_articles": 8,
        "failed_articles": 2,
        "records": records,
    }


def _build_valid_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"
    archive_dir = site_dir / "archive" / "2026" / "07" / "31"

    output_dir.mkdir(parents=True)
    (site_dir / "latest").mkdir(parents=True)
    archive_dir.mkdir(parents=True)

    articles = [
        {
            "source_id": "linux_source",
            "source_name": "Linux Source",
            "category": "linux",
            "title": f"Linux article {index}",
            "url": f"https://example.com/linux-{index}",
            "external_id": f"linux:{index}",
            "content_html": "",
            "content_text": "",
            "content_status": "not_requested",
        }
        for index in range(11)
    ]
    articles.append(
        {
            "source_id": "technical_learning",
            "source_name": "Analog Devices",
            "category": "technical_learning",
            "title": "Phase-Locked Loop Fundamentals",
            "url": "https://example.com/pll",
            "external_id": "learning:pll_fundamentals",
            "source_tags": [
                "technical_learning",
                "learning_lesson_id:pll_fundamentals",
                "learning_content:curated",
            ],
            "content_html": "",
            "content_text": "",
            "content_status": "not_requested",
        }
    )

    payload = {
        "article_count": 12,
        "summary": {
            "content_enrichment": _content_enrichment(),
        },
        "learning": {
            "enabled": True,
            "lesson_ids": ["pll_fundamentals"],
        },
        "articles": articles,
    }

    ranked_text = json.dumps(payload, indent=2)
    (output_dir / "ranked_articles.json").write_text(
        ranked_text,
        encoding="utf-8",
    )
    (archive_dir / "ranked_articles.json").write_text(
        ranked_text,
        encoding="utf-8",
    )

    markdown = (
        "# Daily Tech Brief\n\n"
        "## Linux\n\n"
        "## Technical Learning\n\n"
        "### Phase-Locked Loop Fundamentals\n"
    )
    html = (
        '<html><body><a href="digest-full.epub">Download EPUB</a>'
        '<section id="technical-learning">'
        '<h2>Technical Learning</h2>'
        '<h3>Phase-Locked Loop Fundamentals</h3>'
        "</section></body></html>"
    )

    (output_dir / "digest.md").write_text(markdown, encoding="utf-8")
    (output_dir / "digest.html").write_text(html, encoding="utf-8")
    (site_dir / "index.html").write_text(html, encoding="utf-8")

    public_epub = output_dir / "digest.epub"
    _write_epub(
        public_epub,
        full_content_count=0,
    )
    full_epub = output_dir / "digest-full.epub"
    _write_epub(full_epub)

    public_epub_bytes = public_epub.read_bytes()
    full_epub_bytes = full_epub.read_bytes()
    (site_dir / "digest.epub").write_bytes(
        public_epub_bytes
    )
    (site_dir / "latest" / "digest.epub").write_bytes(
        public_epub_bytes
    )
    (site_dir / "digest-full.epub").write_bytes(
        full_epub_bytes
    )
    (site_dir / "latest" / "digest-full.epub").write_bytes(
        full_epub_bytes
    )
    (archive_dir / "digest-full.epub").write_bytes(
        full_epub_bytes
    )

    opds_dir = site_dir / "opds"
    opds_books_dir = opds_dir / "books"
    opds_books_dir.mkdir(parents=True)
    opds_book = (
        opds_books_dir
        / "daily-tech-brief-2026-07-31.epub"
    )
    opds_book.write_bytes(full_epub_bytes)
    (opds_dir / "catalog.xml").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>urn:daily-tech-brief:opds</id>
  <title>Daily Tech Brief</title>
  <updated>2026-07-31T00:00:00Z</updated>
  <link rel="self" type="application/atom+xml;profile=opds-catalog;kind=acquisition" href="catalog.xml" />
  <entry>
    <id>urn:daily-tech-brief:edition:2026-07-31</id>
    <title>Daily Tech Brief — 2026-07-31</title>
    <updated>2026-07-31T00:00:00Z</updated>
    <link rel="http://opds-spec.org/acquisition" type="application/epub+zip" href="books/daily-tech-brief-2026-07-31.epub" />
  </entry>
</feed>
""",
        encoding="utf-8",
    )

    return output_dir, site_dir


def test_verifies_learning_and_full_text_epub_output(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)

    result = verify_technical_learning_output(
        output_dir=output_dir,
        site_dir=site_dir,
        expected_total=12,
        expected_learning=1,
    )

    assert result.total_articles == 12
    assert result.learning_articles == 1
    assert result.lesson_ids == ("pll_fundamentals",)
    assert result.content_requested == 12
    assert result.content_extracted == 2
    assert result.content_fallback == 8
    assert result.content_failed == 2
    assert result.content_feed == 0
    assert result.content_web == 1
    assert result.content_curated == 1
    assert result.content_summary == 8
    assert result.content_none == 2
    assert result.public_epub_path == output_dir / "digest.epub"
    assert result.full_epub_path == output_dir / "digest-full.epub"
    assert result.opds_catalog_path == site_dir / "opds" / "catalog.xml"
    assert result.opds_book_path == (
        site_dir
        / "opds"
        / "books"
        / "daily-tech-brief-2026-07-31.epub"
    )
    assert result.opds_edition_count == 1


def test_rejects_missing_opds_catalog(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    (site_dir / "opds" / "catalog.xml").unlink()

    with pytest.raises(
        VerificationError,
        match="Required file not found",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_mismatched_opds_book(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    opds_book = (
        site_dir
        / "opds"
        / "books"
        / "daily-tech-brief-2026-07-31.epub"
    )
    opds_book.write_bytes(b"different EPUB")

    with pytest.raises(
        VerificationError,
        match="does not match",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_invalid_opds_acquisition_type(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    catalog_path = site_dir / "opds" / "catalog.xml"
    catalog = catalog_path.read_text(encoding="utf-8")
    catalog_path.write_text(
        catalog.replace(
            'type="application/epub+zip"',
            'type="application/octet-stream"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        VerificationError,
        match="invalid EPUB media type",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_accepts_legacy_nested_processing_summary(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    ranked_path = output_dir / "ranked_articles.json"
    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    enrichment = payload["summary"].pop("content_enrichment")
    payload["summary"]["processing"] = {
        "content_enrichment": enrichment,
    }
    ranked_path.write_text(json.dumps(payload), encoding="utf-8")

    archive_files = list(
        (site_dir / "archive").rglob("ranked_articles.json")
    )
    assert len(archive_files) == 1
    archive_files[0].write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    result = verify_technical_learning_output(
        output_dir=output_dir,
        site_dir=site_dir,
        expected_total=12,
        expected_learning=1,
    )

    assert result.content_requested == 12


def test_rejects_missing_content_enrichment_summary(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    ranked_path = output_dir / "ranked_articles.json"
    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    del payload["summary"]["content_enrichment"]
    ranked_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        VerificationError,
        match="enrichment summary is missing",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_content_enrichment_count_mismatch(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    ranked_path = output_dir / "ranked_articles.json"
    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    payload["summary"]["content_enrichment"][
        "failed_articles"
    ] = 1
    ranked_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        VerificationError,
        match="counts do not add up",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_public_full_content_leak(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    ranked_path = output_dir / "ranked_articles.json"
    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    payload["articles"][0]["content_text"] = "Private full body"
    ranked_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        VerificationError,
        match="publicly exposes full article text",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_legacy_read_more_link(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    _write_epub(
        output_dir / "digest.epub",
        legacy_link=True,
    )

    with pytest.raises(
        VerificationError,
        match="legacy read-more link",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_missing_article_page_break_rules(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    _write_epub(
        output_dir / "digest.epub",
        include_page_breaks=False,
        full_content_count=0,
    )

    with pytest.raises(
        VerificationError,
        match=r"does not contain: article \+ article",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_learning_metadata_mismatch(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    ranked_path = output_dir / "ranked_articles.json"
    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    payload["learning"]["lesson_ids"] = ["different_lesson"]
    ranked_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        VerificationError,
        match="metadata do not match",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_corrupt_epub(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    (output_dir / "digest.epub").write_bytes(b"not-an-epub")

    with pytest.raises(
        VerificationError,
        match="not a valid EPUB ZIP archive",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_corrupt_full_epub(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    (output_dir / "digest-full.epub").write_bytes(
        b"not-an-epub"
    )

    with pytest.raises(
        VerificationError,
        match="not a valid EPUB ZIP archive",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_mismatched_published_full_epub_copy(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    (site_dir / "digest-full.epub").write_bytes(
        b"different"
    )

    with pytest.raises(
        VerificationError,
        match="does not match",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_full_content_in_public_epub(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    _write_epub(
        output_dir / "digest.epub",
        full_content_count=1,
    )

    with pytest.raises(
        VerificationError,
        match="full-content articles; expected 0",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_mismatched_published_epub_copy(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    (site_dir / "latest" / "digest.epub").write_bytes(b"different")

    with pytest.raises(
        VerificationError,
        match="does not match",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_missing_content_origin(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    ranked_path = output_dir / "ranked_articles.json"
    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    del payload["summary"]["content_enrichment"]["records"][0][
        "content_origin"
    ]
    ranked_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        VerificationError,
        match="content_origin is invalid or missing",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_unknown_content_origin(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    ranked_path = output_dir / "ranked_articles.json"
    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    payload["summary"]["content_enrichment"]["records"][0][
        "content_origin"
    ] = "unknown"
    ranked_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        VerificationError,
        match="must not be 'unknown'",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_incompatible_status_and_origin(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    ranked_path = output_dir / "ranked_articles.json"
    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    payload["summary"]["content_enrichment"]["records"][1][
        "content_origin"
    ] = "web"
    ranked_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        VerificationError,
        match="incompatible status and content_origin",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def _write_ranked_payload_to_output_and_archive(
    *,
    output_dir: Path,
    site_dir: Path,
    payload: dict[str, object],
) -> None:
    text = json.dumps(payload, indent=2)
    (output_dir / "ranked_articles.json").write_text(
        text,
        encoding="utf-8",
    )
    archive_files = list(
        (site_dir / "archive").rglob("ranked_articles.json")
    )
    assert len(archive_files) == 1
    archive_files[0].write_text(
        text,
        encoding="utf-8",
    )


def test_accepts_uncurated_learning_summary_fallback(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    ranked_path = output_dir / "ranked_articles.json"
    payload = json.loads(ranked_path.read_text(encoding="utf-8"))

    learning_article = payload["articles"][11]
    learning_article["source_tags"] = [
        "technical_learning",
        "learning_lesson_id:pll_fundamentals",
    ]

    enrichment = payload["summary"]["content_enrichment"]
    learning_record = enrichment["records"][11]
    learning_record["status"] = "summary_fallback"
    learning_record["content_origin"] = "summary"
    enrichment["extracted_articles"] = 1
    enrichment["summary_fallback_articles"] = 9

    _write_ranked_payload_to_output_and_archive(
        output_dir=output_dir,
        site_dir=site_dir,
        payload=payload,
    )
    full_epub = output_dir / "digest-full.epub"
    _write_epub(
        full_epub,
        full_content_count=1,
    )
    full_epub_bytes = full_epub.read_bytes()
    for copy_path in (
        site_dir / "digest-full.epub",
        site_dir / "latest" / "digest-full.epub",
        site_dir
        / "archive"
        / "2026"
        / "07"
        / "31"
        / "digest-full.epub",
        site_dir
        / "opds"
        / "books"
        / "daily-tech-brief-2026-07-31.epub",
    ):
        copy_path.write_bytes(full_epub_bytes)

    result = verify_technical_learning_output(
        output_dir=output_dir,
        site_dir=site_dir,
        expected_total=12,
        expected_learning=1,
    )

    assert result.content_extracted == 1
    assert result.content_fallback == 9
    assert result.content_curated == 0
    assert result.content_summary == 9


def test_accepts_uncurated_learning_web_extraction(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    ranked_path = output_dir / "ranked_articles.json"
    payload = json.loads(ranked_path.read_text(encoding="utf-8"))

    payload["articles"][11]["source_tags"] = [
        "technical_learning",
        "learning_lesson_id:pll_fundamentals",
    ]
    payload["summary"]["content_enrichment"]["records"][11][
        "content_origin"
    ] = "web"

    _write_ranked_payload_to_output_and_archive(
        output_dir=output_dir,
        site_dir=site_dir,
        payload=payload,
    )

    result = verify_technical_learning_output(
        output_dir=output_dir,
        site_dir=site_dir,
        expected_total=12,
        expected_learning=1,
    )

    assert result.content_web == 2
    assert result.content_curated == 0


def test_rejects_non_curated_learning_origin(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    ranked_path = output_dir / "ranked_articles.json"
    payload = json.loads(ranked_path.read_text(encoding="utf-8"))
    payload["summary"]["content_enrichment"]["records"][11][
        "content_origin"
    ] = "web"
    ranked_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        VerificationError,
        match="must use curated origin",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_rejects_archive_enrichment_origin_mismatch(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    archive_files = list(
        (site_dir / "archive").rglob("ranked_articles.json")
    )
    assert len(archive_files) == 1

    payload = json.loads(
        archive_files[0].read_text(encoding="utf-8")
    )
    payload["summary"]["content_enrichment"]["records"][0][
        "content_origin"
    ] = "feed"
    archive_files[0].write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(
        VerificationError,
        match="different content enrichment data",
    ):
        verify_technical_learning_output(
            output_dir=output_dir,
            site_dir=site_dir,
            expected_total=12,
            expected_learning=1,
        )


def test_main_prints_full_content_json_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)

    exit_code = main(
        [
            "--output-dir",
            str(output_dir),
            "--site-dir",
            str(site_dir),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["content_enrichment"] == {
        "requested": 12,
        "extracted": 2,
        "summary_fallback": 8,
        "fetch_failed": 2,
        "content_origins": {
            "feed": 0,
            "web": 1,
            "curated": 1,
            "summary": 8,
            "none": 2,
        },
    }
