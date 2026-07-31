from __future__ import annotations

import json

from src.collector import CollectionResult, write_collection_outputs
from src.models import Article


def _article() -> Article:
    return Article(
        source_id="analog_feed",
        source_name="Analog Feed",
        category="semiconductor",
        source_priority=10,
        source_tags=("analog", "biasing"),
        title="Current Mirror Validation",
        url="https://example.com/current-mirror",
        external_id="current-mirror",
        published_at="2026-07-31T03:00:00Z",
        updated_at=None,
        summary="Short public summary.",
        author="Analog Engineer",
        fetched_at="2026-07-31T04:30:00Z",
        content_html=(
            "<h2>Private feed body</h2>"
            "<p>Detailed analog validation content.</p>"
        ),
        content_text=(
            "Private feed body Detailed analog validation content."
        ),
        content_status="extracted",
    )


def test_raw_article_output_removes_private_full_content(
    tmp_path,
) -> None:
    article = _article()
    result = CollectionResult(
        started_at="2026-07-31T04:30:00Z",
        completed_at="2026-07-31T04:30:01Z",
        duration_seconds=1.0,
        articles=(article,),
        reports=(),
    )

    raw_path, _ = write_collection_outputs(
        result,
        output_dir=tmp_path,
        project={"name": "Daily Tech Brief"},
    )

    payload = json.loads(
        raw_path.read_text(encoding="utf-8")
    )
    public_article = payload["articles"][0]

    assert public_article["summary"] == (
        "Short public summary."
    )
    assert public_article["content_html"] == ""
    assert public_article["content_text"] == ""
    assert public_article["content_status"] == (
        "not_requested"
    )

    assert result.articles[0].content_status == "extracted"
    assert result.articles[0].has_full_content is True
    assert "Private feed body" in (
        result.articles[0].content_html
    )
