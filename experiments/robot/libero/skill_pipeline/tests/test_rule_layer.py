from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

import numpy as np

from experiments.robot.libero.tiptop_repro.affordances import (
    is_probably_articulated,
    is_top_support_surface,
    is_virtual_support_surface,
    object_affordances,
)
from experiments.robot.libero.tiptop_repro.bddl_goals import map_bddl_name_to_scene, parse_bddl_task_goals
from experiments.robot.libero.tiptop_repro.cutamp_domain import build_action_schemas
from experiments.robot.libero.tiptop_repro.predicates import build_symbolic_state
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import (
    _collision_parts_with_filter_debug,
    _exclude_target_support_surface_collision,
    _grasp_6dof_xyzrpy_for_profile,
    _goal_on_target_support_surface_names,
)
from experiments.robot.libero.tiptop_repro.grasp_profiles import (
    GRASP_PROFILE_ADAPTER_PARAM_KEY,
    load_grasp_profile_registry,
)
from experiments.robot.libero.tiptop_repro.real_cutamp_adapter import (
    build_recovery_goal_candidates,
    resolve_skill_goal_surface,
)
from experiments.robot.libero.tiptop_repro.scene_graph import build_scene_graph
from experiments.robot.libero.tiptop_repro.scene_reader import ObjectState, SceneState
from experiments.robot.libero.tiptop_repro.tamp_scene import (
    GroundedAtom,
    TAMPObject,
    TAMPProblem,
    _shift_geometry_to_robot_base,
    _virtual_surface_from_descriptor,
    build_tamp_problem,
)
from experiments.robot.libero.tiptop_repro.task_parser import parse_task
from experiments.robot.libero.tiptop_repro.task_semantics import (
    RuleTaskSemanticsInterpreter,
    TaskSemanticsResult,
    build_rule_layer_record,
)


REPO_ROOT = Path(__file__).resolve().parents[5]
LIBERO90_GRASP_ADAPTER = REPO_ROOT / "skill_packs" / "libero90_legacy" / "code" / "grasp_profiles.py"
LIBERO90_GROUNDING_ADAPTER = REPO_ROOT / "skill_packs" / "libero90_legacy" / "code" / "grounding_profiles.py"
LIBERO90_GEOMETRY_ADAPTER = REPO_ROOT / "skill_packs" / "libero90_legacy" / "code" / "geometry_profiles.py"


KITCHEN_SCENE2_NAMES = [
    "akita_black_bowl_1_main",
    "akita_black_bowl_2_main",
    "akita_black_bowl_3_main",
    "plate_1_main",
    "wooden_cabinet_1_main",
    "wooden_cabinet_1_cabinet_top",
    "wooden_cabinet_1_cabinet_middle",
    "wooden_cabinet_1_cabinet_bottom",
    "ketchup_1_main",
]

BDDL_BACK = """
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:language put the black bowl at the back on the plate)
  (:obj_of_interest
    akita_black_bowl_3
    plate_1
  )
  (:goal
    (And (On akita_black_bowl_3 plate_1))
  )
)
"""

BDDL_FRONT = """
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:language put the black bowl at the front on the plate)
  (:obj_of_interest
    akita_black_bowl_1
    plate_1
  )
  (:goal
    (And (On akita_black_bowl_1 plate_1))
  )
)
"""

BDDL_MIDDLE = """
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:language put the middle black bowl on the plate)
  (:obj_of_interest
    akita_black_bowl_2
    plate_1
  )
  (:goal
    (And (On akita_black_bowl_2 plate_1))
  )
)
"""

BDDL_CABINET_TOP = """
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:language put the middle black bowl on top of the cabinet)
  (:obj_of_interest
    akita_black_bowl_2
    wooden_cabinet_1
  )
  (:goal
    (And (On akita_black_bowl_2 wooden_cabinet_1_top_side))
  )
)
"""

BDDL_STACK_FRONT_ON_MIDDLE = """
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:language stack the black bowl at the front on the black bowl in the middle)
  (:obj_of_interest
    akita_black_bowl_1
    akita_black_bowl_2
  )
  (:goal
    (And (On akita_black_bowl_1 akita_black_bowl_2))
  )
)
"""

BDDL_TOP_DRAWER = """
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:language put the ketchup in the top drawer of the cabinet)
  (:obj_of_interest
    ketchup_1
    wooden_cabinet_1
  )
  (:goal
    (And (Inside ketchup_1 wooden_cabinet_1))
  )
)
"""

BDDL_MUG_FRONT_REGION = """
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:language put the yellow and white mug to the front of the white mug)
  (:regions
    (porcelain_mug_front_region
      (:target kitchen_table)
      (:ranges ((-0.05 -0.3 0.05 -0.2)))
    )
  )
  (:obj_of_interest
    white_yellow_mug_1
    porcelain_mug_1
  )
  (:goal
    (And (On white_yellow_mug_1 kitchen_table_porcelain_mug_front_region))
  )
)
"""

BDDL_WHITE_BOWL_RIGHT_REGION = """
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:language put the white bowl to the right of the plate)
  (:regions
    (plate_right_region
      (:target kitchen_table)
      (:ranges ((-0.05 0.05 0.05 0.15)))
    )
  )
  (:obj_of_interest
    white_bowl_1
    plate_1
  )
  (:goal
    (And (On white_bowl_1 kitchen_table_plate_right_region))
  )
)
"""

BDDL_CHOCOLATE_PUDDING_LEFT_REGION = """
(define (problem LIBERO_Living_Room_Tabletop_Manipulation)
  (:language put the chocolate pudding to the left of the plate)
  (:regions
    (plate_left_region
      (:target living_room_table)
      (:ranges ((0.10 -0.15 0.20 -0.05)))
    )
    (plate_init_region
      (:target living_room_table)
      (:ranges ((0.10 -0.025 0.20 0.025)))
    )
    (pudding_init_region
      (:target living_room_table)
      (:ranges ((-0.10 0.12 0.00 0.22)))
    )
  )
  (:init
    (On plate_1 living_room_table_plate_init_region)
    (On chocolate_pudding_1 living_room_table_pudding_init_region)
  )
  (:obj_of_interest
    chocolate_pudding_1
    plate_1
  )
  (:goal
    (And (On chocolate_pudding_1 living_room_table_plate_left_region))
  )
)
"""

BDDL_CREAM_CHEESE_IN_BASKET = """
(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:language pick up the cream cheese box and put it in the basket)
  (:obj_of_interest
    cream_cheese_1
    basket_1
  )
  (:goal
    (And (In cream_cheese_1 basket_1_contain_region))
  )
)
"""

BDDL_DESK_CADDY_FRONT_COMPARTMENT = """
(define (problem LIBERO_Study_Tabletop_Manipulation)
  (:language pick up the book and place it in the front compartment of the caddy)
  (:regions
    (front_contain_region
      (:target desk_caddy_1)
    )
  )
  (:fixtures
    study_table - study_table
    desk_caddy_1 - desk_caddy
  )
  (:objects
    black_book_1 - black_book
    white_yellow_mug_1 - white_yellow_mug
  )
  (:obj_of_interest
    black_book_1
    desk_caddy_1
  )
  (:goal
    (And (In black_book_1 desk_caddy_1_front_contain_region))
  )
)
"""

BDDL_DESK_CADDY_LEFT_COMPARTMENT = """
(define (problem LIBERO_Study_Tabletop_Manipulation)
  (:language pick up the book and place it in the left compartment of the caddy)
  (:regions
    (left_contain_region
      (:target desk_caddy_1)
    )
  )
  (:fixtures
    study_table - study_table
    desk_caddy_1 - desk_caddy
  )
  (:objects
    black_book_1 - black_book
    white_yellow_mug_1 - white_yellow_mug
  )
  (:obj_of_interest
    black_book_1
    desk_caddy_1
  )
  (:goal
    (And (In black_book_1 desk_caddy_1_left_contain_region))
  )
)
"""

BDDL_RED_MUG_RIGHT_OF_CADDY = """
(define (problem LIBERO_Study_Tabletop_Manipulation)
  (:language pick up the red mug and place it to the right compartment of the caddy)
  (:regions
    (desk_caddy_right_region
      (:target study_table)
      (:ranges ((0.10 -0.06 0.20 0.06)))
    )
    (desk_caddy_init_region
      (:target study_table)
      (:ranges ((-0.06 -0.05 0.06 0.05)))
    )
    (red_mug_init_region
      (:target study_table)
      (:ranges ((0.18 0.10 0.28 0.20)))
    )
  )
  (:fixtures
    study_table - study_table
    desk_caddy_1 - desk_caddy
  )
  (:objects
    red_coffee_mug_1 - red_coffee_mug
    porcelain_mug_1 - porcelain_mug
    black_book_1 - black_book
  )
  (:init
    (On desk_caddy_1 study_table_desk_caddy_init_region)
    (On red_coffee_mug_1 study_table_red_mug_init_region)
  )
  (:obj_of_interest
    red_coffee_mug_1
    desk_caddy_1
  )
  (:goal
    (And (On red_coffee_mug_1 study_table_desk_caddy_right_region))
  )
)
"""


def _scene() -> SceneState:
    objects = {
        "akita_black_bowl_1_main": ObjectState(
            name="akita_black_bowl_1_main",
            pos=np.asarray([0.12, 0.15, 0.03], dtype=np.float32),
        ),
        "akita_black_bowl_2_main": ObjectState(
            name="akita_black_bowl_2_main",
            pos=np.asarray([-0.05, 0.20, 0.03], dtype=np.float32),
        ),
        "akita_black_bowl_3_main": ObjectState(
            name="akita_black_bowl_3_main",
            pos=np.asarray([-0.15, 0.05, 0.03], dtype=np.float32),
        ),
        "plate_1_main": ObjectState(
            name="plate_1_main",
            pos=np.asarray([0.0, 0.0, 0.0], dtype=np.float32),
        ),
        "wooden_cabinet_1_main": ObjectState(
            name="wooden_cabinet_1_main",
            pos=np.asarray([0.0, -0.30, 0.10], dtype=np.float32),
        ),
        "wooden_cabinet_1_cabinet_top": ObjectState(
            name="wooden_cabinet_1_cabinet_top",
            pos=np.asarray([0.0, -0.30, 0.18], dtype=np.float32),
        ),
        "wooden_cabinet_1_cabinet_middle": ObjectState(
            name="wooden_cabinet_1_cabinet_middle",
            pos=np.asarray([0.0, -0.30, 0.05], dtype=np.float32),
        ),
        "wooden_cabinet_1_cabinet_bottom": ObjectState(
            name="wooden_cabinet_1_cabinet_bottom",
            pos=np.asarray([0.0, -0.30, -0.02], dtype=np.float32),
        ),
        "ketchup_1_main": ObjectState(
            name="ketchup_1_main",
            pos=np.asarray([0.18, 0.05, 0.06], dtype=np.float32),
        ),
    }
    return SceneState(
        ee_pos=np.asarray([0.0, 0.0, 0.20], dtype=np.float32),
        ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        gripper_qpos=np.asarray([0.04, -0.04], dtype=np.float32),
        objects=objects,
    )


