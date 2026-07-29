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
    duplicate_ids = sorted(source_id for source_id, count in counts.items() if count > 1)
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

    if runtime.get("lookback_hours", 0) <= 0:
        raise ConfigError("runtime.lookback_hours must be greater than zero")
    if runtime.get("max_articles", 0) <= 0:
        raise ConfigError("runtime.max_articles must be greater than zero")
