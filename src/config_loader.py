from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.models import ConfigError, Source


@dataclass(frozen=True)
class ProjectConfig:
    sources: tuple[Source, ...]
    profile: dict[str, Any]
    settings: dict[str, Any]

    @property
    def enabled_sources(self) -> tuple[Source, ...]:
        return tuple(source for source in self.sources if source.enabled)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Top-level YAML value must be a mapping: {path}")
    return data


def load_project_config(config_dir: Path) -> ProjectConfig:
    sources_data = _load_yaml(config_dir / "sources.yml")
    profile_data = _load_yaml(config_dir / "profile.yml")
    settings_data = _load_yaml(config_dir / "settings.yml")

    raw_sources = sources_data.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ConfigError("sources.yml must contain a non-empty 'sources' list")

    sources = tuple(Source.from_dict(item) for item in raw_sources)
    _validate_unique_source_ids(sources)
    _validate_categories(sources, profile_data)
    _validate_profile(profile_data)
    _validate_settings(settings_data)

    return ProjectConfig(
        sources=sources,
        profile=profile_data,
        settings=settings_data,
    )


def _validate_unique_source_ids(sources: tuple[Source, ...]) -> None:
    counts = Counter(source.id for source in sources)
    duplicate_ids = sorted(
        source_id for source_id, count in counts.items() if count > 1
    )
    if duplicate_ids:
        raise ConfigError(f"Duplicate source ids: {', '.join(duplicate_ids)}")


def _validate_categories(
    sources: tuple[Source, ...], profile_data: dict[str, Any]
) -> None:
    categories = profile_data.get("categories")
    if not isinstance(categories, dict) or not categories:
        raise ConfigError("profile.yml must contain a non-empty 'categories' mapping")

    unknown = sorted(
        {source.category for source in sources if source.category not in categories}
    )
    if unknown:
        raise ConfigError(
            "Sources reference categories missing from profile.yml: "
            + ", ".join(unknown)
        )


def _validate_profile(profile_data: dict[str, Any]) -> None:
    profile = profile_data.get("profile")
    if not isinstance(profile, dict):
        raise ConfigError("profile.yml must contain a 'profile' mapping")

    categories = profile_data["categories"]
    for category_id, category_data in categories.items():
        if not isinstance(category_data, dict):
            raise ConfigError(f"Category '{category_id}' must be a mapping")
        weight = category_data.get("weight")
        quota = category_data.get("daily_quota")
        if not isinstance(weight, int) or not 1 <= weight <= 10:
            raise ConfigError(
                f"Category '{category_id}' weight must be an integer from 1 to 10"
            )
        if not isinstance(quota, int) or quota < 0:
            raise ConfigError(
                f"Category '{category_id}' daily_quota must be a non-negative integer"
            )


def _validate_settings(settings_data: dict[str, Any]) -> None:
    project = settings_data.get("project")
    runtime = settings_data.get("runtime")
    features = settings_data.get("features")

    if not isinstance(project, dict):
        raise ConfigError("settings.yml must contain a 'project' mapping")
    if not isinstance(runtime, dict):
        raise ConfigError("settings.yml must contain a 'runtime' mapping")
    if not isinstance(features, dict):
        raise ConfigError("settings.yml must contain a 'features' mapping")

    _require_non_empty_string(project, "name", prefix="project")
    _require_non_empty_string(project, "version", prefix="project")

    _require_positive_number(runtime, "lookback_hours")
    _require_positive_number(runtime, "request_timeout_seconds")
    _require_positive_integer(runtime, "max_articles")
    _require_positive_integer(runtime, "max_summary_chars")
    _require_non_empty_string(runtime, "output_dir", prefix="runtime")
    _require_non_empty_string(runtime, "user_agent", prefix="runtime")

    if "site_dir" in runtime:
        _require_non_empty_string(runtime, "site_dir", prefix="runtime")

    fail_on_source_error = runtime.get("fail_on_source_error")
    if not isinstance(fail_on_source_error, bool):
        raise ConfigError("runtime.fail_on_source_error must be a boolean")

    _require_boolean_feature(features, "fetch_feeds", required=True)

    for feature_name in (
        "ranking",
        "render_markdown",
        "render_html",
        "render_epub",
        "build_site",
        "ai_editor",
    ):
        _require_boolean_feature(features, feature_name, required=False)


def _require_non_empty_string(
    data: dict[str, Any],
    key: str,
    *,
    prefix: str,
) -> None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{prefix}.{key} must be a non-empty string")


def _require_boolean_feature(
    features: dict[str, Any],
    key: str,
    *,
    required: bool,
) -> None:
    if key not in features:
        if required:
            raise ConfigError(f"features.{key} must be a boolean")
        return

    if not isinstance(features[key], bool):
        raise ConfigError(f"features.{key} must be a boolean")


def _require_positive_number(data: dict[str, Any], key: str) -> None:
    value = data.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"runtime.{key} must be greater than zero")


def _require_positive_integer(data: dict[str, Any], key: str) -> None:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"runtime.{key} must be a positive integer")
