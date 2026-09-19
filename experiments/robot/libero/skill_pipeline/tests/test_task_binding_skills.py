from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from experiments.robot.libero.skill_pipeline.schema import SkillSchemaError, parse_skill_markdown
from experiments.robot.libero.skill_pipeline.task_binding_skills import (
    FAILURE_CONFLICT,
    load_task_binding_resolver,
)
from experiments.robot.libero.tiptop_repro.language_mujoco_goals import resolve_language_mujoco_hints
from experiments.robot.libero.tiptop_repro.scene_reader import ObjectState, SceneState
from experiments.robot.libero.tiptop_repro.scene_graph import ObjectNode, SceneGraph
from experiments.robot.libero.tiptop_repro.task_semantics import RuleTaskSemanticsInterpreter
from experiments.robot.libero.tiptop_repro.tamp_scene import _language_relative_table_region_surface
from experiments.robot.libero.tiptop_repro.task_parser import ParsedTask, parse_task


@dataclass
class FakeObject:
    name: str
    pos: np.ndarray
    geometry: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeScene:
    objects: dict[str, FakeObject]
    joints: dict[str, Any] = field(default_factory=dict)
    table_geometry: dict[str, Any] = field(default_factory=dict)


def _scene() -> FakeScene:
    plate = FakeObject("plate_1_main", np.asarray([0.0, 0.0, 0.8]))
    stove = FakeObject(
        "flat_stove_1_main",
        np.asarray([0.2, 0.0, 0.8]),
        geometry={
            "sites": [
                {"name": "flat_stove_1_cook_region"},
                {"name": "flat_stove_1_cook_region"},
                {"name": "flat_stove_1_top_region"},
            ]
        },
    )
    return FakeScene({plate.name: plate, stove.name: stove})


SKILL = """---
id: bind_plate_to_stove_cook_region
name: Bind plate to stove cook region
kind: task_binding
scope: task_binding
priority: 100
applies_to:
  all:
    - task_language_matches: "plate.*stove"
    - scene_site_matches: ".*stove.*cook_region$"
task_binding_profile: stove_cook_region_v1
---
Static binding evidence.
"""


PROFILES = """schema_version: 1
name: test_task_binding_profiles
profiles:
  stove_cook_region_v1:
    target_selector:
      source: language
    goal_selector:
      source: scene
      category_matches: "^flat_stove$"
    relation: on
    goal_site_selector:
      name_matches: ".*_cook_region$"
      required: true
"""


RANKED_SKILL = """---
id: bind_spatial_black_bowl
kind: task_binding
scope: task_binding
priority: 100
applies_to:
  all:
    - task_language_matches: "black bowl.*place it on the plate"
    - scene_object_matches: "^akita_black_bowl_[0-9]+_main$"
task_binding_profile: spatial_black_bowl_v1
---
Static spatial binding evidence.
"""


RANKED_PROFILES = """schema_version: 1
name: ranked_task_binding_profiles
profiles:
  spatial_black_bowl_v1:
    target_selector:
      source: language_ranked
      name_matches: "^akita_black_bowl_[0-9]+_main$"
    goal_selector:
      source: scene
      name_matches: "^plate_[0-9]+_main$"
    relation: on
"""


FRONT_SKILL = """---
id: bind_stove_front_region
kind: task_binding
scope: task_binding
priority: 100
applies_to:
  all:
    - task_language_matches: "to (?:the )?front of (?:the )?stove"
    - scene_object_matches: "^flat_stove_[0-9]+_button$"
task_binding_profile: stove_front_region_v1
---
Static fixture-relative region binding evidence.
"""


FRONT_PROFILES = """schema_version: 1
name: front_task_binding_profiles
profiles:
  stove_front_region_v1:
    target_selector:
      source: language
    goal_selector:
      source: scene
      name_matches: "^flat_stove_[0-9]+_main$"
    relation: on
    goal_region_selector:
      kind: fixture_front_table
      anchor_name_matches: "^flat_stove_[0-9]+_button$"
      reference_site_matches: "^flat_stove_[0-9]+_cook_region$"
      region_suffix: front_region
"""


