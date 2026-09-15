from __future__ import annotations

import math
import unittest
from pathlib import Path

from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
    RealCuTAMPBackendConfig,
    _config_with_recovery_hints,
    _grasp_6dof_xyzrpy_for_profile as _backend_grasp_6dof_xyzrpy_for_profile,
    _normalize_grasp_sampler_profile as _backend_normalize_grasp_sampler_profile,
    _place_yaw_policies_by_surface,
    _thin_horizontal_world_x_yaws,
    _topdown_6dof_xyzrpy,
)
from experiments.robot.libero.tiptop_repro.grasp_profiles import (
    load_grasp_profile_registry,
    profile_gripper_width as _core_profile_gripper_width,
    pose7_rotation_matrix,
    sample_grasp_profile as _core_sample_grasp_profile,
    sample_grasp_profile_xyzrpy as _core_sample_grasp_profile_xyzrpy,
)
from experiments.robot.libero.tiptop_repro.libero_tiptop_executor import client_config_from_recovery_hints
from experiments.robot.libero.skill_pipeline.skill_pack import resolve_skill_pack


REPO_ROOT = Path(__file__).resolve().parents[5]
LIBERO90_GRASP_REGISTRY = load_grasp_profile_registry(
    resolve_skill_pack("libero90_legacy", repo=REPO_ROOT).grasp_profile_adapter
)


def _normalize_grasp_sampler_profile(value):
    return _backend_normalize_grasp_sampler_profile(value, registry=LIBERO90_GRASP_REGISTRY)


def _grasp_6dof_xyzrpy_for_profile(profile, dims, *, rim, pose=None):
    return _backend_grasp_6dof_xyzrpy_for_profile(
        profile,
        dims,
        rim=rim,
        pose=pose,
        registry=LIBERO90_GRASP_REGISTRY,
    )


def sample_grasp_profile(profile, dims, *, rim, pose=None):
    return _core_sample_grasp_profile(profile, dims, rim=rim, pose=pose, registry=LIBERO90_GRASP_REGISTRY)


def sample_grasp_profile_xyzrpy(profile, dims, *, rim, pose=None):
    return _core_sample_grasp_profile_xyzrpy(profile, dims, rim=rim, pose=pose, registry=LIBERO90_GRASP_REGISTRY)


def profile_gripper_width(profile, dims, *, rim=False, radius=None, pose=None):
    return _core_profile_gripper_width(
        profile,
        dims,
        rim=rim,
        radius=radius,
        pose=pose,
        registry=LIBERO90_GRASP_REGISTRY,
    )


