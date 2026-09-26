from __future__ import annotations

import unittest

import numpy as np

from experiments.robot.libero.tiptop_repro.cutamp_domain import build_action_schemas
from experiments.robot.libero.tiptop_repro.place_in_open_drawer import (
    cavity_from_site,
    evaluate_open_drawer_place,
    place_waypoints,
    site_axis_aligned_half_extents,
)
from experiments.robot.libero.tiptop_repro.predicates import build_symbolic_state
from experiments.robot.libero.tiptop_repro.real_cutamp_adapter import build_recovery_goal_candidates
from experiments.robot.libero.tiptop_repro.scene_graph import build_scene_graph
from experiments.robot.libero.tiptop_repro.scene_reader import JointState, ObjectState, SceneState
from experiments.robot.libero.tiptop_repro.tamp_scene import build_tamp_problem
from experiments.robot.libero.tiptop_repro.task_parser import parse_task
from experiments.robot.libero.tiptop_repro.task_semantics import RuleTaskSemanticsInterpreter

LANGUAGE = "Open the top layer of the drawer and put the cream cheese inside"
REGION = "wooden_cabinet_1_top_region"
PROXY = "wooden_cabinet_1_top_region_inner_floor"
LINK = "wooden_cabinet_1_top_level"
SITE_POS = (0.20, -0.30, 0.12)
SITE_HALF = (0.06, 0.08, 0.04)

BDDL = """
(define (problem LIBERO_Tabletop_Manipulation)
  (:language Open the top layer of the drawer and put the cream cheese inside)
  (:goal
    (And (Inside cream_cheese_1 wooden_cabinet_1_top_region))
  )
)
"""


CHEESE_POS = (0.05, 0.10, 0.04)
CHEESE_HALF = (0.02, 0.01, 0.01)
BOARD_HALF = (0.10, 0.10, 0.004)
SHELL_THICKNESS = 0.006

# ---------------------------------------------------------------------------
# The real LIBERO top-drawer region site and drawer geometry, transcribed from
# the recorded planner problem of the failing episode
# (place_in_open_drawer_20260926/gap_top_s1.problem.json). The site is stored
# rotated a quarter turn about y, so its local half extents are (x, y, z) =
# (0.0299, 0.0756, 0.1022) while the drawer interior is (0.1022, 0.0756,
# 0.0299) in the planner frame. Reading the local triple as an axis-aligned
# box is what put the cavity floor 7.6 cm below the drawer floor.
# ---------------------------------------------------------------------------
REAL_SITE_NAME = "wooden_cabinet_1_top_region"
REAL_SITE_LOCAL_HALF = (0.029929999262094498, 0.07560999691486359, 0.10224000364542007)
REAL_SITE_POS = (0.6918127946555614, -0.08816009759902954, 0.1786300539970398)
REAL_SITE_QUAT = (0.0, -0.7071067811865475, 0.0, 0.7071067811865476)
REAL_SITE_WORLD_HALF = (0.10224000364542007, 0.07560999691486359, 0.029929999262094498)
REAL_DRAWER_FLOOR_Z = 0.15220
REAL_DRAWER_RIM_Z = 0.21040
REAL_CHEESE_HALF_WORLD = (0.0406, 0.0213, 0.0089)
REAL_CHEESE_POS = (0.6013253927230835, 0.1343836486339569, -0.0030930638313293457)
# name -> (axis-aligned box low corner, high corner) of the drawer link.
REAL_DRAWER_BOXES = {
    "wooden_cabinet_1_g11": ([0.5824, -0.0044, 0.1418], [0.8011, 0.0011, 0.2104]),
    "wooden_cabinet_1_g12": ([0.5850, -0.0121, 0.1444], [0.7985, -0.0049, 0.2087]),
    "wooden_cabinet_1_g13": ([0.5850, -0.1712, 0.1444], [0.7985, -0.1641, 0.2087]),
    "wooden_cabinet_1_g14": ([0.7943, -0.1694, 0.1449], [0.7997, -0.0064, 0.2082]),
    "wooden_cabinet_1_g15": ([0.5835, -0.1694, 0.1453], [0.5888, -0.0064, 0.2079]),
    "wooden_cabinet_1_g16": ([0.5847, -0.1683, 0.1441], [0.7986, -0.0064, 0.1522]),
    "wooden_cabinet_1_g18": ([0.6534, 0.0170, 0.1688], [0.7423, 0.0324, 0.1851]),
    "wooden_cabinet_1_g19": ([0.6609, -0.0040, 0.1714], [0.6710, 0.0172, 0.1825]),
    "wooden_cabinet_1_g20": ([0.7256, -0.0040, 0.1713], [0.7358, 0.0172, 0.1825]),
}


