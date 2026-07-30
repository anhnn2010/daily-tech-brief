from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from src.config_loader import load_project_config
from src.models import ConfigError, Source


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_bundled_configuration_is_valid() -> None:
    config = load_project_config(PROJECT_ROOT / "config")
    sources_by_id = {source.id: source for source in config.sources}

    assert len(config.sources) == 18
    assert len(config.enabled_sources) == 17
    assert all(source.official for source in config.sources)
    assert sources_by_id["real_python"].enabled is False
    assert sources_by_id["python_bytes"].enabled is True


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
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    for filename in ("profile.yml", "settings.yml"):
        source_path = PROJECT_ROOT / "config" / filename
        (config_dir / filename).write_text(
            source_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    sources_path = PROJECT_ROOT / "config" / "sources.yml"
    sources_data = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    duplicate = deepcopy(sources_data["sources"][0])
    sources_data["sources"].append(duplicate)
    (config_dir / "sources.yml").write_text(
        yaml.safe_dump(sources_data, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="Duplicate source ids"):
        load_project_config(config_dir)