def _mug_scene() -> SceneState:
    objects = {
        "white_yellow_mug_1_main": ObjectState(
            name="white_yellow_mug_1_main",
            pos=np.asarray([0.64, -0.03, 0.04], dtype=np.float32),
        ),
        "porcelain_mug_1_main": ObjectState(
            name="porcelain_mug_1_main",
            pos=np.asarray([0.58, -0.25, 0.04], dtype=np.float32),
        ),
        "microwave_1_main": ObjectState(
            name="microwave_1_main",
            pos=np.asarray([0.64, 0.32, 0.10], dtype=np.float32),
        ),
    }
    return SceneState(
        ee_pos=np.asarray([0.55, -0.05, 0.20], dtype=np.float32),
        ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        gripper_qpos=np.asarray([0.04, -0.04], dtype=np.float32),
        objects=objects,
    )


def _white_bowl_scene() -> SceneState:
    objects = {
        "white_bowl_1_main": ObjectState(
            name="white_bowl_1_main",
            pos=np.asarray([0.65, -0.27, 0.04], dtype=np.float32),
        ),
        "plate_1_main": ObjectState(
            name="plate_1_main",
            pos=np.asarray([0.64, -0.02, 0.01], dtype=np.float32),
        ),
        "microwave_1_main": ObjectState(
            name="microwave_1_main",
            pos=np.asarray([0.65, -0.25, 0.10], dtype=np.float32),
        ),
    }
    return SceneState(
        ee_pos=np.asarray([0.55, -0.08, 0.20], dtype=np.float32),
        ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        gripper_qpos=np.asarray([0.04, -0.04], dtype=np.float32),
        objects=objects,
    )


def _chocolate_pudding_plate_scene() -> SceneState:
    objects = {
        "chocolate_pudding_1_main": ObjectState(
            name="chocolate_pudding_1_main",
            pos=np.asarray([0.39, 0.15, 0.035], dtype=np.float32),
        ),
        "plate_1_main": ObjectState(
            name="plate_1_main",
            pos=np.asarray([0.64, -0.02, 0.01], dtype=np.float32),
        ),
        "living_room_table_1_main": ObjectState(
            name="living_room_table_1_main",
            pos=np.asarray([0.50, 0.00, 0.00], dtype=np.float32),
        ),
    }
    return SceneState(
        ee_pos=np.asarray([0.42, 0.15, 0.20], dtype=np.float32),
        ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        gripper_qpos=np.asarray([0.04, -0.04], dtype=np.float32),
        objects=objects,
    )


def _cream_cheese_basket_scene() -> SceneState:
    objects = {
        "cream_cheese_1_main": ObjectState(
            name="cream_cheese_1_main",
            pos=np.asarray([0.3445, 0.0438, 0.0257], dtype=np.float32),
            geometry={
                "source": "mujoco_geom",
                "geoms": [
                    {
                        "shape": "box",
                        "size": [0.008936, 0.021336, 0.040608],
                        "pos": [0.3445, 0.0438, 0.0257],
                        "quat": [0.0, 0.70710678, 0.0, -0.70710678],
                        "collision_active": True,
                    }
                ],
            },
        ),
        "basket_1_main": ObjectState(
            name="basket_1_main",
            pos=np.asarray([0.5023, 0.2545, 0.0522], dtype=np.float32),
            geometry={
                "source": "mujoco_geom",
                "geoms": [
                    {
                        "shape": "box",
                        "size": [0.080, 0.065, 0.040],
                        "pos": [0.5023, 0.2545, 0.0522],
                        "quat": [1.0, 0.0, 0.0, 0.0],
                        "collision_active": True,
                    }
                ],
            },
        ),
    }
    return SceneState(
        ee_pos=np.asarray([0.34, 0.04, 0.20], dtype=np.float32),
        ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        gripper_qpos=np.asarray([0.04, -0.04], dtype=np.float32),
        objects=objects,
    )


def _desk_caddy_scene() -> SceneState:
    objects = {
        "black_book_1_main": ObjectState(
            name="black_book_1_main",
            pos=np.asarray([0.53, 0.15, 0.02], dtype=np.float32),
            geometry={
                "source": "mujoco_geom",
                "geoms": [
                    {
                        "shape": "box",
                        "size": [0.050, 0.035, 0.010],
                        "pos": [0.53, 0.15, 0.02],
                        "quat": [1.0, 0.0, 0.0, 0.0],
                        "collision_active": True,
                    }
                ],
            },
        ),
        "desk_caddy_1_main": ObjectState(
            name="desk_caddy_1_main",
            pos=np.asarray([0.35, -0.14, 0.06], dtype=np.float32),
            geometry={
                "source": "mujoco_geom",
                "geoms": [
                    {
                        "shape": "box",
                        "size": [0.0755, 0.2169, 0.08345],
                        "pos": [0.35, -0.14, 0.06],
                        "quat": [1.0, 0.0, 0.0, 0.0],
                        "collision_active": True,
                    }
                ],
                "sites": [
                    {
                        "name": "desk_caddy_1_front_contain_region",
                        "shape": "box",
                        "size": [0.02775, 0.06216, 0.06046],
                        "pos": [0.319, -0.14, 0.04],
                        "quat": [1.0, 0.0, 0.0, 0.0],
                    },
                    {
                        "name": "desk_caddy_1_left_contain_region",
                        "shape": "box",
                        "size": [0.06196, 0.06216, 0.06046],
                        "pos": [0.35, 0.005, 0.06],
                        "quat": [1.0, 0.0, 0.0, 0.0],
                    },
                ],
            },
        ),
        "white_yellow_mug_1_main": ObjectState(
            name="white_yellow_mug_1_main",
            pos=np.asarray([0.55, -0.06, 0.04], dtype=np.float32),
        ),
    }
    return SceneState(
        ee_pos=np.asarray([0.50, 0.12, 0.20], dtype=np.float32),
        ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        gripper_qpos=np.asarray([0.04, -0.04], dtype=np.float32),
        objects=objects,
    )


def _red_mug_caddy_scene() -> SceneState:
    objects = {
        "red_coffee_mug_1_main": ObjectState(
            name="red_coffee_mug_1_main",
            pos=np.asarray([0.58, 0.13, 0.04], dtype=np.float32),
        ),
        "porcelain_mug_1_main": ObjectState(
            name="porcelain_mug_1_main",
            pos=np.asarray([0.49, -0.02, 0.04], dtype=np.float32),
        ),
        "black_book_1_main": ObjectState(
            name="black_book_1_main",
            pos=np.asarray([0.54, 0.22, 0.02], dtype=np.float32),
        ),
        "desk_caddy_1_main": ObjectState(
            name="desk_caddy_1_main",
            pos=np.asarray([0.35, -0.14, 0.06], dtype=np.float32),
        ),
        "study_table_1_main": ObjectState(
            name="study_table_1_main",
            pos=np.asarray([0.50, 0.00, 0.00], dtype=np.float32),
        ),
    }
    return SceneState(
        ee_pos=np.asarray([0.58, 0.13, 0.20], dtype=np.float32),
        ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        gripper_qpos=np.asarray([0.04, -0.04], dtype=np.float32),
        objects=objects,
    )


def run_rule_layer(language: str, bddl_text: str) -> dict:
    scene = _scene()
    parsed = parse_task(language, scene.objects.keys(), bddl_text=bddl_text)
    sym = build_symbolic_state(scene, parsed)
    graph = build_scene_graph(scene, parsed, sym)
    semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
    goals = build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph)
    return build_rule_layer_record(parsed, semantics, recovery_goals=goals)


class ParserHygieneTests(unittest.TestCase):
    def test_middle_does_not_bind_cabinet_without_bddl(self):
        parsed = parse_task("put the middle black bowl on the plate", KITCHEN_SCENE2_NAMES)
        self.assertNotEqual(parsed.target_hint, "wooden_cabinet_1_cabinet_middle")
        self.assertIn("bowl", str(parsed.target_hint))
        self.assertEqual(parsed.goal_hint, "plate_1_main")

    def test_back_does_not_bind_cabinet(self):
        parsed = parse_task("put the black bowl at the back on the plate", KITCHEN_SCENE2_NAMES)
        self.assertIn("bowl", str(parsed.target_hint))
        self.assertEqual(parsed.goal_hint, "plate_1_main")


class BddlGoalTests(unittest.TestCase):
    def test_map_suffix_main(self):
        self.assertEqual(
            map_bddl_name_to_scene("akita_black_bowl_3", KITCHEN_SCENE2_NAMES),
            "akita_black_bowl_3_main",
        )
        self.assertEqual(map_bddl_name_to_scene("plate_1", KITCHEN_SCENE2_NAMES), "plate_1_main")
        self.assertEqual(
            map_bddl_name_to_scene("wooden_cabinet_1_top_side", KITCHEN_SCENE2_NAMES),
            "wooden_cabinet_1_cabinet_top",
        )

    def test_parse_goal_on(self):
        parsed = parse_bddl_task_goals(BDDL_BACK)
        self.assertEqual(parsed["obj_of_interest"][0], "akita_black_bowl_3")
        self.assertEqual(parsed["goal_atoms"][0]["args"], ["akita_black_bowl_3", "plate_1"])

    def test_parse_goal_in_alias(self):
        parsed = parse_bddl_task_goals(BDDL_CREAM_CHEESE_IN_BASKET)
        self.assertEqual(parsed["goal_atoms"][0]["predicate"], "inside")
        self.assertEqual(parsed["goal_atoms"][0]["args"], ["cream_cheese_1", "basket_1_contain_region"])

    def test_parse_goal_in_front_compartment_region(self):
        parsed = parse_bddl_task_goals(BDDL_DESK_CADDY_FRONT_COMPARTMENT)
        self.assertEqual(parsed["goal_atoms"][0]["predicate"], "inside")
        self.assertEqual(
            parsed["goal_atoms"][0]["args"],
            ["black_book_1", "desk_caddy_1_front_contain_region"],
        )

    def test_parse_goal_in_left_compartment_region(self):
        parsed = parse_bddl_task_goals(BDDL_DESK_CADDY_LEFT_COMPARTMENT)
        self.assertEqual(parsed["goal_atoms"][0]["predicate"], "inside")
        self.assertEqual(
            parsed["goal_atoms"][0]["args"],
            ["black_book_1", "desk_caddy_1_left_contain_region"],
        )


