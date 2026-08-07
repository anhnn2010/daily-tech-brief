from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEARNING_STATE_SCHEMA_VERSION = 1


class LearningStateStoreError(ValueError):
    """Raised when learning discovery state cannot be loaded or saved."""


@dataclass(frozen=True)
class LearningState:
    """Persistent state used by learning discovery.

    The first schema intentionally keeps candidate records as JSON objects.
    Discovery-specific validation belongs in the discovery layer, while this
    module is responsible only for persistence and top-level state integrity.
    """

    schema_version: int
    updated_at: str | None
    candidate_articles: tuple[dict[str, Any], ...]
    used_articles: tuple[dict[str, Any], ...]
    candidate_sources: tuple[dict[str, Any], ...]

    @classmethod
    def empty(cls) -> "LearningState":
        """Return a new empty state using the current schema version."""

        return cls(
            schema_version=LEARNING_STATE_SCHEMA_VERSION,
            updated_at=None,
            candidate_articles=(),
            used_articles=(),
            candidate_sources=(),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearningState":
        """Validate and convert a JSON object into learning state."""

        if not isinstance(payload, dict):
            raise LearningStateStoreError(
                "Learning state must be a JSON object"
            )

        schema_version = payload.get("schema_version")
        if schema_version != LEARNING_STATE_SCHEMA_VERSION:
            raise LearningStateStoreError(
                "Unsupported learning state schema_version: "
                f"{schema_version!r}"
            )

        updated_at = payload.get("updated_at")
        if updated_at is not None:
            updated_at = _validate_timestamp(
                updated_at,
                field="updated_at",
            )

        candidate_articles = _validate_record_list(
            payload.get("candidate_articles"),
            field="candidate_articles",
        )
        used_articles = _validate_record_list(
            payload.get("used_articles"),
            field="used_articles",
        )
        candidate_sources = _validate_record_list(
            payload.get("candidate_sources"),
            field="candidate_sources",
        )

        return cls(
            schema_version=schema_version,
            updated_at=updated_at,
            candidate_articles=candidate_articles,
            used_articles=used_articles,
            candidate_sources=candidate_sources,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the state."""

        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "candidate_articles": [
                dict(record)
                for record in self.candidate_articles
            ],
            "used_articles": [
                dict(record)
                for record in self.used_articles
            ],
            "candidate_sources": [
                dict(record)
                for record in self.candidate_sources
            ],
        }


class LearningStateStore:
    """Read and write one persistent learning discovery state file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> LearningState:
        """Load state, returning an empty state when the file is absent."""

        if not self.path.exists():
            return LearningState.empty()

        if not self.path.is_file():
            raise LearningStateStoreError(
                f"Learning state path is not a file: {self.path}"
            )

        try:
            raw_text = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LearningStateStoreError(
                f"Unable to read learning state: {self.path}"
            ) from exc

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LearningStateStoreError(
                f"Learning state contains invalid JSON: {self.path}"
            ) from exc

        return LearningState.from_dict(payload)

    def save(
        self,
        state: LearningState,
        *,
        now: datetime | None = None,
    ) -> LearningState:
        """Atomically save state and return the persisted timestamped state."""

        if not isinstance(state, LearningState):
            raise LearningStateStoreError(
                "state must be a LearningState instance"
            )

        evaluated_at = _normalize_datetime(
            now or datetime.now(timezone.utc)
        )
        persisted_state = LearningState(
            schema_version=state.schema_version,
            updated_at=_to_iso(evaluated_at),
            candidate_articles=state.candidate_articles,
            used_articles=state.used_articles,
            candidate_sources=state.candidate_sources,
        )

        serialized = (
            json.dumps(
                persisted_state.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=False,
            )
            + "\n"
        )

        parent = self.path.parent
        try:
            parent.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise LearningStateStoreError(
                f"Unable to create learning state directory: {parent}"
            ) from exc

        temporary_path = self.path.with_name(
            f".{self.path.name}.tmp"
        )

        try:
            temporary_path.write_text(
                serialized,
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
        except OSError as exc:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise LearningStateStoreError(
                f"Unable to write learning state: {self.path}"
            ) from exc

        return persisted_state


def _validate_record_list(
    value: Any,
    *,
    field: str,
) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise LearningStateStoreError(
            f"{field} must be a list"
        )

    records: list[dict[str, Any]] = []

    for index, record in enumerate(value):
        if not isinstance(record, dict):
            raise LearningStateStoreError(
                f"{field}[{index}] must be an object"
            )
        records.append(dict(record))

    return tuple(records)


def _validate_timestamp(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningStateStoreError(
            f"{field} must be null or a non-empty ISO timestamp"
        )

    normalized = value.strip()

    try:
        parsed = datetime.fromisoformat(
            normalized.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise LearningStateStoreError(
            f"{field} must be a valid ISO timestamp"
        ) from exc

    if parsed.tzinfo is None:
        raise LearningStateStoreError(
            f"{field} must include a timezone"
        )

    return _to_iso(parsed)


def _normalize_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise LearningStateStoreError(
            "now must be a datetime"
        )

    if value.tzinfo is None:
        raise LearningStateStoreError(
            "now must include a timezone"
        )

    return value.astimezone(timezone.utc)


def _to_iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
