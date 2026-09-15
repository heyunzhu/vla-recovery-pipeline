"""Quality-gate checks for frozen generated LIBERO benchmarks.

These checks are intentionally lightweight. They do not run MuJoCo or a policy;
they verify that a frozen generated benchmark is structurally usable by the
runner and that a separately executed smoke run produced the expected artifacts.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping


GOAL_SECTION_RE = re.compile(r"\(:goal\s+(.*?)\n\s*\)\s*\)\s*$", re.DOTALL | re.IGNORECASE)
BAD_RUNTIME_GOAL_RE = re.compile(r"\((Inside|On)\b")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _goal_body(text: str) -> str:
    match = GOAL_SECTION_RE.search(text)
    return match.group(1) if match else ""


def _count_existing(paths: list[Path]) -> int:
    return sum(1 for path in paths if path.exists())


def validate_generated_benchmark(
    benchmark_dir: str | Path,
    *,
    split: str = "smoke",
    require_freeze: bool = True,
) -> dict[str, Any]:
    """Validate a generated benchmark directory without importing LIBERO."""

    root = Path(benchmark_dir)
    errors: list[str] = []
    warnings: list[str] = []
    if not root.exists():
        return {
            "ok": False,
            "benchmark_dir": str(root),
            "split": split,
            "errors": [f"benchmark directory does not exist: {root}"],
            "warnings": warnings,
        }
    if not root.is_dir():
        errors.append(f"benchmark path is not a directory: {root}")

    summary = _read_json(root / "benchmark_summary.json")
    freeze = _read_json(root / "FREEZE.json")
    if require_freeze and not freeze:
        errors.append("FREEZE.json is missing or invalid")

    manifest_dir = root / "manifests"
    split_manifest = manifest_dir / f"{split}_tasks.jsonl"
    all_manifest = manifest_dir / "all_tasks.jsonl"
    split_rows = _read_jsonl(split_manifest)
    all_rows = _read_jsonl(all_manifest)
    if not split_rows:
        errors.append(f"split manifest is missing or empty: {split_manifest}")
    if not all_rows:
        errors.append(f"all manifest is missing or empty: {all_manifest}")

    split_counts = summary.get("splits") if isinstance(summary.get("splits"), Mapping) else {}
    if split_counts:
        expected = (
            sum(int(value or 0) for value in split_counts.values())
            if split == "all"
            else int(split_counts.get(split, 0) or 0)
        )
        if expected != len(split_rows):
            errors.append(f"{split} manifest count mismatch: summary={expected} actual={len(split_rows)}")
        expected_all = sum(int(value or 0) for value in split_counts.values())
        if expected_all != len(all_rows):
            errors.append(f"all manifest count mismatch: summary_splits={expected_all} actual={len(all_rows)}")
    elif summary:
        warnings.append("benchmark_summary.json has no split counts")
    else:
        errors.append("benchmark_summary.json is missing or invalid")

    if freeze:
        if freeze.get("name") and str(freeze.get("name")) != root.name:
            errors.append(f"FREEZE name does not match directory: {freeze.get('name')} != {root.name}")
        if freeze.get("generated_tasks") is not None and int(freeze.get("generated_tasks") or 0) != len(all_rows):
            errors.append(
                f"FREEZE generated_tasks mismatch: freeze={freeze.get('generated_tasks')} actual={len(all_rows)}"
            )
        if not freeze.get("generator_commit"):
            warnings.append("FREEZE.json does not record generator_commit")

    missing_bddl: list[str] = []
    bad_goal_predicates: list[str] = []
    missing_required_fields: list[str] = []
    for row in all_rows:
        task_id = str(row.get("task_id") or "")
        bddl_path = str(row.get("bddl_path") or "")
        if not task_id or not row.get("language") or not bddl_path:
            missing_required_fields.append(task_id or "<missing task_id>")
            continue
        bddl = root / bddl_path
        if not bddl.exists():
            missing_bddl.append(task_id)
            continue
        goal = _goal_body(bddl.read_text(encoding="utf-8", errors="replace"))
        if BAD_RUNTIME_GOAL_RE.search(goal):
            bad_goal_predicates.append(str(bddl.relative_to(root)))

    if missing_required_fields:
        errors.append(f"manifest rows missing required fields: {missing_required_fields[:5]}")
    if missing_bddl:
        errors.append(f"manifest references missing BDDL files: {missing_bddl[:5]}")
    if bad_goal_predicates:
        errors.append(f"generated goal uses non-runtime predicates: {bad_goal_predicates[:5]}")

    by_template: dict[str, int] = defaultdict(int)
    for row in all_rows:
        by_template[str(row.get("template") or "unknown")] += 1

    return {
        "ok": not errors,
        "benchmark_dir": str(root),
        "split": split,
        "summary": {
            "generated_tasks": len(all_rows),
            "split_tasks": len(split_rows),
            "bddl_files": len(list((root / "task_specs").glob("*/*.bddl"))),
            "templates": dict(sorted(by_template.items())),
            "freeze_name": freeze.get("name") if freeze else "",
            "generator_commit": freeze.get("generator_commit") if freeze else "",
        },
        "sample_tasks": [
            {
                "task_id": row.get("task_id"),
                "template": row.get("template"),
                "language": row.get("language"),
                "source_task_id_1based": row.get("source_task_id_1based"),
            }
            for row in split_rows[:5]
        ],
        "errors": errors,
        "warnings": warnings,
    }


def validate_generated_smoke_run(
    run_dir: str | Path,
    *,
    benchmark_dir: str | Path,
    split: str = "smoke",
    min_episodes_per_task: int = 1,
    require_video: bool = True,
) -> dict[str, Any]:
    """Validate that a generated benchmark smoke run produced replay artifacts."""

    run = Path(run_dir)
    benchmark = Path(benchmark_dir)
    errors: list[str] = []
    warnings: list[str] = []
    if not run.exists():
        return {
            "ok": False,
            "run_dir": str(run),
            "benchmark_dir": str(benchmark),
            "split": split,
            "errors": [f"smoke run directory does not exist: {run}"],
            "warnings": warnings,
        }

    manifest_rows = _read_jsonl(benchmark / "manifests" / f"{split}_tasks.jsonl")
    expected_ids = [str(row.get("task_id") or "") for row in manifest_rows if row.get("task_id")]
    expected = set(expected_ids)
    if not expected:
        errors.append(f"could not load expected {split} tasks from benchmark manifest")

    episode_rows: list[dict[str, Any]] = []
    counts_by_task: dict[str, int] = defaultdict(int)
    success_by_task: dict[str, int] = defaultdict(int)
    for episode_json in sorted(run.rglob("episode.json")):
        if any(part.endswith("_annotated_recovery_marked") for part in episode_json.parts):
            continue
        ep_dir = episode_json.parent
        meta = _read_json(episode_json)
        task_id = str(meta.get("generated_task_id") or ep_dir.parent.name)
        if expected and task_id not in expected:
            warnings.append(f"episode task is not in {split} manifest: {task_id}")
        query_trace = ep_dir / "query_trace.jsonl"
        video = ep_dir / "video.mp4"
        row = {
            "task_id": task_id,
            "episode": ep_dir.name,
            "success": bool(meta.get("success")),
            "query_trace": str(query_trace),
            "query_trace_exists": query_trace.exists(),
            "video": str(video),
            "video_exists": video.exists(),
        }
        episode_rows.append(row)
        counts_by_task[task_id] += 1
        success_by_task[task_id] += int(bool(meta.get("success")))

    missing_tasks = [
        task_id for task_id in expected_ids if counts_by_task.get(task_id, 0) < int(min_episodes_per_task)
    ]
    if missing_tasks:
        errors.append(f"smoke run is missing required episodes for tasks: {missing_tasks[:5]}")

    missing_traces = [row["task_id"] for row in episode_rows if not row["query_trace_exists"]]
    if missing_traces:
        errors.append(f"episodes missing query_trace.jsonl: {missing_traces[:5]}")

    if require_video:
        missing_videos = [row["task_id"] for row in episode_rows if not row["video_exists"]]
        if missing_videos:
            errors.append(f"episodes missing video.mp4: {missing_videos[:5]}")

    return {
        "ok": not errors,
        "run_dir": str(run),
        "benchmark_dir": str(benchmark),
        "split": split,
        "summary": {
            "expected_tasks": len(expected_ids),
            "episodes": len(episode_rows),
            "success": sum(row["success"] for row in episode_rows),
            "videos": _count_existing([Path(row["video"]) for row in episode_rows]),
            "query_traces": _count_existing([Path(row["query_trace"]) for row in episode_rows]),
            "min_episodes_per_task": int(min_episodes_per_task),
        },
        "tasks": [
            {
                "task_id": task_id,
                "episodes": counts_by_task.get(task_id, 0),
                "success": success_by_task.get(task_id, 0),
            }
            for task_id in expected_ids
        ],
        "errors": errors,
        "warnings": warnings[:20],
    }
