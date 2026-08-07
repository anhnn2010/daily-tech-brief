from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.models import Article


LEARNING_SIGNAL_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("tutorial", 8),
    ("guide", 8),
    ("fundamentals", 8),
    ("getting started", 7),
    ("how to", 6),
    ("explained", 6),
    ("understanding", 6),
    ("deep dive", 6),
    ("best practices", 5),
    ("debugging", 5),
    ("testing", 4),
    ("automation", 4),
    ("measurement", 4),
    ("architecture", 4),
    ("walkthrough", 4),
    ("tips", 3),
)

NEGATIVE_SIGNAL_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("release notes", -10),
    ("changelog", -10),
    ("released", -8),
    ("release", -7),
    ("webinar", -7),
    ("conference", -6),
    ("event", -5),
    ("earnings", -8),
    ("announcement", -5),
    ("announcing", -5),
    ("available now", -4),
)

TRACK_KEYWORDS: tuple[
    tuple[str, tuple[str, ...]],
    ...
] = (
    (
        "linux_shell",
        (
            "bash",
            "shell",
            "shell script",
            "command line",
            "linux command",
            "shellcheck",
            "awk",
            "sed",
            "xargs",
            "jq",
            "ripgrep",
            "grep",
            "find command",
            "rsync",
            "ssh",
            "cron",
            "path environment variable",
        ),
    ),
    (
        "software_testing",
        (
            "pytest",
            "python test",
            "unit test",
            "integration test",
            "browser testing",
            "component testing",
            "frontend testing",
            "mocking",
            "fixture",
            "test automation",
            "tdd",
            "playwright",
            "selenium",
            "cypress",
            "jest",
            "vitest",
            "bdd",
        ),
    ),
    (
        "web_scraping",
        (
            "web scraping",
            "scrapy",
            "crawler",
            "crawling",
            "data extraction",
            "beautifulsoup",
            "playwright scraping",
        ),
    ),
    (
        "ci_automation",
        (
            "github actions",
            "jenkins",
            "gitlab ci",
            "circleci",
            "ci/cd",
            "ci cd",
            "continuous integration",
            "continuous deployment",
            "pipeline",
            "build automation",
            "deployment",
            "deploying",
            "docker",
            "artifactory",
            "jfrog",
        ),
    ),
    (
        "post_silicon_test",
        (
            "post-silicon",
            "post silicon",
            "silicon validation",
            "silicon debug",
            "silicon characterization",
            "test correlation",
            "shmoo",
            "margining",
            "guard band",
        ),
    ),
    (
        "analog_foundations",
        (
            "current mirror",
            "bandgap",
            "bandgap reference",
            "ldo",
            "low-dropout regulator",
            "charge pump",
            "operational amplifier",
            "op amp",
            "comparator",
            "bias circuit",
            "reference generator",
            "mixed-signal",
        ),
    ),
    (
        "pll_and_clocking",
        (
            "pll",
            "phase-locked loop",
            "clocking",
            "phase noise",
            "clock jitter",
            "vco",
            "voltage-controlled oscillator",
            "loop bandwidth",
            "lock time",
            "frequency synthesizer",
        ),
    ),
    (
        "data_converters",
        (
            "adc",
            "analog-to-digital converter",
            "dac",
            "digital-to-analog converter",
            "enob",
            "sfdr",
            "inl",
            "dnl",
            "quantization",
            "sample and hold",
        ),
    ),
    (
        "software_engineering",
        (
            "python",
            "django",
            "flask",
            "fastapi",
            "api",
            "javascript",
            "vue",
            "architecture",
            "clean code",
            "refactoring",
            "debugging",
            "developer productivity",
            "celery",
            "redis",
            "postgres",
            "mongodb",
        ),
    ),
)

