"""Archive lightweight rollout traces for offline skill scanning."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

TRACE_FILES = ("episode.json", "query_trace.jsonl", "recovery_trace.jsonl")
RUN_METADATA_FILES = (
    "resolved_spec.json",
    "paths.json",
    "git_head.txt",
    "git_status.txt",
    "lanes.json",
    "harness_summary.json",
    "harness_gates.json",
    "harness_report.md",
    "all_done.txt",
)


def default_corpus_root(repo_root: str | Path) -> Path:
    return Path(repo_root) / "analysis_outputs" / "offline_trigger_corpus"


def safe_name(value: str) -> str:
    text = str(value or "").strip()
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text) or "run"


def iter_episode_dirs(run_dir: str | Path) -> Iterable[Path]:
    root = Path(run_dir)
    for episode_json in sorted(root.rglob("episode.json")):
        ep_dir = episode_json.parent
        if not ep_dir.name.startswith("ep"):
            continue
        task_name = ep_dir.parent.name
        is_task_dir = task_name.startswith("task") or task_name.startswith("libero_")
        if not is_task_dir:
            continue
        if any(part.endswith("_annotated_recovery_marked") for part in ep_dir.parts):
            continue
        yield ep_dir


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists() or not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _task_key(task_name: str) -> int:
    if task_name.startswith("task"):
        try:
            return int(task_name.replace("task", ""))
        except ValueError:
            pass
    return -1


def archive_run_for_offline_scan(
    run_dir: str | Path,
    *,
    repo_root: str | Path,
    corpus_root: str | Path | None = None,
    name: str | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Copy trace-only rollout artifacts under the repo for future scans."""

    source = Path(run_dir).resolve()
    repo = Path(repo_root).resolve()
    root = Path(corpus_root).resolve() if corpus_root else default_corpus_root(repo).resolve()
    archive_name = safe_name(name or source.name)
    target = root / archive_name
    if target == source or target in source.parents or source in target.parents:
        raise ValueError(f"refuse to archive a run into itself: source={source} target={target}")
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"offline scan corpus already exists: {target}")
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    metadata_dir = target / "_run_metadata"
    copied_metadata: list[str] = []
    for filename in RUN_METADATA_FILES:
        if _copy_if_exists(source / filename, metadata_dir / filename):
            copied_metadata.append(filename)

    episode_rows: list[dict[str, Any]] = []
    task_counts: Counter[str] = Counter()
    success_counts: Counter[str] = Counter()
    for ep_dir in iter_episode_dirs(source):
        rel = ep_dir.relative_to(source)
        dst_dir = target / rel
        copied: list[str] = []
        for filename in TRACE_FILES:
            if _copy_if_exists(ep_dir / filename, dst_dir / filename):
                copied.append(filename)
        meta = _read_json(ep_dir / "episode.json")
        task = ep_dir.parent.name
        success = bool(meta.get("success"))
        task_counts[task] += 1
        success_counts[task] += int(success)
        episode_rows.append(
            {
                "relative_dir": str(rel).replace("\\", "/"),
                "source_dir": str(ep_dir),
                "task": task,
                "task_id_1based": meta.get("task_id_1based") or _task_key(task),
                "episode": ep_dir.name,
                "episode_idx": meta.get("episode_idx"),
                "seed": meta.get("seed"),
                "success": success,
                "query_rows": _line_count(ep_dir / "query_trace.jsonl"),
                "recovery_rows": _line_count(ep_dir / "recovery_trace.jsonl"),
                "copied_files": copied,
            }
        )

    tasks = []
    for task in sorted(task_counts, key=_task_key):
        episodes = int(task_counts[task])
        successes = int(success_counts[task])
        tasks.append(
            {
                "task": task,
                "episodes": episodes,
                "success": successes,
                "success_rate": successes / episodes if episodes else 0.0,
            }
        )

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_run_dir": str(source),
        "repo_root": str(repo),
        "corpus_dir": str(target),
        "copied_metadata": copied_metadata,
        "episodes": episode_rows,
        "tasks": tasks,
        "overall": {
            "episodes": len(episode_rows),
            "success": sum(1 for row in episode_rows if row["success"]),
            "queries": sum(int(row["query_rows"]) for row in episode_rows),
            "recovery_rows": sum(int(row["recovery_rows"]) for row in episode_rows),
        },
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
