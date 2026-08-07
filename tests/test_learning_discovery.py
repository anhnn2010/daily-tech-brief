from __future__ import annotations

from src.learning.discovery import (
    build_candidate_id,
    canonicalize_url,
    classify_learning_track,
    discover_learning_candidates,
    score_learning_article,
)
from src.models import Article


def _make_article(
    *,
    title: str,
    summary: str = "",
    category: str = "python",
    source_id: str = "example_source",
    source_name: str = "Example Source",
    source_priority: int = 9,
    source_tags: tuple[str, ...] = (),
    url: str = "https://example.com/article",
) -> Article:
    return Article(
        source_id=source_id,
        source_name=source_name,
        category=category,
        source_priority=source_priority,
        source_tags=source_tags,
        title=title,
        url=url,
        external_id=url,
        published_at="2026-08-07T08:00:00Z",
        updated_at=None,
        summary=summary,
        author="Example Author",
        fetched_at="2026-08-07T09:00:00Z",
    )


def test_tutorial_article_scores_above_default_threshold() -> None:
    article = _make_article(
        title="A Practical Pytest Fixtures Tutorial",
        summary=(
            "A step-by-step guide to testing Python applications "
            "with reusable pytest fixtures."
        ),
        category="test_engineering",
        source_tags=(
            "learning_candidate",
            "tutorials",
            "pytest",
        ),
    )

    candidate = score_learning_article(article)

    assert candidate.score >= 12
    assert "tutorial" in candidate.positive_signals
    assert "guide" in candidate.positive_signals
    assert "source:learning_candidate" in candidate.positive_signals
    assert "source:tutorials" in candidate.positive_signals
    assert candidate.track == "software_testing"


def test_release_article_is_penalized() -> None:
    tutorial = _make_article(
        title="Pytest Debugging Guide",
        summary="A practical guide to debugging failing pytest tests.",
        category="test_engineering",
    )
    release = _make_article(
        title="Pytest 10 Released",
        summary="Release announcement and changelog for the latest version.",
        category="test_engineering",
        url="https://example.com/pytest-10-release",
    )

    tutorial_candidate = score_learning_article(tutorial)
    release_candidate = score_learning_article(release)

    assert release_candidate.score < tutorial_candidate.score
    assert "released" in release_candidate.negative_signals
    assert "release" in release_candidate.negative_signals
    assert "changelog" in release_candidate.negative_signals


def test_learning_candidate_source_tag_adds_score() -> None:
    plain = _make_article(
        title="Understanding Python APIs",
        summary="An explanation of API design in Python.",
    )
    tagged = _make_article(
        title="Understanding Python APIs",
        summary="An explanation of API design in Python.",
        source_tags=("learning_candidate",),
        url="https://example.com/tagged",
    )

    plain_candidate = score_learning_article(plain)
    tagged_candidate = score_learning_article(tagged)

    assert tagged_candidate.score == plain_candidate.score + 5


def test_source_topic_tag_does_not_act_as_content_signal() -> None:
    article = _make_article(
        title="Adding Social Authentication to Django",
        summary="Add OAuth login to a Django application.",
        source_id="testdriven_io",
        source_name="TestDriven.io",
        source_tags=(
            "learning_candidate",
            "tutorials",
            "web_scraping",
            "testing",
        ),
    )

    candidate = score_learning_article(article)

    assert candidate.track == "software_engineering"
    assert "testing" not in candidate.positive_signals
    assert "track:web_scraping" not in candidate.positive_signals


def test_linux_shell_track_is_detected() -> None:
    article = _make_article(
        title="Bash Error Handling and ShellCheck",
        summary=(
            "Learn shell scripting patterns for reliable command-line "
            "automation."
        ),
        category="linux",
        source_tags=("shell_script",),
    )

    track, signals = classify_learning_track(article)

    assert track == "linux_shell"
    assert "bash" in signals
    assert "shell" in signals


def test_web_scraping_track_is_detected() -> None:
    article = _make_article(
        title="Web Scraping with Scrapy",
        summary="Build a crawler for structured data extraction.",
        category="python",
        source_tags=("web_scraping", "scrapy"),
    )

    track, signals = classify_learning_track(article)

    assert track == "web_scraping"
    assert "web scraping" in signals
    assert "scrapy" in signals


def test_ci_automation_track_is_detected() -> None:
    article = _make_article(
        title="GitHub Actions Build Automation Guide",
        summary="Create a reusable CI/CD pipeline with Docker.",
        category="automation_ci",
    )

    track, signals = classify_learning_track(article)

    assert track == "ci_automation"
    assert "github actions" in signals


