"""Tests for the language + MuJoCo goal source.

First slice of the BDDL goal-isolation boundary; see
``docs/bddl_goal_context_migration_implementation_plan.md`` and
``docs/geometry_bddl_dependency_audit.md``.

These tests use synthetic scenes only: the local checkout has no MuJoCo/LIBERO
runtime, so binding against real episodes is verified on the server.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

from experiments.robot.libero.tiptop_repro.bddl_goals import _placement_goal_surfaces
from experiments.robot.libero.tiptop_repro.language_mujoco_goals import (
    FAILURE_ACTION,
    FAILURE_AMBIGUOUS,
    FAILURE_DIRECTION,
    FAILURE_PARSE,
    FAILURE_REGION,
    FAILURE_TARGET_NOT_FOUND,
    SOURCE,
    resolve_language_mujoco_hints,
)
from experiments.robot.libero.tiptop_repro.task_parser import parse_task

TABLE_TOP_M = 0.79
BOWL = (0.045, 0.045, 0.035)
PLATE = (0.05, 0.05, 0.005)
BOX = (0.05, 0.05, 0.015)
RAMEKIN = (0.03, 0.03, 0.02)
TABLE = (0.40, 0.40, 0.02)

SPATIAL_SWAP_ON_BOX = "Pick the akita black bowl on the cookies box and place it on the plate"
SPATIAL_SWAP_NEXT_TO_PLATE = "Pick the akita black bowl next to the plate and place it on the plate"
SPATIAL_SWAP_BETWEEN = "Pick the akita black bowl between the plate and the ramekin and place it on the plate"
SPATIAL_SWAP_NOT_BETWEEN = (
    "Pick the akita black bowl not between the plate and the ramekin and place it on the plate"
)
SPATIAL_SWAP_TABLE_CENTER = "Pick the akita black bowl from table center and place it on the plate"
SPATIAL_SWAP_TOP_DRAWER = (
    "Pick the akita black bowl in the top layer of the wooden cabinet and place it on the plate"
)

BDDL_OBJECT_GOAL = """
(define (problem LIBERO_Tabletop_Manipulation)
  (:language pick up the black bowl next to the plate and place it on the plate)
  (:init
    (On akita_black_bowl_1 main_table_next_to_plate_region)
  )
  (:obj_of_interest
    akita_black_bowl_1
    plate_1
  )
  (:goal
    (And (On akita_black_bowl_1 plate_1))
  )
)
"""


@dataclass
class FakeObject:
    name: str
    pos: np.ndarray
    geometry: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeScene:
    objects: Dict[str, FakeObject] = field(default_factory=dict)


def _geometry(half: Sequence[float], sites: Sequence[str] = ()) -> Dict[str, Any]:
    geometry: Dict[str, Any] = {"source": "test", "geoms": [{"name": "g0", "size": list(half)}]}
    if sites:
        geometry["sites"] = [{"name": str(s), "size": [0.01, 0.01, 0.01]} for s in sites]
    return geometry


def _obj(
    name: str,
    xy: Tuple[float, float],
    half: Sequence[float],
    *,
    z: Optional[float] = None,
    sites: Sequence[str] = (),
) -> FakeObject:
    half = tuple(float(v) for v in half)
    height = TABLE_TOP_M + half[2] if z is None else float(z)
    return FakeObject(
        name=name,
        pos=np.asarray([float(xy[0]), float(xy[1]), height], dtype=np.float64),
        geometry=_geometry(half, sites),
    )


def _table() -> FakeObject:
    return _obj("main_table_main", (0.0, 0.0), TABLE, z=TABLE_TOP_M - TABLE[2])


def _scene(*objects: FakeObject) -> FakeScene:
    return FakeScene({obj.name: obj for obj in (_table(),) + tuple(objects)})


class OnBoxSceneTest(unittest.TestCase):
    """spatial_swap task04: the bowl that is *on the cookies box*."""

    def setUp(self) -> None:
        self.cookies = _obj("cookies_1_main", (0.0, -0.05), BOX)
        box_top = float(self.cookies.pos[2]) + BOX[2]
        self.bowl_on_box = _obj(
            "akita_black_bowl_1_main", (0.0, -0.05), BOWL, z=box_top + BOWL[2]
        )
        self.bowl_on_table = _obj("akita_black_bowl_2_main", (0.15, 0.20), BOWL)
        self.plate = _obj("plate_1_main", (0.0, 0.25), PLATE)
        self.scene = _scene(self.cookies, self.bowl_on_box, self.bowl_on_table, self.plate)

    def test_binds_the_bowl_that_is_on_the_box(self) -> None:
        hints = resolve_language_mujoco_hints(SPATIAL_SWAP_ON_BOX, self.scene)
        self.assertIsNone(hints["failure_reason"])
        self.assertEqual(hints["target"], "akita_black_bowl_1_main")
        self.assertEqual(hints["goal"], "plate_1_main")
        self.assertEqual(
            hints["goal_atoms"],
            [{"predicate": "on", "args": ["akita_black_bowl_1_main", "plate_1_main"]}],
        )
        self.assertEqual(hints["goal_surfaces"], ["plate_1_main"])
        self.assertEqual(hints["obj_of_interest"], ["akita_black_bowl_1_main", "plate_1_main"])
        self.assertEqual(hints["init_atoms"], [])
        self.assertEqual(hints["regions"], {})
        self.assertEqual(hints["source"], SOURCE)

    def test_on_relation_scores_are_recorded(self) -> None:
        hints = resolve_language_mujoco_hints(SPATIAL_SWAP_ON_BOX, self.scene)
        scores = hints["binding_evidence"]["target_on"]["scores"]
        self.assertTrue(scores["akita_black_bowl_1_main"]["xy_overlap"])
        self.assertLessEqual(abs(scores["akita_black_bowl_1_main"]["contact_gap_m"]), 0.02)
        self.assertFalse(scores["akita_black_bowl_2_main"]["xy_overlap"])


class NextToSceneTest(unittest.TestCase):
    """spatial_swap task05: the bowl next to the plate."""

    def test_binds_the_bowl_next_to_the_plate(self) -> None:
        near = _obj("akita_black_bowl_1_main", (0.14, 0.20), BOWL)
        far = _obj("akita_black_bowl_2_main", (-0.30, -0.20), BOWL)
        plate = _obj("plate_1_main", (0.0, 0.25), PLATE)
        hints = resolve_language_mujoco_hints(
            SPATIAL_SWAP_NEXT_TO_PLATE, _scene(near, far, plate)
        )
        self.assertIsNone(hints["failure_reason"])
        self.assertEqual(hints["target"], "akita_black_bowl_1_main")

    def test_two_matching_bowls_fail_explicitly(self) -> None:
        left = _obj("akita_black_bowl_1_main", (0.14, 0.25), BOWL)
        right = _obj("akita_black_bowl_2_main", (-0.14, 0.25), BOWL)
        plate = _obj("plate_1_main", (0.0, 0.25), PLATE)
        hints = resolve_language_mujoco_hints(
            SPATIAL_SWAP_NEXT_TO_PLATE, _scene(left, right, plate)
        )
        self.assertEqual(hints["failure_reason"], FAILURE_AMBIGUOUS)
        self.assertIsNone(hints["target"])
        self.assertEqual(hints["goal_atoms"], [])


class BetweenSceneTest(unittest.TestCase):
    """spatial_swap task01 and task06."""

    def setUp(self) -> None:
        self.plate = _obj("plate_1_main", (0.0, 0.25), PLATE)
        self.ramekin = _obj("glazed_rim_porcelain_ramekin_1_main", (-0.25, 0.0), RAMEKIN)
        self.middle = _obj("akita_black_bowl_1_main", (-0.125, 0.125), BOWL)
        self.other = _obj("akita_black_bowl_2_main", (0.20, -0.20), BOWL)
        self.scene = _scene(self.plate, self.ramekin, self.middle, self.other)

    def test_between_selects_the_middle_bowl(self) -> None:
        hints = resolve_language_mujoco_hints(SPATIAL_SWAP_BETWEEN, self.scene)
        self.assertIsNone(hints["failure_reason"])
        self.assertEqual(hints["target"], "akita_black_bowl_1_main")

    def test_not_between_selects_the_other_bowl(self) -> None:
        hints = resolve_language_mujoco_hints(SPATIAL_SWAP_NOT_BETWEEN, self.scene)
        self.assertIsNone(hints["failure_reason"])
        self.assertEqual(hints["target"], "akita_black_bowl_2_main")


class TableCenterTest(unittest.TestCase):
    def test_binds_the_bowl_closest_to_the_table_center(self) -> None:
        near = _obj("akita_black_bowl_1_main", (0.05, 0.05), BOWL)
        far = _obj("akita_black_bowl_2_main", (-0.35, 0.30), BOWL)
        plate = _obj("plate_1_main", (0.0, 0.25), PLATE)
        hints = resolve_language_mujoco_hints(
            SPATIAL_SWAP_TABLE_CENTER, _scene(near, far, plate)
        )
        self.assertIsNone(hints["failure_reason"])
        self.assertEqual(hints["target"], "akita_black_bowl_1_main")


class InsideCabinetTest(unittest.TestCase):
    """spatial_swap task03: bowl inside the top layer of the wooden cabinet."""

    def test_binds_the_bowl_inside_the_cabinet(self) -> None:
        cabinet = _obj("wooden_cabinet_1_main", (0.0, -0.30), (0.12, 0.12, 0.10))
        inside = _obj(
            "akita_black_bowl_1_main",
            (0.0, -0.30),
            BOWL,
            z=float(cabinet.pos[2]) + 0.06,
        )
        outside = _obj("akita_black_bowl_2_main", (0.30, 0.20), BOWL)
        plate = _obj("plate_1_main", (0.0, 0.25), PLATE)
        hints = resolve_language_mujoco_hints(
            SPATIAL_SWAP_TOP_DRAWER, _scene(cabinet, inside, outside, plate)
        )
        self.assertIsNone(hints["failure_reason"])
        self.assertEqual(hints["target"], "akita_black_bowl_1_main")


class ExplicitFailureTest(unittest.TestCase):
    def test_missing_reference_category_reports_target_not_found(self) -> None:
        bowl = _obj("akita_black_bowl_1_main", (0.0, 0.0), BOWL)
        plate = _obj("plate_1_main", (0.0, 0.25), PLATE)
        hints = resolve_language_mujoco_hints(
            SPATIAL_SWAP_ON_BOX, _scene(bowl, plate)
        )
        self.assertEqual(hints["failure_reason"], FAILURE_TARGET_NOT_FOUND)
        self.assertIsNone(hints["target"])
        self.assertEqual(hints["goal_surfaces"], [])

    def test_goal_region_is_refused_not_guessed(self) -> None:
        bowl = _obj("akita_black_bowl_1_main", (0.0, 0.0), BOWL)
        plate = _obj("plate_1_main", (0.0, 0.25), PLATE)
        stove = _obj("flat_stove_1_main", (0.20, -0.20), (0.10, 0.10, 0.02))
        hints = resolve_language_mujoco_hints(
            "Push the plate to the front of the stove", _scene(bowl, plate, stove)
        )
        self.assertEqual(hints["failure_reason"], FAILURE_REGION)
        self.assertEqual(hints["goal_atoms"], [])

    def test_goal_fixture_with_region_sites_is_refused(self) -> None:
        bowl = _obj("akita_black_bowl_1_main", (0.0, 0.0), BOWL)
        plate = _obj("plate_1_main", (0.0, 0.25), PLATE)
        stove = _obj(
            "flat_stove_1_main",
            (0.20, -0.20),
            (0.10, 0.10, 0.02),
            sites=("flat_stove_1_cook_region",),
        )
        hints = resolve_language_mujoco_hints(
            "Put the akita black bowl on the stove", _scene(bowl, plate, stove)
        )
        self.assertEqual(hints["failure_reason"], FAILURE_REGION)
        self.assertEqual(hints["binding_evidence"]["goal_region_sites"], ["flat_stove_1_cook_region"])

    def test_action_language_is_refused(self) -> None:
        cabinet = _obj("wooden_cabinet_1_main", (0.0, -0.30), (0.12, 0.12, 0.10))
        hints = resolve_language_mujoco_hints(
            "Open the top drawer of the cabinet", _scene(cabinet)
        )
        self.assertEqual(hints["failure_reason"], FAILURE_ACTION)

    def test_direction_word_with_several_candidates_is_refused(self) -> None:
        plate_left = _obj("plate_1_main", (0.0, 0.20), PLATE)
        plate_right = _obj("plate_2_main", (0.15, 0.20), PLATE)
        mug = _obj("red_coffee_mug_1_main", (0.0, -0.20), (0.04, 0.04, 0.045))
        hints = resolve_language_mujoco_hints(
            "Put the red mug on the left plate", _scene(plate_left, plate_right, mug)
        )
        self.assertEqual(hints["failure_reason"], FAILURE_DIRECTION)

    def test_direction_word_is_ignored_when_the_category_is_unique(self) -> None:
        plate = _obj("plate_1_main", (0.0, 0.20), PLATE)
        mug = _obj("red_coffee_mug_1_main", (0.0, -0.20), (0.04, 0.04, 0.045))
        hints = resolve_language_mujoco_hints(
            "Put the red mug on the left plate", _scene(plate, mug)
        )
        self.assertIsNone(hints["failure_reason"])
        self.assertEqual(hints["target"], "red_coffee_mug_1_main")
        self.assertEqual(hints["goal"], "plate_1_main")

    def test_unparsable_language_never_falls_back_to_bddl(self) -> None:
        bowl = _obj("akita_black_bowl_1_main", (0.0, 0.0), BOWL)
        hints = resolve_language_mujoco_hints("wave hello", _scene(bowl))
        self.assertEqual(hints["failure_reason"], FAILURE_PARSE)
        self.assertIsNone(hints["target"])
        self.assertIsNone(hints["goal"])
        self.assertEqual(hints["goal_atoms"], [])
        self.assertEqual(hints["goal_surfaces"], [])
        self.assertEqual(hints["regions"], {})
        self.assertEqual(hints["source"], SOURCE)
        self.assertFalse([key for key in hints if key.startswith("bddl")])

    def test_unknown_object_language_fails_without_guessing(self) -> None:
        bowl = _obj("akita_black_bowl_1_main", (0.0, 0.0), BOWL)
        hints = resolve_language_mujoco_hints("wave hello to the camera", _scene(bowl))
        self.assertEqual(hints["failure_reason"], FAILURE_TARGET_NOT_FOUND)
        self.assertIsNone(hints["target"])
        self.assertEqual(hints["goal_atoms"], [])

    def test_empty_language_fails(self) -> None:
        bowl = _obj("akita_black_bowl_1_main", (0.0, 0.0), BOWL)
        hints = resolve_language_mujoco_hints("", _scene(bowl))
        self.assertEqual(hints["failure_reason"], FAILURE_PARSE)


class GoalSurfaceParityTest(unittest.TestCase):
    def test_goal_surfaces_helper_matches_bddl_module(self) -> None:
        atoms = [
            {"predicate": "on", "args": ["a_main", "surface_main"]},
            {"predicate": "inside", "args": ["b_main", "bowl_main"]},
            {"predicate": "on", "args": ["c_main", "surface_main"]},
            {"predicate": "holding", "args": ["d_main"]},
        ]
        hints = resolve_language_mujoco_hints("", None)
        self.assertEqual(hints["goal_surfaces"], [])
        from experiments.robot.libero.tiptop_repro import language_mujoco_goals as module

        self.assertEqual(
            module._placement_goal_surfaces(atoms), _placement_goal_surfaces(atoms)
        )


class ParseTaskSourceSwitchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cookies = _obj("cookies_1_main", (0.0, -0.05), BOX)
        box_top = float(self.cookies.pos[2]) + BOX[2]
        self.bowl_on_box = _obj(
            "akita_black_bowl_1_main", (0.0, -0.05), BOWL, z=box_top + BOWL[2]
        )
        self.bowl_on_table = _obj("akita_black_bowl_2_main", (0.15, 0.20), BOWL)
        self.plate = _obj("plate_1_main", (0.0, 0.25), PLATE)
        self.scene = _scene(self.cookies, self.bowl_on_box, self.bowl_on_table, self.plate)

    def test_language_mujoco_mode_uses_the_language_and_the_scene(self) -> None:
        parsed = parse_task(
            SPATIAL_SWAP_ON_BOX,
            self.scene.objects.keys(),
            scene=self.scene,
            task_goal_source="language_mujoco",
        )
        self.assertEqual(parsed.target_hint, "akita_black_bowl_1_main")
        self.assertEqual(parsed.goal_hint, "plate_1_main")
        diagnostics = parsed.diagnostics
        self.assertEqual(diagnostics["task_goal_source"], "language_mujoco")
        self.assertEqual(
            diagnostics["goal_atoms"],
            [{"predicate": "on", "args": ["akita_black_bowl_1_main", "plate_1_main"]}],
        )
        self.assertEqual(diagnostics["goal_surfaces"], ["plate_1_main"])
        self.assertEqual(diagnostics["goal_regions"], {})
        self.assertEqual(diagnostics["target_source"], "language_mujoco")
        self.assertEqual(diagnostics["goal_source"], "language_mujoco")
        self.assertNotIn("bddl_goal_atoms", diagnostics)
        self.assertNotIn("bddl_regions", diagnostics)
        self.assertIsNone(diagnostics["language_failure_reason"])

    def test_language_mujoco_mode_records_the_failure_reason(self) -> None:
        parsed = parse_task(
            "wave hello",
            self.scene.objects.keys(),
            scene=self.scene,
            task_goal_source="language_mujoco",
        )
        self.assertIsNone(parsed.target_hint)
        self.assertEqual(parsed.diagnostics["language_failure_reason"], FAILURE_PARSE)
        self.assertEqual(parsed.diagnostics["goal_atoms"], [])

    def test_ambiguous_binding_clears_lightweight_parser_guesses(self) -> None:
        left = _obj("akita_black_bowl_1_main", (0.14, 0.25), BOWL)
        right = _obj("akita_black_bowl_2_main", (-0.14, 0.25), BOWL)
        plate = _obj("plate_1_main", (0.0, 0.25), PLATE)
        scene = _scene(left, right, plate)
        parsed = parse_task(
            SPATIAL_SWAP_NEXT_TO_PLATE,
            scene.objects.keys(),
            scene=scene,
            task_goal_source="language_mujoco",
        )
        self.assertEqual(parsed.diagnostics["language_failure_reason"], FAILURE_AMBIGUOUS)
        self.assertIsNone(parsed.target_hint)
        self.assertIsNone(parsed.goal_hint)
        self.assertEqual(parsed.diagnostics["target_source"], "language_mujoco_failed")
        self.assertEqual(parsed.diagnostics["goal_source"], "language_mujoco_failed")

    def test_language_mujoco_mode_ignores_bddl_inputs(self) -> None:
        """Anti-fallback (plan 10.3): BDDL inputs must not influence the result."""
        parsed = parse_task(
            SPATIAL_SWAP_ON_BOX,
            self.scene.objects.keys(),
            bddl_text=BDDL_OBJECT_GOAL,
            bddl_path="C:/does/not/exist.bddl",
            env=object(),
            scene=self.scene,
            task_goal_source="language_mujoco",
        )
        diagnostics = parsed.diagnostics
        self.assertEqual(parsed.target_hint, "akita_black_bowl_1_main")
        self.assertEqual(parsed.goal_hint, "plate_1_main")
        self.assertEqual(diagnostics["task_goal_source"], "language_mujoco")
        self.assertNotIn("bddl_goal_atoms", diagnostics)
        self.assertNotIn("bddl_regions", diagnostics)
        self.assertNotIn("bddl_path", diagnostics)
        self.assertIsNone(diagnostics["language_failure_reason"])

    def test_bddl_mode_is_unchanged_and_aliased(self) -> None:
        parsed = parse_task(
            "pick up the black bowl next to the plate and place it on the plate",
            self.scene.objects.keys(),
            bddl_text=BDDL_OBJECT_GOAL,
        )
        diagnostics = parsed.diagnostics
        self.assertEqual(parsed.target_hint, "akita_black_bowl_1_main")
        self.assertEqual(parsed.goal_hint, "plate_1_main")
        self.assertEqual(diagnostics["target_source"], "bddl")
        self.assertEqual(diagnostics["goal_source"], "bddl")
        self.assertEqual(
            diagnostics["bddl_goal_atoms"],
            [{"predicate": "on", "args": ["akita_black_bowl_1_main", "plate_1_main"]}],
        )
        self.assertEqual(diagnostics["task_goal_source"], "bddl")
        self.assertEqual(diagnostics["goal_atoms"], diagnostics["bddl_goal_atoms"])
        self.assertEqual(diagnostics["goal_surfaces"], diagnostics["bddl_goal_surfaces"])
        self.assertEqual(diagnostics["goal_regions"], diagnostics["bddl_regions"])
        self.assertNotIn("language_failure_reason", diagnostics)

    def test_bddl_mode_still_defaults_to_no_hints(self) -> None:
        parsed = parse_task("pick up the black bowl and place it on the plate", ["akita_black_bowl_1_main"])
        self.assertEqual(parsed.diagnostics["task_goal_source"], "bddl")
        self.assertEqual(parsed.diagnostics["goal_atoms"], [])
        self.assertNotIn("bddl_goal_atoms", parsed.diagnostics)

    def test_unknown_source_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_task("pick up the bowl", ["akita_black_bowl_1_main"], task_goal_source="guess")

    def test_language_mujoco_mode_requires_a_scene(self) -> None:
        with self.assertRaises(ValueError):
            parse_task(
                SPATIAL_SWAP_ON_BOX,
                self.scene.objects.keys(),
                task_goal_source="language_mujoco",
            )


if __name__ == "__main__":
    unittest.main()
