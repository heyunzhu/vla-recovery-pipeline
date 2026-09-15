from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np

from experiments.robot.libero.tiptop_repro.libero_tiptop_executor import (
    LiberoRobotClientConfig,
    client_config_from_recovery_hints,
    _apply_confirmed_holding_latch,
    _apply_world_yaw_to_quat_xyzw,
    _entry_escape_plan_from_config,
    _ee_near_grasp_target,
    _entry_retreat_direction_xy,
    _entry_stage_target_from_spec,
    _execute_place_held_object_xy_align,
    _footprint_center_alignment_delta,
    _footprint_containment_delta,
    _gripper_hold_value,
    _held_transfer_protected_z,
    _nearest_signed_yaw_delta,
    _object_thin_horizontal_yaw,
    _caddy_compartment_opening_from_scene,
    _opening_to_world_frame,
    _place_lift_target_z,
    _place_args_from_label_details,
    _opening_from_serialized_step,
    _place_release_accepts,
    _place_release_geometry,
    _rotate_held_object_world_z_yaw,
    _set_confirmed_holding_latch,
    _shrunk_opening,
    _shrunk_span_m,
    _world_z_yaw_pose_waypoints,
    _wrap_yaw_rad,
    execute_recovery_entry_lift,
)
from experiments.robot.libero.tiptop_repro.optimized_executor import goal_satisfied
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import _serialized_surface_openings
from experiments.robot.libero.tiptop_repro.scene_reader import ObjectState, SceneState
from experiments.robot.libero.tiptop_repro.tamp_scene import TAMPObject, TAMPProblem, _virtual_inner_floor_surface


REPO_ROOT = Path(__file__).resolve().parents[5]
LIBERO90_GEOMETRY_ADAPTER = REPO_ROOT / "skill_packs" / "libero90_legacy" / "code" / "geometry_profiles.py"


class ExecutorHintConfigTests(unittest.TestCase):
    def test_unknown_executor_hint_key_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported executor recovery hint option"):
            client_config_from_recovery_hints(
                {
                    "params": {
                        "executor": {
                            "teleport_to_grasp": True,
                        }
                    }
                }
            )

    def test_place_drop_max_steps_is_consumed(self):
        cfg = client_config_from_recovery_hints(
            {
                "params": {
                    "executor": {
                        "place_drop_max_steps": 80,
                    }
                }
            }
        )

        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.place_drop_max_steps, 80)

    def test_place_release_hook_options_are_consumed(self):
        cfg = client_config_from_recovery_hints(
            {
                "params": {
                    "executor": {
                        "place_release_margin_m": 0.012,
                        "place_open_dwell_steps": 9,
                        "place_retreat_m": 0.05,
                        "place_retreat_max_steps": 22,
                    }
                }
            }
        )

        self.assertIsNotNone(cfg)
        self.assertAlmostEqual(cfg.place_release_margin_m, 0.012)
        self.assertEqual(cfg.place_open_dwell_steps, 9)
        self.assertAlmostEqual(cfg.place_retreat_m, 0.05)
        self.assertEqual(cfg.place_retreat_max_steps, 22)


def _scene(bowl_xy=(0.02, 0.01), bowl_z=0.03, ee=(0.02, 0.01, 0.08), gripper_qpos=(0.04, -0.04)) -> SceneState:
    return SceneState(
        ee_pos=np.asarray(ee, dtype=np.float32),
        ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        gripper_qpos=np.asarray(gripper_qpos, dtype=np.float32),
        objects={
            "akita_black_bowl_1_main": ObjectState(
                name="akita_black_bowl_1_main",
                pos=np.asarray([bowl_xy[0], bowl_xy[1], bowl_z], dtype=np.float32),
            ),
            "plate_1_main": ObjectState(
                name="plate_1_main",
                pos=np.asarray([0.0, 0.0, 0.0], dtype=np.float32),
            ),
        },
    )


def _scene_with_desk_caddy_sites() -> SceneState:
    scene = _scene()
    scene.objects["desk_caddy_1_main"] = ObjectState(
        name="desk_caddy_1_main",
        pos=np.asarray([-0.39840403, -0.13762377, 0.97184], dtype=np.float32),
        quat=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        geometry={
            "geoms": [
                {
                    "shape": "box",
                    "pos": [-0.39840403, -0.13762377, 0.97184],
                    "quat": [1.0, 0.0, 0.0, 0.0],
                    "size": [0.0755, 0.21688, 0.08345],
                    "collision_active": True,
                }
            ],
            "sites": [
                {
                    "name": "desk_caddy_1_front_contain_region",
                    "shape": "box",
                    "pos": [-0.3674, -0.1370, 0.9600],
                    "quat": [1.0, 0.0, 0.0, 0.0],
                    "size": [0.02775, 0.06216, 0.06046],
                },
                {
                    "name": "desk_caddy_1_left_contain_region",
                    "shape": "box",
                    "pos": [-0.3984, -0.0300, 0.9600],
                    "quat": [1.0, 0.0, 0.0, 0.0],
                    "size": [0.03000, 0.12400, 0.06046],
                },
            ],
        },
    )
    return scene


def _desk_caddy_geometry_hint() -> dict:
    return {
        "geometry_profile": "desk_caddy_compartment_inner_floor_v1",
        "geometry_profile_adapter_path": str(LIBERO90_GEOMETRY_ADAPTER),
        "intent": "compartment_inner_floor",
        "planner_primitive": "inner_floor",
        "floor_clearance_m": 0.008,
        "site_margin_m": 0.0,
        "thickness_m": 0.010,
        "release_mode": "high_drop_into_compartment",
        "release_z_offset_m": 0.10,
        "release_z_tolerance_m": 0.04,
        "release_xy_margin_m": 0.012,
        "planner_support_z_offset_m": 0.10,
    }


def _serialized_opening_from_virtual_surface(surface) -> dict:
    metadata = dict((surface.geometry or {}).get("metadata") or {})
    inner = dict(metadata.get("inner_bounds") or {})
    opening = {
        "x_min": float(inner["x_min"]),
        "x_max": float(inner["x_max"]),
        "y_min": float(inner["y_min"]),
        "y_max": float(inner["y_max"]),
        "support_z": float(inner.get("support_z", inner.get("z_min"))),
        "surface_label": surface.name,
        "source": "serialized_surface_inner_bounds",
    }
    for key in (
        "support_surface",
        "source_bddl_region",
        "source_bddl_qualified_region",
        "release_mode",
        "release_z_offset_m",
        "release_z_tolerance_m",
        "release_xy_margin_m",
        "planner_support_z_m",
        "exclude_table_collision",
        "inner_bounds_source",
        "source_site_name",
        "site_margin_m",
        "floor_clearance_m",
        "geometry_profile",
        "geometry_profile_adapter_path",
        "geometry_profile_adapter_warning",
        "inner_bounds_adapter",
        "inner_bounds_adapter_path",
        "inner_bounds_profile",
    ):
        if key in metadata:
            opening[key] = metadata[key]
    return opening


