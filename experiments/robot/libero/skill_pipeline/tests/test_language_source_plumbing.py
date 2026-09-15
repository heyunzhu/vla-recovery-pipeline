"""Both validation paths must inherit the cell's language-source protocol from the baseline.

w0 is launched by run_mining_lane.eval_command; w1..wn are launched by
mine.mining_validation_command. They read the same baseline summary, so a cell can never
score its baseline under one protocol and its recovered rounds under another.
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

from experiments.robot.libero.skill_pipeline import mine

REPO = pathlib.Path(__file__).resolve().parents[5]
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
LANE_SCRIPT = REPO / "scripts" / "recovery" / "skill_pipeline" / "run_mining_lane.py"

ENGINE_BDDL_BASELINE = FIXTURES / "baseline_engine_bddl"
LEGACY_BASELINE = FIXTURES / "baseline_legacy_defaults"


def _load_lane_module():
    spec = importlib.util.spec_from_file_location("_lane_under_test", LANE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


LANE = _load_lane_module()


def _flag_value(argv: list[str], flag: str) -> str | None:
    if flag in argv:
        return argv[argv.index(flag) + 1]
    return None


class BaselineParamsTest(unittest.TestCase):
    def _args(self, baseline: pathlib.Path):
        return type("A", (), {"baseline_run_dir": str(baseline)})()

    def test_reads_the_protocol_from_the_baseline(self):
        params = LANE.baseline_params(self._args(ENGINE_BDDL_BASELINE))
        self.assertEqual(params.get("engine_language_source"), "bddl")
        self.assertEqual(params.get("task_language_source"), "bddl")

    def test_missing_summary_is_empty(self):
        self.assertEqual(LANE.baseline_params(self._args(pathlib.Path("/nonexistent/baseline"))), {})

    def test_legacy_baseline_has_no_flags(self):
        params = LANE.baseline_params(self._args(LEGACY_BASELINE))
        self.assertNotIn("engine_language_source", params)


class LaneEvalCommandTest(unittest.TestCase):
    def _args(self, baseline: pathlib.Path):
        return type("A", (), {
            "baseline_run_dir": str(baseline),
            "repo_root": str(REPO),
            "python_bin": "python",
            "config_name": "pi0_libero",
            "model": "/tmp/model",
            "task_suite_name": "libero_goal_task",
            "num_trials": 15,
            "action_chunk": 5,
            "num_steps_wait": 10,
            "seed": 51,
            "episode_seed_start": 51,
            "max_recovery_calls": 2,
            "save_video": True,
            "fps": 10,
            "skill_pack": "liberopro_lib_v1",
            "skills_dir": "/tmp/skills",
            "max_recovery_steps": 200,
            "max_replans": 1,
            "generated_benchmark_dir": "",
            "capability_registry": "",
        })()

    def test_w0_inherits_the_engine_override(self):
        cmd = LANE.eval_command(self._args(ENGINE_BDDL_BASELINE), 7, "mine_val_task07_w0", pathlib.Path("/tmp/val"))
        self.assertEqual(_flag_value(cmd, "--engine_language_source"), "bddl")
        self.assertEqual(_flag_value(cmd, "--task_language_source"), "bddl")
        self.assertEqual(_flag_value(cmd, "--early_stop_first_n_failures"), "5")

    def test_legacy_baseline_adds_nothing(self):
        cmd = LANE.eval_command(self._args(LEGACY_BASELINE), 7, "mine_val_task07_w0", pathlib.Path("/tmp/val"))
        self.assertIsNone(_flag_value(cmd, "--engine_language_source"))
        self.assertIsNone(_flag_value(cmd, "--task_language_source"))


class MiningValidationCommandTest(unittest.TestCase):
    def _build(self, baseline: pathlib.Path):
        return mine.mining_validation_command(
            baseline_run_dir=baseline,
            skills_root="/tmp/skills",
            val_log_dir="/tmp/val",
            task_id=7,
            writes=2,
        )["argv"]

    def test_rounds_inherit_the_engine_override(self):
        argv = self._build(ENGINE_BDDL_BASELINE)
        self.assertEqual(_flag_value(argv, "--engine_language_source"), "bddl")
        self.assertEqual(_flag_value(argv, "--task_language_source"), "bddl")

    def test_legacy_baseline_falls_back_to_the_historical_defaults(self):
        argv = self._build(LEGACY_BASELINE)
        self.assertEqual(_flag_value(argv, "--engine_language_source"), "policy")
        self.assertEqual(_flag_value(argv, "--task_language_source"), "filename")


if __name__ == "__main__":
    unittest.main()