def _box(name: str, body: str, pos, half, *, shape: str = "box", quat=None) -> dict:
    return {
        "name": name,
        "body_name": body,
        "shape": shape,
        "size": list(half),
        "pos": list(pos),
        "quat": list(quat) if quat is not None else [1.0, 0.0, 0.0, 0.0],
        "collision_active": True,
    }


def _aabb_box(name: str, body: str, low, high) -> dict:
    low = np.asarray(low, dtype=float)
    high = np.asarray(high, dtype=float)
    return _box(name, body, (low + high) / 2.0, (high - low) / 2.0)


def _drawer_shell(site_pos, site_half, thickness: float = SHELL_THICKNESS) -> list[dict]:
    """Bottom plus four walls spanning the site box, like a real drawer link."""
    x, y, z = (float(value) for value in site_pos)
    hx, hy, hz = (float(value) for value in site_half)
    return [
        _box("drawer_bottom", LINK, (x, y, z - hz + thickness), (hx, hy, thickness)),
        _box("drawer_wall_x_min", LINK, (x - hx + thickness, y, z), (thickness, hy, hz)),
        _box("drawer_wall_x_max", LINK, (x + hx - thickness, y, z), (thickness, hy, hz)),
        _box("drawer_wall_y_min", LINK, (x, y - hy + thickness, z), (hx, thickness, hz)),
        _box("drawer_wall_y_max", LINK, (x, y + hy - thickness, z), (hx, thickness, hz)),
    ]


def _scene(
    qpos: float,
    *,
    board: bool = False,
    shell: bool = True,
    site_pos=SITE_POS,
    site_half=SITE_HALF,
    board_pos=None,
    site_quat=None,
) -> SceneState:
    site = {
        "name": "top_region",
        "body_name": LINK,
        "type": 6,
        "shape": "box",
        "pos": list(site_pos),
        "size": list(site_half),
    }
    if site_quat is not None:
        site["quat"] = list(site_quat)
    drawer_geoms: list[dict] = []
    if shell:
        drawer_geoms.extend(_drawer_shell(site_pos, site_half))
    if board:
        drawer_geoms.append(
            _box("drawer_shelf", LINK, site_pos if board_pos is None else board_pos, BOARD_HALF)
        )
    objects = {
        "cream_cheese_1_main": ObjectState(
            name="cream_cheese_1_main",
            pos=np.asarray(CHEESE_POS, dtype=np.float32),
            geometry={"geoms": [_box("cream_cheese_1_g1", "cream_cheese_1_main", CHEESE_POS, CHEESE_HALF)]},
        ),
        "plate_1_main": ObjectState(
            name="plate_1_main",
            pos=np.asarray([-0.10, 0.12, 0.02], dtype=np.float32),
        ),
        LINK: ObjectState(
            name=LINK,
            pos=np.asarray(site_pos, dtype=np.float32),
            geometry={"sites": [site], "geoms": drawer_geoms},
        ),
    }
    return SceneState(
        ee_pos=np.asarray([0.0, 0.0, 0.25], dtype=np.float32),
        ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        gripper_qpos=np.asarray([0.04, -0.04], dtype=np.float32),
        objects=objects,
        joints={LINK: JointState(name=LINK, qpos=qpos)},
        articulation_structure={
            LINK: {
                "joint_name": LINK,
                "body_name": LINK,
                "joint_range": [-0.16, 0.0],
                "reference_position": qpos,
                "frame": "world",
                "sites": {},
            }
        },
    )