TRACK_STRONG_KEYWORDS: dict[str, frozenset[str]] = {
    "linux_shell": frozenset(
        {
            "bash",
            "shell",
            "shell script",
            "shellcheck",
        }
    ),
    "software_testing": frozenset(
        {
            "pytest",
            "python test",
            "unit test",
            "integration test",
            "browser testing",
            "component testing",
            "frontend testing",
            "test automation",
            "tdd",
            "playwright",
            "selenium",
            "cypress",
            "jest",
            "vitest",
            "bdd",
        }
    ),
    "web_scraping": frozenset(
        {
            "web scraping",
            "scrapy",
            "crawler",
            "crawling",
            "beautifulsoup",
        }
    ),
    "ci_automation": frozenset(
        {
            "github actions",
            "jenkins",
            "gitlab ci",
            "circleci",
            "ci/cd",
            "ci cd",
            "continuous integration",
            "continuous deployment",
            "build automation",
            "artifactory",
            "jfrog",
        }
    ),
    "post_silicon_test": frozenset(
        {
            "post-silicon",
            "post silicon",
            "silicon validation",
            "silicon debug",
            "silicon characterization",
            "shmoo",
            "margining",
        }
    ),
    "analog_foundations": frozenset(
        {
            "current mirror",
            "bandgap",
            "bandgap reference",
            "ldo",
            "low-dropout regulator",
            "charge pump",
            "operational amplifier",
            "op amp",
            "comparator",
            "reference generator",
        }
    ),
    "pll_and_clocking": frozenset(
        {
            "pll",
            "phase-locked loop",
            "phase noise",
            "clock jitter",
            "vco",
            "voltage-controlled oscillator",
            "loop bandwidth",
            "frequency synthesizer",
        }
    ),
    "data_converters": frozenset(
        {
            "adc",
            "analog-to-digital converter",
            "dac",
            "digital-to-analog converter",
            "enob",
            "sfdr",
            "inl",
            "dnl",
            "quantization",
        }
    ),
}

TRACK_PRIORITY: tuple[str, ...] = tuple(
    track
    for track, _keywords in TRACK_KEYWORDS
)

SOURCE_TAG_TRACK_HINTS: dict[str, str] = {
    "shell_script": "linux_shell",
    "bash": "linux_shell",
    "command_line": "linux_shell",
    "pytest": "software_testing",
    "software_testing": "software_testing",
    "test_automation": "software_testing",
    "web_testing": "software_testing",
    "browser_automation": "software_testing",
    "web_scraping": "web_scraping",
    "scrapy": "web_scraping",
    "crawling": "web_scraping",
    "data_extraction": "web_scraping",
    "ci": "ci_automation",
    "ci_cd": "ci_automation",
    "github_actions": "ci_automation",
    "build_automation": "ci_automation",
    "post_silicon_learning": "post_silicon_test",
    "post_silicon": "post_silicon_test",
    "analog": "analog_foundations",
    "mixed_signal": "analog_foundations",
    "pll": "pll_and_clocking",
    "clocking": "pll_and_clocking",
    "adc": "data_converters",
    "dac": "data_converters",
    "python": "software_engineering",
    "clean_code": "software_engineering",
    "developer_productivity": "software_engineering",
}

CATEGORY_TRACK_FALLBACKS: dict[str, str] = {
    "test_engineering": "software_testing",
    "automation_ci": "ci_automation",
    "linux": "linux_shell",
    "python": "software_engineering",
    "analog_mixed_signal": "analog_foundations",
}


@dataclass(frozen=True)
class LearningCandidate:
    """One ranked learning candidate discovered from a collected article."""

    id: str
    article: Article
    canonical_url: str
    track: str
    score: int
    positive_signals: tuple[str, ...]
    negative_signals: tuple[str, ...]
    track_signals: tuple[str, ...]

    def to_state_record(self) -> dict[str, object]:
        """Return a JSON-compatible record for the learning state store."""

        return {
            "id": self.id,
            "source_id": self.article.source_id,
            "source_name": self.article.source_name,
            "title": self.article.title,
            "url": self.article.url,
            "canonical_url": self.canonical_url,
            "track": self.track,
            "score": self.score,
            "positive_signals": list(self.positive_signals),
            "negative_signals": list(self.negative_signals),
            "track_signals": list(self.track_signals),
            "status": "candidate",
            "published_at": self.article.published_at,
        }


