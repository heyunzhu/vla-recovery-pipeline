from __future__ import annotations

import importlib.util
import math
import pathlib
import sys
import unittest

import numpy as np

def _repo_root() -> pathlib.Path:
    for parent in pathlib.Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("repository root not found")


REPO_ROOT = _repo_root()
PROBE_PATH = REPO_ROOT / "scripts" / "recovery" / "skill_pipeline" / "collision_attribution_probe.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("collision_attribution_probe", PROBE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()
IDENTITY = [1.0, 0.0, 0.0, 0.0]
YAW_90 = [math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4)]


class SphereObbPenetrationTests(unittest.TestCase):
    def test_identity_quaternion_is_identity(self):
        np.testing.assert_allclose(probe.quat_wxyz_to_matrix(IDENTITY), np.eye(3), atol=1e-12)

    def test_yaw_90_maps_x_to_y(self):
        rotation = probe.quat_wxyz_to_matrix(YAW_90)
        np.testing.assert_allclose(rotation @ np.array([1.0, 0.0, 0.0]), [0.0, 1.0, 0.0], atol=1e-12)

    def test_sphere_deep_inside_reports_radius_plus_depth(self):
        # Centre of a 0.2 m cube: interior clearance is 0.1 m, so penetration is r + 0.1.
        depth = probe.sphere_obb_penetration([0.0, 0.0, 0.0], 0.02, [0.0, 0.0, 0.0], IDENTITY, [0.1, 0.1, 0.1])
        self.assertAlmostEqual(depth, 0.12, places=9)

    def test_sphere_far_outside_reports_negative_clearance(self):
        depth = probe.sphere_obb_penetration([0.0, 0.0, 0.15], 0.02, [0.0, 0.0, 0.0], IDENTITY, [0.1, 0.1, 0.1])
        self.assertAlmostEqual(depth, -0.03, places=9)

    def test_sphere_centred_on_a_face_reports_the_radius(self):
        depth = probe.sphere_obb_penetration([0.0, 0.0, 0.1], 0.02, [0.0, 0.0, 0.0], IDENTITY, [0.1, 0.1, 0.1])
        self.assertAlmostEqual(depth, 0.02, places=9)

    def test_rotation_swaps_which_half_extent_bounds_the_sphere(self):
        # Yaw-90 box: its local x runs along world y and vice versa. A sphere offset
        # along world x is therefore bounded by the local y half extent (0.02).
        along_world_x = probe.sphere_obb_penetration([0.05, 0.0, 0.0], 0.05, [0.0, 0.0, 0.0], YAW_90, [0.1, 0.02, 0.05])
        self.assertAlmostEqual(along_world_x, 0.05 - (0.05 - 0.02), places=9)
        # And one offset along world y is bounded by the local x half extent (0.1),
        # i.e. it is inside the box.
        along_world_y = probe.sphere_obb_penetration([0.0, 0.05, 0.0], 0.05, [0.0, 0.0, 0.0], YAW_90, [0.1, 0.02, 0.05])
        self.assertAlmostEqual(along_world_y, 0.07, places=9)

    def test_translation_is_respected(self):
        # Box spans z in [3.2, 3.4]; the sphere centre sits 0.2 m below it.
        depth = probe.sphere_obb_penetration([1.0, 2.0, 3.0], 0.02, [1.0, 2.0, 3.3], IDENTITY, [0.1, 0.1, 0.1])
        self.assertAlmostEqual(depth, -(0.2 - 0.02), places=9)

    def test_worst_penetration_picks_the_deepest_sphere(self):
        spheres = np.array(
            [
                [0.0, 0.0, 0.30, 0.02],
                [0.0, 0.0, 0.05, 0.02],
                [0.0, 0.0, 0.20, 0.02],
            ]
        )
        depth, index = probe.worst_penetration(spheres, [0.0, 0.0, 0.0], IDENTITY, [0.1, 0.1, 0.1])
        self.assertEqual(index, 1)
        self.assertAlmostEqual(depth, 0.02 - (0.05 - 0.1), places=9)

    def test_empty_sphere_set_is_not_a_collision(self):
        depth, index = probe.worst_penetration(np.zeros((0, 4)), [0.0, 0.0, 0.0], IDENTITY, [0.1, 0.1, 0.1])
        self.assertEqual(index, -1)
        self.assertEqual(depth, 0.0)


class RankingTests(unittest.TestCase):
    def _boxes(self):
        return [
            {"name": "far", "center": [0.0, 0.0, 1.0], "quat": IDENTITY, "half_extents": [0.05, 0.05, 0.05]},
            {"name": "touching", "center": [0.0, 0.0, 0.12], "quat": IDENTITY, "half_extents": [0.05, 0.05, 0.05]},
            {"name": "deep", "center": [0.0, 0.0, 0.0], "quat": IDENTITY, "half_extents": [0.05, 0.05, 0.05]},
        ]

    def test_ranked_worst_first_with_sphere_index(self):
        spheres = np.array([[0.0, 0.0, 0.0, 0.01], [0.0, 0.0, 0.10, 0.01]])
        ranked = probe.rank_obstacles(spheres, self._boxes())
        self.assertEqual([row["name"] for row in ranked], ["deep", "touching", "far"])
        self.assertGreater(ranked[0]["depth_m"], 0.0)
        self.assertLess(ranked[-1]["depth_m"], 0.0)
        self.assertEqual(ranked[0]["sphere_index"], 0)

    def test_ranked_reports_the_deepest_sphere_per_obstacle(self):
        spheres = np.array([[0.0, 0.0, 0.0, 0.01], [0.0, 0.0, 0.10, 0.01]])
        ranked = probe.rank_obstacles(spheres, self._boxes())
        touching = next(row for row in ranked if row["name"] == "touching")
        # The second sphere sits on the touching box's face, so it is the deeper one.
        self.assertEqual(touching["sphere_index"], 1)


if __name__ == "__main__":
    unittest.main()
