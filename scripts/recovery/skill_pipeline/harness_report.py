#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.harness.report import write_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Write harness_summary.json, harness_gates.json, and harness_report.md.")
    parser.add_argument("--run_dir", required=True)
    parser.add_argument("--gates_json", default="", help="Optional JSON dict overriding gate thresholds.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gates = json.loads(args.gates_json) if args.gates_json else None
    print(json.dumps(write_report(args.run_dir, gates=gates), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
