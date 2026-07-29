from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Sequence

from src.config_loader import ProjectConfig, load_project_config
from src.models import ConfigError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and inspect the Daily Tech Brief configuration."
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config"),
        help="Directory containing sources.yml, profile.yml, and settings.yml",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the configuration summary as JSON",
    )
    return parser


def create_summary(config: ProjectConfig) -> dict[str, object]:
    categories: dict[str, list[dict[str, object]]] = defaultdict(list)
    for source in config.enabled_sources:
        categories[source.category].append(
            {
                "id": source.id,
                "name": source.name,
                "priority": source.priority,
                "cadence": source.cadence,
                "format": source.format,
            }
        )

    for category_sources in categories.values():
        category_sources.sort(key=lambda source: (-int(source["priority"]), str(source["name"])))

    return {
        "project": config.settings["project"],
        "total_sources": len(config.sources),
        "enabled_sources": len(config.enabled_sources),
        "categories": dict(sorted(categories.items())),
    }


def print_text_summary(summary: dict[str, object]) -> None:
    project = summary["project"]
    assert isinstance(project, dict)

    print(f"{project['name']} v{project['version']}")
    print(f"Configured sources: {summary['total_sources']}")
    print(f"Enabled sources:    {summary['enabled_sources']}")

    categories = summary["categories"]
    assert isinstance(categories, dict)
    for category, sources in categories.items():
        print(f"\n{category}:")
        for source in sources:
            print(
                f"  - {source['name']} "
                f"(priority={source['priority']}, cadence={source['cadence']}, "
                f"format={source['format']})"
            )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_project_config(args.config_dir)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    summary = create_summary(config)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_text_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
