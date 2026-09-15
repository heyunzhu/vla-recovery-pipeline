from __future__ import annotations

import argparse
import sys
import tempfile
import types
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.runner import (
    _load_eval_tasks,
    episode_seed_for_index,
    init_state_index_for_episode,
    max_steps_for_suite,
)


class _Task:
    def __init__(self, name: str, folder: str):
        self.name = name
        self.language = name.replace("_", " ")
        self.problem_folder = folder
        self.bddl_file = f"{name}.bddl"
        self.init_states_file = f"{name}.pruned_init"


class _Suite:
    def __init__(self, folder: str, names: list[str]):
        self.tasks = [_Task(name, folder) for name in names]
        self.n_tasks = len(self.tasks)

    def get_task(self, idx: int) -> _Task:
        return self.tasks[idx]

    def get_task_init_states(self, idx: int) -> list[list[float]]:
        return [[float(idx)]]


class _BenchmarkModule:
    def __init__(self):
        self._suites = {
            "libero_90": _Suite("libero_90", ["base_task"]),
            "libero_object_with_mug": _Suite("libero_object_with_mug", ["object_task"]),
            "libero_spatial_with_mug": _Suite("libero_spatial_with_mug", ["spatial_task"]),
        }

    def get_benchmark_dict(self):
        return {name: (lambda suite=suite: suite) for name, suite in self._suites.items()}


class RunnerLiberoProTests(unittest.TestCase):
    def test_max_steps_for_libero_pro_family_suites(self):
        self.assertEqual(max_steps_for_suite("libero_10_object_ood"), 520)
        self.assertEqual(max_steps_for_suite("libero_goal_temp"), 300)
        self.assertEqual(max_steps_for_suite("libero_object_with_mug"), 280)
        self.assertEqual(max_steps_for_suite("libero_spatial_with_mug"), 240)
        self.assertEqual(max_steps_for_suite("libero_pro"), 600)

    def test_episode_seed_range_keeps_init_state_order(self):
        self.assertEqual([episode_seed_for_index(90, idx) for idx in range(3)], [90, 90, 90])
        self.assertEqual([episode_seed_for_index(51, idx, 51) for idx in range(15)], list(range(51, 66)))
        self.assertEqual([init_state_index_for_episode(idx, 50) for idx in range(3)], [0, 1, 2])
        self.assertEqual(init_state_index_for_episode(52, 50), 2)

    def test_libero_pro_umbrella_expands_non_base_suites(self):
        old_libero = sys.modules.get("libero")
        old_libero_libero = sys.modules.get("libero.libero")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for folder, task_name in [
                ("libero_object_with_mug", "object_task"),
                ("libero_spatial_with_mug", "spatial_task"),
            ]:
                bddl_dir = root / "bddl_files" / folder
                init_dir = root / "init_states" / folder
                bddl_dir.mkdir(parents=True)
                init_dir.mkdir(parents=True)
                (bddl_dir / f"{task_name}.bddl").write_text("", encoding="utf-8")
                (init_dir / f"{task_name}.pruned_init").write_bytes(b"")
            libero_pkg = types.ModuleType("libero")
            libero_subpkg = types.ModuleType("libero.libero")
            libero_subpkg.get_libero_path = lambda key: str(root / key)
            sys.modules["libero"] = libero_pkg
            sys.modules["libero.libero"] = libero_subpkg
            try:
                args = argparse.Namespace(
                    task_suite_name="libero_pro",
                    task_ids="",
                    generated_benchmark_dir="",
                )
                tasks = _load_eval_tasks(args, _BenchmarkModule())
            finally:
                if old_libero is None:
                    sys.modules.pop("libero", None)
                else:
                    sys.modules["libero"] = old_libero
                if old_libero_libero is None:
                    sys.modules.pop("libero.libero", None)
                else:
                    sys.modules["libero.libero"] = old_libero_libero

        self.assertEqual([task.source_suite for task in tasks], ["libero_object_with_mug", "libero_spatial_with_mug"])
        self.assertEqual([task.task_dir_name for task in tasks], ["libero_object_with_mug_task01", "libero_spatial_with_mug_task01"])
        self.assertEqual([task.max_steps for task in tasks], [280, 240])


if __name__ == "__main__":
    unittest.main()
