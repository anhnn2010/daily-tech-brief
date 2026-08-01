from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import yaml


def _load_module() -> ModuleType:
    path = Path("scripts/report_learning_coverage.py")
    spec = importlib.util.spec_from_file_location(
        "report_learning_coverage",
        path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _lesson(
    lesson_id: str,
    *,
    order: int,
    enabled: bool,
    content_html: str = "",
) -> dict[str, object]:
    return {
        "id": lesson_id,
        "order": order,
        "title": f"Lesson {lesson_id}",
        "source_name": "Example",
        "url": f"https://example.com/{lesson_id}",
        "track": "analog_foundations",
        "topics": ["analog"],
        "difficulty": "intermediate",
        "estimated_minutes": 10 + order,
        "summary": "A useful lesson summary.",
        "why_it_matters": "Useful for post-silicon validation.",
        "enabled": enabled,
        "content_html": content_html,
    }


def _write_library(path: Path) -> None:
    payload = {
        "schema_version": 1,
        "selection": {
            "enabled": True,
            "daily_count": 1,
            "rotation": "sequential",
            "include_in_max_articles": True,
            "history_source": "site_archive",
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "lessons": [
            _lesson(
                "curated",
                order=10,
                enabled=True,
                content_html=(
                    "<h2>Curated</h2>"
                    "<p>Offline content for this lesson.</p>"
                ),
            ),
            _lesson(
                "needs_web",
                order=20,
                enabled=True,
            ),
            _lesson(
                "disabled",
                order=30,
                enabled=False,
                content_html="<p>Disabled curated lesson.</p>",
            ),
        ],
    }
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def test_reports_curated_coverage(tmp_path: Path) -> None:
    module = _load_module()
    library_path = tmp_path / "learning.yml"
    _write_library(library_path)

    report = module.load_learning_coverage(library_path)

    assert report.total_lessons == 3
    assert report.enabled_lessons == 2
    assert report.curated_enabled_lessons == 1
    assert report.uncurated_enabled_lessons == 1
    assert report.coverage_rate == 0.5
    assert report.curated_reading_minutes == 20
    assert report.uncurated_reading_minutes == 30
    assert report.next_uncurated_lesson.lesson_id == "needs_web"


def test_renders_text_and_markdown(tmp_path: Path) -> None:
    module = _load_module()
    library_path = tmp_path / "learning.yml"
    _write_library(library_path)
    report = module.load_learning_coverage(library_path)

    text = module.render_text_report(
        report,
        uncurated_only=True,
    )
    markdown = module.render_markdown_report(
        report,
        uncurated_only=True,
    )

    assert "Curated coverage:         50.0%" in text
    assert "Next lesson to curate:    needs_web" in text
    assert "Lesson needs_web" in text
    assert "Lesson curated" not in text

    assert "## Technical Learning coverage" in markdown
    assert "| Curated coverage | 50.0% |" in markdown
    assert "Next lesson to curate: `needs_web`" in markdown
    assert "Lesson needs_web" in markdown
    assert "Lesson curated" not in markdown


def test_json_output_can_show_only_uncurated_lessons(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_module()
    library_path = tmp_path / "learning.yml"
    _write_library(library_path)

    result = module.main(
        [
            "--input",
            str(library_path),
            "--json",
            "--uncurated-only",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["status"] == "passed"
    assert payload["next_uncurated_lesson_id"] == "needs_web"
    assert [
        record["id"]
        for record in payload["records"]
    ] == ["needs_web"]


def test_bundled_library_reports_two_curated_lessons() -> None:
    module = _load_module()
    report = module.load_learning_coverage(
        "config/learning_library.yml"
    )

    assert report.total_lessons == 16
    assert report.enabled_lessons == 16
    assert report.curated_enabled_lessons == 2
    assert report.uncurated_enabled_lessons == 14
    assert report.next_uncurated_lesson.lesson_id == (
        "voltage_reference_fundamentals"
    )


def test_script_uses_project_root_default_path(
    tmp_path: Path,
) -> None:
    script_path = Path(
        "scripts/report_learning_coverage.py"
    ).resolve()

    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--uncurated-only",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Curated offline lessons:  2" in completed.stdout
    assert "voltage_reference_fundamentals" in completed.stdout
