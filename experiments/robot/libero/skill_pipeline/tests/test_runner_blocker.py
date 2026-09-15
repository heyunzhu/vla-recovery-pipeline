from __future__ import annotations

import collections
import unittest

import numpy as np

from experiments.robot.libero.skill_pipeline.runner import (
    _articulated_blocker_contact_summary,
    _articulated_blocker_features,
    _task_allows_drawer_interaction,
)


def _qstate(**kwargs):
    base = {
        "ee_xyz": [0.0, 0.0, 0.50],
        "gripper_aperture": 0.04,
        "target_name": "akita_black_bowl_1_main",
        "target_xyz": [0.30, 0.0, 0.42],
        "target_ee_distance_m": 0.30,
        "holding_status": "handempty_or_unconfirmed",
        "articulated_blocker_positions": {
            "white_cabinet_1_main": [0.02, 0.0, 0.48],
        },
        "articulated_blocker_joint_state_known": True,
        "articulated_blocker_open_joint_names": ["white_cabinet_1_top_drawer_joint"],
        "articulated_blocker_contact": False,
        "articulated_blocker_contact_name": None,
        "articulated_blocker_contact_robot_name": None,
        "articulated_blocker_contact_count": 0,
        "articulated_blocker_contact_min_distance_m": None,
    }
    base.update(kwargs)
    return base


class _Scene:
    def __init__(self, contacts):
        self.contacts = contacts


