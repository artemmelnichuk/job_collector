"""Collection statistics, console-report, and persistent run-log helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SourceStats:
    """Counters collected for one source adapter."""

    source: str
    queries: list[str] = field(default_factory=list)
    found: int = 0
    unique: int = 0
    duplicates: int = 0
    filtered_out: int = 0
    errors: int = 0
    new: int = 0
    existing: int = 0
    updated: int = 0

    @property
    def query_count(self) -> int:
        return len(self.queries)


@dataclass(slots=True)
class RunStats:
    """Collection-wide statistics grouped by source."""

    sources: dict[str, SourceStats] = field(default_factory=dict)

    def for_source(self, source: str) -> SourceStats:
        return self.sources.setdefault(source, SourceStats(source=source))

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {name: asdict(stats) for name, stats in self.sources.items()}

    def report_lines(self) -> list[str]:
        lines: list[str] = []
        totals = {key: 0 for key in ("found", "unique", "duplicates", "filtered_out", "errors")}

        for stats in self.sources.values():
            lines.extend(
                [
                    f"Source: {stats.source}",
                    f"Queries: {stats.query_count}",
                    f"Found: {stats.found}",
                    f"Unique: {stats.unique}",
                    f"Duplicates: {stats.duplicates}",
                    f"Filtered out (off-context or overqualified): {stats.filtered_out}",
                    f"Errors: {stats.errors}",
                    f"New: {stats.new}",
                    f"Existing: {stats.existing}",
                    f"Updated: {stats.updated}",
                ]
            )
            for key in totals:
                totals[key] += getattr(stats, key)

        lines.extend(
            [
                f"Total found: {totals['found']}",
                f"Unique jobs: {totals['unique']}",
                f"Duplicates: {totals['duplicates']}",
                f"Filtered out (off-context or overqualified): {totals['filtered_out']}",
                f"Errors: {totals['errors']}",
            ]
        )
        return lines

    def print_report(self) -> None:
        print("\n".join(self.report_lines()))


def write_run_log(logs_dir: Path, run_type: str, payload: dict[str, Any]) -> Path:
    """Append one JSON-lines record of this run to logs_dir/collector.jsonl.

    Console output (print_report) disappears the moment the terminal closes;
    settings.yaml has configured a `storage.logs_dir` since the project's
    early days, but nothing ever wrote to it — this is that persistent trail.
    """
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_type": run_type,
        **payload,
    }
    log_path = logs_dir / "collector.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return log_path
