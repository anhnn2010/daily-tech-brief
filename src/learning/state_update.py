from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from src.learning.discovery import (
    LearningCandidate,
    build_candidate_id,
    canonicalize_url,
)
from src.learning.store import LearningState


def merge_candidate_articles(
    state: LearningState,
    candidates: Iterable[LearningCandidate],
    *,
    now: datetime | None = None,
) -> LearningState:
    """Merge discovered candidates into persistent learning state.

    Existing candidates are preserved so they can be reused on later days.
    Rediscovered candidates refresh their mutable discovery metadata while
    keeping the original first_seen_at timestamp.

    Any candidate already present in used_articles is removed from the
    candidate pool.
    """

    evaluated_at = _normalize_datetime(
        now or datetime.now(timezone.utc)
    )
    timestamp = _to_iso(evaluated_at)

    used_ids, used_urls = _build_identity_sets(
        state.used_articles
    )

    existing_by_id: dict[str, dict[str, Any]] = {}
    existing_order: list[str] = []

    for record in state.candidate_articles:
        normalized = _normalize_existing_candidate(record)
        record_id = normalized["id"]
        canonical_url = normalized["canonical_url"]

        if record_id in used_ids or canonical_url in used_urls:
            continue

        if record_id not in existing_by_id:
            existing_order.append(record_id)

        existing_by_id[record_id] = normalized

    incoming_order: list[str] = []

    for candidate in candidates:
        record = candidate.to_state_record()
        record_id = str(record["id"])
        canonical_url = str(record["canonical_url"])

        if record_id in used_ids or canonical_url in used_urls:
            continue

        existing = existing_by_id.get(record_id)

        first_seen_at = timestamp
        if existing is not None:
            first_seen_at = str(
                existing.get("first_seen_at")
                or existing.get("discovered_at")
                or timestamp
            )

        merged = {
            **record,
            "first_seen_at": first_seen_at,
            "last_seen_at": timestamp,
        }

        existing_by_id[record_id] = merged

        if record_id not in incoming_order:
            incoming_order.append(record_id)

    ordered_ids = _deduplicate_order(
        incoming_order + existing_order
    )

    candidate_articles = tuple(
        existing_by_id[record_id]
        for record_id in ordered_ids
        if record_id in existing_by_id
    )

    return LearningState(
        schema_version=state.schema_version,
        updated_at=state.updated_at,
        candidate_articles=candidate_articles,
        used_articles=state.used_articles,
        candidate_sources=state.candidate_sources,
    )


def _normalize_existing_candidate(
    record: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(record)

    canonical_url = normalized.get("canonical_url")
    if not isinstance(canonical_url, str) or not canonical_url.strip():
        url = normalized.get("url")
        if isinstance(url, str) and url.strip():
            canonical_url = canonicalize_url(url)
        else:
            canonical_url = ""

    normalized["canonical_url"] = canonical_url

    record_id = normalized.get("id")
    if not isinstance(record_id, str) or not record_id.strip():
        record_id = build_candidate_id(canonical_url)

    normalized["id"] = record_id

    return normalized


def _build_identity_sets(
    records: Iterable[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    urls: set[str] = set()

    for record in records:
        record_id = record.get("id")
        if isinstance(record_id, str) and record_id.strip():
            ids.add(record_id.strip())

        canonical_url = record.get("canonical_url")
        if isinstance(canonical_url, str) and canonical_url.strip():
            urls.add(canonical_url.strip())
            continue

        url = record.get("url")
        if isinstance(url, str) and url.strip():
            urls.add(canonicalize_url(url))

    return ids, urls


def _deduplicate_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result


def _normalize_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("now must be a datetime")

    if value.tzinfo is None:
        raise ValueError("now must include a timezone")

    return value.astimezone(timezone.utc)


def _to_iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
