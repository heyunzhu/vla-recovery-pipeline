from __future__ import annotations

import unittest

import numpy as np

from experiments.robot.libero.tiptop_repro.start_state_retreat import (
    _clamp,
    _numerical_gradient,
    joint_limits_of,
    retreat_configuration,
)


class _CudaLike:
    """Stands in for cuTAMP's CUDA joint-limit tensor."""

    def __init__(self, array):
        self._array = np.asarray(array, dtype=float)
        self.detached = False

    def detach(self):
        self.detached = True
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self._array


class _Container:
    def __init__(self, limits):
        self.joint_limits = limits


class JointLimitsTests(unittest.TestCase):
    def test_reads_a_tensor_like_limit_pair_from_the_host(self):
        tensor = _CudaLike([[-1.0, -2.0], [1.0, 2.0]])
        lower, upper = joint_limits_of(_Container(tensor))
        self.assertTrue(tensor.detached, "the tensor has to be moved off the device")
        np.testing.assert_allclose(lower, [-1.0, -2.0])
        np.testing.assert_allclose(upper, [1.0, 2.0])

    def test_reads_a_plain_nested_sequence(self):
        lower, upper = joint_limits_of(_Container([[-1.0, -2.0], [1.0, 2.0]]))
        np.testing.assert_allclose(lower, [-1.0, -2.0])
        np.testing.assert_allclose(upper, [1.0, 2.0])

    def test_missing_or_misshaped_limits_are_not_an_error(self):
        self.assertEqual(joint_limits_of(_Container(None)), (None, None))
        self.assertEqual(joint_limits_of(_Container([1.0, 2.0])), (None, None))
        self.assertEqual(joint_limits_of(object()), (None, None))


def _sphere_well(target, radius, dof=7):
    """Smooth penetration: positive inside a Euclidean ball around ``target``."""

    def penetration(q):
        q = np.asarray(q, dtype=float)
        return max(0.0, radius - float(np.linalg.norm(q - np.asarray(target, dtype=float))))

    return penetration


def _box_well(target, radius, dof=7):
    """Chebyshev penetration: flat inside the ball, so the gradient is zero there."""

    def penetration(q):
        q = np.asarray(q, dtype=float)
        return max(0.0, radius - float(np.max(np.abs(q - np.asarray(target, dtype=float)))))

    return penetration


class RetreatConfigurationTests(unittest.TestCase):
    def test_free_start_is_returned_unchanged(self):
        result = retreat_configuration(lambda q: -0.01, [0.0] * 7)
        self.assertTrue(result["free"])
        self.assertFalse(result["needs_retreat"])
        self.assertEqual(result["iterations"], 0)
        self.assertEqual(result["q"], [0.0] * 7)
        self.assertEqual(result["trace"], [])

    def test_escapes_a_smooth_penetration(self):
        penetration = _sphere_well(target=[0.0] * 7, radius=0.05)
        start = [0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        result = retreat_configuration(penetration, start, step_rad=0.05)
        self.assertTrue(result["free"], result)
        self.assertLessEqual(result["penetration_m"], 0.0)
        self.assertGreaterEqual(float(np.linalg.norm(result["q"])), 0.05 - 1e-6)

    def test_escapes_when_the_gradient_is_flat(self):
        # Central differences are all zero inside a Chebyshev ball, so this only
        # succeeds through the single-joint fallback.
        penetration = _box_well(target=[0.0] * 7, radius=0.05)
        result = retreat_configuration(penetration, [0.0] * 7, step_rad=0.05)
        self.assertTrue(result["free"], result)
        self.assertGreaterEqual(float(np.max(np.abs(result["q"]))), 0.05 - 1e-6)

    def test_stays_inside_joint_limits(self):
        penetration = _sphere_well(target=[0.0] * 7, radius=0.5)
        lower = [-0.01] * 7
        upper = [0.01] * 7
        result = retreat_configuration(penetration, [0.0] * 7, lower=lower, upper=upper, step_rad=0.05)
        self.assertFalse(result["free"], "no escape exists inside these limits")
        q = np.asarray(result["q"], dtype=float)
        self.assertTrue(np.all(q >= np.asarray(lower) - 1e-12))
        self.assertTrue(np.all(q <= np.asarray(upper) + 1e-12))

    def test_trace_is_monotone_and_bounded(self):
        penetration = _sphere_well(target=[0.0] * 7, radius=0.2)
        result = retreat_configuration(penetration, [0.001] * 7, step_rad=0.02, max_iters=5)
        self.assertLessEqual(len(result["trace"]), 5)
        self.assertEqual(result["iterations"], len(result["trace"]))
        values = [row["penetration_m"] for row in result["trace"]]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_gives_up_when_nothing_improves(self):
        calls = {"n": 0}

        def never_improves(q):
            calls["n"] += 1
            return 1.0

        result = retreat_configuration(never_improves, [0.0] * 7, max_iters=30)
        self.assertFalse(result["free"])
        self.assertEqual(result["penetration_m"], 1.0)
        self.assertLessEqual(result["iterations"], 1)
        self.assertLess(calls["n"], 30 * 20)

    def test_reports_the_start_penetration(self):
        penetration = _sphere_well(target=[0.0] * 7, radius=0.05)
        result = retreat_configuration(penetration, [0.0] * 7, step_rad=0.05)
        self.assertAlmostEqual(result["initial_penetration_m"], 0.05, places=9)
        self.assertTrue(result["needs_retreat"])


class GradientTests(unittest.TestCase):
    def test_gradient_points_uphill(self):
        def penetration(q):
            q = np.asarray(q, dtype=float)
            return float((q[0] - 1.0) ** 2 + 2.0 * (q[1] + 0.5) ** 2)

        gradient = _numerical_gradient(penetration, np.zeros(2), None, None, 0.01)
        # d/dq0 = 2 (q0 - 1) = -2 at the origin; d/dq1 = 4 (q1 + 0.5) = 2.
        self.assertAlmostEqual(gradient[0], -2.0, places=4)
        self.assertAlmostEqual(gradient[1], 2.0, places=4)

    def test_clamp_leaves_values_alone_without_limits(self):
        q = np.array([5.0, -5.0])
        np.testing.assert_allclose(_clamp(q, None, None), q)


if __name__ == "__main__":
    unittest.main()