class _EntryLiftEnv:
    def __init__(self) -> None:
        self.obs = {
            "robot0_eef_pos": np.asarray([0.1, -0.2, 0.4], dtype=np.float32),
            "robot0_eef_quat": np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
            "robot0_gripper_qpos": np.asarray([0.02, -0.02], dtype=np.float32),
            "robot0_joint_pos": np.zeros(7, dtype=np.float32),
        }
        self.actions = []

    def step(self, action):
        arr = np.asarray(action, dtype=np.float32)
        self.actions.append(arr.astype(float).tolist())
        self.obs = dict(self.obs)
        self.obs["robot0_eef_pos"] = self.obs["robot0_eef_pos"] + arr[:3] * 0.05
        return self.obs, 0.0, False, {}


class _HeldObjectAlignClient:
    def __init__(self, scene: SceneState, cfg: LiberoRobotClientConfig, obj_name: str) -> None:
        self.scene = scene
        self.cfg = cfg
        self.obj_name = obj_name
        self.done = False
        self.num_env_steps = 0
        self.labels: list[str] = []

    def get_scene(self) -> SceneState:
        return self.scene

    def execute_cartesian_waypoints(self, waypoints, gripper: float, max_steps: int, label: str = ""):
        valid = [np.asarray(point, dtype=np.float32).reshape(-1)[:3] for point in waypoints]
        if not valid:
            return {"success": False, "error": "no_waypoints", "done": False, "env_steps": 0}
        goal = valid[-1]
        delta = goal - self.scene.ee_pos[:3]
        self.scene.ee_pos = goal.astype(np.float32)
        obj = self.scene.objects.get(self.obj_name)
        if obj is not None and obj.pos is not None and gripper > 0:
            obj.pos = (obj.pos[:3] + delta).astype(np.float32)
            for geom in list((obj.geometry or {}).get("geoms") or []):
                geom_pos = np.asarray(geom.get("pos", []), dtype=np.float32).reshape(-1)
                if geom_pos.size >= 3:
                    moved = geom_pos.copy()
                    moved[:3] = moved[:3] + delta
                    geom["pos"] = moved[:3].astype(float).tolist()
        self.num_env_steps += 1
        self.labels.append(label)
        return {"success": True, "error": "", "done": False, "env_steps": 1}


