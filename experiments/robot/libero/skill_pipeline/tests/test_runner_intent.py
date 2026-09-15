from __future__ import annotations

import collections
import types
import unittest

import numpy as np

from experiments.robot.libero.skill_pipeline.runner import (
    _target_orientation_features,
    _trajectory_intent_features,
    _wrong_object_progress_features,
)


def _qstate() -> dict:
    return {
        "ee_xyz": [0.0, 0.0, 0.3],
        "target_name": "milk_1_main",
        "vla_pick_target_status": "unknown",
        "pickable_positions": {
            "milk_1_main": [0.30, 0.0, 0.04],
            "alphabet_soup_1_main": [0.08, 0.0, 0.04],
        },
    }


class RunnerIntentFeatureTests(unittest.TestCase):
    def test_carton_orientation_uses_libero_hope_local_y_axis(self):
        scene = types.SimpleNamespace(
            objects={
                "milk_1_main": types.SimpleNamespace(quat=[0.5, 0.5, 0.5, 0.5]),
                "fallen_milk_1_main": types.SimpleNamespace(quat=[1.0, 0.0, 0.0, 0.0]),
            }
        )

        upright = _target_orientation_features(scene, "milk_1_main")
        fallen = _target_orientation_features(scene, "fallen_milk_1_main")

        self.assertEqual(upright["target_orientation"], "upright")
        self.assertAlmostEqual(upright["target_upright_axis_alignment"], 1.0)
        self.assertEqual(fallen["target_orientation"], "fallen")
        self.assertAlmostEqual(fallen["target_upright_axis_alignment"], 0.0)

    def test_wrong_object_intent_requires_persistence_without_motion(self):
        history = collections.deque(maxlen=4)
        actions = np.array([[0.02, 0.0, 0.0]] * 5, dtype=np.float32)
        first = _trajectory_intent_features(
            qstate=_qstate(),
            action_chunk=actions,
            action_chunk_len=5,
            previous_positions=None,
            baseline_positions=_qstate()["pickable_positions"],
            intent_history=history,
        )
        self.assertEqual(first["intent_object_name"], "alphabet_soup_1_main")
        self.assertEqual(first["wrong_object_intent_persist_queries"], 1)
        self.assertEqual(first["vla_pick_target_status"], "unknown")

        second = _trajectory_intent_features(
            qstate=_qstate(),
            action_chunk=actions,
            action_chunk_len=5,
            previous_positions=_qstate()["pickable_positions"],
            baseline_positions=_qstate()["pickable_positions"],
            intent_history=history,
        )
        self.assertEqual(second["wrong_object_intent_persist_queries"], 2)
        self.assertEqual(second["vla_pick_target_status"], "non_target_intent")

    def test_wrong_object_motion_boost_still_requires_trajectory_intent(self):
        history = collections.deque(maxlen=4)
        actions = np.array([[0.02, 0.0, 0.0]] * 5, dtype=np.float32)
        baseline = _qstate()["pickable_positions"]
        current = _qstate()
        current["pickable_positions"] = {
            "milk_1_main": [0.30, 0.0, 0.04],
            "alphabet_soup_1_main": [0.10, 0.0, 0.04],
        }
        boosted = _trajectory_intent_features(
            qstate=current,
            action_chunk=actions,
            action_chunk_len=5,
            previous_positions=baseline,
            baseline_positions=baseline,
            intent_history=history,
        )
        self.assertEqual(boosted["vla_pick_target_status"], "non_target_intent_with_motion")

        off_path = _qstate()
        off_path["pickable_positions"] = current["pickable_positions"]
        no_intent = _trajectory_intent_features(
            qstate=off_path,
            action_chunk=np.array([[0.0, 0.04, 0.0]] * 5, dtype=np.float32),
            action_chunk_len=5,
            previous_positions=baseline,
            baseline_positions=baseline,
            intent_history=collections.deque(maxlen=4),
        )
        self.assertEqual(no_intent["vla_pick_target_status"], "unknown")

    def test_wrong_object_progress_detects_transported_non_target(self):
        baseline = {
            "tomato_sauce_1_main": [0.10, -0.20, 0.04],
            "alphabet_soup_1_main": [-0.20, -0.10, 0.04],
        }
        qstate = {
            "ee_xyz": [0.06, 0.05, 0.20],
            "target_name": "tomato_sauce_1_main",
            "goal_xyz": [0.08, 0.06, 0.04],
            "holding_object": None,
            "intent_object_name": "alphabet_soup_1_main",
            "intent_object_is_target": False,
            "pickable_positions": {
                "tomato_sauce_1_main": [0.10, -0.20, 0.04],
                "alphabet_soup_1_main": [0.07, 0.05, 0.04],
            },
        }

        features = _wrong_object_progress_features(
            qstate=qstate,
            previous_positions=baseline,
            baseline_positions=baseline,
        )

        self.assertEqual(features["wrong_progress_object_name"], "alphabet_soup_1_main")
        self.assertTrue(features["wrong_progress_target_static"])
        self.assertGreater(features["wrong_progress_object_total_motion_m"], 0.25)
        self.assertLess(features["wrong_progress_object_goal_xy_distance_m"], 0.02)
        self.assertEqual(features["vla_wrong_object_progress_status"], "wrong_object_at_goal")

    def test_wrong_object_progress_ignores_when_target_moved(self):
        baseline = {
            "tomato_sauce_1_main": [0.10, -0.20, 0.04],
            "alphabet_soup_1_main": [-0.20, -0.10, 0.04],
        }
        qstate = {
            "ee_xyz": [0.06, 0.05, 0.20],
            "target_name": "tomato_sauce_1_main",
            "goal_xyz": [0.08, 0.06, 0.04],
            "holding_object": None,
            "intent_object_name": "alphabet_soup_1_main",
            "intent_object_is_target": False,
            "pickable_positions": {
                "tomato_sauce_1_main": [0.18, -0.12, 0.04],
                "alphabet_soup_1_main": [0.07, 0.05, 0.04],
            },
        }

        features = _wrong_object_progress_features(
            qstate=qstate,
            previous_positions=baseline,
            baseline_positions=baseline,
        )

        self.assertFalse(features["wrong_progress_target_static"])
        self.assertEqual(features["vla_wrong_object_progress_status"], "no_wrong_progress")


if __name__ == "__main__":
    unittest.main()