class RimGraspSampleTests(unittest.TestCase):
    def test_rim_samples_reach_below_the_lip(self):
        dims = [0.15, 0.15, 0.05]
        half_height = 0.025
        zs = {round(sample[2], 4) for sample in _topdown_6dof_xyzrpy(dims, rim=True)}
        self.assertTrue(zs)
        self.assertTrue(all(half_height - z >= 0.017 for z in zs))

    def test_rim_xy_is_inward_of_the_outer_aabb(self):
        dims = [0.15, 0.15, 0.05]
        half_x = 0.075
        xs = {round(abs(sample[0]), 4) for sample in _topdown_6dof_xyzrpy(dims, rim=True) if abs(sample[0]) > 1e-6}
        self.assertTrue(xs)
        self.assertTrue(all(x <= 0.86 * half_x + 1e-6 for x in xs))
        self.assertTrue(any(x <= 0.78 * half_x + 1e-6 for x in xs))

    def test_sampler_profile_aliases_keep_current_topdown_behavior(self):
        dims = [0.15, 0.15, 0.05]
        self.assertEqual(_normalize_grasp_sampler_profile("default"), "libero_topdown")
        self.assertEqual(
            _grasp_6dof_xyzrpy_for_profile("default", dims, rim=True),
            _topdown_6dof_xyzrpy(dims, rim=True),
        )

    def test_backend_wrapper_uses_shared_profile_sampler(self):
        dims = [0.0638, 0.0687, 0.0804]
        pose = [0.35, 0.02, 0.04, 1.0, 0.0, 0.0, 0.0]
        self.assertEqual(
            _grasp_6dof_xyzrpy_for_profile("can_body_lower_side_v1", dims, rim=False, pose=pose),
            sample_grasp_profile_xyzrpy("can_body_lower_side_v1", dims, rim=False, pose=pose),
        )

    def test_recovery_hints_override_backend_config_without_mutating_it(self):
        cfg = RealCuTAMPBackendConfig(grasp_sampler_profile="libero_topdown")
        updated = _config_with_recovery_hints(cfg, {"grasp_profile": "native"})
        self.assertEqual(updated.grasp_sampler_profile, "native")
        self.assertEqual(cfg.grasp_sampler_profile, "libero_topdown")

    def test_unknown_sampler_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            _normalize_grasp_sampler_profile("not_a_profile")

    def test_bowl_rim_direction_profiles_are_budget_sized_and_off_center(self):
        dims = [0.15, 0.15, 0.05]
        for profile in (
            "bowl_rim_radial_topdown_v1",
            "bowl_rim_tangent_topdown_v1",
            "bowl_rim_cardinal_mixed_topdown_v1",
            "bowl_rim_diagonal_mixed_topdown_v1",
        ):
            samples = _grasp_6dof_xyzrpy_for_profile(profile, dims, rim=True)
            self.assertEqual(len(samples), 64)
            self.assertTrue(all(abs(sample[0]) > 1e-6 or abs(sample[1]) > 1e-6 for sample in samples))
            self.assertTrue(all(sample[2] <= 0.025 - 0.021 for sample in samples))

    def test_open_drawer_bowl_profile_keeps_world_y_away_side_first(self):
        dims = [0.1073792, 0.1046324, 0.0654656]
        pose = [0.7101521, -0.0479371, -0.0086468, 0.6881229, 0.0795654, -0.0764062, 0.7171599]
        samples = sample_grasp_profile("bowl_rim_away_from_open_drawer_topdown_v1", dims, rim=True, pose=pose)
        self.assertEqual(len(samples), 8)
        self.assertTrue(all(sample.metadata.get("away_from_open_drawer") for sample in samples))

        world_from_obj = pose7_rotation_matrix(pose)
        world_y_offsets = [(world_from_obj @ [sample.xyz[0], sample.xyz[1], 0.0])[1] for sample in samples]
        self.assertTrue(all(value < 0.0 for value in world_y_offsets))

    def test_open_drawer_fixed_point_profiles_select_ranked_candidates(self):
        dims = [0.1073792, 0.1046324, 0.0654656]
        half_x = 0.5 * dims[0]
        half_y = 0.5 * dims[1]
        expected_xy = {
            "bowl_rim_open_drawer_p0_topdown_v1": ("P0", 0.0, -0.82 * half_y),
            "bowl_rim_open_drawer_p2_topdown_v1": (
                "P2",
                0.82 * half_x / math.sqrt(2.0),
                -0.82 * half_y / math.sqrt(2.0),
            ),
            "bowl_rim_open_drawer_p4_topdown_v1": ("P4", 0.82 * half_x, 0.0),
        }
        for profile, (point_id, want_x, want_y) in expected_xy.items():
            samples = sample_grasp_profile(profile, dims, rim=True, pose=[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0])
            self.assertEqual(len(samples), 4)
            self.assertEqual({sample.metadata.get("open_drawer_point_id") for sample in samples}, {point_id})
            self.assertTrue(all(abs(sample.xyz[0] - want_x) <= 1e-9 for sample in samples))
            self.assertTrue(all(abs(sample.xyz[1] - want_y) <= 1e-9 for sample in samples))

    def test_mug_body_side_profile_avoids_center_and_handle_expanded_edge(self):
        dims = [0.13, 0.18, 0.11]
        self.assertEqual(_normalize_grasp_sampler_profile("mug_body_side_avoid_handle_v1"), "mug_body_side_avoid_handle_v1")
        samples = _grasp_6dof_xyzrpy_for_profile("mug_body_side_avoid_handle_v1", dims, rim=True)
        self.assertEqual(len(samples), 24)
        self.assertTrue(all(abs(sample[0]) > 1e-6 or abs(sample[1]) > 1e-6 for sample in samples))
        self.assertTrue(all(abs(sample[2] - (0.055 - 0.034)) <= 1e-6 for sample in samples))
        max_xy = max(max(abs(sample[0]), abs(sample[1])) for sample in samples)
        self.assertLessEqual(max_xy, 0.36 * min(dims[0], dims[1]) * 0.5)

    def test_mug_handle_profile_samples_positive_local_y_handle_side(self):
        dims = [0.13, 0.18, 0.11]
        pose = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        self.assertEqual(_normalize_grasp_sampler_profile("mug_handle_topdown_v1"), "mug_handle_topdown_v1")
        samples = sample_grasp_profile("mug_handle_topdown_v1", dims, rim=True, pose=pose)

        self.assertEqual(len(samples), 36)
        self.assertEqual({sample.metadata.get("mug_mode") for sample in samples}, {"handle_topdown"})
        self.assertEqual({sample.metadata.get("grasp_intent") for sample in samples}, {"handle_only"})
        self.assertTrue(all(sample.xyz[1] > 0.0 for sample in samples))
        self.assertTrue(all(abs(sample.xyz[0]) <= 0.010 + 1e-9 for sample in samples))
        self.assertTrue(all(sample.xyz[2] > 0.0 for sample in samples))
        self.assertLessEqual(max(sample.xyz[1] for sample in samples), 0.5 * dims[1] - 0.002 + 1e-9)
        self.assertGreaterEqual(profile_gripper_width("mug_handle_topdown_v1", dims, pose=pose), 0.030)
        self.assertLessEqual(profile_gripper_width("mug_handle_topdown_v1", dims, pose=pose), 0.046)

    def test_mug_handle_then_body_profile_appends_body_side_fallback(self):
        dims = [0.13, 0.18, 0.11]
        pose = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        handle = sample_grasp_profile("mug_handle_topdown_v1", dims, rim=True, pose=pose)
        mixed = sample_grasp_profile("mug_handle_then_body_side_v1", dims, rim=True, pose=pose)

        self.assertEqual(len(mixed), len(handle) + 24)
        self.assertTrue(all(sample.metadata.get("grasp_intent") == "handle_only" for sample in mixed[: len(handle)]))
        self.assertTrue(
            all(sample.metadata.get("grasp_intent") == "body_side_fallback" for sample in mixed[len(handle) :])
        )
        self.assertEqual(
            _grasp_6dof_xyzrpy_for_profile("mug_handle_then_body_side_v1", dims, rim=True, pose=pose)[:2],
            sample_grasp_profile_xyzrpy("mug_handle_topdown_v1", dims, rim=True, pose=pose)[:2],
        )

    def test_mug_handle_x_profiles_sample_the_requested_local_side(self):
        dims = [0.13, 0.18, 0.11]
        pose = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]

        pos_x = sample_grasp_profile("mug_handle_local_pos_x_topdown_v1", dims, rim=True, pose=pose)
        neg_x = sample_grasp_profile("mug_handle_local_neg_x_topdown_v1", dims, rim=True, pose=pose)

        self.assertEqual(len(pos_x), 36)
        self.assertEqual(len(neg_x), 36)
        self.assertTrue(all(sample.xyz[0] > 0.0 for sample in pos_x))
        self.assertTrue(all(sample.xyz[0] < 0.0 for sample in neg_x))
        self.assertTrue(all(abs(sample.xyz[1]) <= 0.010 + 1e-9 for sample in pos_x + neg_x))
        self.assertTrue(all(sample.xyz[2] >= 0.45 * dims[2] - 1e-9 for sample in pos_x + neg_x))
        self.assertTrue(all(sample.xyz[2] <= 0.72 * dims[2] + 1e-9 for sample in pos_x + neg_x))
        self.assertEqual({sample.metadata.get("handle_side") for sample in pos_x}, {"local_positive_x"})
        self.assertEqual({sample.metadata.get("handle_side") for sample in neg_x}, {"local_negative_x"})

    def test_mug_handle_x_then_body_profiles_append_body_side_fallback(self):
        dims = [0.13, 0.18, 0.11]
        pose = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        handle = sample_grasp_profile("mug_handle_local_pos_x_topdown_v1", dims, rim=True, pose=pose)
        mixed = sample_grasp_profile("mug_handle_local_pos_x_then_body_side_v1", dims, rim=True, pose=pose)

        self.assertEqual(len(mixed), len(handle) + 24)
        self.assertEqual({sample.metadata.get("handle_side") for sample in mixed[: len(handle)]}, {"local_positive_x"})
        self.assertTrue(
            all(sample.metadata.get("grasp_intent") == "body_side_fallback" for sample in mixed[len(handle) :])
        )

    def test_executor_hints_can_raise_mug_after_grasp(self):
        cfg = client_config_from_recovery_hints(
            {
                "params": {
                    "executor": {
                        "grasp_close_max_above_m": 0.20,
                        "grasp_lift_probe_m": 0.05,
                        "grasp_lift_probe_max_steps": 18,
                        "grasp_lift_follow_m": 0.025,
                        "recovery_entry_lift_m": 0.045,
                        "recovery_entry_lift_max_steps": 12,
                        "recovery_entry_lift_reached_m": 0.006,
                        "recovery_entry_lift_gripper_value": 0.0,
                        "recovery_entry_escape_profile": "target_side_stage",
                        "recovery_entry_retreat_m": 0.08,
                        "recovery_entry_retreat_max_steps": 28,
                        "recovery_entry_retreat_reached_m": 0.015,
                        "place_hover_clearance_m": 0.14,
                        "place_lift_min_clearance_m": 0.10,
                        "place_lift_max_steps": 45,
                    }
                }
            }
        )
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.grasp_close_max_above_m, 0.20)
        self.assertEqual(cfg.grasp_lift_probe_m, 0.05)
        self.assertEqual(cfg.grasp_lift_probe_max_steps, 18)
        self.assertEqual(cfg.grasp_lift_follow_m, 0.025)
        self.assertEqual(cfg.recovery_entry_lift_m, 0.045)
        self.assertEqual(cfg.recovery_entry_lift_max_steps, 12)
        self.assertEqual(cfg.recovery_entry_lift_reached_m, 0.006)
        self.assertEqual(cfg.recovery_entry_lift_gripper_value, 0.0)
        self.assertEqual(cfg.recovery_entry_escape_profile, "target_side_stage")
        self.assertEqual(cfg.recovery_entry_retreat_m, 0.08)
        self.assertEqual(cfg.recovery_entry_retreat_max_steps, 28)
        self.assertEqual(cfg.recovery_entry_retreat_reached_m, 0.015)
        self.assertEqual(cfg.place_hover_clearance_m, 0.14)
        self.assertEqual(cfg.place_lift_min_clearance_m, 0.10)
        self.assertEqual(cfg.place_lift_max_steps, 45)

    def test_executor_hints_clip_grasp_close_max_above(self):
        cfg = client_config_from_recovery_hints(
            {"params": {"executor": {"grasp_close_max_above_m": 0.50}}}
        )
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.grasp_close_max_above_m, 0.22)

    def test_executor_hints_enable_world_z_place_yaw_after_hover(self):
        cfg = client_config_from_recovery_hints(
            {"params": {"executor": {"place_yaw_after_hover": "world_z_thin_x", "place_yaw_max_cmd": 0.30}}}
        )
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.place_yaw_after_hover, "world_z_thin_x")
        self.assertEqual(cfg.place_yaw_max_cmd, 0.30)
        from_geometry = client_config_from_recovery_hints(
            {
                "params": {
                    "geometry_hints": {
                        "placement_region": {"place_yaw_policy": "thin_horizontal_along_world_x"}
                    }
                }
            }
        )
        self.assertIsNotNone(from_geometry)
        self.assertEqual(from_geometry.place_yaw_after_hover, "world_z_thin_x")

    def test_executor_hints_enable_caddy_held_object_xy_align(self):
        cfg = client_config_from_recovery_hints(
            {
                "params": {
                    "executor": {
                        "place_held_object_xy_align": True,
                        "place_align_reached_m": 0.012,
                        "place_align_step_clip_m": 0.020,
                        "place_align_max_iters": 4,
                        "place_align_max_steps_per_iter": 10,
                    }
                }
            }
        )

        self.assertIsNotNone(cfg)
        self.assertTrue(cfg.place_held_object_xy_align)
        self.assertEqual(cfg.place_align_reached_m, 0.012)
        self.assertEqual(cfg.place_align_step_clip_m, 0.020)
        self.assertEqual(cfg.place_align_max_iters, 4)
        self.assertEqual(cfg.place_align_max_steps_per_iter, 10)

    def test_flat_box_profile_uses_pose_for_world_topdown_short_side_grasps(self):
        dims = [0.017872, 0.042672, 0.081216]
        pose = [0.3445, 0.0438, 0.0257, 0.0, 0.70710678, 0.0, -0.70710678]

        self.assertEqual(
            _normalize_grasp_sampler_profile("flat_box_topdown_short_side_v1"),
            "flat_box_topdown_short_side_v1",
        )
        samples = _grasp_6dof_xyzrpy_for_profile("flat_box_topdown_short_side_v1", dims, rim=False, pose=pose)

        self.assertEqual(len(samples), 24)
        half_thickness = 0.5 * min(dims)
        self.assertTrue(all(abs(sample[0]) <= half_thickness + 1e-6 for sample in samples))
        self.assertTrue(any(abs(sample[2]) > 1e-4 for sample in samples))
        self.assertTrue(any(abs(sample[3]) > 0.1 or abs(sample[4]) > 0.1 for sample in samples))

    def test_flat_box_deep_profile_pushes_close_pose_into_body(self):
        dims = [0.017872, 0.042672, 0.081216]
        pose = [0.3445, 0.0438, 0.0257, 0.0, 0.70710678, 0.0, -0.70710678]

        self.assertEqual(
            _normalize_grasp_sampler_profile("flat_box_topdown_short_side_deep_v1"),
            "flat_box_topdown_short_side_deep_v1",
        )
        samples = sample_grasp_profile("flat_box_topdown_short_side_deep_v1", dims, rim=False, pose=pose)

        self.assertEqual(len(samples), 12)
        half_thickness = 0.5 * min(dims)
        self.assertTrue(all(abs(sample.xyz[0]) <= 0.35 * half_thickness + 1e-6 for sample in samples))
        self.assertTrue(
            all(abs(sample.metadata.get("depth_from_top", 0.0) - 1.35 * half_thickness) < 1e-6 for sample in samples)
        )

    def test_book_profile_closes_a_few_cm_below_the_crown(self):
        dims = [0.0287, 0.1104, 0.1344]
        pose = [0.53, 0.15, 0.88, 1.0, 0.0, 0.0, 0.0]
        samples = sample_grasp_profile("flat_box_topdown_short_side_book_v1", dims, rim=False, pose=pose)
        shallow = sample_grasp_profile("flat_box_topdown_short_side_v1", dims, rim=False, pose=pose)

        self.assertEqual(len(samples), 12)
        yaws = {round(float(sample.metadata.get("world_yaw", 0.0)), 6) for sample in samples}
        self.assertEqual(len(yaws), 2)
        self.assertTrue(all(sample.metadata.get("book_thin_side_only") for sample in samples))
        depths = {round(float(sample.metadata.get("depth_from_top", 0.0)), 6) for sample in samples}
        self.assertEqual(depths, {0.025, 0.032})
        self.assertTrue(all(abs(sample.xyz[2]) >= 0.20 * 0.5 * dims[2] - 1e-6 for sample in samples))
        shallow_depths = {round(float(sample.metadata.get("depth_from_top", 0.0)), 6) for sample in shallow}
        self.assertTrue(max(shallow_depths) <= 0.007 + 1e-6)
        self.assertGreater(min(depths), max(shallow_depths))

    def test_can_body_lower_side_profile_stays_below_top_rim(self):
        dims = [0.0638, 0.0687, 0.0804]
        self.assertEqual(
            _normalize_grasp_sampler_profile("can_body_lower_side_v1"),
            "can_body_lower_side_v1",
        )
        samples = _grasp_6dof_xyzrpy_for_profile("can_body_lower_side_v1", dims, rim=False)

        self.assertEqual(len(samples), 90)
        max_z = max(sample[2] for sample in samples)
        min_z = min(sample[2] for sample in samples)
        self.assertLess(max_z, 0.026)
        self.assertGreaterEqual(min_z, 0.005)
        self.assertTrue(any(abs(sample[0]) > 1e-4 or abs(sample[1]) > 1e-4 for sample in samples))

    def test_moka_pot_handle_profile_only_samples_handle_side(self):
        dims = [0.08141639283096525, 0.14753821819540086, 0.15180038998276296]
        pose = [0.706, -0.011, 0.054, 0.0, 0.0, 0.0, -1.0]
        self.assertEqual(
            _normalize_grasp_sampler_profile("moka_pot_handle_topdown_v1"),
            "moka_pot_handle_topdown_v1",
        )

        samples = sample_grasp_profile("moka_pot_handle_topdown_v1", dims, rim=False, pose=pose)

        self.assertEqual(len(samples), 18)
        self.assertEqual({sample.metadata.get("moka_mode") for sample in samples}, {"handle_topdown"})
        self.assertEqual({sample.metadata.get("grasp_intent") for sample in samples}, {"handle_only"})
        half_y = 0.5 * dims[1]
        half_z = 0.5 * dims[2]
        self.assertTrue(all(abs(sample.xyz[0]) < 1e-6 for sample in samples))
        self.assertTrue(all(sample.xyz[1] >= 0.78 * half_y - 1e-6 for sample in samples))
        self.assertEqual(
            {round(sample.xyz[2], 6) for sample in samples},
            {round(0.38 * half_z, 6), round(0.54 * half_z, 6), round(0.70 * half_z, 6)},
        )
        yaws = {round(abs(sample.metadata.get("world_yaw", 99.0)), 4) for sample in samples}
        self.assertTrue(yaws.issubset({0.0, 3.1416}))
        width = profile_gripper_width("moka_pot_handle_topdown_v1", dims, pose=pose)
        self.assertGreaterEqual(width, 0.030)
        self.assertLessEqual(width, 0.040)
        xyzrpy = _grasp_6dof_xyzrpy_for_profile("moka_pot_handle_topdown_v1", dims, rim=False, pose=pose)
        self.assertEqual(len(xyzrpy), len(samples))

    def test_can_orthogonal_lower_profile_removes_diagonal_yaws_and_lowers_samples(self):
        dims = [0.0638, 0.0687, 0.0804]
        self.assertEqual(
            _normalize_grasp_sampler_profile("can_body_orthogonal_lower_side_v1"),
            "can_body_orthogonal_lower_side_v1",
        )
        samples = _grasp_6dof_xyzrpy_for_profile("can_body_orthogonal_lower_side_v1", dims, rim=False)

        self.assertEqual(len(samples), 60)
        self.assertLess(max(sample[2] for sample in samples), 0.013)
        yaws = {round(sample[5], 4) for sample in samples}
        self.assertTrue(yaws.issubset({0.0, 1.5708, -1.5708, -3.1416}))

    def test_carton_body_profile_uses_pose_aware_deep_orthogonal_samples(self):
        dims = [0.0525, 0.05307, 0.13119]
        pose = [0.56, -0.08, 0.07, 0.5, 0.5, 0.5, 0.5]
        self.assertEqual(
            _normalize_grasp_sampler_profile("carton_body_vertical_deep_v1"),
            "carton_body_vertical_deep_v1",
        )
        samples = sample_grasp_profile("carton_body_vertical_deep_v1", dims, rim=False, pose=pose)

        self.assertEqual(len(samples), 36)
        self.assertEqual({sample.metadata.get("top_axis") for sample in samples}, {1})
        half_top = 0.5 * dims[1]
        self.assertTrue(all(abs(sample.xyz[1]) <= 0.22 * half_top + 1e-6 for sample in samples))
        self.assertTrue(any(sample.metadata.get("depth_from_top", 0.0) >= 0.98 * half_top for sample in samples))
        yaws = {round(abs(sample.metadata.get("world_yaw", 99.0)), 4) for sample in samples}
        self.assertTrue(yaws.issubset({0.0, 1.5708, 3.1416}))

    def test_carton_upright_body_side_profile_rotates_off_gable_ridge(self):
        dims = [0.0525, 0.05307, 0.13119]
        pose = [0.56, -0.08, 0.07, 0.5, 0.5, 0.5, 0.5]
        self.assertEqual(
            _normalize_grasp_sampler_profile("carton_upright_body_side_v1"),
            "carton_upright_body_side_v1",
        )
        samples = sample_grasp_profile("carton_upright_body_side_v1", dims, rim=False, pose=pose)

        self.assertEqual(len(samples), 18)
        self.assertEqual({sample.metadata.get("carton_mode") for sample in samples}, {"upright_body_side"})
        self.assertEqual(
            {sample.metadata.get("carton_grasp_intent") for sample in samples},
            {"rotated_side_wall_avoid_gable_ridge"},
        )
        world_z_offsets = [sample.metadata["world_offset"][2] for sample in samples]
        self.assertGreaterEqual(min(world_z_offsets), 0.029)
        self.assertLessEqual(max(world_z_offsets), 0.042)
        depths = {round(sample.metadata.get("depth_from_top", 0.0), 3) for sample in samples}
        self.assertEqual(depths, {0.024, 0.028, 0.036})
        yaws = {round(sample.metadata.get("world_yaw", 99.0), 4) for sample in samples}
        self.assertEqual(yaws, {-3.1416, 0.0})
        world_offsets = [sample.metadata["world_offset"] for sample in samples]
        self.assertTrue(any(abs(offset[0]) > 1e-4 for offset in world_offsets))
        self.assertTrue(all(abs(offset[1]) < 1e-6 for offset in world_offsets))
        xyzrpy = _grasp_6dof_xyzrpy_for_profile("carton_upright_body_side_v1", dims, rim=False, pose=pose)
        self.assertEqual(len(xyzrpy), len(samples))
        self.assertGreaterEqual(profile_gripper_width("carton_upright_body_side_v1", dims, pose=pose), 0.06)

    def test_carton_fallen_body_side_profile_samples_along_fallen_carton(self):
        dims = [0.0525, 0.05307, 0.13119]
        pose = [0.56, -0.08, 0.07, 1.0, 0.0, 0.0, 0.0]
        self.assertEqual(
            _normalize_grasp_sampler_profile("carton_fallen_body_side_v1"),
            "carton_fallen_body_side_v1",
        )
        samples = sample_grasp_profile("carton_fallen_body_side_v1", dims, rim=False, pose=pose)

        self.assertEqual(len(samples), 36)
        self.assertEqual({sample.metadata.get("carton_mode") for sample in samples}, {"fallen_body_side"})
        world_offsets = [sample.metadata["world_offset"] for sample in samples]
        self.assertTrue(any(abs(offset[1]) > 0.01 for offset in world_offsets))
        self.assertGreaterEqual(min(offset[2] for offset in world_offsets), 0.0)
        self.assertLessEqual(max(offset[2] for offset in world_offsets), 0.013)
        depths = {round(sample.metadata.get("depth_from_top", 0.0), 3) for sample in samples}
        self.assertEqual(depths, {0.014, 0.02, 0.026})
        yaws = {round(abs(sample.metadata.get("world_yaw", 99.0)), 4) for sample in samples}
        self.assertTrue(yaws.issubset({0.0, 1.5708, 3.1416}))
        self.assertGreaterEqual(profile_gripper_width("carton_fallen_body_side_v1", dims, pose=pose), 0.052)

    def test_small_shallow_bowl_profile_keeps_z_above_bottom(self):
        dims = [0.081, 0.081, 0.0345]
        self.assertEqual(
            _normalize_grasp_sampler_profile("bowl_rim_small_shallow_diagonal_topdown_v1"),
            "bowl_rim_small_shallow_diagonal_topdown_v1",
        )
        local_samples = sample_grasp_profile("bowl_rim_small_shallow_diagonal_topdown_v1", dims, rim=True)
        self.assertEqual(len(local_samples), 32)
        for sample in local_samples:
            theta = math.atan2(sample.xyz[1], sample.xyz[0])
            radial = (math.cos(theta), math.sin(theta))
            yaw = float(sample.metadata["world_yaw"])
            jaw_axis = (math.sin(yaw), -math.cos(yaw))
            alignment = abs(radial[0] * jaw_axis[0] + radial[1] * jaw_axis[1])
            self.assertGreater(alignment, 0.999999)

        samples = _grasp_6dof_xyzrpy_for_profile("bowl_rim_small_shallow_diagonal_topdown_v1", dims, rim=True)
        self.assertEqual(len(samples), 32)
        self.assertTrue(all(abs(sample[0]) > 1e-6 and abs(sample[1]) > 1e-6 for sample in samples))
        self.assertTrue(all(sample[2] >= 0.004 for sample in samples))
        self.assertTrue(all(sample[2] <= 0.36 * 0.01725 + 1e-6 for sample in samples))
        max_xy = max(max(abs(sample[0]), abs(sample[1])) for sample in samples)
        self.assertLessEqual(max_xy, 0.70 * 0.0405 / 1.4142 + 1e-4)

    def test_thin_horizontal_world_x_yaws_follow_cuboid_thin_edge(self):
        from types import SimpleNamespace

        book = SimpleNamespace(dims=[0.0287, 0.1104, 0.1344])
        self.assertEqual(_thin_horizontal_world_x_yaws(book), [0.0, math.pi])
        wide = SimpleNamespace(dims=[0.1104, 0.0287, 0.1344])
        self.assertEqual(_thin_horizontal_world_x_yaws(wide), [0.5 * math.pi, -0.5 * math.pi])

    def test_place_yaw_policies_index_original_and_sanitized_names(self):
        from experiments.robot.libero.tiptop_repro.tamp_scene import TAMPObject, TAMPProblem

        surface = TAMPObject(
            name="desk-caddy left inner",
            pos=[0.0, 0.0, 0.9],
            radius=0.05,
            height=0.01,
            role="surface",
            geometry={"metadata": {"place_yaw_policy": "thin_horizontal_along_world_x"}},
        )
        problem = TAMPProblem(movables=[], surfaces=[surface], statics=[], goal_atoms=[])
        policies = _place_yaw_policies_by_surface(problem, {"desk-caddy left inner": "desk_caddy_left_inner"})
        self.assertEqual(policies["desk-caddy left inner"], "thin_horizontal_along_world_x")
        self.assertEqual(policies["desk_caddy_left_inner"], "thin_horizontal_along_world_x")


if __name__ == "__main__":
    unittest.main()
