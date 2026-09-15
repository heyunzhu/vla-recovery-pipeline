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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Summarize a persistent LIBERO harness run.")
    parser.add_argument("--run_dir", required=True)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = summarize_run(args.run_dir)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    overall = summary["overall"]
    print(f"run_dir: {summary['run_dir']}")
    print(
        "overall: "
        f"{overall['success']}/{overall['episodes']} "
        f"success_rate={overall['success_rate']:.3f} "
        f"recoveries={overall['recovery_calls']} "
        f"videos={overall['videos']} annotated={overall['annotated_videos']}"
    )
    for lane in summary["lanes"]:
        print(
            f"{lane['name']}: exit={lane['exit_code'] or 'running'} "
            f"{lane['success']}/{lane['episodes']} "
            f"success_rate={lane['success_rate']:.3f} "
            f"videos={lane['videos']} annotated={lane['annotated_videos']}"
        )
    print("tasks:")
    for row in summary["tasks"]:
        print(
            f"  {row['task']}: {row['success']}/{row['episodes']} "
            f"success_rate={row['success_rate']:.3f} recoveries={row['recovery_calls']}"
        )


if __name__ == "__main__":
    main()