class PlaceGeometryTests(unittest.TestCase):
    def test_shrunk_opening_collapses_when_object_fills_plate(self):
        bounds = {"x_min": -0.07, "x_max": 0.07, "y_min": -0.07, "y_max": 0.07}
        shrunk = _shrunk_opening(bounds, hx=0.08, hy=0.08, margin=0.008)
        self.assertFalse(shrunk["shrunk"])

    def test_collapsed_release_accepts_bowl_over_plate(self):
        cfg = LiberoRobotClientConfig()
        ok, geom = _place_release_geometry(_scene(), "akita_black_bowl_1_main", "plate_1_main", cfg)
        self.assertTrue(geom.get("in_opening"))
        self.assertLessEqual(float(geom["xy_dist"]), cfg.place_drop_align_xy_m)
        self.assertTrue(ok)

    def test_far_xy_does_not_release(self):
        cfg = LiberoRobotClientConfig()
        ok, geom = _place_release_geometry(
            _scene(bowl_xy=(0.20, 0.20)),
            "akita_black_bowl_1_main",
            "plate_1_main",
            cfg,
        )
        self.assertFalse(geom.get("in_opening"))
        self.assertFalse(ok)

    def test_virtual_opening_releases_without_scene_surface(self):
        cfg = LiberoRobotClientConfig()
        opening = {
            "x_min": -0.05,
            "x_max": 0.09,
            "y_min": -0.06,
            "y_max": 0.08,
            "support_z": 0.0,
            "source": "serialized_surface_inner_bounds",
        }
        ok, geom = _place_release_geometry(
            _scene(),
            "akita_black_bowl_1_main",
            None,
            cfg,
            opening_override=opening,
        )

        self.assertTrue(geom.get("in_opening"))
        self.assertEqual(geom.get("release_guard_reason"), "ok")
        self.assertTrue(ok)

    def test_world_serialized_opening_is_not_shifted_to_robot_base(self):
        scene = _scene()
        scene.robot_joint_debug["frame_candidates"] = [
            {
                "name": "robot0_base",
                "pos_world": [-0.75, 0.0, 0.912],
                "quat_world_wxyz": [1.0, 0.0, 0.0, 0.0],
            }
        ]
        opening = {
            "coordinate_frame": "world",
            "x_min": -0.395,
            "x_max": -0.340,
            "y_min": -0.199,
            "y_max": -0.075,
            "support_z": 0.900,
        }

        converted = _opening_to_world_frame(opening, scene)

        self.assertIsNotNone(converted)
        self.assertEqual(converted["coordinate_frame"], "world")
        self.assertFalse(converted["opening_frame_conversion_applied"])
        self.assertAlmostEqual(0.5 * (converted["x_min"] + converted["x_max"]), -0.3675, places=5)

    def test_serialized_surface_opening_preserves_declared_world_frame(self):
        surface = TAMPObject(
            name="desk_caddy_1_main_front_inner_floor",
            pos=[-0.3675, -0.137, 0.895],
            radius=0.05,
            height=0.01,
            role="surface",
            geometry={
                "metadata": {
                    "inner_bounds_coordinate_frame": "world",
                    "inner_bounds": {
                        "x_min": -0.395,
                        "x_max": -0.340,
                        "y_min": -0.199,
                        "y_max": -0.075,
                        "support_z": 0.900,
                    },
                }
            },
        )
        problem = TAMPProblem(
            movables=[],
            surfaces=[surface],
            statics=[],
            goal_atoms=[],
            q_init_debug={
                "world_to_planner_frame": {
                    "base_source": "robot0_base",
                    "method": "full_se3_inverse_robot_base",
                    "origin_world": [-0.75, 0.0, 0.912],
                    "quat_world_wxyz": [1.0, 0.0, 0.0, 0.0],
                }
            },
        )

        openings = _serialized_surface_openings(problem)

        opening = openings["desk_caddy_1_main_front_inner_floor"]
        self.assertEqual(opening["coordinate_frame"], "world")
        self.assertNotIn("planner_frame_origin_world", opening)
        self.assertAlmostEqual(0.5 * (opening["x_min"] + opening["x_max"]), -0.3675, places=5)

    def test_planner_serialized_opening_converts_once_to_world(self):
        surface = TAMPObject(
            name="desk_caddy_1_main_front_inner_floor",
            pos=[0.3825, -0.137, -0.017],
            radius=0.05,
            height=0.01,
            role="surface",
            geometry={
                "metadata": {
                    "inner_bounds_coordinate_frame": "planner_frame",
                    "inner_bounds": {
                        "x_min": 0.355,
                        "x_max": 0.410,
                        "y_min": -0.199,
                        "y_max": -0.075,
                        "support_z": -0.012,
                    },
                }
            },
        )
        problem = TAMPProblem(
            movables=[],
            surfaces=[surface],
            statics=[],
            goal_atoms=[],
            q_init_debug={
                "world_to_planner_frame": {
                    "base_source": "robot0_base",
                    "method": "full_se3_inverse_robot_base",
                    "origin_world": [-0.75, 0.0, 0.912],
                    "quat_world_wxyz": [1.0, 0.0, 0.0, 0.0],
                }
            },
        )

        opening = _serialized_surface_openings(problem)["desk_caddy_1_main_front_inner_floor"]
        converted = _opening_to_world_frame(opening, _scene())

        self.assertEqual(opening["coordinate_frame"], "planner_frame")
        self.assertEqual(converted["coordinate_frame"], "world")
        self.assertTrue(converted["opening_frame_conversion_applied"])
        self.assertAlmostEqual(0.5 * (converted["x_min"] + converted["x_max"]), -0.3675, places=5)
        self.assertAlmostEqual(converted["support_z"], 0.900, places=5)

    def test_high_drop_opening_releases_above_inner_floor(self):
        cfg = LiberoRobotClientConfig()
        opening = {
            "x_min": -0.05,
            "x_max": 0.09,
            "y_min": -0.06,
            "y_max": 0.08,
            "support_z": 0.0,
            "source": "serialized_surface_inner_bounds",
            "release_mode": "high_drop_into_compartment",
            "release_z_offset_m": 0.10,
            "release_z_tolerance_m": 0.04,
            "release_xy_margin_m": 0.012,
        }
        ok, geom = _place_release_geometry(
            _scene(bowl_z=0.10, ee=(0.02, 0.01, 0.16)),
            "akita_black_bowl_1_main",
            None,
            cfg,
            opening_override=opening,
        )

        self.assertGreater(float(geom["z_delta"]), cfg.place_release_z_max_m)
        self.assertEqual(geom.get("release_mode"), "high_drop_into_compartment")
        self.assertTrue(geom.get("in_release_opening"))
        self.assertEqual(geom.get("release_guard_reason"), "ok")
        self.assertTrue(ok)

    def test_book_caddy_high_drop_requires_footprint_containment(self):
        cfg = LiberoRobotClientConfig()
        opening = {
            "x_min": -0.05,
            "x_max": 0.05,
            "y_min": -0.05,
            "y_max": 0.05,
            "support_z": 0.0,
            "source": "caddy_compartment_aabb_crop",
            "surface_label": "desk_caddy_1_main_front_inner_floor",
            "release_mode": "high_drop_into_compartment",
            "release_z_offset_m": 0.10,
            "release_z_tolerance_m": 0.04,
            "release_xy_margin_m": 0.012,
        }
        scene = SceneState(
            ee_pos=np.asarray([0.0, 0.0, 0.16], dtype=np.float32),
            ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
            gripper_qpos=np.asarray([0.0, 0.0], dtype=np.float32),
            objects={
                "black_book_1_main": ObjectState(
                    name="black_book_1_main",
                    pos=np.asarray([0.0, 0.03, 0.10], dtype=np.float32),
                    quat=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                    geometry={
                        "source": "unit_test",
                        "geoms": [
                            {
                                "shape": "box",
                                "pos": [0.0, 0.03, 0.10],
                                "quat": [1.0, 0.0, 0.0, 0.0],
                                "size": [0.01, 0.01, 0.02],
                                "collision_active": True,
                            }
                        ],
                    },
                )
            },
        )

        ok, geom = _place_release_geometry(
            scene,
            "black_book_1_main",
            "desk_caddy_1_main",
            cfg,
            opening_override=opening,
        )

        self.assertTrue(geom.get("in_release_opening"))
        self.assertFalse(geom.get("footprint_contained"))
        self.assertTrue(geom.get("requires_footprint_release"))
        self.assertEqual(geom.get("release_guard_reason"), "footprint_not_contained")
        self.assertFalse(ok)

    def test_book_caddy_high_drop_accepts_small_footprint_tolerance(self):
        cfg = LiberoRobotClientConfig(place_footprint_release_tolerance_m=0.001)
        opening = {
            "x_min": -0.05,
            "x_max": 0.05,
            "y_min": -0.027,
            "y_max": 0.0265,
            "support_z": 0.0,
            "source": "caddy_compartment_aabb_crop",
            "surface_label": "desk_caddy_1_main_front_inner_floor",
            "release_mode": "high_drop_into_compartment",
            "release_z_offset_m": 0.10,
            "release_z_tolerance_m": 0.04,
            "release_xy_margin_m": 0.012,
        }
        scene = SceneState(
            ee_pos=np.asarray([0.0, 0.0, 0.16], dtype=np.float32),
            ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
            gripper_qpos=np.asarray([0.0, 0.0], dtype=np.float32),
            objects={
                "black_book_1_main": ObjectState(
                    name="black_book_1_main",
                    pos=np.asarray([0.0, 0.005, 0.10], dtype=np.float32),
                    quat=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                    geometry={
                        "source": "unit_test",
                        "geoms": [
                            {
                                "shape": "box",
                                "pos": [0.0, 0.005, 0.10],
                                "quat": [1.0, 0.0, 0.0, 0.0],
                                "size": [0.01, 0.01, 0.02],
                                "collision_active": True,
                            }
                        ],
                    },
                )
            },
        )

        ok, geom = _place_release_geometry(
            scene,
            "black_book_1_main",
            "desk_caddy_1_main",
            cfg,
            opening_override=opening,
        )

        self.assertFalse(geom.get("footprint_contained"))
        self.assertTrue(geom.get("footprint_contained_with_tolerance"))
        self.assertLessEqual(float(geom.get("footprint_violation_m")), 0.001)
        self.assertEqual(geom.get("release_guard_reason"), "ok")
        self.assertTrue(ok)

    def test_serialized_opening_preserves_high_drop_metadata(self):
        opening = _opening_from_serialized_step(
            {
                "surface_opening": {
                    "x_min": -0.05,
                    "x_max": 0.09,
                    "y_min": -0.06,
                    "y_max": 0.08,
                    "support_z": 0.0,
                    "release_mode": "high_drop_into_compartment",
                    "release_z_offset_m": 0.10,
                    "release_z_tolerance_m": 0.04,
                    "release_xy_margin_m": 0.012,
                    "planner_support_z_m": 0.10,
                }
            }
        )

        self.assertIsNotNone(opening)
        self.assertEqual(opening["release_mode"], "high_drop_into_compartment")
        self.assertAlmostEqual(float(opening["planner_support_z_m"]), 0.10)

    def test_serialized_planner_frame_opening_converts_to_world(self):
        scene = _scene()
        scene.robot_joint_debug["frame_candidates"] = [
            {
                "name": "robot0_base",
                "pos_world": [-0.66, 0.0, 0.912],
                "quat_world_wxyz": [1.0, 0.0, 0.0, 0.0],
            }
        ]
        opening = _opening_from_serialized_step(
            {
                "surface_opening": {
                    "x_min": 0.60,
                    "x_max": 0.70,
                    "y_min": 0.05,
                    "y_max": 0.15,
                    "support_z": -0.05,
                    "source": "serialized_surface_inner_bounds",
                    "coordinate_frame": "planner_frame",
                    "planner_frame": "robot0_base",
                    "planner_frame_origin_world": [-0.66, 0.0, 0.912],
                    "planner_frame_quat_world_wxyz": [1.0, 0.0, 0.0, 0.0],
                }
            }
        )

        converted = _opening_to_world_frame(opening, scene)

        self.assertIsNotNone(converted)
        assert converted is not None
        self.assertEqual(converted["coordinate_frame"], "world")
        self.assertTrue(converted["opening_frame_conversion_applied"])
        self.assertAlmostEqual(float(converted["x_min"]), -0.06, places=6)
        self.assertAlmostEqual(float(converted["x_max"]), 0.04, places=6)
        self.assertAlmostEqual(float(converted["y_min"]), 0.05, places=6)
        self.assertAlmostEqual(float(converted["y_max"]), 0.15, places=6)
        self.assertAlmostEqual(float(converted["support_z"]), 0.862, places=6)
        np.testing.assert_allclose(converted["opening_center_xy_planner"], [0.65, 0.10], atol=1e-6)
        np.testing.assert_allclose(converted["opening_center_xy_world"], [-0.01, 0.10], atol=1e-6)

    def test_place_label_keeps_unresolved_virtual_surface_label(self):
        obj, surface, surface_label = _place_args_from_label_details(
            "Place(akita_black_bowl_1_main, grasp1, pose1, kitchen_table_plate_right_region, q2)",
            _scene(),
        )

        self.assertEqual(obj, "akita_black_bowl_1_main")
        self.assertIsNone(surface)
        self.assertEqual(surface_label, "kitchen_table_plate_right_region")

    def test_caddy_compartment_declines_scene_recomputed_opening_without_pack_metadata(self):
        scene = _scene_with_desk_caddy_sites()
        obj, surface, surface_label = _place_args_from_label_details(
            "Place(akita_black_bowl_1_main, grasp1, pose1, desk_caddy_1_main_front_inner_floor, q2)",
            scene,
        )
        serialized_opening = {
            "x_min": 0.299,
            "x_max": 0.404,
            "y_min": -0.328,
            "y_max": -0.171,
            "support_z": -0.016,
            "source": "serialized_surface_inner_bounds",
            "release_mode": "high_drop_into_compartment",
            "release_z_offset_m": 0.10,
            "release_z_tolerance_m": 0.04,
            "release_xy_margin_m": 0.012,
            "planner_support_z_m": 0.084,
        }

        opening = _caddy_compartment_opening_from_scene(scene, surface, surface_label, serialized_opening)

        self.assertEqual(obj, "akita_black_bowl_1_main")
        self.assertEqual(surface, "desk_caddy_1_main")
        self.assertEqual(surface_label, "desk_caddy_1_main_front_inner_floor")
        self.assertIsNone(opening)

    def test_caddy_compartment_prefers_serialized_pack_opening(self):
        scene = _scene_with_desk_caddy_sites()
        serialized_opening = {
            "x_min": -0.321,
            "x_max": -0.271,
            "y_min": -0.111,
            "y_max": -0.051,
            "support_z": 0.912,
            "surface_label": "desk_caddy_1_main_front_inner_floor",
            "source": "serialized_surface_inner_bounds",
            "inner_bounds_source": "libero90_desk_caddy_site_bounds",
            "source_site_name": "desk_caddy_1_front_contain_region",
            "release_mode": "high_drop_into_compartment",
        }

        opening = _caddy_compartment_opening_from_scene(
            scene,
            "desk_caddy_1_main",
            "desk_caddy_1_main_front_inner_floor",
            serialized_opening,
        )

        self.assertIsNotNone(opening)
        assert opening is not None
        self.assertEqual(opening["source"], "caddy_compartment_serialized")
        self.assertEqual(opening["executor_opening_source"], "serialized_planner_opening")
        self.assertEqual(opening["source_opening_source"], "serialized_surface_inner_bounds")
        self.assertEqual(opening["compartment"], "front")
        self.assertAlmostEqual(opening["x_min"], -0.321)
        self.assertAlmostEqual(opening["x_max"], -0.271)
        self.assertAlmostEqual(opening["y_min"], -0.111)
        self.assertAlmostEqual(opening["y_max"], -0.051)
        self.assertAlmostEqual(opening["support_z"], 0.912)

    def test_caddy_compartment_rejects_unconverted_serialized_pack_opening(self):
        scene = _scene_with_desk_caddy_sites()
        serialized_opening = {
            "x_min": 0.299,
            "x_max": 0.404,
            "y_min": -0.328,
            "y_max": -0.171,
            "support_z": -0.016,
            "surface_label": "desk_caddy_1_main_front_inner_floor",
            "source": "serialized_surface_inner_bounds",
            "coordinate_frame": "planner_frame",
            "inner_bounds_source": "libero90_desk_caddy_site_bounds",
            "source_site_name": "desk_caddy_1_front_contain_region",
        }

        opening = _caddy_compartment_opening_from_scene(
            scene,
            "desk_caddy_1_main",
            "desk_caddy_1_main_front_inner_floor",
            serialized_opening,
        )

        self.assertIsNone(opening)

    def test_caddy_compartment_pack_and_executor_serialized_opening_parity(self):
        scene = _scene_with_desk_caddy_sites()
        source = scene.objects["desk_caddy_1_main"]
        hint = _desk_caddy_geometry_hint()

        for compartment in ("front", "left"):
            proxy_name = f"desk_caddy_1_main_{compartment}_inner_floor"
            planner_surface = _virtual_inner_floor_surface(proxy_name, source, scene, hint)
            planner_inner = dict(planner_surface.geometry["metadata"]["inner_bounds"])
            serialized_opening = _serialized_opening_from_virtual_surface(planner_surface)

            executor_opening = _caddy_compartment_opening_from_scene(
                scene,
                "desk_caddy_1_main",
                proxy_name,
                serialized_opening,
            )
            self.assertIsNotNone(executor_opening)
            assert executor_opening is not None
            self.assertEqual(executor_opening["source"], "caddy_compartment_serialized")
            self.assertEqual(executor_opening["executor_opening_source"], "serialized_planner_opening")
            self.assertEqual(serialized_opening["inner_bounds_source"], "libero90_desk_caddy_site_bounds")

            for key in ("x_min", "x_max", "y_min", "y_max", "support_z"):
                self.assertAlmostEqual(float(executor_opening[key]), float(planner_inner[key]), places=6)

    def test_desk_caddy_inner_floor_missing_adapter_records_warning_metadata(self):
        scene = _scene_with_desk_caddy_sites()
        source = scene.objects["desk_caddy_1_main"]
        hint = _desk_caddy_geometry_hint()
        hint.pop("geometry_profile_adapter_path")

        surface = _virtual_inner_floor_surface("desk_caddy_1_main_front_inner_floor", source, scene, hint)
        metadata = dict(surface.geometry["metadata"])

        self.assertEqual(metadata["inner_bounds_source"], "geometry_inner_bounds_or_aabb_crop")
        self.assertEqual(
            metadata["geometry_profile_adapter_warning"],
            "desk_caddy_compartment_geometry_adapter_missing",
        )
        self.assertEqual(metadata["geometry_profile"], "desk_caddy_compartment_inner_floor_v1")

    def test_caddy_compartment_crop_does_not_touch_non_caddy_regions(self):
        opening = _caddy_compartment_opening_from_scene(
            _scene(),
            "plate_1_main",
            "kitchen_table_plate_right_region",
            {
                "x_min": -0.1,
                "x_max": 0.1,
                "y_min": -0.1,
                "y_max": 0.1,
                "support_z": 0.0,
            },
        )

        self.assertIsNone(opening)

    def test_footprint_containment_delta_uses_edge_translation(self):
        delta, details = _footprint_containment_delta(
            {"x_min": 0.04, "x_max": 0.06, "y_min": -0.01, "y_max": 0.01},
            {"x_min": -0.03, "x_max": 0.03, "y_min": -0.03, "y_max": 0.03},
        )

        np.testing.assert_allclose(delta, np.asarray([-0.03, 0.0], dtype=np.float32), atol=1e-6)
        self.assertEqual(details["axes"]["x"]["reason"], "max_outside")
        self.assertGreater(float(details["footprint_violation_m"]), 0.0)
        self.assertEqual(float(details["residual_after_delta_m"]), 0.0)

    def test_footprint_containment_delta_centers_oversize_axis(self):
        delta, details = _footprint_containment_delta(
            {"x_min": -0.05, "x_max": 0.05, "y_min": -0.01, "y_max": 0.01},
            {"x_min": -0.03, "x_max": 0.03, "y_min": -0.03, "y_max": 0.03},
        )

        np.testing.assert_allclose(delta, np.asarray([0.0, 0.0], dtype=np.float32), atol=1e-6)
        self.assertEqual(details["axes"]["x"]["reason"], "oversize_center")
        self.assertEqual(details["oversize_axes"], ["x"])
        self.assertFalse(details["fits"])
        self.assertGreater(float(details["residual_after_delta_m"]), 0.0)

    def test_footprint_center_alignment_delta_prefers_center_over_edge_delta(self):
        delta, details = _footprint_center_alignment_delta(
            {"x_min": -0.03, "x_max": -0.01, "y_min": -0.02, "y_max": 0.00},
            {"x_min": -0.05, "x_max": 0.05, "y_min": -0.05, "y_max": 0.05},
            center_tolerance_m=0.006,
        )

        np.testing.assert_allclose(delta, np.asarray([0.02, 0.01], dtype=np.float32), atol=1e-6)
        self.assertTrue(details["contained"])
        self.assertFalse(details["centered"])
        self.assertTrue(details["centered_after_delta"])
        self.assertLessEqual(float(details["center_dist_after_delta_m"]), 1e-6)
        self.assertEqual(details["alignment_policy"], "footprint_center_and_containment")

    def test_caddy_held_object_xy_align_runs_after_yaw_at_hover_height(self):
        cfg = LiberoRobotClientConfig(
            place_held_object_xy_align=True,
            place_align_reached_m=0.006,
            place_align_center_tolerance_m=0.006,
            place_align_step_clip_m=0.020,
            place_align_max_iters=4,
            place_align_max_steps_per_iter=8,
        )
        scene = SceneState(
            ee_pos=np.asarray([0.0, 0.0, 1.20], dtype=np.float32),
            ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
            gripper_qpos=np.asarray([0.0, 0.0], dtype=np.float32),
            objects={
                "black_book_1_main": ObjectState(
                    name="black_book_1_main",
                    pos=np.asarray([0.05, 0.0, 0.98], dtype=np.float32),
                    quat=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                    geometry={
                        "source": "unit_test",
                        "geoms": [
                            {
                                "shape": "box",
                                "pos": [0.05, 0.0, 0.98],
                                "quat": [1.0, 0.0, 0.0, 0.0],
                                "size": [0.01, 0.01, 0.02],
                                "collision_active": True,
                            }
                        ],
                    },
                )
            },
        )
        opening = {
            "x_min": -0.03,
            "x_max": 0.03,
            "y_min": -0.03,
            "y_max": 0.03,
            "support_z": 0.94,
            "source": "caddy_compartment_aabb_crop",
            "surface_label": "desk_caddy_1_main_front_inner_floor",
        }
        client = _HeldObjectAlignClient(scene, cfg, "black_book_1_main")

        result, remaining = _execute_place_held_object_xy_align(
            client,
            "black_book_1_main",
            "desk_caddy_1_main",
            "desk_caddy_1_main_front_inner_floor",
            opening,
            np.asarray([0.0, 0.0], dtype=np.float32),
            cfg.gripper_close_value,
            50,
            "Place(black_book_1_main, grasp1, pose1, desk_caddy_1_main_front_inner_floor, q2)",
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["alignment_mode"], "footprint_center_and_containment")
        self.assertLessEqual(float(result["final_footprint_violation_m"]), 0.006)
        self.assertTrue(result["footprint_centered"])
        self.assertLessEqual(float(result["final_footprint_center_xy_dist"]), cfg.place_align_center_tolerance_m)
        footprint = result["object_footprint_xy"]
        safe = result["safe_opening_xy"]
        self.assertIsNotNone(footprint)
        self.assertIsNotNone(safe)
        assert footprint is not None
        assert safe is not None
        self.assertGreaterEqual(float(footprint["x_min"]), float(safe["x_min"]) - 1e-6)
        self.assertLessEqual(float(footprint["x_max"]), float(safe["x_max"]) + 1e-6)
        self.assertGreaterEqual(float(footprint["y_min"]), float(safe["y_min"]) - 1e-6)
        self.assertLessEqual(float(footprint["y_max"]), float(safe["y_max"]) + 1e-6)
        self.assertAlmostEqual(float(client.scene.ee_pos[2]), 1.20, places=5)
        self.assertTrue(client.labels)
        self.assertTrue(all(label.endswith(":held_object_xy_align") for label in client.labels))
        self.assertLess(remaining, 50)
        for iteration in result["iterations"]:
            if "step_xy_m" in iteration:
                self.assertLessEqual(float(iteration["step_xy_m"]), 0.020 + 1e-6)

    def test_caddy_footprint_align_does_not_stop_on_uncontained_tolerance(self):
        cfg = LiberoRobotClientConfig(
            place_held_object_xy_align=True,
            place_align_reached_m=0.006,
            place_align_center_tolerance_m=0.006,
            place_align_step_clip_m=0.006,
            place_align_max_iters=8,
            place_align_max_steps_per_iter=8,
        )
        scene = SceneState(
            ee_pos=np.asarray([0.0, 0.0, 1.20], dtype=np.float32),
            ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
            gripper_qpos=np.asarray([0.0, 0.0], dtype=np.float32),
            objects={
                "black_book_1_main": ObjectState(
                    name="black_book_1_main",
                    pos=np.asarray([0.0, 0.042, 0.98], dtype=np.float32),
                    quat=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                    geometry={
                        "source": "unit_test",
                        "geoms": [
                            {
                                "shape": "box",
                                "pos": [0.0, 0.042, 0.98],
                                "quat": [1.0, 0.0, 0.0, 0.0],
                                "size": [0.01, 0.003, 0.02],
                                "collision_active": True,
                            }
                        ],
                    },
                )
            },
        )
        opening = {
            "x_min": -0.05,
            "x_max": 0.05,
            "y_min": -0.05,
            "y_max": 0.05,
            "support_z": 0.94,
            "source": "caddy_compartment_aabb_crop",
            "surface_label": "desk_caddy_1_main_front_inner_floor",
        }
        client = _HeldObjectAlignClient(scene, cfg, "black_book_1_main")

        result, _remaining = _execute_place_held_object_xy_align(
            client,
            "black_book_1_main",
            "desk_caddy_1_main",
            "desk_caddy_1_main_front_inner_floor",
            opening,
            np.asarray([0.0, 0.0], dtype=np.float32),
            cfg.gripper_close_value,
            50,
            "Place(black_book_1_main, grasp1, pose1, desk_caddy_1_main_front_inner_floor, q2)",
        )

        self.assertTrue(result["executed"])
        self.assertEqual(result["alignment_mode"], "footprint_center_and_containment")
        self.assertTrue(result["footprint_contained"])
        self.assertTrue(result["footprint_centered"])
        self.assertLessEqual(float(result["final_footprint_violation_m"]), 1e-6)
        self.assertLessEqual(float(result["final_footprint_center_xy_dist"]), cfg.place_align_center_tolerance_m)
        self.assertEqual(result["iterations"][0]["alignment_mode"], "footprint_center_and_containment")
        self.assertNotIn("skipped", result["iterations"][0])

    def test_caddy_footprint_align_reports_failure_when_uncontained(self):
        cfg = LiberoRobotClientConfig(
            place_held_object_xy_align=True,
            place_align_reached_m=0.006,
            place_align_step_clip_m=0.020,
            place_align_max_iters=1,
            place_align_max_steps_per_iter=8,
        )
        scene = SceneState(
            ee_pos=np.asarray([0.0, 0.0, 1.20], dtype=np.float32),
            ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
            gripper_qpos=np.asarray([0.0, 0.0], dtype=np.float32),
            objects={
                "black_book_1_main": ObjectState(
                    name="black_book_1_main",
                    pos=np.asarray([0.0, 0.0, 0.98], dtype=np.float32),
                    quat=np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                    geometry={
                        "source": "unit_test",
                        "geoms": [
                            {
                                "shape": "box",
                                "pos": [0.0, 0.0, 0.98],
                                "quat": [1.0, 0.0, 0.0, 0.0],
                                "size": [0.08, 0.01, 0.02],
                                "collision_active": True,
                            }
                        ],
                    },
                )
            },
        )
        opening = {
            "x_min": -0.05,
            "x_max": 0.05,
            "y_min": -0.05,
            "y_max": 0.05,
            "support_z": 0.94,
            "source": "caddy_compartment_aabb_crop",
            "surface_label": "desk_caddy_1_main_front_inner_floor",
        }
        client = _HeldObjectAlignClient(scene, cfg, "black_book_1_main")

        result, _remaining = _execute_place_held_object_xy_align(
            client,
            "black_book_1_main",
            "desk_caddy_1_main",
            "desk_caddy_1_main_front_inner_floor",
            opening,
            np.asarray([0.0, 0.0], dtype=np.float32),
            cfg.gripper_close_value,
            50,
            "Place(black_book_1_main, grasp1, pose1, desk_caddy_1_main_front_inner_floor, q2)",
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "place_footprint_oversize")
        self.assertFalse(result["footprint_contained"])
        self.assertFalse(result["footprint_fits"])

    def test_recovery_hint_config_accepts_closed_loop_place_alignment(self):
        cfg = client_config_from_recovery_hints(
            {
                "params": {
                    "executor": {
                        "place_held_object_xy_align": True,
                        "place_align_reached_m": 0.0015,
                        "place_align_center_tolerance_m": 0.006,
                        "place_footprint_release_tolerance_m": 0.001,
                        "place_align_step_clip_m": 0.006,
                        "place_align_max_iters": 8,
                        "place_align_max_steps_per_iter": 8,
                        "place_align_retry_lift_m": 0.015,
                        "place_align_retry_lift_max_steps": 10,
                        "place_drop_closed_loop_align": True,
                        "place_drop_align_slices": 3,
                    }
                }
            }
        )

        self.assertIsNotNone(cfg)
        assert cfg is not None
        self.assertTrue(cfg.place_held_object_xy_align)
        self.assertAlmostEqual(cfg.place_align_reached_m, 0.0015)
        self.assertAlmostEqual(cfg.place_align_center_tolerance_m, 0.006)
        self.assertAlmostEqual(cfg.place_footprint_release_tolerance_m, 0.001)
        self.assertAlmostEqual(cfg.place_align_step_clip_m, 0.006)
        self.assertEqual(cfg.place_align_max_iters, 8)
        self.assertEqual(cfg.place_align_max_steps_per_iter, 8)
        self.assertAlmostEqual(cfg.place_align_retry_lift_m, 0.015)
        self.assertEqual(cfg.place_align_retry_lift_max_steps, 10)
        self.assertTrue(cfg.place_drop_closed_loop_align)
        self.assertEqual(cfg.place_drop_align_slices, 3)

    def test_book_caddy_release_rejects_center_misaligned_footprint(self):
        cfg = LiberoRobotClientConfig(place_align_center_tolerance_m=0.006)
        details = {
            "z_ok": True,
            "in_opening": True,
            "release_mode": "high_drop_into_compartment",
            "requires_footprint_release": True,
            "footprint_contained": True,
            "footprint_center_xy_dist": 0.018,
            "in_release_opening": True,
        }

        self.assertFalse(_place_release_accepts(details, cfg))

    def test_tiny_shrunk_opening_releases_when_center_is_in_plate(self):
        cfg = LiberoRobotClientConfig()
        details = {
            "z_ok": True,
            "in_opening": True,
            "in_shrunk": False,
            "xy_dist": 0.015,
            "shrunk_opening": {
                "x_min": -0.025,
                "x_max": -0.011,
                "y_min": -0.018,
                "y_max": -0.004,
                "shrunk": True,
            },
        }
        self.assertLess(_shrunk_span_m(details["shrunk_opening"]), cfg.place_drop_align_xy_m)
        self.assertTrue(_place_release_accepts(details, cfg))

    def test_lift_target_uses_hover_clearance_not_rim(self):
        cfg = LiberoRobotClientConfig()
        lift_z = _place_lift_target_z(ee_z=0.964, surf_top=0.919, hanging=0.0425, cfg=cfg)
        self.assertGreater(lift_z - 0.964, cfg.place_hover_reached_m)
        self.assertAlmostEqual(lift_z, 0.919 + cfg.place_hover_clearance_m + 0.0425, places=4)

    def test_held_transfer_hint_lifts_and_blocks_descent(self):
        cfg = client_config_from_recovery_hints(
            {
                "params": {
                    "executor": {
                        "held_transfer_keep_z": True,
                        "held_transfer_z_margin_m": 0.02,
                        "held_transfer_max_descent_m": 0.0,
                        "held_transfer_max_steps": 45,
                        "held_transfer_reached_m": 0.006,
                    }
                }
            }
        )

        self.assertIsNotNone(cfg)
        assert cfg is not None
        self.assertTrue(cfg.held_transfer_keep_z)
        self.assertEqual(cfg.held_transfer_max_steps, 45)
        self.assertAlmostEqual(_held_transfer_protected_z(0.55, 0.48, cfg), 0.57, places=5)
        self.assertAlmostEqual(_held_transfer_protected_z(0.55, 0.60, cfg), 0.60, places=5)


