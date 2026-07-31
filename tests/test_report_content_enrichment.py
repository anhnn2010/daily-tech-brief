from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _load_module() -> ModuleType:
    path = Path("scripts/report_content_enrichment.py")
    spec = importlib.util.spec_from_file_location(
        "report_content_enrichment",
        path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _record(
    *,
    title: str,
    status: str,
    content_origin: str | None,
    http_status: int | None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "source_id": "example",
        "title": title,
        "url": f"https://example.com/{title.lower()}",
        "status": status,
        "http_status": http_status,
        "content_type": "text/html" if http_status else None,
        "selector": "article" if status == "extracted" else None,
        "word_count": 100 if status == "extracted" else 12,
        "duration_seconds": 0.1,
        "error": None if status == "extracted" else "fallback",
    }
    if content_origin is not None:
        record["content_origin"] = content_origin
    return record


def _write_report(path: Path, records: list[dict[str, object]]) -> None:
    payload = {
        "summary": {
            "content_enrichment": {
                "requested_articles": len(records),
                "extracted_articles": sum(
                    item["status"] == "extracted"
                    for item in records
                ),
                "summary_fallback_articles": sum(
                    item["status"] == "summary_fallback"
                    for item in records
                ),
                "failed_articles": sum(
                    item["status"] == "fetch_failed"
                    for item in records
                ),
                "records": records,
            }
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_reports_content_origin_counts(tmp_path: Path) -> None:
    module = _load_module()
    report_path = tmp_path / "ranked_articles.json"
    _write_report(
        report_path,
        [
            _record(
                title="Feed",
                status="extracted",
                content_origin="feed",
                http_status=None,
            ),
            _record(
                title="Web",
                status="extracted",
                content_origin="web",
                http_status=200,
            ),
            _record(
                title="Lesson",
                status="extracted",
                content_origin="curated",
                http_status=None,
            ),
            _record(
                title="Summary",
                status="summary_fallback",
                content_origin="summary",
                http_status=403,
            ),
        ],
    )

    report = module.load_content_report(report_path)
    rendered = module.render_text_report(report)

    assert report.origin_counts["feed"] == 1
    assert report.origin_counts["web"] == 1
    assert report.origin_counts["curated"] == 1
    assert report.origin_counts["summary"] == 1
    assert "- From feed:         1" in rendered
    assert "- From web:          1" in rendered
    assert "- Curated lessons:   1" in rendered
    assert "origin=curated" in rendered


def test_legacy_records_infer_origin(tmp_path: Path) -> None:
    module = _load_module()
    report_path = tmp_path / "ranked_articles.json"
    _write_report(
        report_path,
        [
            _record(
                title="Old web",
                status="extracted",
                content_origin=None,
                http_status=200,
            ),
            _record(
                title="Old fallback",
                status="summary_fallback",
                content_origin=None,
                http_status=403,
            ),
        ],
    )

    report = module.load_content_report(report_path)

    assert [
        record.content_origin
        for record in report.records
    ] == ["web", "summary"]