class TaskBindingSkillTest(unittest.TestCase):
    @staticmethod
    def _mined_pack() -> Path:
        return (
            Path(__file__).resolve().parents[5]
            / "skill_packs"
            / "libero_pro_task_binding_mining_v1"
            / "skills"
            / "_index.yaml"
        )

    def _pack(self, root: Path, *, conflict: bool = False) -> Path:
        skills = root / "skills"
        profiles = root / "profiles"
        (skills / "task_binding").mkdir(parents=True)
        profiles.mkdir(parents=True)
        (skills / "task_binding" / "stove.md").write_text(SKILL, encoding="utf-8")
        entries = ["task_binding/stove.md"]
        profile_text = PROFILES
        if conflict:
            second = SKILL.replace("bind_plate_to_stove_cook_region", "bind_plate_to_stove_top_region").replace(
                "stove_cook_region_v1", "stove_top_region_v1"
            ).replace("cook_region$", "top_region$")
            (skills / "task_binding" / "top.md").write_text(second, encoding="utf-8")
            entries.append("task_binding/top.md")
            profile_text += """  stove_top_region_v1:
    target_selector:
      source: language
    goal_selector:
      source: scene
      category_matches: "^flat_stove$"
    relation: on
    goal_site_selector:
      name_matches: ".*_top_region$"
      required: true
"""
        (profiles / "task_binding.yaml").write_text(profile_text, encoding="utf-8")
        index = skills / "_index.yaml"
        index.write_text(
            "task_binding_profile_registry: ../profiles/task_binding.yaml\n"
            + "task_binding:\n"
            + "".join(f"  - {entry}\n" for entry in entries),
            encoding="utf-8",
        )
        return index

    def _ranked_pack(self, root: Path) -> Path:
        skills = root / "skills"
        profiles = root / "profiles"
        (skills / "task_binding").mkdir(parents=True)
        profiles.mkdir(parents=True)
        (skills / "task_binding" / "spatial.md").write_text(RANKED_SKILL, encoding="utf-8")
        (profiles / "task_binding.yaml").write_text(RANKED_PROFILES, encoding="utf-8")
        index = skills / "_index.yaml"
        index.write_text(
            "task_binding_profile_registry: ../profiles/task_binding.yaml\n"
            "task_binding:\n"
            "  - task_binding/spatial.md\n",
            encoding="utf-8",
        )
        return index

    def _front_pack(self, root: Path) -> Path:
        skills = root / "skills"
        profiles = root / "profiles"
        (skills / "task_binding").mkdir(parents=True)
        profiles.mkdir(parents=True)
        (skills / "task_binding" / "front.md").write_text(FRONT_SKILL, encoding="utf-8")
        (profiles / "task_binding.yaml").write_text(FRONT_PROFILES, encoding="utf-8")
        index = skills / "_index.yaml"
        index.write_text(
            "task_binding_profile_registry: ../profiles/task_binding.yaml\n"
            "task_binding:\n"
            "  - task_binding/front.md\n",
            encoding="utf-8",
        )
        return index

    @staticmethod
    def _spatial_scene(*, bowl_1: list[float], bowl_2: list[float]) -> FakeScene:
        objects = [
            FakeObject("akita_black_bowl_1_main", np.asarray(bowl_1, dtype=np.float64)),
            FakeObject("akita_black_bowl_2_main", np.asarray(bowl_2, dtype=np.float64)),
            FakeObject("plate_1_main", np.asarray([-0.2, 0.0, 0.8])),
            FakeObject("glazed_rim_porcelain_ramekin_1_main", np.asarray([0.2, 0.0, 0.8])),
        ]
        return FakeScene(
            {obj.name: obj for obj in objects},
            table_geometry={"center": [0.0, 0.0, 0.8]},
        )

    def test_profile_resolves_fixture_site_before_generic_binder(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            resolver = load_task_binding_resolver(self._pack(Path(td)))
            result = resolve_language_mujoco_hints(
                "put the plate on the stove",
                _scene(),
                binding_resolver=resolver,
            )
        self.assertIsNone(result["failure_reason"])
        self.assertEqual(result["target"], "plate_1_main")
        self.assertEqual(result["goal"], "flat_stove_1_cook_region")
        self.assertEqual(result["goal_atoms"], [{"predicate": "on", "args": ["plate_1_main", "flat_stove_1_cook_region"]}])
        self.assertEqual(result["binding_skill"], "bind_plate_to_stove_cook_region")

    def test_task_parser_records_binding_skill_source(self) -> None:
        scene = _scene()
        with tempfile.TemporaryDirectory() as td:
            resolver = load_task_binding_resolver(self._pack(Path(td)))
            parsed = parse_task(
                "put the plate on the stove",
                scene.objects,
                scene=scene,
                task_goal_source="language_mujoco",
                task_binding_resolver=resolver,
            )
        self.assertEqual(parsed.target_hint, "plate_1_main")
        self.assertEqual(parsed.goal_hint, "flat_stove_1_cook_region")
        self.assertEqual(parsed.diagnostics["target_source"], "language_mujoco_skill")
        self.assertEqual(parsed.diagnostics["binding_profile"], "stove_cook_region_v1")

    def test_no_matching_skill_falls_back_to_generic_binder(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            resolver = load_task_binding_resolver(self._pack(Path(td)))
            result = resolve_language_mujoco_hints(
                "put the bowl inside the basket",
                _scene(),
                binding_resolver=resolver,
            )
        self.assertIsNotNone(result["failure_reason"])
        self.assertEqual(result["source"], "language_mujoco")

    def test_conflicting_skills_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            resolver = load_task_binding_resolver(self._pack(Path(td), conflict=True))
            result = resolver.resolve("put the plate on the stove", _scene())
        self.assertIsNotNone(result)
        self.assertEqual(result["failure_reason"], FAILURE_CONFLICT)
        self.assertIsNone(result["target"])

    def test_schema_rejects_bddl_and_concrete_instance_matchers(self) -> None:
        bad = SKILL.replace("scene_site_matches: \".*stove.*cook_region$\"", "bddl_goal_surface_matches: flat_stove_1_cook_region")
        with self.assertRaises(SkillSchemaError):
            parse_skill_markdown(bad)

    def test_ranked_language_selector_chooses_nearest_relation_candidate(self) -> None:
        scene = self._spatial_scene(bowl_1=[0.45, 0.0, 0.8], bowl_2=[0.75, 0.0, 0.8])
        with tempfile.TemporaryDirectory() as td:
            resolver = load_task_binding_resolver(self._ranked_pack(Path(td)))
            result = resolver.resolve(
                "pick up the black bowl next to the ramekin and place it on the plate",
                scene,
            )
        self.assertIsNotNone(result)
        self.assertIsNone(result["failure_reason"])
        self.assertEqual(result["target"], "akita_black_bowl_1_main")
        self.assertIn("target_ranked_candidates", result["binding_evidence"])

    def test_ranked_language_selector_honors_negated_between_relation(self) -> None:
        scene = self._spatial_scene(bowl_1=[0.0, 0.3, 0.8], bowl_2=[0.0, 0.5, 0.8])
        with tempfile.TemporaryDirectory() as td:
            resolver = load_task_binding_resolver(self._ranked_pack(Path(td)))
            result = resolver.resolve(
                "pick up the black bowl not between the plate and the ramekin and place it on the plate",
                scene,
            )
        self.assertIsNotNone(result)
        self.assertIsNone(result["failure_reason"])
        self.assertEqual(result["target"], "akita_black_bowl_2_main")

    def test_front_region_uses_language_and_fixture_topology(self) -> None:
        plate = FakeObject("plate_1_main", np.asarray([0.0, 0.0, 0.8]))
        button = FakeObject("flat_stove_1_button", np.asarray([-0.2, 0.1, 0.8]))
        stove = FakeObject(
            "flat_stove_1_main",
            np.asarray([-0.2, 0.1, 0.8]),
            geometry={
                "sites": [
                    {
                        "name": "flat_stove_1_cook_region",
                        "pos": [-0.05, 0.1, 0.8],
                        "size": [0.075, 0.075, 0.0025],
                    }
                ]
            },
        )
        scene = FakeScene({obj.name: obj for obj in (plate, button, stove)})
        with tempfile.TemporaryDirectory() as td:
            resolver = load_task_binding_resolver(self._front_pack(Path(td)))
            result = resolver.resolve("push the plate to the front of the stove", scene)
        self.assertIsNotNone(result)
        self.assertIsNone(result["failure_reason"])
        self.assertEqual(result["target"], "plate_1_main")
        self.assertEqual(result["goal"], "flat_stove_1_front_region")
        self.assertEqual(
            result["goal_atoms"],
            [{"predicate": "on", "args": ["plate_1_main", "flat_stove_1_front_region"]}],
        )
        descriptor = result["regions"]["flat_stove_1_front_region"]
        self.assertEqual(descriptor["front_anchor_object"], "flat_stove_1_button")
        self.assertNotIn("ranges", descriptor)

    def test_front_region_descriptor_materializes_in_current_scene_frame(self) -> None:
        region = "flat_stove_1_front_region"
        stove = ObjectState(
            "flat_stove_1_main",
            np.asarray([-0.2, 0.1, 0.8]),
            geometry={
                "sites": [
                    {
                        "name": "flat_stove_1_cook_region",
                        "pos": [-0.05, 0.1, 0.8],
                        "size": [0.075, 0.075, 0.0025],
                    }
                ]
            },
        )
        button = ObjectState("flat_stove_1_button", np.asarray([-0.2, 0.1, 0.8]))
        scene = SceneState(
            ee_pos=np.zeros(3),
            ee_quat=np.asarray([0.0, 0.0, 0.0, 1.0]),
            gripper_qpos=np.asarray([0.04, -0.04]),
            objects={stove.name: stove, button.name: button},
        )
        parsed = ParsedTask(
            language="push the plate to the front of the stove",
            target_hint="plate_1_main",
            goal_hint=region,
            operation="place",
            diagnostics={
                "goal_regions": {
                    region: {
                        "kind": "language_relative_table_region",
                        "relation": "front",
                        "reference_object": stove.name,
                        "front_anchor_object": button.name,
                        "rear_anchor_site": "flat_stove_1_cook_region",
                    }
                }
            },
        )
        surface = _language_relative_table_region_surface(
            region,
            {
                "center": [0.0, 0.0, 0.7],
                "bounds": {"x_min": -0.6, "x_max": 0.6, "y_min": -0.4, "y_max": 0.4, "z": 0.7},
            },
            scene,
            parsed,
        )
        self.assertIsNotNone(surface)
        self.assertLess(surface.pos[0], button.pos[0])
        self.assertAlmostEqual(surface.pos[1], button.pos[1], places=6)
        self.assertEqual(surface.geometry["kind"], "virtual_language_relative_table_region")

    def test_state_action_binding_is_explicitly_semantics_only(self) -> None:
        stove = FakeObject("flat_stove_1_main", np.asarray([0.0, 0.0, 0.8]))
        scene = FakeScene({stove.name: stove})
        resolver = load_task_binding_resolver(self._mined_pack(), mining=True)
        result = resolver.resolve("turn on the stove", scene)
        self.assertIsNotNone(result)
        self.assertIsNone(result["failure_reason"])
        self.assertEqual(result["goal_atoms"], [{"predicate": "turnon", "args": [stove.name]}])
        self.assertEqual(result["binding_capability"], "semantics_only")
        parsed = parse_task(
            "turn on the stove",
            scene.objects,
            scene=scene,
            task_goal_source="language_mujoco",
            task_binding_resolver=resolver,
        )
        self.assertEqual(parsed.diagnostics["binding_capability"], "semantics_only")

    def test_compound_open_then_inside_preserves_both_final_atoms(self) -> None:
        bowl = FakeObject("akita_black_bowl_1_main", np.asarray([0.0, 0.0, 0.8]))
        drawer = FakeObject("wooden_cabinet_1_cabinet_top", np.asarray([0.2, 0.0, 0.8]))
        scene = FakeScene({obj.name: obj for obj in (bowl, drawer)})
        resolver = load_task_binding_resolver(self._mined_pack(), mining=True)
        result = resolver.resolve("open the top drawer and put the bowl inside", scene)
        self.assertIsNotNone(result)
        self.assertIsNone(result["failure_reason"])
        self.assertEqual(result["target"], bowl.name)
        self.assertEqual(result["goal"], drawer.name)
        self.assertEqual(
            result["goal_atoms"],
            [
                {"predicate": "inside", "args": [bowl.name, drawer.name]},
                {"predicate": "open", "args": [drawer.name]},
            ],
        )
        self.assertEqual(result["binding_capability"], "semantics_only")

    def test_rule_semantics_does_not_replace_bound_state_goal_with_heuristics(self) -> None:
        stove = FakeObject("flat_stove_1_main", np.asarray([0.0, 0.0, 0.8]))
        scene = FakeScene({stove.name: stove})
        resolver = load_task_binding_resolver(self._mined_pack(), mining=True)
        parsed = parse_task(
            "turn on the stove",
            scene.objects,
            scene=scene,
            task_goal_source="language_mujoco",
            task_binding_resolver=resolver,
        )
        graph = SceneGraph(
            task_language=parsed.language,
            ee_pos=[0.0, 0.0, 0.0],
            gripper_open=True,
            objects=[ObjectNode(stove.name, [0.0, 0.0, 0.8])],
            world_atoms=[],
        )
        semantics = RuleTaskSemanticsInterpreter().interpret(parsed, graph)
        self.assertEqual(semantics.goal_object, stove.name)
        self.assertEqual(semantics.required_final_atoms[0]["predicate"], "turnon")
        self.assertEqual(semantics.task_progress["next_subgoal"], f"turnon {stove.name}")


if __name__ == "__main__":
    unittest.main()