class GraspNearTests(unittest.TestCase):
    def test_near_rim_is_close_enough(self):
        cfg = LiberoRobotClientConfig()
        near, details = _ee_near_grasp_target(_scene(), "akita_black_bowl_1_main", cfg)
        self.assertTrue(near)
        self.assertLessEqual(details["xy_m"], details["max_xy_m"])

    def test_pick_reach_is_tighter_than_generic_near_goal(self):
        cfg = LiberoRobotClientConfig()
        self.assertLess(cfg.pick_reach_position_m, cfg.near_goal_position_m)

    def test_far_ee_skips_close(self):
        cfg = LiberoRobotClientConfig()
        near, _ = _ee_near_grasp_target(_scene(ee=(0.40, 0.40, 0.30)), "akita_black_bowl_1_main", cfg)
        self.assertFalse(near)


class RecoveryEntryLiftTests(unittest.TestCase):
    def test_entry_lift_only_commands_z_without_rotation(self):
        env = _EntryLiftEnv()
        callbacks = []
        cfg = LiberoRobotClientConfig(
            recovery_entry_lift_m=0.045,
            recovery_entry_lift_max_steps=12,
            recovery_entry_lift_reached_m=0.006,
            recovery_entry_lift_gripper_value=0.0,
        )

        obs, event = execute_recovery_entry_lift(
            env,
            env.obs,
            client_cfg=cfg,
            max_env_steps=12,
            step_callback=lambda obs, meta: callbacks.append(meta),
        )

        self.assertTrue(event["executed"])
        self.assertTrue(event["success"])
        self.assertGreaterEqual(event["ee_lift_m"], 0.039)
        self.assertLess(event["xy_shift_m"], 1e-6)
        self.assertAlmostEqual(float(obs["robot0_eef_pos"][0]), 0.1, places=6)
        self.assertAlmostEqual(float(obs["robot0_eef_pos"][1]), -0.2, places=6)
        self.assertTrue(env.actions)
        for action in env.actions:
            self.assertEqual(action[:2], [0.0, 0.0])
            self.assertEqual(action[3:6], [0.0, 0.0, 0.0])
            self.assertEqual(action[6], 0.0)
        self.assertTrue(callbacks)
        self.assertEqual(callbacks[0]["label"], "recovery_entry_lift")
        self.assertEqual(callbacks[0]["phase"], "recovery_entry_lift")

    def test_entry_retreat_direction_moves_away_from_nearest_cabinet(self):
        scene = SceneState(
            ee_pos=np.asarray([0.10, 0.02, 0.48], dtype=np.float32),
            ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
            gripper_qpos=np.asarray([0.04, -0.04], dtype=np.float32),
            objects={
                "white_cabinet_1_main": ObjectState(
                    name="white_cabinet_1_main",
                    pos=np.asarray([0.04, 0.02, 0.42], dtype=np.float32),
                ),
                "akita_black_bowl_1_main": ObjectState(
                    name="akita_black_bowl_1_main",
                    pos=np.asarray([0.25, 0.02, 0.42], dtype=np.float32),
                ),
            },
        )

        direction, details = _entry_retreat_direction_xy(scene)

        self.assertGreater(direction[0], 0.99)
        self.assertAlmostEqual(float(direction[1]), 0.0, places=5)
        self.assertEqual(details["blocker_name"], "white_cabinet_1_main")
        self.assertEqual(details["strategy"], "away_from_nearest_drawer_or_cabinet")

    def test_target_side_stage_moves_near_black_bowl_from_cabinet_side(self):
        scene = SceneState(
            ee_pos=np.asarray([0.05, 0.00, 0.58], dtype=np.float32),
            ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
            gripper_qpos=np.asarray([0.04, -0.04], dtype=np.float32),
            objects={
                "white_cabinet_1_main": ObjectState(
                    name="white_cabinet_1_main",
                    pos=np.asarray([0.14, 0.16, 0.42], dtype=np.float32),
                ),
                "akita_black_bowl_1_main": ObjectState(
                    name="akita_black_bowl_1_main",
                    pos=np.asarray([0.03, -0.04, 0.42], dtype=np.float32),
                ),
            },
        )

        goal, details = _entry_stage_target_from_spec(
            scene,
            {"kind": "target_side_stage", "stand_off_m": 0.11, "max_xy_motion_m": 0.18},
        )

        self.assertAlmostEqual(float(goal[2]), 0.58, places=5)
        self.assertEqual(details["target"]["target_name"], "akita_black_bowl_1_main")
        self.assertLess(float(goal[1]), -0.04)

    def test_two_step_escape_profile_declares_two_staging_steps(self):
        cfg = LiberoRobotClientConfig(recovery_entry_escape_profile="two_step_escape")
        plan = _entry_escape_plan_from_config(cfg)

        self.assertEqual(plan["profile"], "two_step_escape")
        self.assertEqual(len(plan["steps"]), 2)
        self.assertEqual(plan["steps"][0]["kind"], "away_blocker")
        self.assertEqual(plan["steps"][1]["kind"], "target_side_stage")


