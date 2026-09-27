"""The installed grasp profile is top-down in *world* terms, in either object frame.

Why this test exists. Every LIBERO-Goal task04 run passes
``--real_cutamp_grasp_dof 6 --grasp_sampler_profile cream_cheese_flat_box_topdown_deep_v1
--grasp_profile_adapter <pack>/code/grasp_profiles.py``, and
``real_cutamp_backend.py``:func:`_allow_mesh_6dof_grasp_sampling` then monkeypatches
``cutamp.samplers.grasp_6dof_sampler`` (and the copy imported into
``cutamp.particle_initialization``) for the whole ``run_cutamp`` call. cuTAMP's *native*
sampler therefore never runs, and reading it -- or measuring it directly the way
``compare_grasps.py`` did -- says nothing about the grasps the runs get. The native sampler
is separately easy to misread: it hard-codes ``pitch = 0``, takes ``roll`` from
``{±π/4, ±π/3, ±π/2}`` and ``yaw`` from ``{±π/2}``, so it can never emit the
roll = pitch = 0 family, and it ignores ``num_faces`` entirely.

What is asserted here is the property that actually matters and that survives either
labelling of the object's local frame: the grasp frame's z axis is world +z (the tool points
straight down), because the profile derives the vertical axis from the object pose instead
of assuming a fixed local axis. The measured world distribution with the profile installed
is 64/64 top-down with tool z = -1.000, in canonical and non-canonical frames alike; with
cuTAMP's native sampler on the same object it is 0/64.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from experiments.robot.libero.tiptop_repro.grasp_profiles import (
    pose7_rotation_matrix,
    profile_gripper_width,
    registry_from_adapter_paths,
    rot_z,
    sample_grasp_profile,
)

PACK = "libero_goal_task_from_goal_swap_v1_cross_suite_mining_20260914"
PROFILE = "cream_cheese_flat_box_topdown_deep_v1"

# Measured on the task04 problem solved in open_drawer_run_20260926: the cheese as cuTAMP
# registers it with and without CUTAMP_CANONICAL_OBJECT_FRAME.
CANONICAL = {
    "dims": [0.04267, 0.08122, 0.01787],
    "pose": [0.6013, 0.1344, -0.0031, 0.7071, -0.0, 0.0, -0.7071],
    "top_axis": 2,
    "long_axis": 1,
}
UNCANONICAL = {
    "dims": [0.01787, 0.04267, 0.08122],
    "pose": [0.6013, 0.1344, -0.0031, 0.0, 0.7071, -0.0, -0.7071],
    "top_axis": 0,
    "long_axis": 2,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _adapter_path() -> Path:
    return _repo_root() / "skill_packs" / PACK / "code" / "grasp_profiles.py"


def _samples(frame: dict) -> list:
    registry = registry_from_adapter_paths([_adapter_path()])
    return sample_grasp_profile(PROFILE, frame["dims"], rim=False, pose=frame["pose"], registry=registry)


class PackGraspProfileTests(unittest.TestCase):
    def test_adapter_is_the_one_the_task04_launchers_name(self):
        index = _repo_root() / "skill_packs" / PACK / "skills" / "_index.yaml"
        self.assertTrue(_adapter_path().exists(), _adapter_path())
        self.assertTrue(index.exists(), index)
        hint = index.parent / "fail_only/recovery_hint/grasp/grasp_cream_cheese_flat_box_topdown_deep.md"
        self.assertTrue(hint.exists(), hint)
        text = hint.read_text(encoding="utf-8")
        self.assertIn(f"grasp_profile: {PROFILE}", text)
        # The hint is a fail_only draft: skills/_index.yaml loads nothing online, so the
        # profile is in play only because our launchers hard-code its name.
        self.assertIn("online: []", index.read_text(encoding="utf-8"))

    def test_profile_yields_24_distinct_pose_aware_candidates(self):
        for name, frame in (("canonical", CANONICAL), ("uncanonical", UNCANONICAL)):
            with self.subTest(frame=name):
                samples = _samples(frame)
                self.assertEqual(len(samples), 24)
                xyzrpy = np.asarray([sample.xyzrpy() for sample in samples], dtype=np.float64)
                self.assertEqual(len(np.unique(np.round(xyzrpy, 9), axis=0)), 24)
                # 2 depths x 3 long-axis offsets x 4 yaws.
                self.assertEqual(len({round(sample.metadata["depth_from_top"], 9) for sample in samples}), 2)
                self.assertEqual(len({round(sample.metadata["world_yaw"], 9) for sample in samples}), 4)
                self.assertTrue(all(sample.metadata["top_axis"] == frame["top_axis"] for sample in samples))
                self.assertTrue(all(sample.metadata["long_axis"] == frame["long_axis"] for sample in samples))

    def test_grasp_frame_z_is_world_up_in_both_object_frames(self):
        """The invariant the runs depend on -- and the one the native sampler cannot meet."""
        for name, frame in (("canonical", CANONICAL), ("uncanonical", UNCANONICAL)):
            with self.subTest(frame=name):
                world_from_obj = pose7_rotation_matrix(frame["pose"])
                dims = np.asarray(frame["dims"], dtype=np.float64)
                half = 0.5 * dims
                seen_depths, seen_offsets = set(), set()
                for sample in _samples(frame):
                    yaw = float(sample.metadata["world_yaw"])
                    object_from_grasp = world_from_obj.T @ rot_z(yaw)
                    if name == "canonical":
                        # Only unambiguous here: with the thin axis already local z the pack
                        # spells the grasp as a pure yaw about the object's own z, so roll and
                        # pitch are exactly zero -- the family cuTAMP's native sampler cannot
                        # express. In the uncanonical frame the same rotation is spelled at a
                        # gimbal-lock singularity, where matrix_to_xyz_rpy cannot round-trip
                        # the sign of roll/pitch; that is why the check below is done on world
                        # axes instead of on the rpy spelling.
                        self.assertAlmostEqual(float(sample.rpy[0]), 0.0, places=10)
                        self.assertAlmostEqual(float(sample.rpy[1]), 0.0, places=10)
                    world_z = world_from_obj @ object_from_grasp[:, 2]
                    np.testing.assert_allclose(world_z, [0.0, 0.0, 1.0], atol=1e-9)
                    # The grasp origin lies on the object's own vertical axis. Expressed in
                    # world terms -- which is what survives a change of local frame labels --
                    # it is dropped below the object centre by 0.15 or 0.35 of the half
                    # thickness, and shifted along the long axis by 0.08 of its half length.
                    local = np.asarray(sample.xyz, dtype=np.float64)
                    world_offset = world_from_obj @ local
                    self.assertLess(float(world_offset[2]), 0.0)
                    seen_depths.add(round(abs(float(world_offset[2])) / float(half[frame["top_axis"]]), 6))
                    seen_offsets.add(round(float(np.linalg.norm(world_offset[:2])) / float(half[frame["long_axis"]]), 6))
                # depth below the top face: 0.35 or 0.15 of the half thickness
                self.assertEqual(seen_depths, {0.35, 0.15})
                # long-axis shift: centred, or 0.08 of the half length either way
                self.assertEqual(seen_offsets, {0.0, 0.08})

    def test_both_horizontal_extents_appear_as_the_straddle_span(self):
        """Half the yaw choices close across the 81 mm extent, half across the 42.7 mm one.

        Both hands are emitted on purpose (the profile does not know cuTAMP's gripper width),
        so a caller must not assume all 24 candidates are geometrically equivalent.
        """
        samples = _samples(CANONICAL)
        dims = np.asarray(CANONICAL["dims"], dtype=np.float64)
        horizontal = [axis for axis in range(3) if axis != CANONICAL["top_axis"]]
        straddles = set()
        for sample in samples:
            object_from_grasp = pose7_rotation_matrix(CANONICAL["pose"]).T @ rot_z(
                float(sample.metadata["world_yaw"])
            )
            for column in (0, 1):
                axis = object_from_grasp[:, column]
                closing = [index for index in range(3) if abs(float(axis[index])) > 0.5]
                self.assertEqual(len(closing), 1, axis)
                other = [index for index in horizontal if index != closing[0]]
                self.assertEqual(len(other), 1)
                straddles.add(round(float(dims[other[0]]), 6))
        self.assertEqual(straddles, {round(float(dims[0]), 6), round(float(dims[1]), 6)})

    def test_gripper_width_tracks_the_short_horizontal_axis(self):
        dims = np.asarray(CANONICAL["dims"], dtype=np.float64)
        expected = round(2.25 * 0.5 * float(min(dims[0], dims[1])), 6)
        widths = set()
        for frame in (CANONICAL, UNCANONICAL):
            registry = registry_from_adapter_paths([_adapter_path()])
            widths.add(
                round(
                    profile_gripper_width(PROFILE, frame["dims"], pose=frame["pose"], registry=registry),
                    6,
                )
            )
        # 2.25 x the short horizontal half extent, and frame-independent
        self.assertEqual(widths, {expected})


if __name__ == "__main__":
    unittest.main()
