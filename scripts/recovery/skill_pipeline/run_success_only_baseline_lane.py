#!/usr/bin/env python3
"""Run skills-off LIBERO evals while retaining only per-task success rates.

This helper intentionally treats the normal skill-pipeline runner as a black box:
it runs one task at a time with recovery/skills/video disabled, reads the five
episode success bits, appends an aggregate row, then removes the runner output.
The final directory contains success_rates.jsonl and summary.json only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def parse_task_ids(spec: str) -> list[int]:
    ids: list[int] = []
    for part in str(spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            step = 1 if end >= start else -1
            ids.extend(range(start, end + step, step))
        else:
            ids.append(int(part))
    return ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Run success-only skills-off baseline lane.")
    parser.add_argument("--log_dir", required=True)
    parser.add_argument("--exp_prefix", default="success_only_baseline")
    parser.add_argument("--openvla_repo_root", required=True)
    parser.add_argument("--python_bin", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--config_name", default="pi0_libero")
    parser.add_argument("--task_suite_name", default="libero_90")
    parser.add_argument("--num_trials", type=int, default=5)
    parser.add_argument("--seed", type=int, default=90)
    parser.add_argument("--action_chunk", type=int, default=5)
    parser.add_argument("--num_steps_wait", type=int, default=10)
    parser.add_argument("--policy_in_process", action="store_true", default=True)
    return parser.parse_args()


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] {message}", flush=True)


def load_existing(path: Path) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        rows[int(row["task_id"])] = row
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    total_episodes = sum(int(row.get("episodes") or 0) for row in rows)
    total_success = sum(int(row.get("success") or 0) for row in rows)
    payload = {
        "tasks": rows,
        "num_tasks": len(rows),
        "episodes": total_episodes,
        "success": total_success,
        "success_rate": (total_success / total_episodes) if total_episodes else 0.0,
        "note": "skills/recovery/videos disabled; runner episode directories are deleted after aggregation",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_task_result(run_root: Path, task_id: int) -> dict[str, Any]:
    task_dir = run_root / f"task{int(task_id):02d}"
    if not task_dir.is_dir():
        raise FileNotFoundError(f"missing task output: {task_dir}")
    episodes: list[dict[str, Any]] = []
    for ep_dir in sorted(path for path in task_dir.iterdir() if path.is_dir() and path.name.startswith("ep")):
        meta_path = ep_dir / "episode.json"
        if meta_path.exists():
            episodes.append(json.loads(meta_path.read_text(encoding="utf-8")))
    success = sum(int(bool(item.get("success"))) for item in episodes)
    return {
        "task_id": int(task_id),
        "episodes": len(episodes),
        "success": success,
        "success_rate": (success / len(episodes)) if episodes else 0.0,
    }


def main() -> int:
    args = parse_args()
    out_dir = Path(args.log_dir)
    scratch_dir = out_dir / "_scratch"
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "success_rates.jsonl"
    summary_path = out_dir / "summary.json"
    tasks = parse_task_ids(args.tasks)
    existing = load_existing(jsonl_path)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    runner = Path(args.openvla_repo_root) / "scripts/recovery/skill_pipeline/run_skill_eval.py"
    for task_id in tasks:
        if task_id in existing:
            log(f"skip task{task_id:02d}: already aggregated")
            continue
        exp_name = f"{args.exp_prefix}_task{task_id:02d}"
        run_root = scratch_dir / exp_name
        if run_root.exists():
            shutil.rmtree(run_root)
        cmd = [
            args.python_bin,
            str(runner),
            "--log_dir",
            str(scratch_dir),
            "--exp_name",
            exp_name,
            "--openvla_repo_root",
            args.openvla_repo_root,
            "--config_name",
            args.config_name,
            "--pretrained_path",
            args.model,
            "--task_suite_name",
            args.task_suite_name,
            "--task_ids",
            str(task_id),
            "--num_trials_per_task",
            str(args.num_trials),
            "--seed",
            str(args.seed),
            "--action_chunk",
            str(args.action_chunk),
            "--num_steps_wait",
            str(args.num_steps_wait),
        ]
        if args.policy_in_process:
            cmd.append("--policy_in_process")
        log("+ " + " ".join(cmd))
        subprocess.run(cmd, env=env, check=True)
        row = read_task_result(run_root, task_id)
        row["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        append_jsonl(jsonl_path, row)
        existing[task_id] = row
        write_summary(summary_path, [existing[item] for item in sorted(existing)])
        shutil.rmtree(run_root)
        log(f"task{task_id:02d}: success={row['success']}/{row['episodes']}")

    write_summary(summary_path, [existing[item] for item in sorted(existing)])
    if scratch_dir.exists() and not any(scratch_dir.iterdir()):
        scratch_dir.rmdir()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"ERROR: {exc}")
        raise