class ConfirmedHoldingLatchTests(unittest.TestCase):
    def test_lift_probe_latch_makes_closed_gripper_holding(self):
        latch = {}
        _set_confirmed_holding_latch(
            latch,
            "akita_black_bowl_1_main",
            source="lift_probe",
            label="Pick(akita_black_bowl_1_main, grasp1, q1)",
            snapshot={"object_followed": True, "object_lift_m": 0.02},
        )
        scene = _scene(gripper_qpos=(0.002, -0.002))

        self.assertTrue(_apply_confirmed_holding_latch(scene, latch))
        self.assertEqual(scene.holding_evidence["status"], "holding")
        self.assertEqual(scene.holding_evidence["object_name"], "akita_black_bowl_1_main")
        self.assertTrue(scene.holding_evidence["latched"])
        self.assertTrue(
            goal_satisfied(
                scene,
                [{"predicate": "holding", "args": ["akita_black_bowl_1_main"]}],
            ).ok
        )

    def test_open_gripper_clears_latch(self):
        latch = {"active": True, "object_name": "akita_black_bowl_1_main"}
        scene = _scene(gripper_qpos=(0.04, -0.04))

        self.assertFalse(_apply_confirmed_holding_latch(scene, latch))
        self.assertFalse(latch["active"])
        self.assertEqual(latch["clear_reason"], "gripper_open")

    def test_pick_preserves_closed_when_latch_is_active(self):
        cfg = LiberoRobotClientConfig()
        self.assertEqual(_gripper_hold_value("Pick(obj, grasp1, q1)", False, cfg), cfg.gripper_open_value)
        self.assertEqual(
            _gripper_hold_value("Pick(obj, grasp1, q1)", False, cfg, preserve_closed=True),
            cfg.gripper_close_value,
        )


