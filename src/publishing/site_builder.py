from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .opds_builder import OpdsBuildResult, build_opds_catalog


@dataclass(frozen=True)
class SiteBuildResult:
    """Summary of a generated static site."""

    site_dir: Path
    index_path: Path
    latest_dir: Path
    archive_dir: Path
    archive_index_path: Path
    archive_manifest_path: Path
    opds_catalog_path: Path | None
    opds_edition_count: int
    opds_skipped_dates: tuple[str, ...]
    archive_date: str
    generated_at: str
    article_count: int
    copied_files: tuple[Path, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "site_dir": str(self.site_dir),
            "index_path": str(self.index_path),
            "latest_dir": str(self.latest_dir),
            "archive_dir": str(self.archive_dir),
            "archive_index_path": str(self.archive_index_path),
            "archive_manifest_path": str(self.archive_manifest_path),
            "opds_catalog_path": (
                str(self.opds_catalog_path)
                if self.opds_catalog_path is not None
                else None
            ),
            "opds_edition_count": self.opds_edition_count,
            "opds_skipped_dates": list(self.opds_skipped_dates),
            "archive_date": self.archive_date,
            "generated_at": self.generated_at,
            "article_count": self.article_count,
            "copied_files": [str(path) for path in self.copied_files],
        }


def build_static_site(
    output_dir: Path,
    site_dir: Path,
    *,
    timezone_name: str,
) -> SiteBuildResult:
    """Build a GitHub Pages-ready static site from generated digest files.

    Existing archive entries under ``site_dir/archive`` are preserved. The
    current edition replaces an existing archive entry for the same local
    calendar date.
    """

    output_dir = Path(output_dir)
    site_dir = Path(site_dir)

    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError("timezone_name must be a non-empty string")

    local_timezone = _load_timezone(timezone_name.strip())
    source_files = _load_source_files(output_dir)
    ranked_payload = _read_json(source_files["ranked_articles"])

    generated_at = _load_generated_at(ranked_payload)
    generated_datetime = _parse_datetime(generated_at)
    local_generated_at = generated_datetime.astimezone(local_timezone)
    archive_date = local_generated_at.date().isoformat()
    article_count = _load_article_count(ranked_payload)

    latest_dir = site_dir / "latest"
    archive_root = site_dir / "archive"
    archive_dir = (
        archive_root
        / f"{local_generated_at.year:04d}"
        / f"{local_generated_at.month:02d}"
        / f"{local_generated_at.day:02d}"
    )

    site_dir.mkdir(parents=True, exist_ok=True)
    _replace_directory(latest_dir)
    _replace_directory(archive_dir)
    archive_root.mkdir(parents=True, exist_ok=True)

    copied_files: list[Path] = []

    root_index = site_dir / "index.html"
    latest_index = latest_dir / "index.html"
    archive_index = archive_dir / "index.html"

    for destination in (root_index, latest_index, archive_index):
        _copy_file(source_files["digest_html"], destination)
        copied_files.append(destination)

    public_files = {
        "digest_markdown": "digest.md",
        "digest_epub": "digest.epub",
        "digest_full_epub": "digest-full.epub",
        "ranked_articles": "ranked_articles.json",
        "source_report": "source_report.json",
    }

    for source_key, public_name in public_files.items():
        source_path = source_files.get(source_key)
        if source_path is None:
            continue

        root_destination = site_dir / public_name
        latest_destination = latest_dir / public_name
        archive_destination = archive_dir / public_name

        for destination in (
            root_destination,
            latest_destination,
            archive_destination,
        ):
            _copy_file(source_path, destination)
            copied_files.append(destination)

    archive_manifest_path = archive_root / "index.json"
    archive_entries = _load_archive_entries(archive_manifest_path)
    current_entry = {
        "date": archive_date,
        "generated_at": generated_at,
        "article_count": article_count,
        "path": (
            f"{local_generated_at.year:04d}/"
            f"{local_generated_at.month:02d}/"
            f"{local_generated_at.day:02d}/"
        ),
        "title": _load_project_name(ranked_payload),
    }
    archive_entries = _merge_archive_entry(
        archive_entries,
        current_entry,
    )

    archive_manifest = {
        "schema_version": 1,
        "timezone": timezone_name.strip(),
        "latest_date": archive_entries[0]["date"],
        "edition_count": len(archive_entries),
        "editions": archive_entries,
    }
    _write_json_atomic(archive_manifest_path, archive_manifest)
    copied_files.append(archive_manifest_path)

    archive_listing_path = archive_root / "index.html"
    project_name = _load_project_name(ranked_payload)
    archive_listing = _render_archive_index(
        project_name=project_name,
        timezone_name=timezone_name.strip(),
        entries=archive_entries,
    )
    _write_text_atomic(archive_listing_path, archive_listing)
    copied_files.append(archive_listing_path)

    opds_result = _build_optional_opds_catalog(
        site_dir,
        catalog_title=project_name,
    )
    if opds_result is not None:
        copied_files.append(opds_result.catalog_path)
        copied_files.extend(
            edition.published_epub
            for edition in opds_result.editions
        )

    metadata_path = site_dir / "site.json"
    metadata = {
        "schema_version": 1,
        "project": ranked_payload.get("project", {}),
        "generated_at": generated_at,
        "local_generated_at": local_generated_at.isoformat(),
        "timezone": timezone_name.strip(),
        "article_count": article_count,
        "latest_path": "latest/",
        "archive_path": "archive/",
        "archive_date": archive_date,
        "opds_path": (
            "opds/catalog.xml"
            if opds_result is not None
            else None
        ),
        "opds_edition_count": (
            len(opds_result.editions)
            if opds_result is not None
            else 0
        ),
        "opds_skipped_dates": (
            list(opds_result.skipped_dates)
            if opds_result is not None
            else []
        ),
    }
    _write_json_atomic(metadata_path, metadata)
    copied_files.append(metadata_path)

    nojekyll_path = site_dir / ".nojekyll"
    _write_text_atomic(nojekyll_path, "")
    copied_files.append(nojekyll_path)

    return SiteBuildResult(
        site_dir=site_dir,
        index_path=root_index,
        latest_dir=latest_dir,
        archive_dir=archive_dir,
        archive_index_path=archive_listing_path,
        archive_manifest_path=archive_manifest_path,
        opds_catalog_path=(
            opds_result.catalog_path
            if opds_result is not None
            else None
        ),
        opds_edition_count=(
            len(opds_result.editions)
            if opds_result is not None
            else 0
        ),
        opds_skipped_dates=(
            opds_result.skipped_dates
            if opds_result is not None
            else ()
        ),
        archive_date=archive_date,
        generated_at=generated_at,
        article_count=article_count,
        copied_files=tuple(copied_files),
    )


