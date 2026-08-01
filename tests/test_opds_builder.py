from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.publishing.opds_builder import build_opds_catalog


ATOM = {"atom": "http://www.w3.org/2005/Atom"}
ACQUISITION_REL = "http://opds-spec.org/acquisition"


def _write_manifest(
    site_dir: Path,
) -> None:
    archive_dir = site_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "timezone": "Asia/Ho_Chi_Minh",
                "latest_date": "2026-08-01",
                "edition_count": 3,
                "editions": [
                    {
                        "date": "2026-08-01",
                        "generated_at": (
                            "2026-08-01T00:30:00Z"
                        ),
                        "article_count": 12,
                        "path": "2026/08/01/",
                        "title": "Daily Tech Brief",
                    },
                    {
                        "date": "2026-07-31",
                        "generated_at": (
                            "2026-07-31T00:30:00Z"
                        ),
                        "article_count": 11,
                        "path": "2026/07/31/",
                        "title": "Daily Tech Brief",
                    },
                    {
                        "date": "2026-07-30",
                        "generated_at": (
                            "2026-07-30T00:30:00Z"
                        ),
                        "article_count": 10,
                        "path": "2026/07/30/",
                        "title": "Daily Tech Brief",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_full_epub(
    site_dir: Path,
    date_path: str,
    payload: bytes,
) -> Path:
    path = (
        site_dir
        / "archive"
        / date_path
        / "digest-full.epub"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_builds_acquisition_feed_and_dated_books(
    tmp_path: Path,
) -> None:
    site_dir = tmp_path / "site"
    _write_manifest(site_dir)
    _write_full_epub(
        site_dir,
        "2026/08/01",
        b"latest full epub",
    )
    _write_full_epub(
        site_dir,
        "2026/07/31",
        b"older full epub",
    )

    result = build_opds_catalog(site_dir)

    assert result.catalog_path == (
        site_dir / "opds" / "catalog.xml"
    )
    assert result.skipped_dates == ("2026-07-30",)
    assert [
        edition.date
        for edition in result.editions
    ] == [
        "2026-08-01",
        "2026-07-31",
    ]

    latest_book = (
        site_dir
        / "opds"
        / "books"
        / "daily-tech-brief-2026-08-01.epub"
    )
    older_book = (
        site_dir
        / "opds"
        / "books"
        / "daily-tech-brief-2026-07-31.epub"
    )
    assert latest_book.read_bytes() == b"latest full epub"
    assert older_book.read_bytes() == b"older full epub"

    root = ET.parse(result.catalog_path).getroot()
    entries = root.findall("atom:entry", ATOM)
    assert len(entries) == 2

    assert entries[0].findtext(
        "atom:title",
        namespaces=ATOM,
    ) == "Daily Tech Brief — 2026-08-01"

    acquisition = entries[0].find(
        f"atom:link[@rel='{ACQUISITION_REL}']",
        ATOM,
    )
    assert acquisition is not None
    assert acquisition.attrib == {
        "rel": ACQUISITION_REL,
        "type": "application/epub+zip",
        "href": (
            "books/"
            "daily-tech-brief-2026-08-01.epub"
        ),
    }

    alternate = entries[0].find(
        "atom:link[@rel='alternate']",
        ATOM,
    )
    assert alternate is not None
    assert alternate.attrib["href"] == (
        "../archive/2026/08/01/"
    )


def test_replaces_stale_opds_directory(
    tmp_path: Path,
) -> None:
    site_dir = tmp_path / "site"
    _write_manifest(site_dir)
    _write_full_epub(
        site_dir,
        "2026/08/01",
        b"latest",
    )

    stale = site_dir / "opds" / "books" / "stale.epub"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"stale")

    build_opds_catalog(site_dir)

    assert not stale.exists()


def test_rejects_catalog_without_any_full_epub(
    tmp_path: Path,
) -> None:
    site_dir = tmp_path / "site"
    _write_manifest(site_dir)

    with pytest.raises(
        FileNotFoundError,
        match="No archived digest-full.epub",
    ):
        build_opds_catalog(site_dir)


def test_rejects_archive_path_traversal(
    tmp_path: Path,
) -> None:
    site_dir = tmp_path / "site"
    archive_dir = site_dir / "archive"
    archive_dir.mkdir(parents=True)
    (archive_dir / "index.json").write_text(
        json.dumps(
            {
                "editions": [
                    {
                        "date": "2026-08-01",
                        "generated_at": (
                            "2026-08-01T00:30:00Z"
                        ),
                        "article_count": 12,
                        "path": "../../private/",
                        "title": "Daily Tech Brief",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="must stay inside site/archive",
    ):
        build_opds_catalog(site_dir)
