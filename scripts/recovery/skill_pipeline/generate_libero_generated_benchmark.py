#!/usr/bin/env python3
"""Generate a LIBERO-derived skill-mining benchmark directory."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

from experiments.robot.libero.skill_pipeline.generated_benchmark import (
    GenerationConfig,
    SourceTask,
    generate_candidates,
    inventory_from_libero,
    split_candidates,
    write_generated_benchmark,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _source_from_mapping(row: dict[str, Any]) -> SourceTask:
    if "bddl_text" not in row:
        bddl_path = row.get("bddl_path")
        if not bddl_path:
            raise ValueError("inventory rows require either bddl_text or bddl_path")
        row = dict(row)
        row["bddl_text"] = Path(str(bddl_path)).read_text(encoding="utf-8")
    return SourceTask.from_bddl(
        suite=str(row.get("suite") or "libero_90"),
        task_id_1based=int(row.get("task_id_1based") or row.get("task_id") or 0),
        language=str(row.get("language") or ""),
        bddl_text=str(row["bddl_text"]),
        problem_folder=str(row.get("problem_folder") or ""),
        bddl_file=str(row.get("bddl_file") or ""),
        bddl_path=str(row.get("bddl_path") or ""),
    )


def _env_load_filter_candidates(
    candidates,
    *,
    resolution: int,
    seed: int,
    progress_every: int = 25,
) -> tuple[list[Any], dict[str, Any]]:
    os.environ.setdefault("MUJOCO_GL", "egl")
    os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    from libero.libero.envs import OffScreenRenderEnv

    kept = []
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="libero_generated_env_load_") as td:
        scratch = Path(td)
        total = len(candidates)
        for idx, candidate in enumerate(candidates, start=1):
            if progress_every > 0 and (idx == 1 or idx % progress_every == 0 or idx == total):
                print(f"[env-load] {idx}/{total} {candidate.task_id}", file=sys.stderr, flush=True)
            bddl_path = scratch / f"{candidate.task_id}.bddl"
            bddl_path.write_text(candidate.bddl_text, encoding="utf-8")
            row: dict[str, Any] = {
                "task_id": candidate.task_id,
                "template": candidate.template,
                "language": candidate.language,
                "source_suite": candidate.source_suite,
                "source_task_id_1based": candidate.source_task_id_1based,
                "ok": False,
            }
            env = None
            try:
                env = OffScreenRenderEnv(
                    bddl_file_name=str(bddl_path),
                    camera_heights=resolution,
                    camera_widths=resolution,
                )
                env.seed(seed)
                env.reset()
                check_success = getattr(env, "check_success", None)
                if callable(check_success):
                    check_success()
                row["ok"] = True
                kept.append(candidate)
            except Exception as exc:
                row.update(
                    {
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
            rows.append(row)
    report = {
        "schema_version": 1,
        "resolution": resolution,
        "seed": seed,
        "before": len(candidates),
        "kept": len(kept),
        "failed": len(candidates) - len(kept),
        "failures_by_template": _count_by(
            (row["template"] for row in rows if not row.get("ok"))
        ),
        "results": rows,
    }
    return kept, report


def _count_by(items) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(item)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="libero_90", help="Source LIBERO suite to read.")
    parser.add_argument(
        "--out-dir",
        default=str(_repo_root() / "benchmarks" / "libero_generated"),
        help="Output benchmark directory.",
    )
    parser.add_argument(
        "--inventory-jsonl",
        default="",
        help="Optional source inventory JSONL. If omitted, imports LIBERO and reads --suite live.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-limit", type=int, default=300)
    parser.add_argument("--validation-limit", type=int, default=50)
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    parser.add_argument("--smoke-per-template", type=int, default=1)
    parser.add_argument("--canonical-episodes-per-task", type=int, default=5)
    parser.add_argument("--max-candidates-per-source", type=int, default=12)
    parser.add_argument(
        "--template",
        action="append",
        dest="templates",
        help="Template to enable. May be passed multiple times. Defaults to safe templates.",
    )
    parser.add_argument(
        "--include-relative-regions",
        action="store_true",
        help="Experimental: also emit synthetic left/right/front/back region tasks. Disabled unless explicitly allowed.",
    )
    parser.add_argument(
        "--allow-experimental-relative-place",
        action="store_true",
        help="Allow the currently experimental relative_place template.",
    )
    parser.add_argument(
        "--include-multi-goal-sources",
        action="store_true",
        help="Allow original tasks with multiple placement goals as source templates.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts but do not write files.",
    )
    parser.add_argument(
        "--env-load-filter",
        action="store_true",
        help="Load/reset generated BDDL candidates with LIBERO and keep only valid tasks before splitting.",
    )
    parser.add_argument("--env-load-resolution", type=int, default=128)
    parser.add_argument("--env-load-seed", type=int, default=0)
    parser.add_argument("--env-load-progress-every", type=int, default=25)
    parser.add_argument(
        "--env-load-report",
        default="env_load_filter_result.json",
        help="Report path relative to --out-dir, or absolute path. Used only with --env-load-filter.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    templates = tuple(args.templates) if args.templates else None
    requested_templates = set(templates or ())
    if (args.include_relative_regions or "relative_place" in requested_templates) and not args.allow_experimental_relative_place:
        raise SystemExit(
            "relative_place is temporarily disabled for stable generated benchmarks. "
            "Pass --allow-experimental-relative-place only for geometry-authoring experiments."
        )
    cfg_kwargs = {
        "source_suite": args.suite,
        "seed": args.seed,
        "max_candidates_per_source": args.max_candidates_per_source,
        "train_limit": args.train_limit,
        "validation_limit": args.validation_limit,
        "smoke_per_template": args.smoke_per_template,
        "validation_fraction": args.validation_fraction,
        "canonical_episodes_per_task": args.canonical_episodes_per_task,
        "include_relative_regions": args.include_relative_regions,
        "include_multi_goal_sources": args.include_multi_goal_sources,
    }
    if templates is not None:
        cfg_kwargs["templates"] = templates
    cfg = GenerationConfig(**cfg_kwargs)

    if args.inventory_jsonl:
        sources = [_source_from_mapping(row) for row in _read_jsonl(Path(args.inventory_jsonl))]
    else:
        sources = inventory_from_libero(args.suite)

    candidates = generate_candidates(sources, cfg)
    env_load_report = None
    before_env_load = len(candidates)
    if args.env_load_filter:
        candidates, env_load_report = _env_load_filter_candidates(
            candidates,
            resolution=args.env_load_resolution,
            seed=args.env_load_seed,
            progress_every=args.env_load_progress_every,
        )
    splits = split_candidates(candidates, cfg)
    counts = {name: len(tasks) for name, tasks in splits.items()}
    print(
        json.dumps(
            {
                "source_tasks": len(sources),
                "generated_candidates": len(candidates),
                "generated_candidates_before_env_load": before_env_load,
                "env_load_filter": (
                    {
                        "kept": env_load_report["kept"],
                        "failed": env_load_report["failed"],
                        "failures_by_template": env_load_report["failures_by_template"],
                    }
                    if env_load_report
                    else None
                ),
                "splits": counts,
                "out_dir": str(Path(args.out_dir)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.dry_run:
        return
    summary = write_generated_benchmark(args.out_dir, sources=sources, splits=splits, config=cfg)
    if env_load_report is not None:
        report_path = Path(args.env_load_report)
        if not report_path.is_absolute():
            report_path = Path(args.out_dir) / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(env_load_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary["env_load_filter"] = {
            "report": str(report_path),
            "before": env_load_report["before"],
            "kept": env_load_report["kept"],
            "failed": env_load_report["failed"],
            "failures_by_template": env_load_report["failures_by_template"],
        }
        Path(args.out_dir, "benchmark_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
