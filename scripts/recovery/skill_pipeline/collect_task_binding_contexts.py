#!/usr/bin/env python3
"""Collect one static language + MuJoCo binding context per LIBERO task."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any


os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        "Collect one cached task-binding context per task; no policy, rollout, or mining is run."
    )
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--task_suite_name", default="libero_90")
    parser.add_argument("--task_ids", default="")
    parser.add_argument("--generated_benchmark_dir", default="")
    parser.add_argument("--generated_split", choices=["smoke", "train", "validation", "all"], default="all")
    parser.add_argument("--generated_task_ids", default="")
    parser.add_argument("--task_language_source", choices=["auto", "filename", "bddl"], default="auto")
    parser.add_argument("--engine_language_source", choices=["auto", "policy", "bddl"], default="auto")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--resolution", type=int, default=128)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--refresh", action="store_true", help="Replace existing per-task contexts.")
    return parser.parse_args()


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("_") or "task"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _task_metadata(task: Any) -> dict[str, Any]:
    return {
        "task_id_1based": int(task.task_id_1based),
        "task_dir_name": str(task.task_dir_name),
        "source_suite": str(task.source_suite),
        "source_task_id_1based": int(task.source_task_id_1based),
        "generated_task_id": str(task.generated_task_id or ""),
        "generated_split": str(task.generated_split or ""),
        "generated_template": str(task.generated_template or ""),
    }


def main() -> None:
    args = parse_args()
    repo = _repo_root()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from libero.libero import benchmark

    from experiments.robot.libero.skill_pipeline.runner import (
        LIBERO_ENV_RESOLUTION,
        _get_libero_env,
        _load_eval_tasks,
        apply_language_sources,
    )
    from experiments.robot.libero.skill_pipeline.task_binding_context import build_task_binding_context
    from experiments.robot.libero.tiptop_repro.scene_reader import read_scene

    tasks = apply_language_sources(_load_eval_tasks(args, benchmark), args)
    if args.limit > 0:
        tasks = tasks[: args.limit]
    out_dir = Path(args.out_dir).expanduser().resolve()
    context_dir = out_dir / "contexts"
    rows: list[dict[str, Any]] = []
    failures = 0

    for task in tasks:
        task_key = _safe_name(task.task_dir_name or task.generated_task_id or f"task{task.task_id_1based:04d}")
        output_path = context_dir / f"{task_key}.json"
        if output_path.exists() and not args.refresh:
            try:
                cached = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cached = None
            if isinstance(cached, dict):
                rows.append(
                    {
                        "task_key": task_key,
                        "status": "cached",
                        "path": str(output_path.relative_to(out_dir)),
                        "task_fingerprint": cached.get("task_fingerprint"),
                        "binding_failure_reason": (cached.get("binding") or {}).get("failure_reason"),
                    }
                )
                continue

        env = None
        try:
            env, _ = _get_libero_env(task, int(args.resolution or LIBERO_ENV_RESOLUTION), int(args.seed))
            env.seed(int(args.seed))
            env.reset()
            if len(task.initial_states) <= 0:
                raise ValueError("LIBERO task has no initial states")
            obs = env.set_init_state(task.initial_states[0])
            scene = read_scene(env, obs)
            language = str(task.engine_language or task.language)
            context = build_task_binding_context(
                language,
                scene,
                task=_task_metadata(task),
                language_source=str(args.engine_language_source),
                seed=int(args.seed),
                init_state_index=0,
            )
            _write_json(output_path, context)
            rows.append(
                {
                    "task_key": task_key,
                    "status": "collected",
                    "path": str(output_path.relative_to(out_dir)),
                    "task_fingerprint": context["task_fingerprint"],
                    "snapshot_fingerprint": context["snapshot_fingerprint"],
                    "binding_failure_reason": context["binding"].get("failure_reason"),
                }
            )
        except Exception as exc:
            failures += 1
            rows.append(
                {
                    "task_key": task_key,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback_tail": traceback.format_exc().splitlines()[-8:],
                }
            )
        finally:
            if env is not None:
                close = getattr(env, "close", None)
                if callable(close):
                    close()

    index_path = out_dir / "index.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    summary = {
        "tasks": len(rows),
        "collected": sum(row["status"] == "collected" for row in rows),
        "cached": sum(row["status"] == "cached" for row in rows),
        "failed": failures,
        "binding_failures": sum(bool(row.get("binding_failure_reason")) for row in rows),
        "policy_rollout_steps": 0,
        "mining_performed": False,
        "index": str(index_path),
    }
    _write_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