def test_gitlab_ci_beats_framework_keywords() -> None:
    article = _make_article(
        title=(
            "Deploying a Flask and Vue App to Heroku "
            "with Docker and GitLab CI"
        ),
        summary=(
            "A deployment tutorial using Flask, Vue, Docker, "
            "and GitLab CI."
        ),
        category="python",
    )

    track, signals = classify_learning_track(article)

    assert track == "ci_automation"
    assert "gitlab ci" in signals


def test_pytest_beats_fastapi_framework_keyword() -> None:
    article = _make_article(
        title=(
            "Developing and Testing an Asynchronous API "
            "with FastAPI and Pytest"
        ),
        summary=(
            "Build a FastAPI service and test it with pytest "
            "fixtures."
        ),
        category="python",
    )

    track, signals = classify_learning_track(article)

    assert track == "software_testing"
    assert "pytest" in signals


def test_non_python_testing_uses_software_testing_track() -> None:
    article = _make_article(
        title="Testing Vue Components in the Browser",
        summary=(
            "A practical guide to browser testing Vue components "
            "with modern testing tools."
        ),
        category="linux",
    )

    track, _signals = classify_learning_track(article)

    assert track == "software_testing"


def test_pll_track_is_detected() -> None:
    article = _make_article(
        title="PLL Phase Noise Fundamentals",
        summary=(
            "Understanding phase-locked loop jitter, VCO noise, "
            "and loop bandwidth."
        ),
        category="analog_mixed_signal",
    )

    track, signals = classify_learning_track(article)

    assert track == "pll_and_clocking"
    assert "pll" in signals
    assert "phase noise" in signals


def test_measurement_alone_does_not_select_post_silicon_track() -> None:
    article = _make_article(
        title="Understanding AI and Learning Outcomes",
        summary=(
            "A measurement framework for evaluating learning outcomes "
            "and responsible AI use."
        ),
        category="ai",
        source_id="openai_news",
        source_name="OpenAI News",
        source_priority=10,
    )

    candidate = score_learning_article(article)

    assert candidate.track == "general_technical"
    assert "measurement" in candidate.positive_signals
    assert "track:post_silicon_test" not in candidate.positive_signals


def test_post_silicon_specific_signal_selects_post_silicon_track() -> None:
    article = _make_article(
        title="Post-Silicon Characterization and Shmoo Testing Guide",
        summary=(
            "A practical guide to silicon characterization, margining, "
            "and test correlation."
        ),
        category="test_engineering",
    )

    track, signals = classify_learning_track(article)

    assert track == "post_silicon_test"
    assert "post silicon" in signals
    assert "shmoo" in signals


def test_unknown_topic_uses_general_technical_track() -> None:
    article = _make_article(
        title="An Interesting Engineering Essay",
        summary="General thoughts about technical work.",
        category="open_source",
        source_priority=5,
    )

    track, signals = classify_learning_track(article)

    assert track == "general_technical"
    assert signals == ()


def test_category_is_only_a_track_fallback() -> None:
    article = _make_article(
        title="Django API Architecture Guide",
        summary="Understand Django API architecture patterns.",
        category="linux",
        source_tags=(),
    )

    track, signals = classify_learning_track(article)

    assert track == "software_engineering"
    assert "django" in signals
    assert "category:linux" not in signals


def test_source_tag_is_used_when_content_has_no_track_signal() -> None:
    article = _make_article(
        title="A Practical Tutorial",
        summary="Step-by-step examples for everyday work.",
        category="open_source",
        source_tags=("shell_script",),
    )

    track, signals = classify_learning_track(article)

    assert track == "linux_shell"
    assert signals == ("tag:shell_script",)


def test_test_engineering_category_falls_back_to_software_testing() -> None:
    article = _make_article(
        title="A Practical Tutorial",
        summary="Step-by-step examples for everyday work.",
        category="test_engineering",
        source_tags=(),
    )

    track, signals = classify_learning_track(article)

    assert track == "software_testing"
    assert signals == ("category:test_engineering",)


def test_canonicalize_url_removes_tracking_parameters() -> None:
    url = (
        "HTTPS://Example.COM/tutorial/?"
        "utm_source=newsletter&ref=home&chapter=2#section"
    )

    canonical = canonicalize_url(url)

    assert canonical == "https://example.com/tutorial?chapter=2"


def test_canonicalize_url_normalizes_trailing_slash() -> None:
    assert canonicalize_url(
        "https://example.com/tutorial/"
    ) == "https://example.com/tutorial"

    assert canonicalize_url(
        "https://example.com/"
    ) == "https://example.com/"


