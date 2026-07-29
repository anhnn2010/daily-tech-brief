from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


class ConfigError(ValueError):
    """Raised when a project configuration is invalid."""


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    provider: str
    format: str
    url: str
    category: str
    priority: int
    cadence: str
    enabled: bool
    official: bool
    tags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Source":
        required = {
            "id",
            "name",
            "provider",
            "format",
            "url",
            "category",
            "priority",
            "cadence",
            "enabled",
            "official",
        }
        missing = sorted(required - data.keys())
        if missing:
            raise ConfigError(
                f"Source is missing required fields: {', '.join(missing)}"
            )

        source = cls(
            id=str(data["id"]).strip(),
            name=str(data["name"]).strip(),
            provider=str(data["provider"]).strip(),
            format=str(data["format"]).strip(),
            url=str(data["url"]).strip(),
            category=str(data["category"]).strip(),
            priority=data["priority"],
            cadence=str(data["cadence"]).strip(),
            enabled=data["enabled"],
            official=data["official"],
            tags=tuple(str(tag).strip() for tag in data.get("tags", [])),
        )
        source.validate()
        return source

    def validate(self) -> None:
        if not self.id:
            raise ConfigError("Source id must not be empty")
        if not self.id.replace("_", "").isalnum() or self.id.lower() != self.id:
            raise ConfigError(
                f"Source id '{self.id}' must use lowercase letters, numbers, and underscores"
            )
        if not self.name:
            raise ConfigError(f"Source '{self.id}' name must not be empty")
        if self.provider != "feed":
            raise ConfigError(
                f"Source '{self.id}' has unsupported provider '{self.provider}'"
            )
        if self.format not in {"rss", "atom"}:
            raise ConfigError(
                f"Source '{self.id}' has unsupported feed format '{self.format}'"
            )

        parsed_url = urlparse(self.url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ConfigError(f"Source '{self.id}' has invalid URL '{self.url}'")

        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise ConfigError(f"Source '{self.id}' priority must be an integer")
        if not 1 <= self.priority <= 10:
            raise ConfigError(
                f"Source '{self.id}' priority must be between 1 and 10"
            )
        if self.cadence not in {"daily", "weekly"}:
            raise ConfigError(
                f"Source '{self.id}' cadence must be 'daily' or 'weekly'"
            )
        if not isinstance(self.enabled, bool):
            raise ConfigError(f"Source '{self.id}' enabled must be a boolean")
        if not isinstance(self.official, bool):
            raise ConfigError(f"Source '{self.id}' official must be a boolean")
        if not self.category:
            raise ConfigError(f"Source '{self.id}' category must not be empty")
