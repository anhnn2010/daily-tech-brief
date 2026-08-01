from __future__ import annotations

import json
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


_ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"
_DC_NAMESPACE = "http://purl.org/dc/terms/"
_OPDS_ACQUISITION_REL = "http://opds-spec.org/acquisition"
_EPUB_MEDIA_TYPE = "application/epub+zip"
_OPDS_FEED_MEDIA_TYPE = (
    "application/atom+xml;profile=opds-catalog;kind=acquisition"
)
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ET.register_namespace("", _ATOM_NAMESPACE)
ET.register_namespace("dc", _DC_NAMESPACE)


@dataclass(frozen=True)
class OpdsEdition:
    """One downloadable Daily Tech Brief edition in the OPDS catalog."""

    date: str
    generated_at: str
    article_count: int
    title: str
    archive_path: str
    source_epub: Path
    published_epub: Path


@dataclass(frozen=True)
class OpdsBuildResult:
    """Summary of a generated OPDS catalog."""

    catalog_path: Path
    books_dir: Path
    editions: tuple[OpdsEdition, ...]
    skipped_dates: tuple[str, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "catalog_path": str(self.catalog_path),
            "books_dir": str(self.books_dir),
            "edition_count": len(self.editions),
            "skipped_dates": list(self.skipped_dates),
            "editions": [
                {
                    "date": edition.date,
                    "generated_at": edition.generated_at,
                    "article_count": edition.article_count,
                    "title": edition.title,
                    "archive_path": edition.archive_path,
                    "source_epub": str(edition.source_epub),
                    "published_epub": str(edition.published_epub),
                }
                for edition in self.editions
            ],
        }


def build_opds_catalog(
    site_dir: Path,
    *,
    catalog_title: str = "Daily Tech Brief",
    language: str = "en",
) -> OpdsBuildResult:
    """Build an OPDS 1.x acquisition catalog from archived full EPUB files.

    The static-site archive manifest is treated as the source of truth. Each
    edition that has ``digest-full.epub`` is copied to a stable dated filename
    under ``site/opds/books`` and listed in ``site/opds/catalog.xml``.

    Older archive entries created before full EPUB publication are skipped so
    OPDS can be introduced without rebuilding historical editions first.
    """

    site_dir = Path(site_dir)
    catalog_title = _require_non_empty_string(
        catalog_title,
        field="catalog_title",
    )
    language = _require_non_empty_string(
        language,
        field="language",
    )

    archive_manifest_path = site_dir / "archive" / "index.json"
    manifest = _read_json_object(archive_manifest_path)
    archive_entries = _load_archive_entries(manifest)

    opds_dir = site_dir / "opds"
    books_dir = opds_dir / "books"
    _replace_directory(opds_dir)
    books_dir.mkdir(parents=True, exist_ok=True)

    editions: list[OpdsEdition] = []
    skipped_dates: list[str] = []

    for entry in archive_entries:
        edition_date = entry["date"]
        archive_relative_path = entry["path"]
        source_epub = (
            site_dir
            / "archive"
            / archive_relative_path
            / "digest-full.epub"
        )

        if not source_epub.is_file():
            skipped_dates.append(edition_date)
            continue

        published_epub = (
            books_dir
            / f"daily-tech-brief-{edition_date}.epub"
        )
        _copy_file(source_epub, published_epub)

        editions.append(
            OpdsEdition(
                date=edition_date,
                generated_at=entry["generated_at"],
                article_count=entry["article_count"],
                title=entry["title"],
                archive_path=archive_relative_path,
                source_epub=source_epub,
                published_epub=published_epub,
            )
        )

    if not editions:
        raise FileNotFoundError(
            "No archived digest-full.epub files were available "
            "for the OPDS catalog"
        )

    catalog_path = opds_dir / "catalog.xml"
    _write_catalog(
        catalog_path,
        title=catalog_title,
        language=language,
        editions=tuple(editions),
    )

    return OpdsBuildResult(
        catalog_path=catalog_path,
        books_dir=books_dir,
        editions=tuple(editions),
        skipped_dates=tuple(skipped_dates),
    )


