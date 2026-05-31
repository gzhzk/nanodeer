"""JSON report writer for benchmark runs."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from benchmarks.types import BenchmarkReport


def write_json_report(report: BenchmarkReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

