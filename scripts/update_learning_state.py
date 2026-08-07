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
from src.learning.state_update import merge_candidate_articles
from src.learning.store import LearningStateStore
from src.models import Article


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover Technical Learning candidates from raw articles "
            "and persist the diversified candidate pool."
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
        default=Path("output/learning_state.json"),
        help="Path to the persistent learning_state.json.",
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
        help="Maximum diversified candidates merged per run.",
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
        "--dry-run",
        action="store_true",
        help="Run discovery and merge without writing the state file.",
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


def update_learning_state(
    *,
    articles: Sequence[Article],
    state_path: Path,
    minimum_score: int,
    limit: int,
    max_per_source: int,
    max_per_track: int,
    dry_run: bool,
) -> dict[str, Any]:
    store = LearningStateStore(state_path)
    existing_state = store.load()

    discovery_result = discover_learning_candidates(
        articles,
        used_articles=existing_state.used_articles,
        minimum_score=minimum_score,
        maximum_candidates=max(1, len(articles)),
    )

    selection_result = select_diverse_candidates(
        discovery_result.candidates,
        maximum_selected=limit,
        max_per_source=max_per_source,
        max_per_track=max_per_track,
    )

    merged_state = merge_candidate_articles(
        existing_state,
        selection_result.selected,
    )

    persisted_state = merged_state
    if not dry_run:
        persisted_state = store.save(merged_state)

    previous_ids = {
        str(record.get("id"))
        for record in existing_state.candidate_articles
        if record.get("id")
    }
    current_ids = {
        str(record.get("id"))
        for record in persisted_state.candidate_articles
        if record.get("id")
    }

    selected_ids = {
        candidate.id
        for candidate in selection_result.selected
    }

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
        "previous_candidate_count": len(
            existing_state.candidate_articles
        ),
        "persisted_candidate_count": len(
            persisted_state.candidate_articles
        ),
        "new_candidate_count": len(
            selected_ids - previous_ids
        ),
        "removed_candidate_count": len(
            previous_ids - current_ids
        ),
        "state_path": str(state_path),
        "dry_run": dry_run,
        "updated_at": persisted_state.updated_at,
    }


def print_summary(payload: dict[str, Any]) -> None:
    print("Learning candidate state update")
    print()
    print(
        f"- Input articles:       {payload['input_articles']}"
    )
    print(
        f"- Minimum score:        {payload['minimum_score']}"
    )
    print(
        f"- Discovered:           "
        f"{payload['discovered_candidate_count']}"
    )
    print(
        f"- Selected this run:    "
        f"{payload['selected_candidate_count']}"
    )
    print(
        f"- Rejected:             {payload['rejected_count']}"
    )
    print(
        f"- Skipped as used:      "
        f"{payload['skipped_used_count']}"
    )
    print(
        f"- Skipped source cap:   "
        f"{payload['skipped_source_limit']}"
    )
    print(
        f"- Skipped track cap:    "
        f"{payload['skipped_track_limit']}"
    )
    print(
        f"- Previous candidates:  "
        f"{payload['previous_candidate_count']}"
    )
    print(
        f"- New candidates:       "
        f"{payload['new_candidate_count']}"
    )
    print(
        f"- Removed candidates:   "
        f"{payload['removed_candidate_count']}"
    )
    print(
        f"- Persisted candidates: "
        f"{payload['persisted_candidate_count']}"
    )
    print(
        f"- State:                {payload['state_path']}"
    )

    if payload["dry_run"]:
        print("- Write:                dry-run")
    else:
        print(
            f"- Updated at:           "
            f"{payload['updated_at']}"
        )


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
        payload = update_learning_state(
            articles=articles,
            state_path=args.state,
            minimum_score=args.minimum_score,
            limit=args.limit,
            max_per_source=args.max_per_source,
            max_per_track=args.max_per_track,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        print(
            f"Learning state update failed: {exc}",
            file=sys.stderr,
        )
        return 1

    print_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
