from __future__ import annotations

from typing import Any


def compare_summaries(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    base_tasks = {row["task"]: row for row in baseline.get("tasks") or []}
    cand_tasks = {row["task"]: row for row in candidate.get("tasks") or []}
    tasks = sorted(set(base_tasks) | set(cand_tasks), key=_task_sort_key)
    rows: list[dict[str, Any]] = []
    for task in tasks:
        b = base_tasks.get(task, {})
        c = cand_tasks.get(task, {})
        b_rate = float(b.get("success_rate") or 0.0)
        c_rate = float(c.get("success_rate") or 0.0)
        rows.append(
            {
                "task": task,
                "baseline_success_rate": b_rate,
                "candidate_success_rate": c_rate,
                "delta": c_rate - b_rate,
                "baseline_success": b.get("success", 0),
                "candidate_success": c.get("success", 0),
                "baseline_episodes": b.get("episodes", 0),
                "candidate_episodes": c.get("episodes", 0),
            }
        )
    b_overall = float((baseline.get("overall") or {}).get("success_rate") or 0.0)
    c_overall = float((candidate.get("overall") or {}).get("success_rate") or 0.0)
    return {
        "baseline_run_dir": baseline.get("run_dir", ""),
        "candidate_run_dir": candidate.get("run_dir", ""),
        "overall": {
            "baseline_success_rate": b_overall,
            "candidate_success_rate": c_overall,
            "delta": c_overall - b_overall,
        },
        "tasks": rows,
    }


def _task_sort_key(task: str) -> tuple[int, str]:
    if task.startswith("task"):
        try:
            return (int(task.replace("task", "")), task)
        except ValueError:
            pass
    return (10_000, task)
