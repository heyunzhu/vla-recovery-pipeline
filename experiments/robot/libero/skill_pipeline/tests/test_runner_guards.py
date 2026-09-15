from __future__ import annotations

import unittest

from experiments.robot.libero.skill_pipeline.runner import (
    check_trigger_exclusivity,
    parse_args,
    should_early_stop_first_failures,
)
from experiments.robot.libero.tiptop_repro.libero_tiptop_executor import _apply_trajectory_hook


class _Args:
    enable_residual_trigger = False
    enable_skills = False
    allow_trigger_ablation = False


class RunnerGuardTests(unittest.TestCase):
    def test_residual_flag_rejected(self):
        with self.assertRaises(ValueError):
            parse_args(["--pretrained_path", "x", "--enable_residual_trigger"])

    def test_skills_default_off(self):
        args = parse_args(["--pretrained_path", "x"])
        self.assertFalse(args.enable_skills)
        self.assertFalse(args.enable_mining_skills)
        self.assertEqual(args.force_recovery_query, -1)
        check_trigger_exclusivity(args)

    def test_online_and_mining_skills_exclusive(self):
        with self.assertRaises(ValueError):
            parse_args(["--pretrained_path", "x", "--enable_skills", "--enable_mining_skills"])

    def test_skill_enabled_run_requires_explicit_pack_or_index(self):
        with self.assertRaisesRegex(ValueError, "explicit --skill_pack or --skill_index"):
            parse_args(["--pretrained_path", "x", "--enable_skills"])
        args = parse_args(
            ["--pretrained_path", "x", "--enable_skills", "--skill_pack", "libero90_legacy"]
        )
        self.assertEqual(args.skill_pack, "libero90_legacy")

    def test_negative_early_stop_rejected(self):
        with self.assertRaises(ValueError):
            parse_args(["--pretrained_path", "x", "--early_stop_first_n_failures", "-1"])

    def test_episode_slice_defaults_to_zero_and_rejects_negative_index(self):
        self.assertEqual(parse_args(["--pretrained_path", "x"]).episode_index_start, 0)
        self.assertEqual(parse_args(["--pretrained_path", "x", "--episode_index_start", "6"]).episode_index_start, 6)
        with self.assertRaises(ValueError):
            parse_args(["--pretrained_path", "x", "--episode_index_start", "-1"])

    def test_early_stop_first_failures_helper(self):
        self.assertFalse(
            should_early_stop_first_failures(completed_episodes=4, successes=0, first_n_failures=5)
        )
        self.assertFalse(
            should_early_stop_first_failures(completed_episodes=5, successes=1, first_n_failures=5)
        )
        self.assertTrue(
            should_early_stop_first_failures(completed_episodes=5, successes=0, first_n_failures=5)
        )


class ExecutorHookTests(unittest.TestCase):
    def test_keep_closed_override(self):
        class Bridge:
            def before_trajectory_step(self, state):
                return {
                    "keep_gripper_closed": True,
                    "gripper_hold_value": state["gripper_close_value"],
                    "skill_id": "hold_then_pick_traj_opens",
                    "backend": "keep_gripper_closed",
                }

        skip, hold, meta = _apply_trajectory_hook(
            Bridge(),
            {"gripper_close_value": 1.0, "label": "Pick(x)"},
            default_hold=-1.0,
        )
        self.assertFalse(skip)
        self.assertEqual(hold, 1.0)
        self.assertTrue(meta["hook_fired"])

    def test_no_bridge_keeps_default(self):
        skip, hold, meta = _apply_trajectory_hook(None, {}, default_hold=-1.0)
        self.assertFalse(skip)
        self.assertEqual(hold, -1.0)
        self.assertEqual(meta, {})


if __name__ == "__main__":
    unittest.main()