def test_candidate_id_is_stable_for_tracking_variants() -> None:
    first = canonicalize_url(
        "https://example.com/tutorial?utm_source=a"
    )
    second = canonicalize_url(
        "https://example.com/tutorial?utm_source=b"
    )

    assert first == second
    assert build_candidate_id(first) == build_candidate_id(second)


def test_discovery_rejects_low_scoring_articles() -> None:
    articles = (
        _make_article(
            title="Company Earnings Update",
            summary="Quarterly earnings announcement.",
            source_priority=5,
        ),
        _make_article(
            title="Conference Event Announcement",
            summary="Join our upcoming industry event.",
            source_priority=5,
            url="https://example.com/conference",
        ),
    )

    result = discover_learning_candidates(
        articles,
        minimum_score=12,
    )

    assert result.candidates == ()
    assert result.selected is None
    assert result.rejected_count == 2
    assert result.skipped_used_count == 0


def test_discovery_skips_article_already_used_by_id() -> None:
    article = _make_article(
        title="Pytest Tutorial",
        summary="A practical guide to Python testing.",
        category="test_engineering",
        source_tags=("learning_candidate", "tutorials"),
    )
    canonical_url = canonicalize_url(article.url)
    candidate_id = build_candidate_id(canonical_url)

    result = discover_learning_candidates(
        (article,),
        used_articles=(
            {
                "id": candidate_id,
                "canonical_url": canonical_url,
            },
        ),
    )

    assert result.candidates == ()
    assert result.skipped_used_count == 1


def test_discovery_skips_article_already_used_by_url() -> None:
    article = _make_article(
        title="Bash Tutorial",
        summary="A practical shell scripting guide.",
        category="linux",
        source_tags=("learning_candidate", "tutorials"),
        url="https://example.com/bash?utm_source=digest",
    )

    result = discover_learning_candidates(
        (article,),
        used_articles=(
            {
                "url": "https://example.com/bash?utm_source=old",
            },
        ),
    )

    assert result.candidates == ()
    assert result.skipped_used_count == 1


def test_discovery_ranks_highest_score_first() -> None:
    lower = _make_article(
        title="Understanding Python Testing",
        summary="Testing Python applications with pytest.",
        category="test_engineering",
        source_priority=8,
        url="https://example.com/lower",
    )
    higher = _make_article(
        title="Pytest Tutorial and Best Practices Guide",
        summary=(
            "A deep dive into testing and debugging Python "
            "applications with pytest fixtures."
        ),
        category="test_engineering",
        source_priority=10,
        source_tags=("learning_candidate", "tutorials"),
        url="https://example.com/higher",
    )

    result = discover_learning_candidates(
        (lower, higher),
        minimum_score=0,
    )

    assert len(result.candidates) == 2
    assert result.selected is not None
    assert result.selected.article.url == higher.url
    assert result.candidates[0].score > result.candidates[1].score


def test_discovery_honors_maximum_candidates() -> None:
    articles = tuple(
        _make_article(
            title=f"Python Testing Tutorial {index}",
            summary="A practical pytest testing guide.",
            category="test_engineering",
            source_tags=("learning_candidate", "tutorials"),
            url=f"https://example.com/article-{index}",
        )
        for index in range(5)
    )

    result = discover_learning_candidates(
        articles,
        maximum_candidates=3,
    )

    assert len(result.candidates) == 3


def test_candidate_state_record_is_json_compatible() -> None:
    article = _make_article(
        title="Bash Automation Tutorial",
        summary="A guide to shell scripting and command-line automation.",
        category="linux",
        source_tags=("learning_candidate", "tutorials"),
    )

    candidate = score_learning_article(article)
    record = candidate.to_state_record()

    assert record["id"] == candidate.id
    assert record["source_id"] == article.source_id
    assert record["title"] == article.title
    assert record["track"] == "linux_shell"
    assert record["score"] == candidate.score
    assert record["status"] == "candidate"
    assert isinstance(record["positive_signals"], list)
    assert isinstance(record["negative_signals"], list)
    assert isinstance(record["track_signals"], list)


def test_invalid_discovery_limits_are_rejected() -> None:
    article = _make_article(
        title="Python Tutorial",
        summary="A practical guide.",
    )

    try:
        discover_learning_candidates(
            (article,),
            minimum_score=-1,
        )
    except ValueError as exc:
        assert str(exc) == "minimum_score must be non-negative"
    else:
        raise AssertionError("negative minimum_score was accepted")

    try:
        discover_learning_candidates(
            (article,),
            maximum_candidates=0,
        )
    except ValueError as exc:
        assert str(exc) == "maximum_candidates must be greater than zero"
    else:
        raise AssertionError("zero maximum_candidates was accepted")
