from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"_decode_error": line[:300]})
    return rows


def _lane_dirs(run_dir: Path) -> list[Path]:
    if not run_dir.exists():
        return []
    out: list[Path] = []
    for path in sorted(run_dir.iterdir()):
        if not path.is_dir():
            continue
        if path.name == "pids" or path.name.endswith("_annotated_recovery_marked"):
            continue
        if any(path.glob("*/ep*/episode.json")) or (path / "runner_and_export.log").exists():
            out.append(path)
    return out


def _skill_id(row: dict[str, Any]) -> str:
    return str(
        row.get("skill_id")
        or row.get("primary_skill_id")
        or row.get("selected_skill_id")
        or row.get("trigger_skill_id")
        or ""
    )


def summarize_run(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir)
    lanes: list[dict[str, Any]] = []
    task_rows: dict[str, dict[str, Any]] = {}
    overall = {
        "episodes": 0,
        "success": 0,
        "recovery_calls": 0,
        "videos": 0,
        "annotated_videos": 0,
    }
    all_skill_events: Counter[str] = Counter()
    all_skill_episodes: Counter[str] = Counter()

    for lane_dir in _lane_dirs(root):
        lane_skill_events: Counter[str] = Counter()
        lane_skill_episodes: Counter[str] = Counter()
        lane_tasks: dict[str, dict[str, Any]] = {}
        episodes = []
        for ep_path in sorted(lane_dir.glob("*/ep*/episode.json")):
            ep_dir = ep_path.parent
            data = read_json(ep_path)
            task = ep_path.parts[-3]
            success = bool(data.get("success"))
            recovery_calls = int(data.get("recovery_calls") or 0)
            rows = read_jsonl(ep_dir / "recovery_trace.jsonl")
            event_skill_ids = [_skill_id(row) for row in rows]
            event_skill_ids = [skill_id for skill_id in event_skill_ids if skill_id]
            episode_skill_ids = sorted(set(event_skill_ids))

            task_bucket = lane_tasks.setdefault(
                task,
                {"task": task, "episodes": 0, "success": 0, "recovery_calls": 0, "skill_episodes": Counter()},
            )
            task_bucket["episodes"] += 1
            task_bucket["success"] += int(success)
            task_bucket["recovery_calls"] += recovery_calls
            for skill_id in episode_skill_ids:
                task_bucket["skill_episodes"][skill_id] += 1
                lane_skill_episodes[skill_id] += 1
                all_skill_episodes[skill_id] += 1
            for skill_id in event_skill_ids:
                lane_skill_events[skill_id] += 1
                all_skill_events[skill_id] += 1

            episodes.append(
                {
                    "task": task,
                    "episode": ep_path.parts[-2],
                    "success": success,
                    "recovery_calls": recovery_calls,
                    "skill_ids": episode_skill_ids,
                    "video": str(ep_dir / "video.mp4") if (ep_dir / "video.mp4").exists() else "",
                }
            )

        videos = list(lane_dir.glob("*/ep*/video.mp4"))
        annotated_dir = Path(str(lane_dir) + "_annotated_recovery_marked")
        annotated = list(annotated_dir.glob("*/ep*/video_annotated_recovery.mp4")) if annotated_dir.exists() else []
        exit_path = root / f"{lane_dir.name}.exitcode"
        exit_code = exit_path.read_text(encoding="utf-8").strip() if exit_path.exists() else None

        lane_success = sum(int(ep["success"]) for ep in episodes)
        lane_recovery = sum(int(ep["recovery_calls"]) for ep in episodes)
        lanes.append(
            {
                "name": lane_dir.name,
                "path": str(lane_dir),
                "exit_code": exit_code,
                "episodes": len(episodes),
                "success": lane_success,
                "success_rate": lane_success / len(episodes) if episodes else 0.0,
                "recovery_calls": lane_recovery,
                "videos": len(videos),
                "annotated_videos": len(annotated),
                "tasks": _serialize_task_rows(lane_tasks),
                "skill_event_counts": dict(lane_skill_events.most_common()),
                "skill_episode_counts": dict(lane_skill_episodes.most_common()),
            }
        )
        overall["episodes"] += len(episodes)
        overall["success"] += lane_success
        overall["recovery_calls"] += lane_recovery
        overall["videos"] += len(videos)
        overall["annotated_videos"] += len(annotated)
        for task, row in lane_tasks.items():
            bucket = task_rows.setdefault(
                task,
                {"task": task, "episodes": 0, "success": 0, "recovery_calls": 0, "skill_episodes": Counter()},
            )
            bucket["episodes"] += row["episodes"]
            bucket["success"] += row["success"]
            bucket["recovery_calls"] += row["recovery_calls"]
            bucket["skill_episodes"].update(row["skill_episodes"])

    overall["success_rate"] = overall["success"] / overall["episodes"] if overall["episodes"] else 0.0
    return {
        "run_dir": str(root),
        "overall": overall,
        "lanes": lanes,
        "tasks": _serialize_task_rows(task_rows),
        "skill_event_counts": dict(all_skill_events.most_common()),
        "skill_episode_counts": dict(all_skill_episodes.most_common()),
        "all_done": (root / "all_done.txt").read_text(encoding="utf-8", errors="replace")
        if (root / "all_done.txt").exists()
        else "",
    }


def _serialize_task_rows(rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for task in sorted(rows, key=_task_sort_key):
        row = rows[task]
        episodes = int(row["episodes"])
        success = int(row["success"])
        out.append(
            {
                "task": task,
                "episodes": episodes,
                "success": success,
                "success_rate": success / episodes if episodes else 0.0,
                "recovery_calls": int(row["recovery_calls"]),
                "skill_episode_counts": dict(row["skill_episodes"].most_common()),
            }
        )
    return out


def _task_sort_key(task: str) -> tuple[int, str]:
    if task.startswith("task"):
        try:
            return (int(task.replace("task", "")), task)
        except ValueError:
            pass
    return (10_000, task)


def write_summary(run_dir: str | Path, summary: dict[str, Any] | None = None) -> Path:
    root = Path(run_dir)
    payload = summary or summarize_run(root)
    path = root / "harness_summary.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
