from __future__ import annotations

from src.main import _print_execution_summary


def _summary(*, unknown: int = 0) -> dict[str, object]:
    return {
        "fetched_sources": 33,
        "total_sources": 34,
        "warning_sources": 0,
        "failed_sources": 1,
        "article_count": 2813,
        "processing": {
            "time_filter": {"kept_articles": 33},
            "deduplication": {"unique_articles": 27},
            "selected_articles": 12,
            "content_enrichment": {
                "requested_articles": 12,
                "extracted_articles": 7,
                "summary_fallback_articles": 5,
                "failed_articles": 0,
                "content_origins": {
                    "feed": 2,
                    "web": 4,
                    "curated": 1,
                    "summary": 5,
                    "none": 0,
                    "unknown": unknown,
                },
            },
        },
        "output_paths": ["output/digest.epub"],
    }


def test_prints_content_origin_counts(capsys) -> None:
    _print_execution_summary(_summary())

    output = capsys.readouterr().out

    assert (
        "Content origins:         "
        "feed=2, web=4, curated=1, summary=5, none=0"
        in output
    )
    assert "unknown=" not in output


def test_prints_unknown_origin_only_when_present(capsys) -> None:
    _print_execution_summary(_summary(unknown=1))

    output = capsys.readouterr().out

    assert "none=0, unknown=1" in output
