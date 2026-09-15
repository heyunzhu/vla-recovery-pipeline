#!/usr/bin/env python3
"""Smoke-test generated LIBERO BDDL files by loading and resetting envs."""

from __future__ import annotations

import argparse
import json
import os
import traceback
from pathlib import Path
from typing import Any


os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Smoke-test generated LIBERO BDDL files.")
    parser.add_argument("--benchmark-dir", required=True, help="Generated benchmark root.")
    parser.add_argument("--split", default="smoke", choices=["smoke", "train", "validation", "all"])
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of tasks to test. 0 means all.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--resolution", type=int, default=128)
    parser.add_argument("--out-json", default="", help="Optional output JSON path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.benchmark_dir).resolve()
    manifest = root / "manifests" / "all_tasks.jsonl"
    rows = _read_jsonl(manifest)
    if args.split != "all":
        rows = [row for row in rows if row.get("split") == args.split]
    rows = sorted(rows, key=lambda row: str(row.get("task_id") or ""))
    if args.limit > 0:
        rows = rows[: args.limit]

    from libero.libero.envs import OffScreenRenderEnv

    results: list[dict[str, Any]] = []
    for row in rows:
        bddl_path = root / str(row["bddl_path"])
        result: dict[str, Any] = {
            "task_id": row.get("task_id"),
            "split": row.get("split"),
            "template": row.get("template"),
            "language": row.get("language"),
            "bddl_path": str(bddl_path),
            "ok": False,
        }
        env = None
        try:
            env = OffScreenRenderEnv(
                bddl_file_name=str(bddl_path),
                camera_heights=args.resolution,
                camera_widths=args.resolution,
            )
            env.seed(args.seed)
            obs = env.reset()
            check_success = getattr(env, "check_success", None)
            if callable(check_success):
                check_success()
            result.update(
                {
                    "ok": True,
                    "obs_keys": sorted(str(key) for key in getattr(obs, "keys", lambda: [])()),
                }
            )
        except Exception as exc:
            result.update(
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
        results.append(result)

    summary = {
        "benchmark_dir": str(root),
        "split": args.split,
        "tested": len(results),
        "ok": sum(1 for result in results if result.get("ok")),
        "failed": sum(1 for result in results if not result.get("ok")),
        "results": results,
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(text + "\n", encoding="utf-8")
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
