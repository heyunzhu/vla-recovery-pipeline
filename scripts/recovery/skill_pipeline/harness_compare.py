#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.harness.collector import summarize_run
from experiments.robot.libero.skill_pipeline.harness.comparator import compare_summaries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Compare two LIBERO harness runs by per-task success rate.")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = compare_summaries(summarize_run(args.baseline), summarize_run(args.candidate))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
