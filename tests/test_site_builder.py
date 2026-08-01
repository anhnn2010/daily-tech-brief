from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.publishing.site_builder import build_static_site


EPUB_BYTES = b"PK\x03\x04sample epub payload"
UPDATED_EPUB_BYTES = b"PK\x03\x04updated epub payload"


def write_generated_output(
    output_dir: Path,
    *,
    generated_at: str = "2026-07-29T23:30:00Z",
    article_count: int = 3,
    include_optional_files: bool = True,
    include_epub: bool = True,
    epub_content: bytes = EPUB_BYTES,
    full_epub_content: bytes = b"PK\x03\x04full epub payload",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "digest.html").write_text(
        "<!doctype html><html><body>Latest digest</body></html>",
        encoding="utf-8",
    )
    (output_dir / "ranked_articles.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project": {
                    "name": "Daily Tech Brief",
                    "version": "0.7.0",
                },
                "generated_at": generated_at,
                "article_count": article_count,
                "articles": [],
            }
        ),
        encoding="utf-8",
    )

    if include_optional_files:
        (output_dir / "digest.md").write_text(
            "# Daily Tech Brief\n",
            encoding="utf-8",
        )
        (output_dir / "source_report.json").write_text(
            json.dumps({"sources": []}),
            encoding="utf-8",
        )

    if include_epub:
        (output_dir / "digest.epub").write_bytes(epub_content)
        (output_dir / "digest-full.epub").write_bytes(
            full_epub_content
        )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_static_site_creates_latest_and_local_date_archive(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"
    write_generated_output(output_dir)

    result = build_static_site(
        output_dir,
        site_dir,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    archive_dir = site_dir / "archive" / "2026" / "07" / "30"

    assert result.archive_date == "2026-07-30"
    assert result.article_count == 3
    assert result.index_path == site_dir / "index.html"
    assert result.latest_dir == site_dir / "latest"
    assert result.archive_dir == archive_dir

    assert (site_dir / "index.html").is_file()
    assert (site_dir / "latest" / "index.html").is_file()
    assert (archive_dir / "index.html").is_file()

    assert (site_dir / "digest.md").is_file()
    assert (site_dir / "latest" / "digest.md").is_file()
    assert (archive_dir / "digest.md").is_file()

    epub_destinations = (
        site_dir / "digest.epub",
        site_dir / "latest" / "digest.epub",
        archive_dir / "digest.epub",
    )
    for epub_path in epub_destinations:
        assert epub_path.read_bytes() == EPUB_BYTES
        assert epub_path in result.copied_files
    full_epub_destinations = (
        site_dir / "digest-full.epub",
        site_dir / "latest" / "digest-full.epub",
        archive_dir / "digest-full.epub",
    )
    for epub_path in full_epub_destinations:
        assert epub_path.read_bytes() == b"PK\x03\x04full epub payload"
        assert epub_path in result.copied_files

    opds_catalog = site_dir / "opds" / "catalog.xml"
    opds_book = (
        site_dir
        / "opds"
        / "books"
        / "daily-tech-brief-2026-07-30.epub"
    )
    assert result.opds_catalog_path == opds_catalog
    assert result.opds_edition_count == 1
    assert result.opds_skipped_dates == ()
    assert opds_catalog.is_file()
    assert opds_book.read_bytes() == b"PK\x03\x04full epub payload"
    assert opds_catalog in result.copied_files
    assert opds_book in result.copied_files

    catalog_xml = opds_catalog.read_text(encoding="utf-8")
    assert "http://opds-spec.org/acquisition" in catalog_xml
    assert "books/daily-tech-brief-2026-07-30.epub" in catalog_xml

    assert (site_dir / "ranked_articles.json").is_file()
    assert (site_dir / "source_report.json").is_file()
    assert (site_dir / ".nojekyll").is_file()

    assert (
        site_dir / "index.html"
    ).read_text(encoding="utf-8") == (
        output_dir / "digest.html"
    ).read_text(encoding="utf-8")


def test_build_static_site_writes_archive_manifest_and_metadata(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"
    write_generated_output(output_dir)

    build_static_site(
        output_dir,
        site_dir,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    manifest = read_json(site_dir / "archive" / "index.json")
    metadata = read_json(site_dir / "site.json")
    archive_html = (
        site_dir / "archive" / "index.html"
    ).read_text(encoding="utf-8")

    assert manifest["timezone"] == "Asia/Ho_Chi_Minh"
    assert manifest["latest_date"] == "2026-07-30"
    assert manifest["edition_count"] == 1
    assert manifest["editions"] == [
        {
            "date": "2026-07-30",
            "generated_at": "2026-07-29T23:30:00Z",
            "article_count": 3,
            "path": "2026/07/30/",
            "title": "Daily Tech Brief",
        }
    ]

    assert metadata["project"]["version"] == "0.7.0"
    assert metadata["archive_date"] == "2026-07-30"
    assert metadata["latest_path"] == "latest/"
    assert metadata["archive_path"] == "archive/"
    assert metadata["article_count"] == 3
    assert metadata["opds_path"] == "opds/catalog.xml"
    assert metadata["opds_edition_count"] == 1
    assert metadata["opds_skipped_dates"] == []
    assert "2026/07/30/" in archive_html
    assert "3 articles" in archive_html


def test_build_static_site_preserves_existing_archive_entries(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"
    old_archive_dir = site_dir / "archive" / "2026" / "07" / "29"
    old_archive_dir.mkdir(parents=True)
    (old_archive_dir / "index.html").write_text(
        "Older edition",
        encoding="utf-8",
    )
    old_epub = old_archive_dir / "digest.epub"
    old_epub.write_bytes(b"older archived epub")

    archive_root = site_dir / "archive"
    (archive_root / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "timezone": "Asia/Ho_Chi_Minh",
                "latest_date": "2026-07-29",
                "edition_count": 1,
                "editions": [
                    {
                        "date": "2026-07-29",
                        "generated_at": "2026-07-28T23:30:00Z",
                        "article_count": 2,
                        "path": "2026/07/29/",
                        "title": "Daily Tech Brief",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    write_generated_output(output_dir)

    build_static_site(
        output_dir,
        site_dir,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    manifest = read_json(archive_root / "index.json")

    assert (old_archive_dir / "index.html").read_text(
        encoding="utf-8"
    ) == "Older edition"
    assert old_epub.read_bytes() == b"older archived epub"
    assert manifest["edition_count"] == 2
    assert [
        edition["date"] for edition in manifest["editions"]
    ] == [
        "2026-07-30",
        "2026-07-29",
    ]

    catalog_xml = (
        site_dir / "opds" / "catalog.xml"
    ).read_text(encoding="utf-8")
    assert "daily-tech-brief-2026-07-30.epub" in catalog_xml
    assert "daily-tech-brief-2026-07-29.epub" not in catalog_xml


def test_build_static_site_replaces_same_day_archive_without_duplicate(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"

    write_generated_output(
        output_dir,
        generated_at="2026-07-29T23:30:00Z",
        article_count=3,
    )
    build_static_site(
        output_dir,
        site_dir,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    same_day_archive = (
        site_dir / "archive" / "2026" / "07" / "30"
    )
    (same_day_archive / "stale.txt").write_text(
        "remove me",
        encoding="utf-8",
    )

    write_generated_output(
        output_dir,
        generated_at="2026-07-30T05:00:00Z",
        article_count=7,
        epub_content=UPDATED_EPUB_BYTES,
        full_epub_content=b"PK\x03\x04updated full epub",
    )
    (output_dir / "digest.html").write_text(
        "<!doctype html><html><body>Updated digest</body></html>",
        encoding="utf-8",
    )

    build_static_site(
        output_dir,
        site_dir,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    manifest = read_json(site_dir / "archive" / "index.json")

    assert not (same_day_archive / "stale.txt").exists()
    assert "Updated digest" in (
        same_day_archive / "index.html"
    ).read_text(encoding="utf-8")
    assert (
        same_day_archive / "digest.epub"
    ).read_bytes() == UPDATED_EPUB_BYTES
    assert (
        site_dir / "digest.epub"
    ).read_bytes() == UPDATED_EPUB_BYTES
    assert (
        site_dir / "latest" / "digest.epub"
    ).read_bytes() == UPDATED_EPUB_BYTES
    assert manifest["edition_count"] == 1
    assert manifest["editions"][0]["article_count"] == 7
    assert (
        manifest["editions"][0]["generated_at"]
        == "2026-07-30T05:00:00Z"
    )
    assert (
        site_dir
        / "opds"
        / "books"
        / "daily-tech-brief-2026-07-30.epub"
    ).read_bytes() == b"PK\x03\x04updated full epub"


def test_build_static_site_allows_missing_optional_files(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"
    write_generated_output(
        output_dir,
        include_optional_files=False,
        include_epub=False,
    )

    result = build_static_site(
        output_dir,
        site_dir,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    assert result.index_path.is_file()
    assert not (site_dir / "digest.md").exists()
    assert not (site_dir / "digest.epub").exists()
    assert not (site_dir / "source_report.json").exists()
    assert (site_dir / "ranked_articles.json").is_file()
    assert result.opds_catalog_path is None
    assert result.opds_edition_count == 0
    assert not (site_dir / "opds").exists()


def test_build_static_site_allows_epub_to_be_disabled(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"
    write_generated_output(output_dir, include_epub=False)

    result = build_static_site(
        output_dir,
        site_dir,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    archive_dir = site_dir / "archive" / "2026" / "07" / "30"

    assert result.index_path.is_file()
    assert (site_dir / "digest.md").is_file()
    assert (site_dir / "source_report.json").is_file()
    assert not (site_dir / "digest.epub").exists()
    assert not (site_dir / "latest" / "digest.epub").exists()
    assert not (archive_dir / "digest.epub").exists()


def test_build_static_site_removes_stale_opds_when_no_full_epub_exists(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"
    stale_catalog = site_dir / "opds" / "catalog.xml"
    stale_catalog.parent.mkdir(parents=True)
    stale_catalog.write_text("stale", encoding="utf-8")

    write_generated_output(
        output_dir,
        include_epub=False,
    )

    result = build_static_site(
        output_dir,
        site_dir,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    assert result.opds_catalog_path is None
    assert result.opds_edition_count == 0
    assert not (site_dir / "opds").exists()


@pytest.mark.parametrize(
    "missing_name",
    [
        "digest.html",
        "ranked_articles.json",
    ],
)
def test_build_static_site_requires_core_generated_files(
    tmp_path: Path,
    missing_name: str,
) -> None:
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"
    write_generated_output(output_dir)
    (output_dir / missing_name).unlink()

    with pytest.raises(
        FileNotFoundError,
        match="Required generated files are missing",
    ):
        build_static_site(
            output_dir,
            site_dir,
            timezone_name="Asia/Ho_Chi_Minh",
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "project": {"name": "Daily Tech Brief"},
                "article_count": 1,
            },
            "generated_at",
        ),
        (
            {
                "project": {"name": "Daily Tech Brief"},
                "generated_at": "not-a-date",
                "article_count": 1,
            },
            "valid ISO datetime",
        ),
        (
            {
                "project": {"name": "Daily Tech Brief"},
                "generated_at": "2026-07-30T00:00:00Z",
                "article_count": -1,
            },
            "non-negative integer",
        ),
    ],
)
def test_build_static_site_validates_ranked_metadata(
    tmp_path: Path,
    payload: dict,
    message: str,
) -> None:
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"
    output_dir.mkdir()

    (output_dir / "digest.html").write_text(
        "<html></html>",
        encoding="utf-8",
    )
    (output_dir / "ranked_articles.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        build_static_site(
            output_dir,
            site_dir,
            timezone_name="Asia/Ho_Chi_Minh",
        )


def test_build_static_site_rejects_unknown_timezone(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    site_dir = tmp_path / "site"
    write_generated_output(output_dir)

    with pytest.raises(ValueError, match="Unknown timezone"):
        build_static_site(
            output_dir,
            site_dir,
            timezone_name="Mars/Olympus_Mons",
        )