def _real_drawer_scene(qpos: float = -0.15, *, cheese_half=None) -> SceneState:
    """The recorded LIBERO top drawer, with the region site in its real frame."""
    cheese_half = REAL_CHEESE_HALF_WORLD if cheese_half is None else cheese_half
    site = {
        "name": REAL_SITE_NAME,
        "body_name": LINK,
        "type": 6,
        "shape": "box",
        "pos": list(REAL_SITE_POS),
        "size": list(REAL_SITE_LOCAL_HALF),
        "quat": list(REAL_SITE_QUAT),
    }
    drawer_geoms = [
        _aabb_box(name, LINK, low, high) for name, (low, high) in REAL_DRAWER_BOXES.items()
    ]
    objects = {
        "cream_cheese_1_main": ObjectState(
            name="cream_cheese_1_main",
            pos=np.asarray(REAL_CHEESE_POS, dtype=np.float32),
            geometry={
                "geoms": [
                    _box("cream_cheese_1_g1", "cream_cheese_1_main", REAL_CHEESE_POS, cheese_half)
                ]
            },
        ),
        LINK: ObjectState(
            name=LINK,
            pos=np.asarray(REAL_SITE_POS, dtype=np.float32),
            geometry={"sites": [site], "geoms": drawer_geoms},
        ),
    }
    return SceneState(
        ee_pos=np.asarray([0.0, 0.0, 0.25], dtype=np.float32),
        ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
        gripper_qpos=np.asarray([0.04, -0.04], dtype=np.float32),
        objects=objects,
        joints={LINK: JointState(name=LINK, qpos=qpos)},
        articulation_structure={
            LINK: {
                "joint_name": LINK,
                "body_name": LINK,
                "joint_range": [-0.16, 0.0],
                "reference_position": qpos,
                "frame": "world",
                "sites": {},
            }
        },
    )


def _pipeline(qpos: float, hints=None, **scene_kwargs):
    scene = _scene(qpos, **scene_kwargs)
    parsed = parse_task(LANGUAGE, scene.objects.keys(), bddl_text=BDDL)
    sym = build_symbolic_state(scene, parsed)
    graph = build_scene_graph(scene, parsed, sym)
    semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
    goals = build_recovery_goal_candidates(
        scene, parsed, sym, semantics, graph=graph, recovery_hints=hints
    )
    return scene, parsed, sym, graph, semantics, goals


def _placement_goal(goals):
    return [
        goal
        for goal in goals
        if any(
            atom.predicate == "inside" and len(atom.args) == 2 and atom.args[1] == REGION
            for atom in goal.atoms
        )
    ]


