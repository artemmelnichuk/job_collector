"""Configuration loading and query selection for the collector CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one YAML mapping and fail clearly when the file is malformed."""
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8-sig") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")
    return data


def load_configuration(config_dir: Path) -> dict[str, Any]:
    """Load all three project configuration files."""
    config_dir = Path(config_dir)
    return {
        "queries": load_yaml(config_dir / "job_queries.yaml"),
        "companies": load_yaml(config_dir / "companies.yaml"),
        "settings": load_yaml(config_dir / "settings.yaml"),
    }


def select_queries(query_config: dict[str, Any], requested: str | None) -> list[dict[str, str]]:
    """Flatten configured categories and optionally select one exact query."""
    selected: list[dict[str, str]] = []
    categories = query_config.get("categories", {})
    if not isinstance(categories, dict):
        raise ValueError("job_queries.yaml: categories must be a mapping")

    for category, queries in categories.items():
        if not isinstance(queries, list):
            raise ValueError(f"job_queries.yaml: category {category!r} must be a list")
        for value in queries:
            item = {"query": str(value), "category": str(category)}
            if requested is None or item["query"].casefold() == requested.casefold():
                selected.append(item)

    if requested is not None and not selected:
        raise ValueError(f"Query is not configured: {requested}")
    return selected