@dataclass(frozen=True)
class DiscoveryResult:
    """Result of one rule-based learning discovery pass."""

    candidates: tuple[LearningCandidate, ...]
    rejected_count: int
    skipped_used_count: int

    @property
    def selected(self) -> LearningCandidate | None:
        """Return the highest-ranked candidate, if any."""

        if not self.candidates:
            return None
        return self.candidates[0]


def discover_learning_candidates(
    articles: Iterable[Article],
    *,
    used_articles: Iterable[dict[str, object]] = (),
    minimum_score: int = 12,
    maximum_candidates: int = 100,
) -> DiscoveryResult:
    """Discover and rank learning-oriented articles.

    This function is intentionally pure: it does not read or write files and
    does not modify the current Technical Learning production pipeline.
    """

    if minimum_score < 0:
        raise ValueError("minimum_score must be non-negative")
    if maximum_candidates <= 0:
        raise ValueError("maximum_candidates must be greater than zero")

    used_ids, used_urls = _build_used_sets(used_articles)

    candidates: list[LearningCandidate] = []
    rejected_count = 0
    skipped_used_count = 0

    for article in articles:
        canonical_url = canonicalize_url(article.url)
        candidate_id = build_candidate_id(canonical_url)

        if candidate_id in used_ids or canonical_url in used_urls:
            skipped_used_count += 1
            continue

        candidate = score_learning_article(
            article,
            canonical_url=canonical_url,
        )

        if candidate.score < minimum_score:
            rejected_count += 1
            continue

        candidates.append(candidate)

    candidates.sort(
        key=lambda candidate: (
            -candidate.score,
            -candidate.article.source_priority,
            candidate.article.title.casefold(),
            candidate.canonical_url,
        )
    )

    return DiscoveryResult(
        candidates=tuple(candidates[:maximum_candidates]),
        rejected_count=rejected_count,
        skipped_used_count=skipped_used_count,
    )


def score_learning_article(
    article: Article,
    *,
    canonical_url: str | None = None,
) -> LearningCandidate:
    """Score one article for learning value using deterministic rules."""

    normalized_url = (
        canonical_url
        if canonical_url is not None
        else canonicalize_url(article.url)
    )

    # Content signals must come only from the article itself. Source tags are
    # metadata hints and must not make every article from a tutorial source
    # look like it contains words such as "testing" or "web scraping".
    content_text = _build_content_text(article)

    positive_signals: list[str] = []
    negative_signals: list[str] = []
    score = 0

    for signal, weight in LEARNING_SIGNAL_WEIGHTS:
        if _contains_phrase(content_text, signal):
            positive_signals.append(signal)
            score += weight

    for signal, weight in NEGATIVE_SIGNAL_WEIGHTS:
        if _contains_phrase(content_text, signal):
            negative_signals.append(signal)
            score += weight

    source_tags = {
        tag.casefold()
        for tag in article.source_tags
    }

    if "learning_candidate" in source_tags:
        score += 5
        positive_signals.append("source:learning_candidate")

    if "tutorials" in source_tags:
        score += 3
        positive_signals.append("source:tutorials")

    if article.source_priority >= 9:
        score += 2
        positive_signals.append("source:high_priority")

    track, track_signals = classify_learning_track(
        article,
        content_text=content_text,
    )

    content_track_signals = tuple(
        signal
        for signal in track_signals
        if not signal.startswith("tag:")
        and not signal.startswith("category:")
    )
    if content_track_signals:
        score += min(6, 2 * len(content_track_signals))
        positive_signals.append(f"track:{track}")

    return LearningCandidate(
        id=build_candidate_id(normalized_url),
        article=article,
        canonical_url=normalized_url,
        track=track,
        score=score,
        positive_signals=tuple(positive_signals),
        negative_signals=tuple(negative_signals),
        track_signals=track_signals,
    )


