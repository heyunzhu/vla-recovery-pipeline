from __future__ import annotations

import os
import types
import unittest
from unittest import mock

import numpy as np

from experiments.robot.libero.tiptop_repro.libero_panda_frames import quat_wxyz_to_matrix
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
    _canonical_rest_frame,
    _cuboid_from_single_box_part,
    _signed_permutation_matrices,
)

# The cream cheese exactly as it reaches the backend: the TAMPObject pose plus the one
# MuJoCo box geom under it. Thin axis (1.79 cm) is the geom's local x.
CHEESE_OBJ = types.SimpleNamespace(
    pos=[0.6013253889977932, 0.1343836486339569, -0.0030785202980041504],
    quat=[3.783598568072678e-18, -6.390960201729242e-17, -1.085692751949325e-17, -1.0],
)
CHEESE_PART = {
    "size": [0.008936000056564808, 0.02133600041270256, 0.040608000010252],
    "local_pos": [3.725290298461914e-09, 0.0, 0.0],
    "local_quat": [0.7071067811865476, 9.411199260821144e-26, 0.7071067811865475, 2.7352141987770637e-25],
}


class SignedPermutationTests(unittest.TestCase):
    def test_there_are_twenty_four_right_handed_ones(self):
        # 3x3 signed permutations: 6 orderings x 8 sign flips = 48, half right-handed.
        perms = _signed_permutation_matrices()
        self.assertEqual(len(perms), 24)
        for matrix in perms:
            self.assertAlmostEqual(float(np.linalg.det(matrix)), 1.0, places=9)

    def test_they_are_orthonormal(self):
        for matrix in _signed_permutation_matrices():
            np.testing.assert_allclose(matrix @ matrix.T, np.eye(3), atol=1e-12)


class CanonicalRestFrameTests(unittest.TestCase):
    def test_an_already_upright_object_keeps_z_up(self):
        frame = _canonical_rest_frame([0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0])
        self.assertAlmostEqual(float((np.eye(3) @ frame[:3, :3])[2, 2]), 1.0)

    def test_a_pure_yaw_stays_a_pure_yaw(self):
        quat = [np.cos(0.3), 0.0, 0.0, np.sin(0.3)]
        frame = _canonical_rest_frame([0.0, 0.0, 0.0, *quat])
        combined = quat_wxyz_to_matrix(quat) @ frame[:3, :3]
        self.assertAlmostEqual(float(combined[2, 2]), 1.0, places=6)
        np.testing.assert_allclose(combined[:2, 2], [0.0, 0.0], atol=1e-6)

    def test_a_sideways_frame_is_turned_upright(self):
        # 90 degrees about y: local x ends up vertical.
        quat = [np.cos(np.pi / 4), 0.0, np.sin(np.pi / 4), 0.0]
        frame = _canonical_rest_frame([0.0, 0.0, 0.0, *quat])
        combined = quat_wxyz_to_matrix(quat) @ frame[:3, :3]
        self.assertAlmostEqual(float(combined[2, 2]), 1.0, places=6)

    def test_the_cheese_frame_becomes_upright(self):
        rot = quat_wxyz_to_matrix(CHEESE_OBJ.quat)
        frame = _canonical_rest_frame([*CHEESE_OBJ.pos, *CHEESE_OBJ.quat])
        combined = rot @ frame[:3, :3]
        self.assertAlmostEqual(float(combined[2, 2]), 1.0, places=6)
        np.testing.assert_allclose(combined[:2, 2], [0.0, 0.0], atol=1e-6)


class CuboidFromSingleBoxPartTests(unittest.TestCase):
    def test_the_flag_off_path_is_untouched(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CUTAMP_CANONICAL_OBJECT_FRAME", None)
            dims, pose = _cuboid_from_single_box_part(CHEESE_OBJ, CHEESE_PART)
        np.testing.assert_allclose(dims, [0.017872, 0.042672, 0.081216], atol=1e-6)
        np.testing.assert_allclose(pose[:3], CHEESE_OBJ.pos, atol=1e-9)

    def test_canonicalisation_puts_the_thin_axis_on_z(self):
        with mock.patch.dict(os.environ, {"CUTAMP_CANONICAL_OBJECT_FRAME": "1"}):
            dims, pose = _cuboid_from_single_box_part(CHEESE_OBJ, CHEESE_PART)
        self.assertAlmostEqual(dims[2], 0.017872, places=6, msg="thin axis should be local z")
        np.testing.assert_allclose(
            sorted(dims), sorted([0.017872, 0.042672, 0.081216]), atol=1e-5
        )

    def test_the_canonicalised_pose_is_upright(self):
        with mock.patch.dict(os.environ, {"CUTAMP_CANONICAL_OBJECT_FRAME": "1"}):
            _, pose = _cuboid_from_single_box_part(CHEESE_OBJ, CHEESE_PART)
        rot = quat_wxyz_to_matrix(pose[3:7])
        np.testing.assert_allclose(rot[:2, 2], [0.0, 0.0], atol=1e-6)
        self.assertAlmostEqual(float(rot[2, 2]), 1.0, places=6)

    def test_the_object_does_not_move(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CUTAMP_CANONICAL_OBJECT_FRAME", None)
            _, before = _cuboid_from_single_box_part(CHEESE_OBJ, CHEESE_PART)
        with mock.patch.dict(os.environ, {"CUTAMP_CANONICAL_OBJECT_FRAME": "1"}):
            _, after = _cuboid_from_single_box_part(CHEESE_OBJ, CHEESE_PART)
        np.testing.assert_allclose(after[:3], before[:3], atol=1e-9)

    def test_the_described_box_is_physically_the_same(self):
        """Same 8 corners in world space, or the collision geometry would have moved."""
        def corners(dims, pose):
            rot = quat_wxyz_to_matrix(pose[3:7])
            half = np.asarray(dims, dtype=float) / 2.0
            out = set()
            for sx in (-1.0, 1.0):
                for sy in (-1.0, 1.0):
                    for sz in (-1.0, 1.0):
                        point = np.asarray(pose[:3]) + rot @ (half * np.array([sx, sy, sz]))
                        out.add(tuple(np.round(point, 6).tolist()))
            return out

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CUTAMP_CANONICAL_OBJECT_FRAME", None)
            dims_before, pose_before = _cuboid_from_single_box_part(CHEESE_OBJ, CHEESE_PART)
        with mock.patch.dict(os.environ, {"CUTAMP_CANONICAL_OBJECT_FRAME": "1"}):
            dims_after, pose_after = _cuboid_from_single_box_part(CHEESE_OBJ, CHEESE_PART)
        self.assertEqual(corners(dims_after, pose_after), corners(dims_before, pose_before))


if __name__ == "__main__":
    unittest.main()