def _build_optional_opds_catalog(
    site_dir: Path,
    *,
    catalog_title: str,
) -> OpdsBuildResult | None:
    """Build OPDS when at least one archived full EPUB is available."""

    try:
        return build_opds_catalog(
            site_dir,
            catalog_title=catalog_title,
        )
    except FileNotFoundError:
        opds_dir = site_dir / "opds"
        if opds_dir.exists():
            shutil.rmtree(opds_dir)
        return None



def _load_source_files(output_dir: Path) -> dict[str, Path | None]:
    required = {
        "digest_html": output_dir / "digest.html",
        "ranked_articles": output_dir / "ranked_articles.json",
    }
    optional = {
        "digest_markdown": output_dir / "digest.md",
        "digest_epub": output_dir / "digest.epub",
        "digest_full_epub": output_dir / "digest-full.epub",
        "source_report": output_dir / "source_report.json",
    }

    missing = [
        str(path)
        for path in required.values()
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Required generated files are missing: " + ", ".join(missing)
        )

    result: dict[str, Path | None] = dict(required)
    result.update(
        {
            key: path if path.is_file() else None
            for key, path in optional.items()
        }
    )
    return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file: {path}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _load_generated_at(payload: dict[str, Any]) -> str:
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        raise ValueError(
            "ranked_articles.json must contain a non-empty generated_at"
        )

    _parse_datetime(generated_at)
    return generated_at.strip()


def _load_article_count(payload: dict[str, Any]) -> int:
    article_count = payload.get("article_count")
    if (
        not isinstance(article_count, int)
        or isinstance(article_count, bool)
        or article_count < 0
    ):
        raise ValueError(
            "ranked_articles.json article_count must be "
            "a non-negative integer"
        )
    return article_count


def _load_project_name(payload: dict[str, Any]) -> str:
    project = payload.get("project")
    if not isinstance(project, dict):
        return "Daily Tech Brief"

    project_name = project.get("name")
    if not isinstance(project_name, str) or not project_name.strip():
        return "Daily Tech Brief"
    return project_name.strip()