def classify_learning_track(
    article: Article,
    *,
    content_text: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Return the best learning track and the signals that selected it.

    Article title and summary decide the track whenever they contain a known
    topic. Source tags and category are only fallbacks for ambiguous content.
    """

    text = (
        content_text
        if content_text is not None
        else _build_content_text(article)
    )

    content_scores: dict[str, int] = {}
    content_matches: dict[str, list[str]] = {}

    for track, keywords in TRACK_KEYWORDS:
        strong_keywords = TRACK_STRONG_KEYWORDS.get(
            track,
            frozenset(),
        )

        for keyword in keywords:
            if not _contains_phrase(text, keyword):
                continue

            weight = 3 if keyword in strong_keywords else 1
            content_scores[track] = (
                content_scores.get(track, 0) + weight
            )
            content_matches.setdefault(track, []).append(keyword)

    if content_scores:
        best_track = _choose_track(content_scores)
        return best_track, tuple(
            content_matches.get(best_track, ())
        )

    tag_scores: dict[str, int] = {}
    tag_matches: dict[str, list[str]] = {}

    for tag in article.source_tags:
        normalized_tag = (
            tag.casefold()
            .replace("-", "_")
            .replace(" ", "_")
        )
        track = SOURCE_TAG_TRACK_HINTS.get(normalized_tag)
        if track is None:
            continue

        tag_scores[track] = tag_scores.get(track, 0) + 1
        tag_matches.setdefault(track, []).append(f"tag:{tag}")

    if tag_scores:
        best_track = _choose_track(tag_scores)
        return best_track, tuple(
            tag_matches.get(best_track, ())
        )

    category_track = CATEGORY_TRACK_FALLBACKS.get(
        article.category
    )
    if category_track is not None:
        return (
            category_track,
            (f"category:{article.category}",),
        )

    return "general_technical", ()


def canonicalize_url(url: str) -> str:
    """Normalize a URL for stable candidate identity and deduplication."""

    raw = str(url or "").strip()
    if not raw:
        return ""

    parts = urlsplit(raw)
    scheme = parts.scheme.casefold()
    netloc = parts.netloc.casefold()

    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(
            parts.query,
            keep_blank_values=True,
        )
        if not (
            key.casefold().startswith("utm_")
            or key.casefold()
            in {
                "ref",
                "source",
                "campaign",
                "mc_cid",
                "mc_eid",
            }
        )
    ]
    query = urlencode(filtered_query)

    return urlunsplit(
        (
            scheme,
            netloc,
            path,
            query,
            "",
        )
    )


def build_candidate_id(canonical_url: str) -> str:
    """Build a stable candidate ID from a canonical URL."""

    digest = hashlib.sha256(
        canonical_url.encode("utf-8")
    ).hexdigest()
    return f"article:{digest[:24]}"


def _choose_track(scores: dict[str, int]) -> str:
    priority_index = {
        track: index
        for index, track in enumerate(TRACK_PRIORITY)
    }
    return min(
        scores,
        key=lambda track: (
            -scores[track],
            priority_index.get(
                track,
                len(priority_index),
            ),
            track,
        ),
    )


def _build_used_sets(
    records: Iterable[dict[str, object]],
) -> tuple[set[str], set[str]]:
    used_ids: set[str] = set()
    used_urls: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            continue

        record_id = record.get("id")
        if isinstance(record_id, str) and record_id.strip():
            used_ids.add(record_id.strip())

        canonical_url = record.get("canonical_url")
        if isinstance(canonical_url, str) and canonical_url.strip():
            used_urls.add(canonical_url.strip())
            continue

        url = record.get("url")
        if isinstance(url, str) and url.strip():
            used_urls.add(canonicalize_url(url))

    return used_ids, used_urls


def _build_content_text(article: Article) -> str:
    fields: Sequence[str] = (
        article.title,
        article.summary,
    )

    return " ".join(
        _normalize_text(field)
        for field in fields
        if field
    )


def _normalize_text(value: str) -> str:
    normalized = str(value).casefold()
    normalized = re.sub(r"[_/\-]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9+#. ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_text(phrase)
    if not normalized_phrase:
        return False

    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(normalized_phrase)
        + r"(?![a-z0-9])"
    )
    return re.search(pattern, text) is not None
