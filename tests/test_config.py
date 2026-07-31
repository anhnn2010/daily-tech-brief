from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from src.config_loader import load_project_config
from src.models import ConfigError, Source


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPTIONAL_FEATURES = (
    "ranking",
    "render_markdown",
    "render_html",
    "render_epub",
    "build_site",
    "ai_editor",
)


def _copy_bundled_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    for filename in ("sources.yml", "profile.yml", "settings.yml"):
        source_path = PROJECT_ROOT / "config" / filename
        (config_dir / filename).write_text(
            source_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    return config_dir


def _read_settings(config_dir: Path) -> dict:
    return yaml.safe_load(
        (config_dir / "settings.yml").read_text(encoding="utf-8")
    )


def _write_settings(config_dir: Path, settings: dict) -> None:
    (config_dir / "settings.yml").write_text(
        yaml.safe_dump(settings, sort_keys=False),
        encoding="utf-8",
    )


def test_bundled_configuration_is_valid() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    sources_by_id = {source.id: source for source in config.sources}

    assert len(config.sources) == 34
    assert len(config.enabled_sources) == 33
    assert all(source.official for source in config.sources)
    assert sources_by_id["real_python"].enabled is False
    assert sources_by_id["python_bytes"].enabled is True
    assert sources_by_id["n8n_blog"].enabled is True
    assert sources_by_id["fastapi_releases"].enabled is True
    assert sources_by_id["shellcheck_releases"].enabled is True
    assert sources_by_id["jq_releases"].enabled is True

    assert config.settings["project"] == {
        "name": "Daily Tech Brief",
        "version": "0.7.0",
    }

    runtime = config.settings["runtime"]
    assert runtime["output_dir"] == "output"
    assert runtime["site_dir"] == "site"
    assert runtime["user_agent"] == "DailyTechBrief/0.7.0"

    assert config.settings["features"] == {
        "fetch_feeds": True,
        "ranking": True,
        "render_markdown": True,
        "render_html": True,
        "render_epub": True,
        "build_site": True,
        "ai_editor": False,
    }


    categories = config.profile["categories"]
    assert "analog_mixed_signal" in categories
    assert categories["analog_mixed_signal"] == {
        "label": "Analog / Mixed-Signal",
        "weight": 10,
        "daily_quota": 1,
    }
    assert categories["semiconductor"]["daily_quota"] == 1
    assert sum(
        category["daily_quota"]
        for category in categories.values()
    ) == 12

    high_priority_keywords = {
        keyword.casefold()
        for keyword in config.profile["keywords"]["high_priority"]
    }
    assert {
        "pll",
        "phase noise",
        "bandgap reference",
        "shell script",
        "workflow automation",
    } <= high_priority_keywords


def test_source_ids_are_unique() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    source_ids = [source.id for source in config.sources]

    assert len(source_ids) == len(set(source_ids))


def test_all_source_categories_exist_in_profile() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    categories = set(config.profile["categories"])

    assert {source.category for source in config.sources} <= categories


def test_invalid_source_url_is_rejected() -> None:
    source = {
        "id": "bad_source",
        "name": "Bad Source",
        "provider": "feed",
        "format": "rss",
        "url": "not-a-url",
        "category": "ai",
        "priority": 5,
        "cadence": "daily",
        "enabled": True,
        "official": True,
    }

    with pytest.raises(ConfigError, match="invalid URL"):
        Source.from_dict(source)


def test_duplicate_source_id_is_rejected(tmp_path: Path) -> None:
    config_dir = _copy_bundled_config(tmp_path)

    sources_path = config_dir / "sources.yml"
    sources_data = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    duplicate = deepcopy(sources_data["sources"][0])
    sources_data["sources"].append(duplicate)
    sources_path.write_text(
        yaml.safe_dump(sources_data, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Duplicate source ids"):
        load_project_config(config_dir)


@pytest.mark.parametrize(
    "feature_name",
    ("fetch_feeds",) + OPTIONAL_FEATURES,
)
def test_feature_flags_must_be_boolean(
    tmp_path: Path,
    feature_name: str,
) -> None:
    config_dir = _copy_bundled_config(tmp_path)
    settings = _read_settings(config_dir)
    settings["features"][feature_name] = "true"
    _write_settings(config_dir, settings)

    with pytest.raises(
        ConfigError,
        match=rf"features\.{feature_name} must be a boolean",
    ):
        load_project_config(config_dir)


def test_fetch_feeds_feature_is_required(tmp_path: Path) -> None:
    config_dir = _copy_bundled_config(tmp_path)
    settings = _read_settings(config_dir)
    settings["features"].pop("fetch_feeds")
    _write_settings(config_dir, settings)

    with pytest.raises(
        ConfigError,
        match=r"features\.fetch_feeds must be a boolean",
    ):
        load_project_config(config_dir)


def test_legacy_config_without_optional_features_is_valid(
    tmp_path: Path,
) -> None:
    config_dir = _copy_bundled_config(tmp_path)
    settings = _read_settings(config_dir)

    for feature_name in OPTIONAL_FEATURES:
        settings["features"].pop(feature_name)

    settings["runtime"].pop("site_dir")
    _write_settings(config_dir, settings)

    config = load_project_config(config_dir)

    assert config.settings["features"] == {"fetch_feeds": True}
    assert "site_dir" not in config.settings["runtime"]