class RunnerBlockerTests(unittest.TestCase):
    def test_drawer_interaction_language_is_exempt(self):
        self.assertTrue(_task_allows_drawer_interaction("open the top drawer of the cabinet"))
        self.assertTrue(_task_allows_drawer_interaction("put the ketchup in the top drawer of the cabinet"))
        self.assertFalse(_task_allows_drawer_interaction("put the black bowl on top of the cabinet"))
        self.assertFalse(_task_allows_drawer_interaction("put the black bowl on the plate"))

    def test_open_drawer_blocker_status_for_open_hand_bowl_pick(self):
        action_chunk = np.zeros((5, 7), dtype=np.float32)
        contact_history = collections.deque([True, True], maxlen=3)
        features = _articulated_blocker_features(
            qstate=_qstate(
                articulated_blocker_contact=True,
                articulated_blocker_contact_name="white_cabinet_1_top_level",
                articulated_blocker_contact_robot_name="robot0_rightfinger_collision",
                articulated_blocker_contact_count=1,
                articulated_blocker_contact_min_distance_m=-0.001,
            ),
            action_chunk=action_chunk,
            action_chunk_len=5,
            task_description="put the black bowl on top of the cabinet",
            contact_history=contact_history,
        )

        self.assertEqual(features["vla_articulated_blocker_status"], "blocked_open_drawer_before_pick")
        self.assertEqual(features["path_articulated_blocker_name"], "white_cabinet_1_main")
        self.assertEqual(features["articulated_blocker_contact_persist_queries"], 3)
        self.assertLess(features["path_articulated_blocker_min_xy_distance_m"], 0.13)
        self.assertGreater(features["blocker_target_future_min_xy_distance_m"], 0.085)

    def test_default_open_cabinet_risk_without_contact_does_not_trigger(self):
        action_chunk = np.zeros((5, 7), dtype=np.float32)
        features = _articulated_blocker_features(
            qstate=_qstate(
                ee_xyz=[0.0, 0.0, 0.50],
                target_xyz=[0.36, 0.12, 0.42],
                target_ee_distance_m=0.38,
                articulated_blocker_positions={
                    "white_cabinet_1_main": [0.28, 0.0, 0.48],
                },
                articulated_blocker_open_joint_names=["white_cabinet_1_top_level"],
            ),
            action_chunk=action_chunk,
            action_chunk_len=5,
            task_description="put the black bowl on the plate",
        )

        self.assertEqual(features["vla_articulated_blocker_status"], "clear")
        self.assertGreater(features["path_articulated_blocker_min_xy_distance_m"], 0.13)

    def test_requires_three_consecutive_blocker_contact_queries(self):
        action_chunk = np.zeros((5, 7), dtype=np.float32)
        contact_history: collections.deque = collections.deque(maxlen=3)
        qstate = _qstate(
            articulated_blocker_contact=True,
            articulated_blocker_contact_name="white_cabinet_1_top_level",
            articulated_blocker_contact_robot_name="robot0_leftfinger_collision",
            articulated_blocker_contact_count=1,
            articulated_blocker_contact_min_distance_m=0.0,
        )

        first = _articulated_blocker_features(
            qstate=qstate,
            action_chunk=action_chunk,
            action_chunk_len=5,
            task_description="put the black bowl on the plate",
            contact_history=contact_history,
        )
        second = _articulated_blocker_features(
            qstate=qstate,
            action_chunk=action_chunk,
            action_chunk_len=5,
            task_description="put the black bowl on the plate",
            contact_history=contact_history,
        )
        third = _articulated_blocker_features(
            qstate=qstate,
            action_chunk=action_chunk,
            action_chunk_len=5,
            task_description="put the black bowl on the plate",
            contact_history=contact_history,
        )

        self.assertEqual(first["vla_articulated_blocker_status"], "clear")
        self.assertEqual(first["articulated_blocker_contact_persist_queries"], 1)
        self.assertEqual(second["vla_articulated_blocker_status"], "clear")
        self.assertEqual(second["articulated_blocker_contact_persist_queries"], 2)
        self.assertEqual(third["vla_articulated_blocker_status"], "blocked_open_drawer_before_pick")
        self.assertEqual(third["articulated_blocker_contact_persist_queries"], 3)

    def test_contact_summary_only_counts_gripper_to_articulated_blocker(self):
        summary = _articulated_blocker_contact_summary(
            _Scene(
                [
                    {
                        "geom1_name": "robot0_leftfinger_collision",
                        "geom1_body_name": "robot0_leftfinger",
                        "object1": None,
                        "geom2_name": "white_cabinet_1_top_level_collision",
                        "geom2_body_name": "white_cabinet_1_top_level",
                        "object2": "white_cabinet_1_main",
                        "distance": -0.0005,
                    },
                    {
                        "geom1_name": "robot0_rightfinger_collision",
                        "geom1_body_name": "robot0_rightfinger",
                        "object1": None,
                        "geom2_name": "white_cabinet_1_top_level_collision",
                        "geom2_body_name": "white_cabinet_1_top_level",
                        "object2": "white_cabinet_1_main",
                        "distance": 0.010,
                    },
                ]
            )
        )

        self.assertTrue(summary["articulated_blocker_contact"])
        self.assertEqual(summary["articulated_blocker_contact_name"], "white_cabinet_1_main")
        self.assertEqual(summary["articulated_blocker_contact_count"], 1)
        self.assertLess(summary["articulated_blocker_contact_min_distance_m"], 0.0)

    def test_true_drawer_tasks_and_closed_drawers_do_not_trigger(self):
        action_chunk = np.zeros((5, 7), dtype=np.float32)
        drawer_task = _articulated_blocker_features(
            qstate=_qstate(),
            action_chunk=action_chunk,
            action_chunk_len=5,
            task_description="put the ketchup in the top drawer of the cabinet",
        )
        self.assertEqual(drawer_task["vla_articulated_blocker_status"], "task_allows_drawer_interaction")

        closed_drawer = _articulated_blocker_features(
            qstate=_qstate(articulated_blocker_open_joint_names=[]),
            action_chunk=action_chunk,
            action_chunk_len=5,
            task_description="put the black bowl on the plate",
        )
        self.assertEqual(closed_drawer["vla_articulated_blocker_status"], "drawer_not_open")

        unknown_open = _articulated_blocker_features(
            qstate=_qstate(
                articulated_blocker_joint_state_known=False,
                articulated_blocker_open_joint_names=[],
            ),
            action_chunk=action_chunk,
            action_chunk_len=5,
            task_description="put the black bowl on the plate",
        )
        self.assertEqual(unknown_open["vla_articulated_blocker_status"], "drawer_not_open")


if __name__ == "__main__":
    unittest.main()
