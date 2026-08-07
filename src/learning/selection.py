from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.learning.discovery import LearningCandidate


@dataclass(frozen=True)
class SelectionResult:
    """Result of diversified learning candidate selection."""

    selected: tuple[LearningCandidate, ...]
    skipped_source_limit: int
    skipped_track_limit: int

    @property
    def top(self) -> LearningCandidate | None:
        """Return the highest-ranked selected candidate, if any."""

        if not self.selected:
            return None
        return self.selected[0]


def select_diverse_candidates(
    candidates: Iterable[LearningCandidate],
    *,
    maximum_selected: int = 20,
    max_per_source: int = 3,
    max_per_track: int = 4,
) -> SelectionResult:
    """Select a diverse candidate pool from scored learning articles.

    Candidates are ordered by score first, then source priority, title, and
    canonical URL. Source and track caps prevent one large archive feed or one
    topic from dominating the preview/persistence pool.
    """

    if maximum_selected <= 0:
        raise ValueError(
            "maximum_selected must be greater than zero"
        )
    if max_per_source <= 0:
        raise ValueError(
            "max_per_source must be greater than zero"
        )
    if max_per_track <= 0:
        raise ValueError(
            "max_per_track must be greater than zero"
        )

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.score,
            -candidate.article.source_priority,
            candidate.article.title.casefold(),
            candidate.canonical_url,
        ),
    )

    selected: list[LearningCandidate] = []
    source_counts: dict[str, int] = {}
    track_counts: dict[str, int] = {}

    skipped_source_limit = 0
    skipped_track_limit = 0

    for candidate in ranked:
        source_id = candidate.article.source_id
        track = candidate.track

        if source_counts.get(source_id, 0) >= max_per_source:
            skipped_source_limit += 1
            continue

        if track_counts.get(track, 0) >= max_per_track:
            skipped_track_limit += 1
            continue

        selected.append(candidate)
        source_counts[source_id] = (
            source_counts.get(source_id, 0) + 1
        )
        track_counts[track] = (
            track_counts.get(track, 0) + 1
        )

        if len(selected) >= maximum_selected:
            break

    return SelectionResult(
        selected=tuple(selected),
        skipped_source_limit=skipped_source_limit,
        skipped_track_limit=skipped_track_limit,
    )