class RuleLayerKitchenScene2Tests(unittest.TestCase):
    def test_back_bowl_is_three(self):
        record = run_rule_layer("put the black bowl at the back on the plate", BDDL_BACK)
        self.assertEqual(record["parser_target_hint"], "akita_black_bowl_1_main")
        self.assertEqual(record["target_name"], "akita_black_bowl_3_main")
        self.assertEqual(record["target_source"], "bddl")
        self.assertEqual(record["semantics_target"], "akita_black_bowl_3_main")
        self.assertEqual(record["semantics_goal"], "plate_1_main")
        atoms = [atom for goal in record["recovery_goals"] for atom in goal["atoms"]]
        self.assertIn({"predicate": "on", "args": ["akita_black_bowl_3_main", "plate_1_main"]}, atoms)

    def test_front_bowl_is_one(self):
        record = run_rule_layer("put the black bowl at the front on the plate", BDDL_FRONT)
        self.assertEqual(record["target_name"], "akita_black_bowl_1_main")
        self.assertEqual(record["target_source"], "bddl")
        atoms = [atom for goal in record["recovery_goals"] for atom in goal["atoms"]]
        self.assertIn({"predicate": "on", "args": ["akita_black_bowl_1_main", "plate_1_main"]}, atoms)

    def test_middle_bowl_is_two_not_cabinet(self):
        record = run_rule_layer("put the middle black bowl on the plate", BDDL_MIDDLE)
        self.assertNotEqual(record["parser_target_hint"], "wooden_cabinet_1_cabinet_middle")
        self.assertEqual(record["target_name"], "akita_black_bowl_2_main")
        self.assertEqual(record["semantics_target"], "akita_black_bowl_2_main")
        atoms = [atom for goal in record["recovery_goals"] for atom in goal["atoms"]]
        self.assertIn({"predicate": "on", "args": ["akita_black_bowl_2_main", "plate_1_main"]}, atoms)
        cabinet_goals = [
            atom
            for goal in record["recovery_goals"]
            for atom in goal["atoms"]
            if "cabinet_middle" in str(atom.get("args"))
        ]
        self.assertEqual(cabinet_goals, [])

    def test_cabinet_top_bddl_binding_is_preserved(self):
        record = run_rule_layer("put the middle black bowl on top of the cabinet", BDDL_CABINET_TOP)
        self.assertEqual(record["goal_source"], "bddl")
        self.assertEqual(record["goal_name"], "wooden_cabinet_1_cabinet_top")
        self.assertEqual(record["semantics_goal"], "wooden_cabinet_1_cabinet_top")
        self.assertIn(
            {"predicate": "on", "args": ["akita_black_bowl_2_main", "wooden_cabinet_1_cabinet_top"], "source": "task_semantics", "confidence": 1.0},
            record["required_final_atoms"],
        )
        self.assertEqual(record["recovery_goals"][0]["surface_names"], ["wooden_cabinet_1_cabinet_top"])
        self.assertEqual(
            record["recovery_goals"][0]["atoms"],
            [
                {"predicate": "on", "args": ["akita_black_bowl_2_main", "wooden_cabinet_1_cabinet_top"]},
                {"predicate": "handempty", "args": []},
            ],
        )

    def test_skill_grounding_hint_resolves_language_cabinet_body_to_top(self):
        scene = _scene()
        parsed = parse_task("put the middle black bowl on top of the cabinet", scene.objects.keys())
        resolved, grounding = resolve_skill_goal_surface(
            scene,
            parsed,
            "akita_black_bowl_2_main",
            "wooden_cabinet_1_main",
            {
                "params": {
                    "grounding_hints": {
                        "placement_surface": {
                            "intent": "top_support",
                            "object_class": "cabinet",
                            "prefer": ["*_cabinet_top"],
                            "avoid": ["*_cabinet_middle", "*_cabinet_bottom", "*_door", "*_handle"],
                            "fallback": ["*_main"],
                        }
                    }
                }
            },
        )
        self.assertEqual(resolved, "wooden_cabinet_1_cabinet_top")
        self.assertEqual(grounding["from"], "wooden_cabinet_1_main")
        self.assertEqual(grounding["to"], "wooden_cabinet_1_cabinet_top")

        unchanged, no_grounding = resolve_skill_goal_surface(
            scene,
            parsed,
            "akita_black_bowl_2_main",
            "wooden_cabinet_1_main",
            {},
        )
        self.assertEqual(unchanged, "wooden_cabinet_1_main")
        self.assertEqual(no_grounding, {})


class CabinetTopSupportTests(unittest.TestCase):
    def test_cabinet_top_is_place_on_support_surface(self):
        name = "wooden_cabinet_1_cabinet_top"
        aff = object_affordances(name)

        self.assertTrue(is_top_support_surface(name))
        self.assertIn("surface", aff)
        self.assertIn("top_support", aff)
        self.assertNotIn("container", aff)
        self.assertFalse(is_probably_articulated(name))

        schemas = build_action_schemas(_scene(), surface_names=[name])
        matching_place_on = [
            schema
            for schema in schemas
            if schema.name == "place_on" and schema.parameters == ["akita_black_bowl_2_main", name]
        ]
        matching_place_in = [
            schema
            for schema in schemas
            if schema.name == "place_in" and schema.parameters == ["akita_black_bowl_2_main", name]
        ]
        self.assertEqual(len(matching_place_on), 1)
        self.assertEqual(matching_place_in, [])
        self.assertTrue(matching_place_on[0].supported_by_executor)

    def test_on_goal_excludes_only_target_top_support_collision(self):
        target_surface = TAMPObject(
            name="wooden_cabinet_1_cabinet_top",
            pos=[0.0, 0.0, 0.2],
            radius=0.1,
            height=0.05,
            role="surface",
        )
        other_surface = TAMPObject(
            name="wooden_cabinet_1_cabinet_middle",
            pos=[0.0, 0.0, 0.1],
            radius=0.1,
            height=0.05,
            role="surface",
        )
        problem = TAMPProblem(
            movables=[],
            surfaces=[target_surface, other_surface],
            statics=[],
            goal_atoms=[
                GroundedAtom(
                    "on",
                    ("akita_black_bowl_2_main", "wooden_cabinet_1_cabinet_top"),
                )
            ],
        )

        target_supports = _goal_on_target_support_surface_names(problem)
        self.assertEqual(target_supports, {"wooden_cabinet_1_cabinet_top"})
        self.assertTrue(_exclude_target_support_surface_collision(target_surface, target_supports))
        self.assertFalse(_exclude_target_support_surface_collision(other_surface, target_supports))


