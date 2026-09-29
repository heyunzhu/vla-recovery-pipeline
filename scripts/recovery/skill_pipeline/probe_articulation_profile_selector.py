"""Evaluate articulation-profile selection over LIBERO initial states.

This probe does not load a VLA model and does not run cuTAMP/cuRobo. It only
settles each simulator initial state, reads MuJoCo geometry, and asks the normal
skill runtime which articulation profile it would select.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from collections import Counter
from types import SimpleNamespace
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-suite-name", required=True)
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--skill-pack", default="bottom_drawer_articulation_v1")
    parser.add_argument("--seed-start", type=int, default=51)
    parser.add_argument("--count", type=int, default=15)
    parser.add_argument("--settle-steps", type=int, default=10)
    parser.add_argument("--task-language-source", default="bddl")
    parser.add_argument("--engine-language-source", default="bddl")
    parser.add_argument("--output", default="")
    return parser.parse_args()


def collect(args: argparse.Namespace) -> dict[str, Any]:
    os.environ.setdefault("MUJOCO_GL", "egl")

    from libero.libero import benchmark

    from experiments.robot.libero.skill_pipeline.runner import (
        LIBERO_DUMMY_ACTION,
        LIBERO_ENV_RESOLUTION,
        _get_libero_env,
        _load_eval_tasks,
        _patch_torch_load,
        _query_state,
        apply_language_sources,
        init_state_index_for_episode,
    )
    from experiments.robot.libero.skill_pipeline.runtime import SkillRuntime
    from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_pack

    _patch_torch_load()
    loader_args = SimpleNamespace(
        task_suite_name=str(args.task_suite_name),
        task_ids=str(int(args.task_id)),
        generated_benchmark_dir="",
        generated_split="smoke",
        generated_task_ids="",
        task_language_source=str(args.task_language_source),
        engine_language_source=str(args.engine_language_source),
    )
    tasks = apply_language_sources(_load_eval_tasks(loader_args, benchmark), loader_args)
    if len(tasks) != 1:
        raise ValueError(f"expected one task, got {len(tasks)}")
    task = tasks[0]
    pack = resolve_skill_pack(str(args.skill_pack), repo=REPO_ROOT)
    env, task_description = _get_libero_env(task, LIBERO_ENV_RESOLUTION, int(args.seed_start))
    rows: list[dict[str, Any]] = []
    try:
        for episode_idx in range(int(args.count)):
            seed = int(args.seed_start) + episode_idx
            init_state_idx = init_state_index_for_episode(episode_idx, len(task.initial_states))
            env.seed(seed)
            env.reset()
            obs = env.set_init_state(task.initial_states[init_state_idx])
            for _ in range(max(0, int(args.settle_steps))):
                obs, _, _, _ = env.step(LIBERO_DUMMY_ACTION)
            engine_description = str(task.engine_language or task_description)
            state = _query_state(env, obs, engine_description)
            state.update(
                {
                    "task_description": engine_description,
                    "source_suite": str(task.source_suite),
                }
            )
            decision = SkillRuntime.from_index(pack.skill_index).force_recovery_query(state)
            params = dict((decision.get("recovery_hints") or {}).get("params") or {})
            selection = dict(params.get("articulation_profile_selection") or {})
            geometry = dict(selection.get("geometry") or {})
            nearest = dict(geometry.get("nearest_obstacle") or {})
            rows.append(
                {
                    "episode_idx": episode_idx,
                    "seed": seed,
                    "init_state_idx": init_state_idx,
                    "profile": str(params.get("articulation_profile") or ""),
                    "status": str(selection.get("status") or ""),
                    "best_score": selection.get("best_score"),
                    "runner_up_score": selection.get("runner_up_score"),
                    "score_margin": selection.get("score_margin"),
                    "nearest_obstacle": str(nearest.get("name") or ""),
                    "nearest_obstacle_clearance_m": nearest.get("clearance_m"),
                    "features": dict(selection.get("features") or {}),
                }
            )
    finally:
        close = getattr(env, "close", None)
        if callable(close):
            close()

    return {
        "task_suite_name": str(args.task_suite_name),
        "task_id": int(args.task_id),
        "task_description": str(task.engine_language or task_description),
        "skill_pack": str(args.skill_pack),
        "seed_start": int(args.seed_start),
        "count": int(args.count),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "profile_counts": dict(Counter(row["profile"] for row in rows)),
        "minimum_score_margin": min(
            (float(row["score_margin"]) for row in rows if row["score_margin"] is not None),
            default=None,
        ),
        "maximum_best_score": max(
            (float(row["best_score"]) for row in rows if row["best_score"] is not None),
            default=None,
        ),
        "rows": rows,
    }


def main() -> int:
    args = _args()
    report = collect(args)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output = pathlib.Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
