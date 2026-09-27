from __future__ import annotations

import unittest

import numpy as np

from scripts.recovery.skill_pipeline.place_trajectory_probe import (
    joint_space_path,
    worst_per_phase,
)


class JointSpacePathTests(unittest.TestCase):
    def test_both_endpoints_are_included(self):
        path = joint_space_path([0.0, 0.0], [1.0, 2.0], 5)
        np.testing.assert_allclose(path[0], [0.0, 0.0])
        np.testing.assert_allclose(path[-1], [1.0, 2.0])

    def test_it_is_evenly_spaced(self):
        path = joint_space_path([0.0], [1.0], 5)
        np.testing.assert_allclose([float(p[0]) for p in path], [0.0, 0.25, 0.5, 0.75, 1.0])

    def test_a_short_request_still_yields_two_points(self):
        self.assertEqual(len(joint_space_path([0.0], [1.0], 0)), 2)
        self.assertEqual(len(joint_space_path([0.0], [1.0], 1)), 2)

    def test_it_handles_a_seven_dof_arm(self):
        start = [0.0] * 7
        target = [0.1 * index for index in range(7)]
        path = joint_space_path(start, target, 9)
        self.assertEqual(len(path), 9)
        self.assertEqual(path[4].shape, (7,))

    def test_a_shape_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "shape mismatch"):
            joint_space_path([0.0, 0.0], [1.0], 3)


class WorstPerPhaseTests(unittest.TestCase):
    def test_it_keeps_the_deepest_sample_of_each_phase(self):
        rows = [
            {"phase": "start", "worst_depth_m": 0.01, "worst_obstacle": "cabinet"},
            {"phase": "transit", "worst_depth_m": 0.02, "worst_obstacle": "cabinet"},
            {"phase": "transit", "worst_depth_m": 0.03, "worst_obstacle": "stove"},
            {"phase": "goal", "worst_depth_m": -0.01, "worst_obstacle": "cabinet"},
        ]
        phases = worst_per_phase(rows)
        self.assertEqual(phases["transit"]["samples"], 2)
        self.assertAlmostEqual(phases["transit"]["worst_depth_m"], 0.03)
        self.assertEqual(phases["transit"]["worst_obstacle"], "stove")
        self.assertAlmostEqual(phases["goal"]["worst_depth_m"], -0.01)

    def test_an_empty_sweep_folds_to_nothing(self):
        self.assertEqual(worst_per_phase([]), {})


if __name__ == "__main__":
    unittest.main()
