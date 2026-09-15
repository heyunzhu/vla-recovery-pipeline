from __future__ import annotations

import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.coordinator import check_draft
from experiments.robot.libero.skill_pipeline.schema import load_skill, spec_from_mapping
from experiments.robot.libero.skill_pipeline.validate import (
    FAIL_RECALL_MIN,
    SameInitMetrics,
    TriggerMetrics,
    admission_ok,
    compare_same_init,
    evaluate_heldout_triggers,
    iter_fire_indices,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hold_then_pick_traj_opens.md"


def _fail_episode():
    return {
        "meta": {"success": False, "task_id_1based": 56, "episode_idx": 1, "seed": 7},
        "queries": [],
        "recovery": [
            {"kind": "lift_probe", "object_followed": True, "aperture": 0.03, "label": "close"},
            {
                "kind": "trajectory",
                "label": "Pick(alphabet_soup)",
                "aperture": 0.03,
                "gripper_hold_value": -1.0,
            },
        ],
    }


def _success_episode():
    return {
        "meta": {"success": True, "task_id_1based": 56, "episode_idx": 0, "seed": 7},
        "queries": [],
        "recovery": [],
    }


class ValidateTests(unittest.TestCase):
    def test_heldout_recall_and_success_fp(self):
        spec = load_skill(FIXTURE)
        metrics = evaluate_heldout_triggers(spec, [_fail_episode(), _success_episode()])
        self.assertGreaterEqual(metrics.fail_recall, FAIL_RECALL_MIN)
        self.assertEqual(metrics.n_success_fire, 0)
        self.assertTrue(admission_ok(metrics, same_init_improved=True, success_regressed=False))

    def test_same_init_regression_blocks_admission(self):
        off = [{"meta": {"success": True, "task_id_1based": 56, "episode_idx": 0, "seed": 1}}]
        on = [{"meta": {"success": False, "task_id_1based": 56, "episode_idx": 0, "seed": 1}}]
        same = compare_same_init(off, on)
        self.assertIsInstance(same, SameInitMetrics)
        self.assertEqual(same.n_regressed, 1)
        metrics = TriggerMetrics(n_fail=1, n_fail_hit=1, n_success=1, n_success_fire=0)
        self.assertFalse(admission_ok(metrics, same_init_improved=False, success_regressed=True))

    def test_coordinator_schema_only_not_online(self):
        spec = load_skill(FIXTURE)
        report = check_draft(spec)
        self.assertTrue(report.ok)
        self.assertFalse(report.online_ready)

    def test_writing_episodes_need_heldout(self):
        spec = load_skill(FIXTURE)
        spec.evidence["episodes"] = ["ep00"]
        report = check_draft(spec, writing_episodes=["ep00"])
        self.assertFalse(report.ok)
        self.assertEqual(report.library, "pair")

    def test_fail_only_writing_episodes_are_draft_ok(self):
        spec = load_skill(FIXTURE)
        spec.track = "fail_only"
        spec.backend = "cutamp_recover"
        spec.evidence["episodes"] = ["ep00"]
        report = check_draft(spec, writing_episodes=["ep00"])
        self.assertTrue(report.ok)
        self.assertFalse(report.online_ready)
        self.assertEqual(report.library, "fail_only")
        self.assertTrue(any("fail_only" in item for item in report.warnings))

    def test_query_trigger_state_keeps_task_and_blocker_context(self):
        spec = spec_from_mapping(
            {
                "id": "drawer_blocked_open_hand",
                "kind": "repair",
                "track": "fail_only",
                "hook": "after_pi0_query",
                "priority": 50,
                "backend": "cutamp_recover",
                "trigger": {
                    "all": [
                        {"aperture_gt": 0.025},
                        {"holding_status_is": "handempty_or_unconfirmed"},
                        {"nearest_pickable_is_target": True},
                        {"target_future_min_xy_distance_lt": 0.055},
                        {"vla_articulated_blocker_status_is": "blocked_open_drawer_before_pick"},
                        {"ee_stalled": {"window": 3, "max_disp_m": 0.020}},
                    ]
                },
            }
        )
        episode = {
            "meta": {"success": False, "task_id_1based": 30, "episode_idx": 1, "seed": 90},
            "queries": [
                {
                    "ee_xyz": [0.0, 0.0, 0.4],
                    "gripper_aperture": 0.039,
                    "holding_status": "handempty_or_unconfirmed",
                    "nearest_pickable_is_target": True,
                    "target_future_min_xy_distance_m": 0.04,
                    "vla_articulated_blocker_status": "blocked_open_drawer_before_pick",
                },
                {
                    "ee_xyz": [0.004, 0.0, 0.4],
                    "gripper_aperture": 0.039,
                    "holding_status": "handempty_or_unconfirmed",
                    "nearest_pickable_is_target": True,
                    "target_future_min_xy_distance_m": 0.04,
                    "vla_articulated_blocker_status": "blocked_open_drawer_before_pick",
                },
                {
                    "ee_xyz": [0.006, 0.0, 0.4],
                    "gripper_aperture": 0.039,
                    "holding_status": "handempty_or_unconfirmed",
                    "nearest_pickable_is_target": True,
                    "target_future_min_xy_distance_m": 0.04,
                    "vla_articulated_blocker_status": "blocked_open_drawer_before_pick",
                },
            ],
        }
        self.assertEqual(iter_fire_indices(spec, episode), [2])


if __name__ == "__main__":
    unittest.main()
