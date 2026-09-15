#!/usr/bin/env python3
"""Replay draft/shadow diagnostic signals over an existing query_trace.jsonl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.diagnostics.registry import default_registry_path, load_registry
from experiments.robot.libero.skill_pipeline.diagnostics.replay import replay_query_rows
from experiments.robot.libero.skill_pipeline.diagnostics.runtime import DiagnosticSignalRuntime, parse_active_statuses
from experiments.robot.libero.skill_pipeline.trace_schema import read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Replay diagnostic signals over query_trace.jsonl")
    parser.add_argument("--query-trace", required=True, help="Path to query_trace.jsonl")
    parser.add_argument("--out-jsonl", required=True, help="Output augmented query_trace jsonl")
    parser.add_argument("--registry", default=str(default_registry_path()))
    parser.add_argument("--statuses", default="shadow", help="Comma-separated statuses to compute")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry = load_registry(args.registry)
    runtime = DiagnosticSignalRuntime.from_registry(registry, active_statuses=parse_active_statuses(args.statuses))
    rows = replay_query_rows(read_jsonl(args.query_trace), runtime)
    out = Path(args.out_jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
