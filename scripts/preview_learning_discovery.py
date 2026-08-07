from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.learning.discovery import discover_learning_candidates
from src.learning.selection import select_diverse_candidates
from src.learning.store import LearningStateStore
from src.models import Article


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preview rule-based Technical Learning discovery using "
            "an existing raw_articles.json file."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("output/raw_articles.json"),
        help="Path to raw_articles.json.",
    )
    parser.add_argument(
        "--state",
        type=Path,
        help=(
            "Optional learning_state.json. Used articles from this "
            "state are excluded from discovery."
        ),
    )
    parser.add_argument(
        "--minimum-score",
        type=int,
        default=12,
        help="Minimum learning score required for a candidate.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of diversified candidates to print.",
    )
    parser.add_argument(
        "--max-per-source",
        type=int,
        default=3,
        help="Maximum selected candidates from one source.",
    )
    parser.add_argument(
        "--max-per-track",
        type=int,
        default=4,
        help="Maximum selected candidates from one learning track.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the preview as JSON.",
    )
    return parser


def load_raw_articles(path: Path) -> tuple[Article, ...]:
    payload = _read_json_object(path)
    records = payload.get("articles")

    if not isinstance(records, list):
        raise ValueError(
            f"{path} must contain an articles list"
        )

    articles: list[Article] = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(
                f"{path} articles[{index}] must be an object"
            )
        articles.append(
            _article_from_record(
                record,
                index=index,
                source=path,
            )
        )

    return tuple(articles)


def _article_from_record(
    record: dict[str, Any],
    *,
    index: int,
    source: Path,
) -> Article:
    prefix = f"{source} articles[{index}]"

    source_tags = record.get("source_tags", [])
    if not isinstance(source_tags, list) or not all(
        isinstance(tag, str)
        for tag in source_tags
    ):
        raise ValueError(
            f"{prefix}.source_tags must be a list of strings"
        )

    return Article(
        source_id=_require_string(
            record.get("source_id"),
            field=f"{prefix}.source_id",
        ),
        source_name=_require_string(
            record.get("source_name"),
            field=f"{prefix}.source_name",
        ),
        category=_require_string(
            record.get("category"),
            field=f"{prefix}.category",
        ),
        source_priority=_require_integer(
            record.get("source_priority"),
            field=f"{prefix}.source_priority",
        ),
        source_tags=tuple(source_tags),
        title=_require_string(
            record.get("title"),
            field=f"{prefix}.title",
        ),
        url=_require_string(
            record.get("url"),
            field=f"{prefix}.url",
        ),
        external_id=_optional_string(
            record.get("external_id")
        ),
        published_at=_optional_string(
            record.get("published_at")
        ),
        updated_at=_optional_string(
            record.get("updated_at")
        ),
        summary=str(record.get("summary") or ""),
        author=_optional_string(
            record.get("author")
        ),
        fetched_at=_require_string(
            record.get("fetched_at"),
            field=f"{prefix}.fetched_at",
        ),
        content_html=str(
            record.get("content_html") or ""
        ),
        content_text=str(
            record.get("content_text") or ""
        ),
        content_status=str(
            record.get("content_status")
            or "not_requested"
        ),
    )


def build_preview_payload(
    *,
    articles: Sequence[Article],
    state_path: Path | None,
    minimum_score: int,
    limit: int,
    max_per_source: int,
    max_per_track: int,
) -> dict[str, Any]:
    used_articles: tuple[dict[str, Any], ...] = ()

    if state_path is not None:
        state = LearningStateStore(state_path).load()
        used_articles = state.used_articles

    discovery_result = discover_learning_candidates(
        articles,
        used_articles=used_articles,
        minimum_score=minimum_score,
        maximum_candidates=max(1, len(articles)),
    )

    selection_result = select_diverse_candidates(
        discovery_result.candidates,
        maximum_selected=limit,
        max_per_source=max_per_source,
        max_per_track=max_per_track,
    )

    return {
        "schema_version": 1,
        "input_articles": len(articles),
        "minimum_score": minimum_score,
        "discovered_candidate_count": len(
            discovery_result.candidates
        ),
        "selected_candidate_count": len(
            selection_result.selected
        ),
        "rejected_count": discovery_result.rejected_count,
        "skipped_used_count": discovery_result.skipped_used_count,
        "skipped_source_limit": (
            selection_result.skipped_source_limit
        ),
        "skipped_track_limit": (
            selection_result.skipped_track_limit
        ),
        "max_per_source": max_per_source,
        "max_per_track": max_per_track,
        "selected_candidate_id": (
            selection_result.top.id
            if selection_result.top is not None
            else None
        ),
        "candidates": [
            {
                "rank": index,
                **candidate.to_state_record(),
            }
            for index, candidate in enumerate(
                selection_result.selected,
                start=1,
            )
        ],
    }


def print_preview(payload: dict[str, Any]) -> None:
    print("Learning discovery preview")
    print()
    print(
        f"- Input articles:     {payload['input_articles']}"
    )
    print(
        f"- Minimum score:      {payload['minimum_score']}"
    )
    print(
        f"- Discovered:         "
        f"{payload['discovered_candidate_count']}"
    )
    print(
        f"- Selected:           "
        f"{payload['selected_candidate_count']}"
    )
    print(
        f"- Rejected:           {payload['rejected_count']}"
    )
    print(
        f"- Skipped as used:    {payload['skipped_used_count']}"
    )
    print(
        f"- Source cap:         {payload['max_per_source']}"
    )
    print(
        f"- Track cap:          {payload['max_per_track']}"
    )
    print(
        f"- Skipped source cap: "
        f"{payload['skipped_source_limit']}"
    )
    print(
        f"- Skipped track cap:  "
        f"{payload['skipped_track_limit']}"
    )
    print()

    candidates = payload["candidates"]
    if not candidates:
        print("No learning candidates met the selection rules.")
        return

    for candidate in candidates:
        signals = ", ".join(
            candidate["positive_signals"]
        )
        negative = ", ".join(
            candidate["negative_signals"]
        )

        print(
            f"{candidate['rank']:02}. "
            f"[score={candidate['score']}] "
            f"[{candidate['track']}] "
            f"{candidate['title']}"
        )
        print(
            f"    source: {candidate['source_name']} "
            f"({candidate['source_id']})"
        )
        print(
            f"    published: "
            f"{candidate['published_at'] or '-'}"
        )
        print(
            f"    positive: {signals or '-'}"
        )
        print(
            f"    negative: {negative or '-'}"
        )
        print(
            f"    url: {candidate['canonical_url']}"
        )
        print()


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"File not found: {path}")

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} contains invalid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"{path} must contain a JSON object"
        )

    return payload


def _require_string(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    normalized = value.strip()
    return normalized or None


def _require_integer(
    value: Any,
    *,
    field: str,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
    ):
        raise ValueError(
            f"{field} must be an integer"
        )
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        articles = load_raw_articles(args.input)
        payload = build_preview_payload(
            articles=articles,
            state_path=args.state,
            minimum_score=args.minimum_score,
            limit=args.limit,
            max_per_source=args.max_per_source,
            max_per_track=args.max_per_track,
        )
    except (OSError, ValueError) as exc:
        print(
            f"Learning discovery preview failed: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print_preview(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