class TopDrawerGroundingGeometryTests(unittest.TestCase):
    def _parsed_semantics(self):
        scene = _scene()
        parsed = parse_task(
            "put the ketchup in the top drawer of the cabinet",
            scene.objects.keys(),
            bddl_text=BDDL_TOP_DRAWER,
        )
        sym = build_symbolic_state(scene, parsed)
        graph = build_scene_graph(scene, parsed, sym)
        semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
        return scene, parsed, sym, graph, semantics

    def _hints(self):
        return {
            "params": {
                "grounding_hints": {
                    "placement_surface": {
                        "intent": "drawer_container",
                        "relation": "inside",
                        "object_class": "cabinet",
                        "drawer_level": "top",
                        "prefer": ["*_cabinet_top"],
                        "avoid": ["*_top_side", "*_cabinet_middle", "*_cabinet_bottom", "*_door", "*_handle"],
                        "fallback": ["*_main"],
                    }
                },
                "geometry_hints": {
                    "placement_region": {
                        "intent": "drawer_inner_floor",
                        "relation": "inside",
                        "object_class": "cabinet",
                        "drawer_level": "top",
                        "container_name_matches": ["*_cabinet_top"],
                        "proxy_suffix": "inner_floor",
                    }
                },
            }
        }

    def test_top_drawer_inside_goal_compiles_to_inner_floor_place_on(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        goals = build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
        proxy = "wooden_cabinet_1_cabinet_top_inner_floor"
        matching = [
            goal
            for goal in goals
            if goal.atoms
            and goal.atoms[0] == GroundedAtom("on", ("ketchup_1_main", proxy))
        ]

        self.assertTrue(matching)
        goal = matching[0]
        self.assertEqual(goal.surface_names, [proxy])
        self.assertEqual(goal.grounding["intent"], "drawer_inner_floor")
        self.assertEqual(goal.grounding["from"], "wooden_cabinet_1_cabinet_top")
        self.assertEqual(goal.grounding["surface_grounding"]["from"], "wooden_cabinet_1_main")

    def test_top_drawer_inner_floor_is_registered_as_place_on_surface(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        goal = next(
            item
            for item in build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
            if item.surface_names == ["wooden_cabinet_1_cabinet_top_inner_floor"]
        )
        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal.atoms,
            surface_names=goal.surface_names,
            init_atoms=graph.world_atoms,
            required_final_atoms=[{"predicate": atom.predicate, "args": list(atom.args)} for atom in goal.atoms],
            recovery_hints=hints,
        )
        proxy = "wooden_cabinet_1_cabinet_top_inner_floor"
        surfaces = {obj.name: obj for obj in problem.surfaces}

        self.assertIn(proxy, surfaces)
        self.assertTrue(is_virtual_support_surface(proxy))
        aff = object_affordances(proxy)
        self.assertIn("surface", aff)
        self.assertNotIn("container", aff)
        place_on = [
            schema
            for schema in problem.action_schemas
            if schema.name == "place_on" and schema.parameters == ["ketchup_1_main", proxy]
        ]
        self.assertEqual(len(place_on), 1)
        self.assertTrue(place_on[0].supported_by_executor)
        supports = _goal_on_target_support_surface_names(problem)
        self.assertEqual(supports, {proxy})
        self.assertTrue(_exclude_target_support_surface_collision(surfaces[proxy], supports))


class MugFrontRegionGroundingGeometryTests(unittest.TestCase):
    def _parsed_semantics(self):
        scene = _mug_scene()
        parsed = parse_task(
            "put the yellow and white mug to the front of the white mug",
            scene.objects.keys(),
            bddl_text=BDDL_MUG_FRONT_REGION,
        )
        sym = build_symbolic_state(scene, parsed)
        graph = build_scene_graph(scene, parsed, sym)
        semantics = TaskSemanticsResult(
            target_object="white_yellow_mug_1_main",
            goal_object="microwave_1_main",
            relevant_objects=["white_yellow_mug_1_main", "microwave_1_main"],
            task_atoms=[],
            required_final_atoms=[
                {
                    "predicate": "inside",
                    "args": ["white_yellow_mug_1_main", "microwave_1_main"],
                    "source": "task_semantics",
                    "confidence": 1.0,
                }
            ],
            task_progress={"requires_inside": True},
        )
        return scene, parsed, sym, graph, semantics

    def _hints(self):
        return {
            "grasp_profile": "mug_body_side_avoid_handle_v1",
            "params": {
                GRASP_PROFILE_ADAPTER_PARAM_KEY: str(LIBERO90_GRASP_ADAPTER),
                "grounding_hints": {
                    "placement_surface": {
                        "intent": "fixed_table_region",
                        "relation": "on",
                        "task_language_matches": [
                            "yellow and white mug.*front.*white mug|front.*white mug.*yellow and white mug"
                        ],
                        "target_name_matches": ["*mug*"],
                        "region_name": "kitchen_table_porcelain_mug_front_region",
                        "rewrite_misgrounded_goals": ["*microwave*"],
                    }
                },
                "geometry_hints": {
                    "placement_region": {
                        "intent": "fixed_table_rect",
                        "region_name": "kitchen_table_porcelain_mug_front_region",
                        "support_surface": "table",
                        "bounds_m": {"x_min": 0.60, "x_max": 0.70, "y_min": -0.30, "y_max": -0.20},
                        "thickness_m": 0.010,
                        "place_z_offset_m": 0.160,
                    }
                },
            },
        }

    def test_bddl_region_and_microwave_misbinding_rewrite_to_table_region(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        goals = build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
        region = "kitchen_table_porcelain_mug_front_region"
        matching = [
            goal
            for goal in goals
            if goal.atoms and goal.atoms[0] == GroundedAtom("on", ("white_yellow_mug_1_main", region))
        ]

        self.assertTrue(matching)
        goal = matching[0]
        self.assertEqual(goal.surface_names, [region])
        self.assertEqual(goal.grounding["intent"], "fixed_table_region")
        self.assertEqual(goal.grounding["compiled_predicate"], "on")

    def test_fixed_front_region_is_registered_as_place_on_surface(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        region = "kitchen_table_porcelain_mug_front_region"
        goal = next(
            item
            for item in build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
            if item.surface_names == [region]
        )
        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal.atoms,
            surface_names=goal.surface_names,
            init_atoms=graph.world_atoms,
            required_final_atoms=[{"predicate": atom.predicate, "args": list(atom.args)} for atom in goal.atoms],
            recovery_hints=hints,
        )
        surfaces = {obj.name: obj for obj in problem.surfaces}

        self.assertIn(region, surfaces)
        self.assertEqual(surfaces[region].geometry["kind"], "virtual_fixed_table_rect")
        candidates = problem.place_candidates[region]
        self.assertTrue(np.allclose(candidates[0][:2], np.asarray([0.65, -0.25], dtype=np.float32)))
        self.assertAlmostEqual(float(candidates[0][2]), float(problem.table_z + 0.160), places=5)
        place_on = [
            schema
            for schema in problem.action_schemas
            if schema.name == "place_on" and schema.parameters == ["white_yellow_mug_1_main", region]
        ]
        self.assertEqual(len(place_on), 1)
        supports = _goal_on_target_support_surface_names(problem)
        self.assertEqual(supports, {region})
        self.assertTrue(_exclude_target_support_surface_collision(surfaces[region], supports))
        mug_grasps = problem.grasps["white_yellow_mug_1_main"]
        self.assertTrue(mug_grasps)
        self.assertTrue(all(item.metadata.get("sampler") == "mug_body_side_avoid_handle_v1" for item in mug_grasps[:3]))


class WhiteBowlRightRegionGroundingGeometryTests(unittest.TestCase):
    def _parsed_semantics(self):
        scene = _white_bowl_scene()
        parsed = parse_task(
            "put the white bowl to the right of the plate",
            scene.objects.keys(),
            bddl_text=BDDL_WHITE_BOWL_RIGHT_REGION,
        )
        sym = build_symbolic_state(scene, parsed)
        graph = build_scene_graph(scene, parsed, sym)
        semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
        return scene, parsed, sym, graph, semantics

    def _hints(self):
        return {
            "grasp_profile": "bowl_rim_small_shallow_diagonal_topdown_v1",
            "params": {
                GRASP_PROFILE_ADAPTER_PARAM_KEY: str(LIBERO90_GRASP_ADAPTER),
                "grounding_hints": {
                    "placement_surface": {
                        "intent": "fixed_table_region",
                        "relation": "on",
                        "task_language_matches": ["white bowl.*right.*plate|right.*plate.*white bowl"],
                        "target_name_matches": ["*white_bowl*"],
                        "region_name": "kitchen_table_plate_right_region",
                        "rewrite_misgrounded_goals": ["plate_1_main", "*plate*"],
                    }
                },
                "geometry_hints": {
                    "placement_region": {
                        "intent": "fixed_table_rect",
                        "region_name": "kitchen_table_plate_right_region",
                        "support_surface": "table",
                        "bounds_m": {"x_min": 0.60, "x_max": 0.70, "y_min": 0.05, "y_max": 0.15},
                        "thickness_m": 0.010,
                        "place_z_offset_m": 0.160,
                    }
                },
            },
        }

    def test_plate_right_region_rewrites_plate_goal_to_table_region(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        goals = build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
        region = "kitchen_table_plate_right_region"
        matching = [
            goal
            for goal in goals
            if goal.atoms and goal.atoms[0] == GroundedAtom("on", ("white_bowl_1_main", region))
        ]

        self.assertTrue(matching)
        goal = matching[0]
        self.assertTrue(goal.name.startswith("bddl_required"))
        self.assertEqual(goal.surface_names, [region])
        self.assertEqual(goal.grounding["intent"], "fixed_table_region")
        self.assertEqual(goal.grounding["from"], region)
        self.assertEqual(goal.grounding["compiled_predicate"], "on")

    def test_plate_right_region_is_registered_as_place_on_surface(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        region = "kitchen_table_plate_right_region"
        goal = next(
            item
            for item in build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
            if item.surface_names == [region]
        )
        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal.atoms,
            surface_names=goal.surface_names,
            init_atoms=graph.world_atoms,
            required_final_atoms=[{"predicate": atom.predicate, "args": list(atom.args)} for atom in goal.atoms],
            recovery_hints=hints,
        )
        surfaces = {obj.name: obj for obj in problem.surfaces}

        self.assertIn(region, surfaces)
        self.assertEqual(surfaces[region].geometry["kind"], "virtual_fixed_table_rect")
        candidates = problem.place_candidates[region]
        self.assertTrue(np.allclose(candidates[0][:2], np.asarray([0.65, 0.10], dtype=np.float32)))
        self.assertAlmostEqual(float(candidates[0][2]), float(problem.table_z + 0.160), places=5)
        place_on = [
            schema
            for schema in problem.action_schemas
            if schema.name == "place_on" and schema.parameters == ["white_bowl_1_main", region]
        ]
        self.assertEqual(len(place_on), 1)
        supports = _goal_on_target_support_surface_names(problem)
        self.assertEqual(supports, {region})
        self.assertTrue(_exclude_target_support_surface_collision(surfaces[region], supports))
        bowl_grasps = problem.grasps["white_bowl_1_main"]
        self.assertTrue(bowl_grasps)
        self.assertTrue(
            all(
                item.metadata.get("sampler") == "bowl_rim_small_shallow_diagonal_topdown_v1"
                for item in bowl_grasps[:3]
            )
        )

    def test_plate_right_region_candidates_can_prefer_far_corner(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        region_hint = hints["params"]["geometry_hints"]["placement_region"]
        region_hint.update(
            {
                "place_candidate_policy": "farthest_from_reference_with_corners",
                "place_candidate_reference_object": "plate_1_main",
                "place_candidate_edge_margin_m": 0.003,
                "place_candidate_max_count": 9,
            }
        )
        region = "kitchen_table_plate_right_region"
        goal = next(
            item
            for item in build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
            if item.surface_names == [region]
        )
        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal.atoms,
            surface_names=goal.surface_names,
            init_atoms=graph.world_atoms,
            required_final_atoms=[{"predicate": atom.predicate, "args": list(atom.args)} for atom in goal.atoms],
            recovery_hints=hints,
        )
        surface = next(obj for obj in problem.surfaces if obj.name == region)
        metadata = surface.geometry["metadata"]
        candidates = problem.place_candidates[region]

        self.assertEqual(metadata["place_candidate_policy"], "farthest_from_reference_with_corners")
        self.assertTrue(np.allclose(metadata["place_candidate_reference_pos"][:2], scene.objects["plate_1_main"].pos[:2]))
        self.assertEqual(len(candidates), 9)
        self.assertTrue(np.all(candidates[:, 0] >= 0.60))
        self.assertTrue(np.all(candidates[:, 0] <= 0.70))
        self.assertTrue(np.all(candidates[:, 1] >= 0.05))
        self.assertTrue(np.all(candidates[:, 1] <= 0.15))
        plate_xy = np.asarray(scene.objects["plate_1_main"].pos[:2], dtype=np.float32)
        distances = np.linalg.norm(candidates[:, :2] - plate_xy, axis=1)
        self.assertAlmostEqual(float(distances[0]), float(np.max(distances)), places=6)
        self.assertTrue(np.allclose(candidates[0][:2], np.asarray([0.697, 0.147], dtype=np.float32)))


class CollisionPartFilterTests(unittest.TestCase):
    def test_matching_body_name_keeps_mismatched_libero_geom_parts(self):
        obj = TAMPObject(
            name="plate_1_main",
            pos=[0.0, 0.0, 0.0],
            radius=0.1,
            height=0.02,
            role="static_context",
            geometry={
                "metadata": {
                    "collision_parts": [
                        {"geom_id": 1, "name": "plate_1_g0", "body_name": "plate_1_main", "shape": "box"},
                        {"geom_id": 2, "name": "microwave_1_g0", "body_name": "plate_1_main", "shape": "box"},
                        {"geom_id": 3, "name": "geom_123", "body_name": "plate_1_main", "shape": "box"},
                    ]
                }
            },
        )

        parts, debug = _collision_parts_with_filter_debug(obj)
        names = [part.get("name") for part in parts]

        self.assertEqual(names, ["plate_1_g0", "microwave_1_g0", "geom_123"])
        self.assertEqual(debug["dropped_collision_part_count"], 0)
        self.assertEqual(debug["kept_collision_part_count"], 1)
        self.assertEqual(debug["kept_collision_parts"][0]["name"], "microwave_1_g0")
        self.assertEqual(debug["kept_collision_parts"][0]["reason"], "matching_body_name_overrides_geom_name")

    def test_mismatched_body_name_is_filtered_even_when_geom_name_matches(self):
        obj = TAMPObject(
            name="black_book_1_main",
            pos=[0.0, 0.0, 0.0],
            radius=0.1,
            height=0.02,
            role="movable",
            geometry={
                "metadata": {
                    "collision_parts": [
                        {"geom_id": 1, "name": "black_book_1_g0", "body_name": "black_book_1_main", "shape": "box"},
                        {"geom_id": 2, "name": "black_book_1_g1", "body_name": "white_yellow_mug_1_main", "shape": "box"},
                    ]
                }
            },
        )

        parts, debug = _collision_parts_with_filter_debug(obj)
        names = [part.get("name") for part in parts]

        self.assertEqual(names, ["black_book_1_g0"])
        self.assertEqual(debug["dropped_collision_part_count"], 1)
        self.assertEqual(debug["dropped_collision_parts"][0]["name"], "black_book_1_g1")
        self.assertEqual(debug["dropped_collision_parts"][0]["reason"], "mismatched_libero_body_name")

    def test_missing_body_name_falls_back_to_geom_name_filter(self):
        obj = TAMPObject(
            name="black_book_1_main",
            pos=[0.0, 0.0, 0.0],
            radius=0.1,
            height=0.02,
            role="movable",
            geometry={
                "metadata": {
                    "collision_parts": [
                        {"geom_id": 1, "name": "black_book_1_g0", "shape": "box"},
                        {"geom_id": 2, "name": "white_yellow_mug_1_g7", "shape": "box"},
                    ]
                }
            },
        )

        parts, debug = _collision_parts_with_filter_debug(obj)
        names = [part.get("name") for part in parts]

        self.assertEqual(names, ["black_book_1_g0"])
        self.assertEqual(debug["dropped_collision_part_count"], 1)
        self.assertEqual(debug["dropped_collision_parts"][0]["name"], "white_yellow_mug_1_g7")
        self.assertEqual(debug["dropped_collision_parts"][0]["reason"], "mismatched_libero_geom_name")

    def test_black_book_collision_part_keeps_polluted_geom_name_when_body_matches(self):
        obj = TAMPObject(
            name="black_book_1_main",
            pos=[0.0, 0.0, 0.0],
            radius=0.1,
            height=0.02,
            role="movable",
            geometry={
                "metadata": {
                    "collision_parts": [
                        {
                            "geom_id": 93,
                            "name": "white_yellow_mug_1_g7",
                            "body_name": "black_book_1_main",
                            "shape": "box",
                        },
                    ]
                }
            },
        )

        parts, debug = _collision_parts_with_filter_debug(obj)

        self.assertEqual([part.get("name") for part in parts], ["white_yellow_mug_1_g7"])
        self.assertEqual(debug["filtered_collision_part_count"], 1)
        self.assertEqual(debug["dropped_collision_part_count"], 0)
        self.assertEqual(debug["kept_collision_parts"][0]["reason"], "matching_body_name_overrides_geom_name")


class PlateSideBddlRegionGroundingGeometryTests(unittest.TestCase):
    def _parsed_semantics(self):
        scene = _chocolate_pudding_plate_scene()
        parsed = parse_task(
            "put the chocolate pudding to the left of the plate",
            scene.objects.keys(),
            bddl_text=BDDL_CHOCOLATE_PUDDING_LEFT_REGION,
        )
        sym = build_symbolic_state(scene, parsed)
        graph = build_scene_graph(scene, parsed, sym)
        semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
        return scene, parsed, sym, graph, semantics

    def _hints(self):
        return {
            "grasp_profile": "flat_box_topdown_short_side_deep_v1",
            "params": {
                GRASP_PROFILE_ADAPTER_PARAM_KEY: str(LIBERO90_GRASP_ADAPTER),
                "grounding_hints": {
                    "placement_surface": {
                        "grounding_profile": "plate_side_table_region_v1",
                        "grounding_profile_adapter_path": str(LIBERO90_GROUNDING_ADAPTER),
                        "intent": "bddl_table_region",
                        "relation": "on",
                        "task_language_matches": [
                            r"\bto the (left|right) of the plate\b|\b(left|right) of the plate\b"
                        ],
                        "target_name_matches": ["*chocolate_pudding*", "*cream_cheese*", "*butter*", "*box*"],
                        "bddl_goal_surface_matches": [
                            "*_table_plate_left_region",
                            "*_table_plate_right_region",
                        ],
                        "region_name_from_bddl_goal": True,
                        "rewrite_misgrounded_goals": ["plate_1_main", "*plate*"],
                    }
                },
                "geometry_hints": {
                    "placement_region": {
                        "geometry_profile": "plate_side_region_geometry_v1",
                        "geometry_profile_adapter_path": str(LIBERO90_GEOMETRY_ADAPTER),
                        "intent": "bddl_table_rect",
                        "relation": "on",
                        "support_surface": "table",
                        "region_name_from_bddl_goal": True,
                        "bddl_goal_surface_matches": [
                            "*_table_plate_left_region",
                            "*_table_plate_right_region",
                        ],
                        "bounds_from_bddl_region": True,
                        "align_bddl_regions_to_scene": True,
                        "thickness_m": 0.010,
                        "min_span_m": 0.045,
                        "place_z_offset_m": 0.160,
                    }
                },
            },
        }

    def test_bddl_goal_surface_is_recorded_without_becoming_goal_hint(self):
        _scene, parsed, _sym, _graph, _semantics = self._parsed_semantics()

        self.assertEqual(parsed.goal_hint, "plate_1_main")
        self.assertEqual(parsed.diagnostics["bddl_goal_surfaces"], ["living_room_table_plate_left_region"])
        self.assertIn("living_room_table_plate_left_region", parsed.diagnostics["bddl_regions"])
        self.assertTrue(parsed.diagnostics["bddl_init_atoms"])

    def test_plate_left_bddl_region_rewrites_plate_goal_to_dynamic_region(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        goals = build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
        region = "living_room_table_plate_left_region"
        matching = [
            goal
            for goal in goals
            if goal.atoms and goal.atoms[0] == GroundedAtom("on", ("chocolate_pudding_1_main", region))
        ]

        self.assertTrue(matching)
        goal = matching[0]
        self.assertEqual(goal.surface_names, [region])
        self.assertEqual(goal.grounding["intent"], "bddl_table_region")
        self.assertEqual(goal.grounding["source"], "skill_grounding_profile_adapter")
        self.assertEqual(goal.grounding["grounding_profile"], "plate_side_table_region_v1")
        self.assertEqual(goal.grounding["to"], region)

    def test_plate_left_bddl_region_is_registered_as_place_on_surface(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        region = "living_room_table_plate_left_region"
        goal = next(
            item
            for item in build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
            if item.surface_names == [region]
        )
        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal.atoms,
            surface_names=goal.surface_names,
            init_atoms=graph.world_atoms,
            required_final_atoms=[{"predicate": atom.predicate, "args": list(atom.args)} for atom in goal.atoms],
            recovery_hints=hints,
        )
        surfaces = {obj.name: obj for obj in problem.surfaces}

        self.assertIn(region, surfaces)
        self.assertEqual(surfaces[region].geometry["kind"], "virtual_fixed_table_rect")
        self.assertEqual(
            surfaces[region].geometry["metadata"]["source_bddl_qualified_region"],
            "living_room_table_plate_left_region",
        )
        self.assertEqual(
            surfaces[region].geometry["metadata"]["fixed_table_rect_source"],
            "libero90_geometry_profile_adapter",
        )
        self.assertEqual(
            surfaces[region].geometry["metadata"]["geometry_profile"],
            "plate_side_region_geometry_v1",
        )
        candidates = problem.place_candidates[region]
        self.assertAlmostEqual(float(candidates[0][0]), 0.64, places=5)
        self.assertAlmostEqual(float(candidates[0][1]), -0.12, places=5)
        self.assertAlmostEqual(float(candidates[0][2]), float(problem.table_z + 0.160), places=5)
        place_on = [
            schema
            for schema in problem.action_schemas
            if schema.name == "place_on" and schema.parameters == ["chocolate_pudding_1_main", region]
        ]
        self.assertEqual(len(place_on), 1)


class DeskCaddySideBddlRegionGroundingGeometryTests(unittest.TestCase):
    def _parsed_semantics(self):
        scene = _red_mug_caddy_scene()
        parsed = parse_task(
            "pick up the red mug and place it to the right compartment of the caddy",
            scene.objects.keys(),
            bddl_text=BDDL_RED_MUG_RIGHT_OF_CADDY,
        )
        sym = build_symbolic_state(scene, parsed)
        graph = build_scene_graph(scene, parsed, sym)
        semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
        return scene, parsed, sym, graph, semantics

    def _hints(self):
        return {
            "grasp_profile": "mug_body_side_avoid_handle_v1",
            "params": {
                GRASP_PROFILE_ADAPTER_PARAM_KEY: str(LIBERO90_GRASP_ADAPTER),
                "grounding_hints": {
                    "placement_surface": {
                        "grounding_profile": "desk_caddy_side_table_region_v1",
                        "grounding_profile_adapter_path": str(LIBERO90_GROUNDING_ADAPTER),
                        "intent": "bddl_table_region",
                        "relation": "on",
                        "task_language_matches": [
                            r"\bto the (left|right)(?: compartment)? of the caddy\b|\b(left|right) of the caddy\b"
                        ],
                        "target_name_matches": ["*mug*", "*cup*"],
                        "bddl_goal_surface_matches": [
                            "*_desk_caddy_left_region",
                            "*_desk_caddy_right_region",
                        ],
                        "region_name_from_bddl_goal": True,
                        "rewrite_misgrounded_goals": ["desk_caddy_1_main", "*desk_caddy*"],
                    }
                },
                "geometry_hints": {
                    "placement_region": {
                        "geometry_profile": "desk_caddy_side_region_geometry_v1",
                        "geometry_profile_adapter_path": str(LIBERO90_GEOMETRY_ADAPTER),
                        "intent": "bddl_table_rect",
                        "relation": "on",
                        "support_surface": "table",
                        "region_name_from_bddl_goal": True,
                        "bddl_goal_surface_matches": [
                            "*_desk_caddy_left_region",
                            "*_desk_caddy_right_region",
                        ],
                        "bounds_from_bddl_region": True,
                        "align_bddl_regions_to_scene": True,
                        "thickness_m": 0.010,
                        "min_span_m": 0.045,
                        "place_z_offset_m": 0.160,
                        "region_crop_policy": "away_from_reference",
                        "region_crop_reference_object": "desk_caddy_1_main",
                        "region_crop_keep_fraction": 0.65,
                        "region_crop_edge_margin_m": 0.004,
                        "place_candidate_policy": "farthest_from_reference_with_corners",
                        "place_candidate_reference_object": "desk_caddy_1_main",
                        "place_candidate_edge_margin_m": 0.004,
                        "place_candidate_max_count": 9,
                    }
                },
            },
        }

    def test_bddl_goal_surface_is_recorded_without_becoming_goal_hint(self):
        _scene, parsed, _sym, _graph, _semantics = self._parsed_semantics()

        self.assertEqual(parsed.goal_hint, "desk_caddy_1_main")
        self.assertEqual(parsed.diagnostics["bddl_goal_surfaces"], ["study_table_desk_caddy_right_region"])
        self.assertIn("study_table_desk_caddy_right_region", parsed.diagnostics["bddl_regions"])
        self.assertTrue(parsed.diagnostics["bddl_init_atoms"])

    def test_caddy_right_bddl_region_rewrites_caddy_goal_to_dynamic_region(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        goals = build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
        region = "study_table_desk_caddy_right_region"
        matching = [
            goal
            for goal in goals
            if goal.atoms and goal.atoms[0] == GroundedAtom("on", ("red_coffee_mug_1_main", region))
        ]

        self.assertTrue(matching)
        goal = matching[0]
        self.assertEqual(goal.surface_names, [region])
        self.assertEqual(goal.grounding["intent"], "bddl_table_region")
        self.assertEqual(goal.grounding["source"], "skill_grounding_profile_adapter")
        self.assertEqual(goal.grounding["grounding_profile"], "desk_caddy_side_table_region_v1")
        self.assertEqual(goal.grounding["to"], region)
        self.assertNotIn(
            GroundedAtom("on", ("red_coffee_mug_1_main", "desk_caddy_1_main")),
            [candidate.atoms[0] for candidate in goals if candidate.atoms],
        )

    def test_caddy_right_bddl_region_is_registered_as_place_on_surface(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        region = "study_table_desk_caddy_right_region"
        goal = next(
            item
            for item in build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
            if item.surface_names == [region]
        )
        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal.atoms,
            surface_names=goal.surface_names,
            init_atoms=graph.world_atoms,
            required_final_atoms=[{"predicate": atom.predicate, "args": list(atom.args)} for atom in goal.atoms],
            recovery_hints=hints,
        )
        surfaces = {obj.name: obj for obj in problem.surfaces}

        self.assertIn(region, surfaces)
        self.assertEqual(surfaces[region].geometry["kind"], "virtual_fixed_table_rect")
        metadata = surfaces[region].geometry["metadata"]
        self.assertEqual(metadata["fixed_table_rect_source"], "libero90_geometry_profile_adapter")
        self.assertEqual(metadata["geometry_profile"], "desk_caddy_side_region_geometry_v1")
        self.assertEqual(metadata["source_bddl_qualified_region"], "study_table_desk_caddy_right_region")
        self.assertTrue(metadata["region_crop_applied"])
        self.assertEqual(metadata["region_crop_reference_object"], "desk_caddy_1_main")
        self.assertEqual(metadata["region_crop_axis"], "x")
        self.assertTrue(metadata["region_crop_keep_high"])
        inner = metadata["inner_bounds"]
        self.assertAlmostEqual(float(inner["x_min"]), 0.489, places=5)
        self.assertAlmostEqual(float(inner["x_max"]), 0.546, places=5)
        self.assertIn(region, problem.place_candidates)
        candidates = problem.place_candidates[region]
        self.assertEqual(len(candidates), 9)
        self.assertTrue(np.all(candidates[:, 0] >= float(inner["x_min"]) - 1e-6))
        self.assertTrue(np.all(candidates[:, 0] <= float(inner["x_max"]) + 1e-6))
        caddy_xy = np.asarray(scene.objects["desk_caddy_1_main"].pos[:2], dtype=np.float32)
        distances = np.linalg.norm(candidates[:, :2] - caddy_xy, axis=1)
        self.assertAlmostEqual(float(distances[0]), float(np.max(distances)), places=6)
        self.assertAlmostEqual(float(problem.place_candidates[region][0][2]), float(problem.table_z + 0.160), places=5)
        place_on = [
            schema
            for schema in problem.action_schemas
            if schema.name == "place_on" and schema.parameters == ["red_coffee_mug_1_main", region]
        ]
        self.assertEqual(len(place_on), 1)


class FlatBoxContainerInsideRegionTests(unittest.TestCase):
    def _parsed_semantics(self):
        scene = _cream_cheese_basket_scene()
        parsed = parse_task(
            "pick up the cream cheese box and put it in the basket",
            scene.objects.keys(),
            bddl_text=BDDL_CREAM_CHEESE_IN_BASKET,
        )
        sym = build_symbolic_state(scene, parsed)
        graph = build_scene_graph(scene, parsed, sym)
        semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
        return scene, parsed, sym, graph, semantics

    def _hints(self):
        return {
            "grasp_profile": "flat_box_topdown_short_side_v1",
            "params": {
                GRASP_PROFILE_ADAPTER_PARAM_KEY: str(LIBERO90_GRASP_ADAPTER),
                "geometry_hints": {
                    "placement_region": {
                        "intent": "container_inner_floor",
                        "relation": "inside",
                        "container_name_matches": ["*basket*", "*container*"],
                        "proxy_suffix": "inner_floor",
                        "margin_m": 0.018,
                        "floor_clearance_m": 0.006,
                        "thickness_m": 0.010,
                        "min_span_m": 0.045,
                    }
                }
            },
        }

    def test_bddl_contain_region_compiles_to_container_inner_floor(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        goals = build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
        proxy = "basket_1_main_inner_floor"
        matching = [
            goal
            for goal in goals
            if goal.name.startswith("bddl_required")
            and goal.atoms
            and goal.atoms[0] == GroundedAtom("on", ("cream_cheese_1_main", proxy))
        ]

        self.assertTrue(matching)
        goal = matching[0]
        self.assertEqual(goal.surface_names, [proxy])
        self.assertEqual(goal.grounding["intent"], "container_inner_floor")
        self.assertEqual(goal.grounding["from"], "basket_1_main")
        self.assertEqual(goal.grounding["container_region_alias"]["from"], "basket_1_contain_region")
        self.assertEqual(goal.grounding["compiled_predicate"], "on")

    def test_container_inner_floor_surface_and_flat_box_grasps_are_registered(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = self._hints()
        proxy = "basket_1_main_inner_floor"
        goal = next(
            item
            for item in build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
            if item.surface_names == [proxy]
        )
        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal.atoms,
            surface_names=goal.surface_names,
            init_atoms=graph.world_atoms,
            required_final_atoms=[{"predicate": atom.predicate, "args": list(atom.args)} for atom in goal.atoms],
            recovery_hints=hints,
        )
        surfaces = {obj.name: obj for obj in problem.surfaces}

        self.assertIn(proxy, surfaces)
        self.assertEqual(surfaces[proxy].geometry["kind"], "virtual_inner_floor")
        self.assertEqual(surfaces[proxy].geometry["metadata"]["source_object"], "basket_1_main")
        self.assertIn(proxy, problem.place_candidates)
        place_on = [
            schema
            for schema in problem.action_schemas
            if schema.name == "place_on" and schema.parameters == ["cream_cheese_1_main", proxy]
        ]
        self.assertEqual(len(place_on), 1)
        supports = _goal_on_target_support_surface_names(problem)
        self.assertEqual(supports, {proxy, "basket_1_main"})
        self.assertTrue(_exclude_target_support_surface_collision(surfaces[proxy], supports))
        self.assertTrue(_exclude_target_support_surface_collision(surfaces["basket_1_main"], supports))
        box_grasps = problem.grasps["cream_cheese_1_main"]
        self.assertTrue(box_grasps)
        self.assertTrue(all(item.metadata.get("sampler") == "flat_box_topdown_short_side_v1" for item in box_grasps))
        target = next(obj for obj in problem.movables if obj.name == "cream_cheese_1_main")
        backend_samples = _grasp_6dof_xyzrpy_for_profile(
            "flat_box_topdown_short_side_v1",
            [2.0 * float(value) for value in target.half_extents],
            rim=False,
            pose=[*target.pos, *target.quat],
            registry=load_grasp_profile_registry(adapter_path=LIBERO90_GRASP_ADAPTER),
        )
        self.assertEqual(len(box_grasps), len(backend_samples))
        self.assertTrue(np.allclose(box_grasps[0].metadata["local_xyz"], backend_samples[0][:3]))


class DeskCaddyCompartmentTests(unittest.TestCase):
    def _parsed_semantics(self, compartment: str):
        scene = _desk_caddy_scene()
        bddl_text = {
            "front": BDDL_DESK_CADDY_FRONT_COMPARTMENT,
            "left": BDDL_DESK_CADDY_LEFT_COMPARTMENT,
        }[compartment]
        parsed = parse_task(
            f"pick up the book and place it in the {compartment} compartment of the caddy",
            scene.objects.keys(),
            bddl_text=bddl_text,
        )
        sym = build_symbolic_state(scene, parsed)
        graph = build_scene_graph(scene, parsed, sym)
        semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
        return scene, parsed, sym, graph, semantics

    def _hints(self):
        return {
            "params": {
                "grounding_hints": {
                    "placement_surface": {
                        "grounding_profile": "desk_caddy_compartment_v1",
                        "grounding_profile_adapter_path": str(LIBERO90_GROUNDING_ADAPTER),
                        "intent": "container_compartment",
                        "relation": "inside",
                        "object_class": "desk_caddy",
                        "region_name_matches": [
                            "*_front_contain_region",
                            "*_back_contain_region",
                            "*_left_contain_region",
                            "*_right_contain_region",
                        ],
                        "container_name_matches": ["*desk_caddy*"],
                        "proxy_suffix": "inner_floor",
                    }
                },
                "geometry_hints": {
                    "placement_region": {
                        "geometry_profile": "desk_caddy_compartment_inner_floor_v1",
                        "geometry_profile_adapter": "libero90_legacy_geometry_profiles",
                        "geometry_profile_adapter_path": str(LIBERO90_GEOMETRY_ADAPTER),
                        "planner_primitive": "inner_floor",
                        "intent": "compartment_inner_floor",
                        "relation": "inside",
                        "object_class": "desk_caddy",
                        "container_name_matches": ["*desk_caddy*"],
                        "region_name_matches": [
                            "*_front_contain_region",
                            "*_back_contain_region",
                            "*_left_contain_region",
                            "*_right_contain_region",
                        ],
                        "proxy_suffix": "inner_floor",
                        "margin_m": 0.010,
                        "floor_clearance_m": 0.008,
                        "thickness_m": 0.010,
                        "min_span_m": 0.040,
                        "place_z_offset_m": 0.100,
                        "place_candidate_policy": "center_and_entry_high_drop",
                        "place_candidate_entry_fraction": 0.30,
                        "release_mode": "high_drop_into_compartment",
                        "release_z_offset_m": 0.100,
                        "release_z_tolerance_m": 0.040,
                        "release_xy_margin_m": 0.012,
                        "planner_support_z_offset_m": 0.100,
                        "exclude_source_collision": True,
                        "exclude_table_collision": True,
                        "place_yaw_policy": "thin_horizontal_along_world_x",
                    }
                },
            }
        }

    def test_bddl_front_contain_region_compiles_to_front_inner_floor(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics("front")
        hints = self._hints()
        goals = build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
        proxy = "desk_caddy_1_main_front_inner_floor"
        matching = [
            goal
            for goal in goals
            if goal.name.startswith("bddl_required")
            and goal.atoms
            and goal.atoms[0] == GroundedAtom("on", ("black_book_1_main", proxy))
        ]

        self.assertTrue(matching)
        goal = matching[0]
        self.assertEqual(goal.surface_names, [proxy])
        self.assertEqual(goal.grounding["intent"], "compartment_inner_floor")
        self.assertEqual(goal.grounding["from"], "desk_caddy_1_main")
        self.assertEqual(goal.grounding["to"], proxy)
        self.assertEqual(goal.grounding["compartment"], "front")
        self.assertEqual(goal.grounding["container_region_alias"]["from"], "desk_caddy_1_front_contain_region")
        self.assertEqual(goal.grounding["container_region_alias"]["grounding_profile"], "desk_caddy_compartment_v1")
        self.assertEqual(goal.grounding["compiled_predicate"], "on")

    def test_bddl_left_contain_region_compiles_to_left_inner_floor(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics("left")
        hints = self._hints()
        goals = build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
        proxy = "desk_caddy_1_main_left_inner_floor"
        matching = [
            goal
            for goal in goals
            if goal.name.startswith("bddl_required")
            and goal.atoms
            and goal.atoms[0] == GroundedAtom("on", ("black_book_1_main", proxy))
        ]

        self.assertTrue(matching)
        goal = matching[0]
        self.assertEqual(goal.surface_names, [proxy])
        self.assertEqual(goal.grounding["intent"], "compartment_inner_floor")
        self.assertEqual(goal.grounding["from"], "desk_caddy_1_main")
        self.assertEqual(goal.grounding["to"], proxy)
        self.assertEqual(goal.grounding["compartment"], "left")
        self.assertEqual(goal.grounding["container_region_alias"]["from"], "desk_caddy_1_left_contain_region")
        self.assertEqual(goal.grounding["container_region_alias"]["grounding_profile"], "desk_caddy_compartment_v1")
        self.assertEqual(goal.grounding["compiled_predicate"], "on")

    def test_compartment_inner_floor_surface_is_registered_and_excludes_caddy_collision(self):
        hints = self._hints()
        for compartment, axis, direction in (("front", "x", -1), ("left", "y", 1)):
            with self.subTest(compartment=compartment):
                scene, parsed, sym, graph, semantics = self._parsed_semantics(compartment)
                proxy = f"desk_caddy_1_main_{compartment}_inner_floor"
                goal = next(
                    item
                    for item in build_recovery_goal_candidates(
                        scene,
                        parsed,
                        sym,
                        semantics,
                        graph=graph,
                        recovery_hints=hints,
                    )
                    if item.surface_names == [proxy]
                )
                problem = build_tamp_problem(
                    scene,
                    parsed,
                    sym,
                    goal_atoms_override=goal.atoms,
                    surface_names=goal.surface_names,
                    init_atoms=graph.world_atoms,
                    required_final_atoms=[{"predicate": atom.predicate, "args": list(atom.args)} for atom in goal.atoms],
                    recovery_hints=hints,
                )
                surfaces = {obj.name: obj for obj in problem.surfaces}
                statics = {obj.name: obj for obj in problem.statics}

                self.assertIn(proxy, surfaces)
                self.assertIn("desk_caddy_1_main", statics)
                self.assertEqual(surfaces[proxy].geometry["kind"], "virtual_inner_floor")
                metadata = surfaces[proxy].geometry["metadata"]
                self.assertEqual(metadata["source_object"], "desk_caddy_1_main")
                self.assertEqual(metadata["compartment"], compartment)
                self.assertTrue(metadata["exclude_source_collision"])
                self.assertTrue(metadata["exclude_table_collision"])
                self.assertEqual(metadata["place_yaw_policy"], "thin_horizontal_along_world_x")
                excluded = _goal_on_target_support_surface_names(problem)
                self.assertIn(proxy, excluded)
                self.assertIn("desk_caddy_1_main", excluded)
                self.assertIn("table", excluded)
                table = surfaces.get("table")
                self.assertIsNotNone(table)
                self.assertTrue(_exclude_target_support_surface_collision(table, excluded))
                self.assertEqual(metadata["release_mode"], "high_drop_into_compartment")
                self.assertAlmostEqual(float(metadata["release_z_offset_m"]), 0.100, places=4)
                self.assertAlmostEqual(float(metadata["release_z_tolerance_m"]), 0.040, places=4)
                self.assertAlmostEqual(float(metadata["release_xy_margin_m"]), 0.012, places=4)
                self.assertAlmostEqual(
                    float(metadata["planner_support_z_m"]),
                    float(metadata["inner_bounds"]["support_z"]) + 0.100,
                    places=4,
                )
                self.assertIn(proxy, problem.place_candidates)
                self.assertEqual(len(problem.place_candidates[proxy]), 2)
                self.assertAlmostEqual(
                    float(problem.place_candidates[proxy][0][2]),
                    float(metadata["inner_bounds"]["support_z"]) + 0.100,
                    places=4,
                )
                if axis == "x":
                    center = float(problem.place_candidates[proxy][0][0])
                    caddy_center = float(scene.objects["desk_caddy_1_main"].pos[0])
                else:
                    center = float(problem.place_candidates[proxy][0][1])
                    caddy_center = float(scene.objects["desk_caddy_1_main"].pos[1])
                if direction < 0:
                    self.assertLess(center, caddy_center)
                else:
                    self.assertGreater(center, caddy_center)
                self.assertEqual(metadata["inner_bounds_source"], "libero90_desk_caddy_site_bounds")
                self.assertEqual(metadata["inner_bounds_adapter"], "libero90_legacy_geometry_profiles")
                self.assertEqual(metadata["inner_bounds_profile"], "desk_caddy_compartment_inner_floor_v1")
                self.assertIn(f"{compartment}_contain_region", metadata["source_site_name"])
                place_on = [
                    schema
                    for schema in problem.action_schemas
                    if schema.name == "place_on" and schema.parameters == ["black_book_1_main", proxy]
                ]
                self.assertEqual(len(place_on), 1)
                self.assertTrue(place_on[0].supported_by_executor)
                supports = _goal_on_target_support_surface_names(problem)
                self.assertEqual(supports, {proxy, "desk_caddy_1_main", "table"})
                self.assertTrue(_exclude_target_support_surface_collision(surfaces[proxy], supports))
                self.assertTrue(_exclude_target_support_surface_collision(statics["desk_caddy_1_main"], supports))
                self.assertTrue(_exclude_target_support_surface_collision(surfaces["table"], supports))

    def test_geometry_shift_moves_sites_and_metadata_sites_to_planner_frame(self):
        base_position = np.asarray([-0.75, 0.0, 0.0], dtype=np.float64)
        base_quat = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
        geometry = {
            "geoms": [{"pos": [-0.3674, -0.1370, 0.9600], "quat": [1.0, 0.0, 0.0, 0.0]}],
            "sites": [{"name": "raw", "pos": [-0.3674, -0.1370, 0.9600], "quat": [1.0, 0.0, 0.0, 0.0]}],
            "metadata": {
                "sites": [{"name": "meta", "pos": [-0.3674, -0.1370, 0.9600], "quat": [1.0, 0.0, 0.0, 0.0]}],
                "containment_sites": [
                    {"name": "contain", "pos": [-0.3674, -0.1370, 0.9600], "quat": [1.0, 0.0, 0.0, 0.0]}
                ],
            },
        }

        shifted = _shift_geometry_to_robot_base(geometry, base_position, base_quat)

        self.assertAlmostEqual(float(shifted["geoms"][0]["pos"][0]), 0.3826, places=4)
        self.assertAlmostEqual(float(shifted["sites"][0]["pos"][0]), 0.3826, places=4)
        self.assertAlmostEqual(float(shifted["metadata"]["sites"][0]["pos"][0]), 0.3826, places=4)
        self.assertAlmostEqual(float(shifted["metadata"]["containment_sites"][0]["pos"][0]), 0.3826, places=4)

    def test_compartment_inner_floor_uses_shifted_site_bounds_when_scene_has_robot_base(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics("front")
        scene.robot_joint_debug["frame_candidates"] = [
            {
                "name": "robot0_base",
                "pos_world": [-0.75, 0.0, 0.0],
                "quat_world_wxyz": [1.0, 0.0, 0.0, 0.0],
            }
        ]
        hints = self._hints()
        proxy = "desk_caddy_1_main_front_inner_floor"
        goal = next(
            item
            for item in build_recovery_goal_candidates(
                scene,
                parsed,
                sym,
                semantics,
                graph=graph,
                recovery_hints=hints,
            )
            if item.surface_names == [proxy]
        )

        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal.atoms,
            surface_names=goal.surface_names,
            init_atoms=graph.world_atoms,
            required_final_atoms=[{"predicate": atom.predicate, "args": list(atom.args)} for atom in goal.atoms],
            recovery_hints=hints,
        )
        surface = next(obj for obj in problem.surfaces if obj.name == proxy)
        metadata = surface.geometry["metadata"]
        inner = metadata["inner_bounds"]
        center_x = 0.5 * (float(inner["x_min"]) + float(inner["x_max"]))

        self.assertAlmostEqual(center_x, 0.319 + 0.75, places=5)
        self.assertNotAlmostEqual(center_x, 0.319, places=3)
        self.assertEqual(metadata["inner_bounds_coordinate_frame"], "planner_frame")
        self.assertEqual(problem.q_init_debug["world_to_planner_frame"]["origin_world"], [-0.75, 0.0, 0.0])


class BowlStackSupportTests(unittest.TestCase):
    def _parsed_semantics(self):
        scene = _scene()
        parsed = parse_task(
            "stack the black bowl at the front on the black bowl in the middle",
            scene.objects.keys(),
            bddl_text=BDDL_STACK_FRONT_ON_MIDDLE,
        )
        sym = build_symbolic_state(scene, parsed)
        graph = build_scene_graph(scene, parsed, sym)
        semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
        return scene, parsed, sym, graph, semantics

    def test_bowl_stack_goal_support_needs_grounding_hint(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        no_hint_goals = build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph)
        no_hint = next(goal for goal in no_hint_goals if goal.name.startswith("bddl_required"))
        self.assertEqual(no_hint.atoms[0], GroundedAtom("on", ("akita_black_bowl_1_main", "akita_black_bowl_2_main")))
        self.assertEqual(no_hint.surface_names, [])

        hints = {
            "params": {
                "geometry_hints": {
                    "movable_support_surface": {
                        "geometry_profile": "bowl_stack_support_geometry_v1",
                        "intent": "stack_support",
                        "object_class": "bowl",
                        "require_movable": True,
                    }
                },
                "grounding_hints": {
                    "support_object": {
                        "grounding_profile": "bowl_stack_support_v1",
                        "grounding_profile_adapter_path": str(LIBERO90_GROUNDING_ADAPTER),
                        "intent": "stack_support",
                        "object_class": "bowl",
                        "relation": "on",
                    }
                }
            }
        }
        hinted_goals = build_recovery_goal_candidates(
            scene,
            parsed,
            sym,
            semantics,
            graph=graph,
            recovery_hints=hints,
        )
        hinted = next(goal for goal in hinted_goals if goal.name.startswith("bddl_required"))
        self.assertEqual(hinted.surface_names, ["akita_black_bowl_2_main"])
        self.assertEqual(hinted.grounding["movable_support_surface_names"], ["akita_black_bowl_2_main"])

    def test_bowl_stack_support_is_registered_as_surface_for_cutamp(self):
        scene, parsed, sym, graph, semantics = self._parsed_semantics()
        hints = {
            "params": {
                "geometry_hints": {
                    "movable_support_surface": {
                        "geometry_profile": "bowl_stack_support_geometry_v1",
                        "intent": "stack_support",
                        "object_class": "bowl",
                        "require_movable": True,
                    }
                },
                "grounding_hints": {
                    "support_object": {
                        "grounding_profile": "bowl_stack_support_v1",
                        "grounding_profile_adapter_path": str(LIBERO90_GROUNDING_ADAPTER),
                        "intent": "stack_support",
                        "object_class": "bowl",
                        "relation": "on",
                    }
                }
            }
        }
        goal = next(
            item
            for item in build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
            if item.name.startswith("bddl_required")
        )
        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal.atoms,
            surface_names=goal.surface_names,
            init_atoms=graph.world_atoms,
            required_final_atoms=[{"predicate": atom.predicate, "args": list(atom.args)} for atom in goal.atoms],
        )

        self.assertIn("akita_black_bowl_2_main", [obj.name for obj in problem.surfaces])
        self.assertNotIn("akita_black_bowl_2_main", [obj.name for obj in problem.movables])
        place_on = [
            schema
            for schema in problem.action_schemas
            if schema.name == "place_on"
            and schema.parameters == ["akita_black_bowl_1_main", "akita_black_bowl_2_main"]
        ]
        self.assertEqual(len(place_on), 1)
        self.assertTrue(place_on[0].supported_by_executor)

    def test_bowl_stack_support_collision_is_excluded_like_explicit_support_surface(self):
        target = TAMPObject(
            name="akita_black_bowl_1_main",
            pos=[0.0, 0.0, 0.1],
            radius=0.05,
            height=0.05,
            role="target_movable",
        )
        support = TAMPObject(
            name="akita_black_bowl_2_main",
            pos=[0.0, 0.0, 0.05],
            radius=0.06,
            height=0.04,
            role="surface",
        )
        other = TAMPObject(
            name="akita_black_bowl_3_main",
            pos=[0.1, 0.0, 0.05],
            radius=0.06,
            height=0.04,
            role="surface",
        )
        problem = TAMPProblem(
            movables=[target],
            surfaces=[support, other],
            statics=[],
            goal_atoms=[GroundedAtom("on", ("akita_black_bowl_1_main", "akita_black_bowl_2_main"))],
        )

        supports = _goal_on_target_support_surface_names(problem)
        self.assertEqual(supports, {"akita_black_bowl_2_main"})
        self.assertTrue(_exclude_target_support_surface_collision(support, supports))
        self.assertFalse(_exclude_target_support_surface_collision(other, supports))


class GenericGeometryDescriptorTests(unittest.TestCase):
    def test_descriptor_builder_normalizes_basic_surface_shapes(self):
        surface = _virtual_surface_from_descriptor(
            "custom_round_region",
            {
                "shape": "cyl",
                "center": [0.1, 0.2, 0.03],
                "radius": 0.04,
                "height": 0.012,
                "metadata": {"affordances": ["placement_region"]},
            },
        )

        self.assertEqual(surface.geometry["shape"], "cylinder")
        self.assertEqual(surface.geometry["metadata"]["geometry_descriptor_shape"], "cylinder")
        self.assertIn("surface", surface.geometry["metadata"]["affordances"])
        self.assertEqual(surface.half_extents, [0.04, 0.04, 0.006])

    def test_inline_geometry_descriptor_creates_pack_virtual_surface(self):
        scene = _scene()
        parsed = parse_task(
            "put the black bowl at the front on the custom slot",
            scene.objects.keys(),
            bddl_text=BDDL_FRONT,
        )
        sym = build_symbolic_state(scene, parsed)
        surface_name = "custom_slot_inner_floor"
        hints = {
            "params": {
                "geometry_hints": {
                    surface_name: {
                        "surface_descriptor": {
                            "shape": "oriented_box",
                            "kind": "virtual_custom_slot",
                            "center": [0.21, -0.11, 0.015],
                            "quat": [1.0, 0.0, 0.0, 0.0],
                            "half_extents": [0.040, 0.020, 0.005],
                            "inner_bounds": {
                                "x_min": 0.17,
                                "x_max": 0.25,
                                "y_min": -0.13,
                                "y_max": -0.09,
                                "support_z": 0.020,
                            },
                        }
                    }
                }
            }
        }
        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=[GroundedAtom("on", ("akita_black_bowl_1_main", surface_name))],
            surface_names=[surface_name],
            recovery_hints=hints,
        )
        surfaces = {surface.name: surface for surface in problem.surfaces}

        self.assertIn(surface_name, surfaces)
        self.assertEqual(surfaces[surface_name].geometry["kind"], "virtual_custom_slot")
        self.assertEqual(surfaces[surface_name].geometry["shape"], "rotated_box")
        self.assertIn(surface_name, problem.place_candidates)

    def test_goal_atom_surface_can_create_pack_virtual_surface_without_surface_names(self):
        scene = _scene()
        parsed = parse_task(
            "put the black bowl at the front on the custom slot",
            scene.objects.keys(),
            bddl_text=BDDL_FRONT,
        )
        sym = build_symbolic_state(scene, parsed)
        surface_name = "custom_slot_inner_floor"
        hints = {
            "params": {
                "geometry_hints": {
                    surface_name: {
                        "surface_descriptor": {
                            "shape": "box",
                            "kind": "virtual_custom_slot",
                            "center": [0.21, -0.11, 0.015],
                            "half_extents": [0.040, 0.020, 0.005],
                        }
                    }
                }
            }
        }
        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=[GroundedAtom("on", ("akita_black_bowl_1_main", surface_name))],
            recovery_hints=hints,
        )
        surfaces = {surface.name: surface for surface in problem.surfaces}

        self.assertIn(surface_name, surfaces)
        self.assertIn(surface_name, problem.place_candidates)

    def test_grounding_adapter_can_rewrite_to_pack_declared_virtual_surface(self):
        with tempfile.TemporaryDirectory() as td:
            adapter = Path(td) / "grounding_adapter.py"
            adapter.write_text(
                "def rewrite_placement_atom(profile, hint, atom, scene, parsed, target, hint_key):\n"
                "    return {'predicate': 'on', 'object': atom.args[0], 'surface': 'custom_slot_inner_floor'}\n"
                "\n"
                "def is_known_or_virtual_surface(profile, hint, surface, scene, parsed, hint_key):\n"
                "    return surface == 'custom_slot_inner_floor'\n",
                encoding="utf-8",
            )
            scene = _scene()
            parsed = parse_task(
                "put the black bowl at the front on the custom slot",
                scene.objects.keys(),
                bddl_text=BDDL_FRONT,
            )
            sym = build_symbolic_state(scene, parsed)
            graph = build_scene_graph(scene, parsed, sym)
            semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
            hints = {
                "params": {
                    "grounding_hints": {
                        "custom_surface": {
                            "grounding_profile": "custom_slot_rewrite_v1",
                            "grounding_profile_adapter_path": str(adapter),
                        }
                    },
                    "geometry_hints": {
                        "custom_slot_inner_floor": {
                            "surface_descriptor": {
                                "shape": "box",
                                "center": [0.21, -0.11, 0.015],
                                "half_extents": [0.040, 0.020, 0.005],
                            }
                        }
                    },
                }
            }

            goals = build_recovery_goal_candidates(scene, parsed, sym, semantics, graph=graph, recovery_hints=hints)
            goal = next(item for item in goals if item.surface_names == ["custom_slot_inner_floor"])

            self.assertEqual(goal.atoms[0], GroundedAtom("on", ("akita_black_bowl_1_main", "custom_slot_inner_floor")))
            self.assertEqual(goal.grounding["source"], "skill_grounding_adapter")


if __name__ == "__main__":
    unittest.main()