def _load_archive_entries(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []

    payload = _read_json(path)
    editions = payload.get("editions", [])
    if not isinstance(editions, list):
        raise ValueError(
            "archive/index.json editions must be a list"
        )

    valid_entries: list[dict[str, Any]] = []
    for entry in editions:
        if not isinstance(entry, dict):
            continue

        date = entry.get("date")
        generated_at = entry.get("generated_at")
        article_count = entry.get("article_count")
        public_path = entry.get("path")
        title = entry.get("title")

        if (
            isinstance(date, str)
            and isinstance(generated_at, str)
            and isinstance(article_count, int)
            and not isinstance(article_count, bool)
            and article_count >= 0
            and isinstance(public_path, str)
            and isinstance(title, str)
        ):
            valid_entries.append(
                {
                    "date": date,
                    "generated_at": generated_at,
                    "article_count": article_count,
                    "path": public_path,
                    "title": title,
                }
            )

    return valid_entries


def _merge_archive_entry(
    existing_entries: list[dict[str, Any]],
    current_entry: dict[str, Any],
) -> list[dict[str, Any]]:
    entries_by_date = {
        str(entry["date"]): entry
        for entry in existing_entries
    }
    entries_by_date[str(current_entry["date"])] = current_entry

    return sorted(
        entries_by_date.values(),
        key=lambda entry: (
            str(entry["date"]),
            str(entry["generated_at"]),
        ),
        reverse=True,
    )


def _render_archive_index(
    *,
    project_name: str,
    timezone_name: str,
    entries: list[dict[str, Any]],
) -> str:
    edition_items = "\n".join(
        (
            '        <li class="edition">'
            f'<a href="{escape(str(entry["path"]), quote=True)}">'
            f'{escape(str(entry["date"]))}</a>'
            f'<span>{int(entry["article_count"])} '
            f'{"article" if int(entry["article_count"]) == 1 else "articles"}'
            "</span></li>"
        )
        for entry in entries
    )

    if not edition_items:
        edition_items = (
            '        <li class="empty">No archived editions yet.</li>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(project_name)} — Archive</title>
  <style>
    :root {{
      color-scheme: light dark;
      --background: #f4f6f8;
      --surface: #ffffff;
      --text: #1f2933;
      --muted: #5f6c7b;
      --border: #d8dee6;
      --accent: #2457c5;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --background: #11151a;
        --surface: #191f26;
        --text: #edf2f7;
        --muted: #aab6c3;
        --border: #34404c;
        --accent: #8eb0ff;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--background);
      color: var(--text);
      font-family: system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      line-height: 1.6;
    }}
    main {{
      width: min(760px, calc(100% - 32px));
      margin: 0 auto;
      padding: 48px 0 64px;
    }}
    a {{
      color: var(--accent);
      text-underline-offset: 0.18em;
    }}
    h1 {{
      margin-bottom: 8px;
      font-size: clamp(2rem, 7vw, 3.2rem);
      line-height: 1.1;
    }}
    .meta {{
      margin-top: 0;
      color: var(--muted);
    }}
    .editions {{
      margin: 32px 0;
      padding: 0;
      list-style: none;
    }}
    .edition {{
      display: flex;
      justify-content: space-between;
      gap: 20px;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
      padding: 15px 16px;
    }}
    .edition:first-child {{
      border-radius: 12px 12px 0 0;
    }}
    .edition:last-child {{
      border-bottom: 0;
      border-radius: 0 0 12px 12px;
    }}
    .edition span, .empty {{
      color: var(--muted);
    }}
    .back {{
      display: inline-block;
      margin-top: 16px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(project_name)} Archive</h1>
    <p class="meta">
      Editions are grouped by local date in {escape(timezone_name)}.
    </p>
    <ul class="editions">
{edition_items}
    </ul>
    <a class="back" href="../">← Latest edition</a>
  </main>
</body>
</html>
"""


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            "generated_at must be a valid ISO datetime"
        ) from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"Unknown timezone '{timezone_name}'"
        ) from exc


def _replace_directory(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    path.mkdir(parents=True, exist_ok=True)


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(
        destination.suffix + ".tmp"
    )
    shutil.copyfile(source, temporary_path)
    temporary_path.replace(destination)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    _write_text_atomic(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)
