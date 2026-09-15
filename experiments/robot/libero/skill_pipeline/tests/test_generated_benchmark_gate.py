from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.generated_benchmark_gate import (
    validate_generated_benchmark,
    validate_generated_smoke_run,
)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _make_benchmark(root: Path, *, goal_predicate: str = "in") -> dict:
    task_id = "libero_90_gen_t001_put_inside_container_deadbeef"
    bddl_rel = "task_specs/smoke/libero_90_gen_t001_put_inside_container_deadbeef.bddl"
    row = {
        "task_id": task_id,
        "split": "smoke",
        "template": "put_inside_container",
        "language": "pick up the black book and place it in the caddy",
        "source_suite": "libero_90",
        "source_task_id_1based": 1,
        "bddl_path": bddl_rel,
    }
    (root / "manifests").mkdir(parents=True)
    (root / "task_specs" / "smoke").mkdir(parents=True)
    _write_jsonl(root / "manifests" / "smoke_tasks.jsonl", [row])
    _write_jsonl(root / "manifests" / "all_tasks.jsonl", [row])
    (root / bddl_rel).write_text(
        f"""
(define (problem LIBERO_Study_Tabletop_Manipulation)
  (:language pick up the black book and place it in the caddy)
  (:goal
    (And ({goal_predicate} black_book_1 desk_caddy_1_front_contain_region))
  )
)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    _write_json(
        root / "benchmark_summary.json",
        {
            "schema_version": 1,
            "generated_tasks": 1,
            "splits": {"smoke": 1},
            "templates": {"put_inside_container": 1},
        },
    )
    _write_json(
        root / "FREEZE.json",
        {
            "schema_version": 1,
            "name": root.name,
            "generator_commit": "abc1234",
            "generated_tasks": 1,
        },
    )
    return row


class GeneratedBenchmarkGateTests(unittest.TestCase):
    def test_validates_frozen_benchmark(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "libero90_generated_v1_envfiltered_1"
            row = _make_benchmark(root)
            report = validate_generated_benchmark(root)
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["summary"]["generated_tasks"], 1)
            self.assertEqual(report["sample_tasks"][0]["task_id"], row["task_id"])

    def test_all_split_uses_total_split_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "libero90_generated_v1_envfiltered_1"
            _make_benchmark(root)
            report = validate_generated_benchmark(root, split="all")
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["summary"]["split_tasks"], 1)

    def test_rejects_non_runtime_goal_predicate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "libero90_generated_v1_envfiltered_1"
            _make_benchmark(root, goal_predicate="Inside")
            report = validate_generated_benchmark(root)
            self.assertFalse(report["ok"], report)
            self.assertTrue(any("non-runtime predicates" in error for error in report["errors"]))

    def test_validates_smoke_run_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "libero90_generated_v1_envfiltered_1"
            row = _make_benchmark(root)
            run = Path(td) / "smoke_run"
            ep = run / row["task_id"] / "ep00"
            ep.mkdir(parents=True)
            _write_json(ep / "episode.json", {"generated_task_id": row["task_id"], "success": False})
            (ep / "query_trace.jsonl").write_text("{}\n", encoding="utf-8")
            (ep / "video.mp4").write_bytes(b"mp4")

            report = validate_generated_smoke_run(run, benchmark_dir=root)
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["summary"]["episodes"], 1)
            self.assertEqual(report["tasks"][0]["episodes"], 1)


if __name__ == "__main__":
    unittest.main()