def _write_catalog(
    catalog_path: Path,
    *,
    title: str,
    language: str,
    editions: tuple[OpdsEdition, ...],
) -> None:
    newest = editions[0]

    feed = ET.Element(_atom("feed"))
    _add_text(feed, "id", "urn:daily-tech-brief:opds")
    _add_text(feed, "title", title)
    _add_text(feed, "updated", newest.generated_at)
    _add_text(feed, "author", None)
    author = feed[-1]
    _add_text(author, "name", title)
    _add_dc_text(feed, "language", language)

    ET.SubElement(
        feed,
        _atom("link"),
        {
            "rel": "self",
            "type": _OPDS_FEED_MEDIA_TYPE,
            "href": "catalog.xml",
        },
    )

    for edition in editions:
        entry = ET.SubElement(feed, _atom("entry"))
        _add_text(
            entry,
            "id",
            f"urn:daily-tech-brief:edition:{edition.date}",
        )
        _add_text(
            entry,
            "title",
            f"{edition.title} — {edition.date}",
        )
        _add_text(entry, "updated", edition.generated_at)

        entry_author = ET.SubElement(entry, _atom("author"))
        _add_text(entry_author, "name", edition.title)
        _add_dc_text(entry, "language", language)

        summary = ET.SubElement(
            entry,
            _atom("summary"),
            {"type": "text"},
        )
        summary.text = (
            f"{edition.article_count} selected articles with full text "
            "and Technical Learning for offline reading."
        )

        ET.SubElement(
            entry,
            _atom("link"),
            {
                "rel": _OPDS_ACQUISITION_REL,
                "type": _EPUB_MEDIA_TYPE,
                "href": (
                    "books/"
                    f"daily-tech-brief-{edition.date}.epub"
                ),
            },
        )
        ET.SubElement(
            entry,
            _atom("link"),
            {
                "rel": "alternate",
                "type": "text/html",
                "href": (
                    "../archive/"
                    f"{edition.archive_path}"
                ),
            },
        )

    tree = ET.ElementTree(feed)
    ET.indent(tree, space="  ")

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = catalog_path.with_suffix(
        catalog_path.suffix + ".tmp"
    )
    tree.write(
        temporary_path,
        encoding="utf-8",
        xml_declaration=True,
    )
    temporary_path.replace(catalog_path)


def _load_archive_entries(
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    raw_entries = manifest.get("editions")
    if not isinstance(raw_entries, list):
        raise ValueError(
            "archive/index.json editions must be a list"
        )

    entries = tuple(
        _validate_archive_entry(raw, index=index)
        for index, raw in enumerate(raw_entries)
    )

    return tuple(
        sorted(
            entries,
            key=lambda item: item["generated_at"],
            reverse=True,
        )
    )


def _validate_archive_entry(
    raw: Any,
    *,
    index: int,
) -> dict[str, Any]:
    prefix = f"archive editions[{index}]"
    if not isinstance(raw, dict):
        raise ValueError(f"{prefix} must be an object")

    edition_date = _require_non_empty_string(
        raw.get("date"),
        field=f"{prefix}.date",
    )
    if not _DATE_PATTERN.fullmatch(edition_date):
        raise ValueError(
            f"{prefix}.date must use YYYY-MM-DD format"
        )

    generated_at = _require_non_empty_string(
        raw.get("generated_at"),
        field=f"{prefix}.generated_at",
    )
    _parse_datetime(generated_at)

    article_count = raw.get("article_count")
    if (
        not isinstance(article_count, int)
        or isinstance(article_count, bool)
        or article_count < 0
    ):
        raise ValueError(
            f"{prefix}.article_count must be a "
            "non-negative integer"
        )

    archive_path = _require_non_empty_string(
        raw.get("path"),
        field=f"{prefix}.path",
    )
    path = Path(archive_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(
            f"{prefix}.path must stay inside site/archive"
        )

    title = _require_non_empty_string(
        raw.get("title"),
        field=f"{prefix}.title",
    )

    return {
        "date": edition_date,
        "generated_at": generated_at,
        "article_count": article_count,
        "path": archive_path,
        "title": title,
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Archive manifest not found: {path}"
        )

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON file: {path}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"JSON root must be an object: {path}"
        )

    return payload


def _replace_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(
        destination.suffix + ".tmp"
    )
    shutil.copyfile(source, temporary_path)
    temporary_path.replace(destination)


def _require_non_empty_string(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _parse_datetime(value: str) -> datetime:
    normalized = value
    if value.endswith("Z"):
        normalized = value[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Invalid generated_at datetime: {value}"
        ) from exc

    if parsed.tzinfo is None:
        raise ValueError(
            "generated_at datetime must include a timezone"
        )

    return parsed


def _atom(local_name: str) -> str:
    return f"{{{_ATOM_NAMESPACE}}}{local_name}"


def _dc(local_name: str) -> str:
    return f"{{{_DC_NAMESPACE}}}{local_name}"


def _add_text(
    parent: ET.Element,
    local_name: str,
    text: str | None,
) -> ET.Element:
    element = ET.SubElement(
        parent,
        _atom(local_name),
    )
    if text is not None:
        element.text = text
    return element


def _add_dc_text(
    parent: ET.Element,
    local_name: str,
    text: str,
) -> ET.Element:
    element = ET.SubElement(
        parent,
        _dc(local_name),
    )
    element.text = text
    return element