class OpenDrawerPlaceTests(unittest.TestCase):
    def test_goal_stays_on_the_top_region(self):
        _scene_obj, _parsed, _sym, _graph, semantics, goals = _pipeline(-0.15)
        self.assertEqual(semantics.target_object, "cream_cheese_1_main")
        self.assertEqual(semantics.goal_object, REGION)
        required = [
            (atom["predicate"], tuple(atom["args"]))
            for atom in semantics.required_final_atoms
        ]
        self.assertIn(("inside", ("cream_cheese_1_main", REGION)), required)
        self.assertFalse(any("plate" in arg for _pred, args in required for arg in args))
        self.assertTrue(goals)
        for goal in goals:
            for atom in goal.atoms:
                self.assertNotIn("plate", " ".join(atom.args))

    def test_open_drawer_releases_inside_the_cavity_and_lets_go(self):
        scene, parsed, sym, _graph, _semantics, goals = _pipeline(-0.15)
        matching = [
            goal
            for goal in goals
            if any(atom.predicate == "on" and atom.args == ("cream_cheese_1_main", PROXY) for atom in goal.atoms)
            and any(atom.predicate == "handempty" for atom in goal.atoms)
        ]
        self.assertEqual(len(matching), 1)
        goal = matching[0]
        self.assertFalse(any(atom.predicate == "holding" for atom in goal.atoms))
        self.assertEqual(goal.grounding["from"], REGION)
        self.assertEqual(goal.grounding["to"], PROXY)
        release = goal.grounding["release_pos"]
        floor_z = SITE_POS[2] - SITE_HALF[2]
        ceiling_z = SITE_POS[2] + SITE_HALF[2]
        self.assertEqual(release[0], SITE_POS[0])
        self.assertEqual(release[1], SITE_POS[1])
        self.assertGreater(release[2], floor_z)
        self.assertLess(release[2], ceiling_z)

        waypoints = place_waypoints(
            {"approach_pos": goal.grounding["approach_pos"], "release_pos": release, "retreat_pos": goal.grounding["retreat_pos"]}
        )
        self.assertEqual(waypoints[-1]["gripper"], "open")
        self.assertEqual(waypoints[1]["gripper"], "open")
        self.assertGreater(waypoints[-1]["pos"][2], ceiling_z)

        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal.atoms,
            surface_names=goal.surface_names,
            required_final_atoms=[{"predicate": atom.predicate, "args": list(atom.args)} for atom in goal.atoms],
        )
        self.assertIn(PROXY, problem.place_candidates)
        candidate = problem.place_candidates[PROXY][0]
        self.assertAlmostEqual(float(candidate[0]), SITE_POS[0], places=5)
        self.assertAlmostEqual(float(candidate[1]), SITE_POS[1], places=5)
        self.assertAlmostEqual(float(candidate[2]), float(release[2]), places=5)
        place_on = [
            schema
            for schema in problem.action_schemas
            if schema.name == "place_on" and schema.parameters == ["cream_cheese_1_main", PROXY]
        ]
        self.assertEqual(len(place_on), 1)
        self.assertTrue(place_on[0].supported_by_executor)
        place_in = [schema for schema in build_action_schemas(scene) if schema.name == "place_in"]
        self.assertTrue(place_in)
        self.assertTrue(all(not schema.supported_by_executor for schema in place_in))

    def test_release_uses_the_top_of_the_gap(self):
        site_pos = (0.20, -0.30, 0.20)
        site_half = (0.06, 0.08, 0.14)
        board_pos = (0.20, -0.30, 0.12)
        _scene_obj, _parsed, _sym, _graph, _semantics, goals = _pipeline(
            -0.15,
            board=True,
            site_pos=site_pos,
            site_half=site_half,
            board_pos=board_pos,
        )
        matching = [
            goal
            for goal in goals
            if any(atom.predicate == "on" and atom.args == ("cream_cheese_1_main", PROXY) for atom in goal.atoms)
        ]
        self.assertEqual(len(matching), 1)
        release = matching[0].grounding["release_pos"]
        ceiling_z = site_pos[2] + site_half[2]
        gap_hi = ceiling_z - CHEESE_HALF[2] - 0.001
        self.assertAlmostEqual(release[2], gap_hi, places=5)
        self.assertEqual(release[0], site_pos[0])
        self.assertEqual(release[1], site_pos[1])
        # The object's own half height is the gripper reach below its centre.
        self.assertGreater(release[2] - CHEESE_HALF[2], board_pos[2] + BOARD_HALF[2])

    def test_deep_gripper_is_refused_when_it_would_hit_the_board(self):
        # A gripper declared to reach 9 cm below the object cannot release next
        # to a board only 1.1 cm above the cavity floor.
        _scene_obj, _parsed, _sym, _graph, _semantics, goals = _pipeline(
            -0.15, board=True, hints={"open_drawer_hand_below_object_m": 0.09}
        )
        placement = _placement_goal(goals)
        self.assertEqual(len(placement), 1)
        self.assertEqual(placement[0].grounding.get("open_drawer_place_status"), "no_cavity")
        self.assertEqual(placement[0].grounding.get("open_drawer_place_reason"), "hand_clearance_infeasible")

    def test_closed_drawer_is_refused(self):
        scene, parsed, sym, _graph, _semantics, goals = _pipeline(0.0)
        placement = _placement_goal(goals)
        self.assertEqual(len(placement), 1)
        goal = placement[0]
        self.assertEqual(goal.grounding.get("open_drawer_place_status"), "closed")
        self.assertFalse(any(atom.args and atom.args[-1] == PROXY for atom in goal.atoms))
        self.assertFalse(any("plate" in " ".join(atom.args) for other in goals for atom in other.atoms))
        problem = build_tamp_problem(
            scene,
            parsed,
            sym,
            goal_atoms_override=goal.atoms,
            surface_names=goal.surface_names,
        )
        self.assertNotIn(REGION, problem.place_candidates)
        self.assertNotIn(PROXY, problem.place_candidates)
        refusals = problem.q_init_debug["open_drawer_place"]
        self.assertEqual(refusals[0]["status"], "closed")

    # ------------------------------------------------------------------
    # Regressions for the frame bug found in the recorded failing episode.
    # ------------------------------------------------------------------

    def test_rotated_region_site_is_read_in_the_planner_frame(self):
        site = {
            "name": REAL_SITE_NAME,
            "type": 6,
            "shape": "box",
            "pos": list(REAL_SITE_POS),
            "size": list(REAL_SITE_LOCAL_HALF),
            "quat": list(REAL_SITE_QUAT),
        }
        half = site_axis_aligned_half_extents(site)
        self.assertIsNotNone(half)
        np.testing.assert_allclose(half, REAL_SITE_WORLD_HALF, atol=1e-9)
        # The unrotated reading is the bug: it swaps the x and z extents.
        self.assertAlmostEqual(float(half[0]), float(REAL_SITE_LOCAL_HALF[2]), places=9)
        self.assertAlmostEqual(float(half[2]), float(REAL_SITE_LOCAL_HALF[0]), places=9)

        cavity, reason = cavity_from_site(
            site, object_half=np.asarray(REAL_CHEESE_HALF_WORLD, dtype=float)
        )
        self.assertEqual(reason, "")
        self.assertIsNotNone(cavity)
        floor_z = float(REAL_SITE_POS[2]) - float(REAL_SITE_WORLD_HALF[2])
        ceiling_z = float(REAL_SITE_POS[2]) + float(REAL_SITE_WORLD_HALF[2])
        self.assertAlmostEqual(cavity["floor_z"], floor_z, places=9)
        self.assertAlmostEqual(cavity["ceiling_z"], ceiling_z, places=9)
        # The floor must sit on the drawer floor, not 7.6 cm below it.
        self.assertGreater(cavity["floor_z"], REAL_DRAWER_FLOOR_Z - 0.01)
        self.assertLess(cavity["ceiling_z"], REAL_DRAWER_RIM_Z + 0.001)
        span_x = cavity["inner_bounds"]["x_max"] - cavity["inner_bounds"]["x_min"]
        self.assertGreater(span_x, 0.18)

    def test_real_goal_task04_drawer_is_ready_below_the_rim(self):
        scene = _real_drawer_scene()
        decision = evaluate_open_drawer_place(scene, REAL_SITE_NAME, "cream_cheese_1_main")
        self.assertIsNotNone(decision)
        self.assertEqual(decision["status"], "ready", decision.get("reason"))
        # The old frame bug produced floor 0.07639 / release 0.27093, i.e. a
        # release 6 cm above the real drawer rim.
        self.assertGreater(decision["floor_z"], 0.14)
        self.assertLess(decision["release_pos"][2], REAL_DRAWER_RIM_Z)
        self.assertGreater(decision["release_pos"][2], REAL_DRAWER_FLOOR_Z)
        self.assertGreater(decision["hand_below_object_m"], 0.0)
        self.assertEqual(decision["hand_below_object_source"], "object_half_height")
        # The site box must be consistent with the drawer link's own geometry.
        geometry = decision["drawer_geometry_aabb"]
        self.assertIsNotNone(geometry)
        self.assertGreaterEqual(geometry["box_count"], len(REAL_DRAWER_BOXES))
        problem_boxes = decision["site_world_aabb"]
        self.assertGreaterEqual(problem_boxes["lo"][2], geometry["lo"][2] - 0.02)
        self.assertLessEqual(problem_boxes["hi"][2], geometry["hi"][2] + 0.02)

    def test_site_box_outside_the_drawer_geometry_is_refused(self):
        # A site whose box is far taller than the drawer link's own geometry is
        # the signature of reading site_size in the wrong frame.
        scene, parsed, sym, _graph, _semantics, goals = _pipeline(-0.15, shell=False, board=True)
        placement = _placement_goal(goals)
        self.assertEqual(len(placement), 1)
        self.assertEqual(
            placement[0].grounding.get("open_drawer_place_status"), "cavity_geometry_mismatch"
        )
        self.assertFalse(any(atom.args and atom.args[-1] == PROXY for atom in placement[0].atoms))

    def test_object_larger_than_the_cavity_is_refused(self):
        scene = _real_drawer_scene(cheese_half=(0.15, 0.15, 0.05))
        decision = evaluate_open_drawer_place(scene, REAL_SITE_NAME, "cream_cheese_1_main")
        self.assertIsNotNone(decision)
        self.assertEqual(decision["status"], "object_does_not_fit")
        self.assertIn("does not fit", decision["reason"])

    def test_non_box_site_is_refused(self):
        site = {
            "name": REAL_SITE_NAME,
            "type": 0,
            "shape": "sphere",
            "pos": list(REAL_SITE_POS),
            "size": [0.03, 0.0, 0.0],
            "quat": [1.0, 0.0, 0.0, 0.0],
        }
        cavity, reason = cavity_from_site(site)
        self.assertIsNone(cavity)
        self.assertEqual(reason, "unsupported_site_type")


if __name__ == "__main__":
    unittest.main()