class PlaceHoverYawTests(unittest.TestCase):
    def test_nearest_yaw_picks_the_shorter_world_z_turn(self):
        target, delta = _nearest_signed_yaw_delta(-112.0 * np.pi / 180.0, (0.0, np.pi))
        self.assertAlmostEqual(abs(target), np.pi, places=6)
        self.assertLess(abs(delta), 1.3)
        self.assertGreater(abs(delta), 1.0)

    def test_world_z_yaw_keeps_roll_pitch_and_only_changes_heading(self):
        start = np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        rotated = _apply_world_yaw_to_quat_xyzw(start, 0.5 * np.pi)
        again = _apply_world_yaw_to_quat_xyzw(rotated, -0.5 * np.pi)
        self.assertTrue(np.allclose(np.abs(again), np.abs(start), atol=1e-5) or np.allclose(again, start, atol=1e-5))
        waypoints = _world_z_yaw_pose_waypoints(np.array([0.1, -0.2, 1.0]), start, 0.48, 0.16)
        self.assertEqual(len(waypoints), 3)
        self.assertEqual(waypoints[0]["position"], [0.1, -0.2, 1.0])

    def test_thin_horizontal_yaw_follows_local_x_when_that_edge_is_thinner(self):
        yaw = 35.0 * np.pi / 180.0
        cosine, sine = float(np.cos(yaw / 2.0)), float(np.sin(yaw / 2.0))
        quat_wxyz = np.asarray([cosine, 0.0, 0.0, sine], dtype=np.float32)
        scene = SceneState(
            ee_pos=np.zeros(3, dtype=np.float32),
            ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
            gripper_qpos=np.asarray([0.0, 0.0], dtype=np.float32),
            objects={
                "black_book_1_main": ObjectState(
                    name="black_book_1_main",
                    pos=np.asarray([-0.4, -0.2, 1.0], dtype=np.float32),
                    quat=quat_wxyz,
                    geometry={"geoms": [{"shape": "box", "size": [0.014, 0.055, 0.067]}]},
                )
            },
        )
        got = _object_thin_horizontal_yaw(scene, "black_book_1_main")
        self.assertIsNotNone(got)
        self.assertLess(abs(_wrap_yaw_rad(got - yaw)), 0.05)

    def test_hover_yaw_skips_when_policy_is_off(self):
        result = _rotate_held_object_world_z_yaw(
            client=type("C", (), {"cfg": LiberoRobotClientConfig()})(),
            obj_name="black_book_1_main",
            gripper=1.0,
            remaining_steps=40,
            label="Place(...)",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["skipped"], "policy_off")
        self.assertEqual(result["env_steps"], 0)


if __name__ == "__main__":
    unittest.main()
