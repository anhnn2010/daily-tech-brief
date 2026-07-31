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
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "EPUB/category-technical-learning.xhtml",
            f"<html><body><h1>Technical Learning</h1><h2>{title}</h2></body></html>",
        )


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
        }
    )

    payload = {
        "article_count": 12,
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
        '<html><body><a href="digest.epub">Download EPUB</a>'
        '<section id="technical-learning">'
        '<h2>Technical Learning</h2>'
        '<h3>Phase-Locked Loop Fundamentals</h3>'
        "</section></body></html>"
    )

    (output_dir / "digest.md").write_text(markdown, encoding="utf-8")
    (output_dir / "digest.html").write_text(html, encoding="utf-8")
    (site_dir / "index.html").write_text(html, encoding="utf-8")

    output_epub = output_dir / "digest.epub"
    _write_epub(output_epub)
    epub_bytes = output_epub.read_bytes()
    (site_dir / "digest.epub").write_bytes(epub_bytes)
    (site_dir / "latest" / "digest.epub").write_bytes(epub_bytes)

    return output_dir, site_dir


def test_verifies_complete_technical_learning_output(
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
    assert result.archive_file == (
        site_dir
        / "archive"
        / "2026"
        / "07"
        / "31"
        / "ranked_articles.json"
    )
    assert result.checked_epub_copies == (
        site_dir / "digest.epub",
        site_dir / "latest" / "digest.epub",
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


def test_rejects_missing_markdown_section(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    (output_dir / "digest.md").write_text(
        "# Daily Tech Brief\n",
        encoding="utf-8",
    )

    with pytest.raises(
        VerificationError,
        match="does not contain: ## Technical Learning",
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


def test_rejects_mismatched_published_epub_copy(
    tmp_path: Path,
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    (site_dir / "latest" / "digest.epub").write_bytes(
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


def test_main_returns_one_and_prints_json_on_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir, site_dir = _build_valid_artifacts(tmp_path)
    (output_dir / "digest.md").unlink()

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

    assert exit_code == 1
    assert payload["status"] == "failed"
    assert "Required file not found" in payload["error"]
