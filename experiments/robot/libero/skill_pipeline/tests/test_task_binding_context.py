from __future__ import annotations

import json
import unittest
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from experiments.robot.libero.skill_pipeline.task_binding_context import build_task_binding_context


@dataclass
class FakeObject:
    name: str
    pos: np.ndarray
    quat: np.ndarray = field(default_factory=lambda: np.asarray([1.0, 0.0, 0.0, 0.0]))
    geometry: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeJoint:
    name: str
    qpos: float
    qvel: float = 0.0


@dataclass
class FakeScene:
    objects: dict[str, FakeObject]
    joints: dict[str, FakeJoint] = field(default_factory=dict)


def _obj(name: str, xyz: tuple[float, float, float], *, sites: tuple[str, ...] = ()) -> FakeObject:
    return FakeObject(
        name=name,
        pos=np.asarray(xyz, dtype=np.float64),
        geometry={
            "source": "test",
            "geoms": [
                {
                    "name": f"{name}_geom",
                    "shape": "box",
                    "size": [0.04, 0.04, 0.02],
                    "pos": list(xyz),
                    "quat": [1.0, 0.0, 0.0, 0.0],
                    "collision_active": True,
                    "mesh_vertices": [[0.0, 0.0, 0.0]],
                    "mesh_faces": [[0, 0, 0]],
                }
            ],
            "sites": [
                {
                    "name": site,
                    "body_name": name,
                    "shape": "box",
                    "size": [0.02, 0.02, 0.005],
                    "pos": list(xyz),
                }
                for site in sites
            ],
        },
    )


class TaskBindingContextTest(unittest.TestCase):
    def test_collects_compact_language_and_scene_context(self) -> None:
        bowl = _obj("akita_black_bowl_1_main", (0.0, 0.0, 0.83))
        plate = _obj("plate_1_main", (0.2, 0.0, 0.80))
        scene = FakeScene(
            {bowl.name: bowl, plate.name: plate},
            {
                "cabinet_drawer_joint": FakeJoint("cabinet_drawer_joint", 0.1),
                "robot0_joint1": FakeJoint("robot0_joint1", 0.0),
            },
        )
        context = build_task_binding_context(
            "put the black bowl on the plate",
            scene,
            task={"source_suite": "test", "task_id_1based": 1},
        )
        self.assertEqual(context["input_contract"]["policy_rollout_steps"], 0)
        self.assertEqual(context["binding"]["target"], bowl.name)
        self.assertEqual(context["binding"]["goal"], plate.name)
        self.assertEqual(context["binding"]["goal_atoms"][0]["predicate"], "on")
        self.assertEqual([joint["name"] for joint in context["scene"]["articulated_joints"]], ["cabinet_drawer_joint"])
        dumped = json.dumps(context)
        self.assertNotIn("mesh_vertices", dumped)
        self.assertNotIn("mesh_faces", dumped)
        self.assertNotIn("bddl_goal_atoms", dumped)

    def test_records_region_failure_and_mujoco_site(self) -> None:
        plate = _obj("plate_1_main", (0.0, 0.0, 0.80))
        stove = _obj(
            "flat_stove_1_main",
            (0.2, 0.0, 0.80),
            sites=("flat_stove_1_cook_region",),
        )
        context = build_task_binding_context(
            "put the plate on the stove",
            FakeScene({plate.name: plate, stove.name: stove}),
        )
        self.assertEqual(context["binding"]["failure_reason"], "language_goal_region_unsupported")
        stove_row = next(row for row in context["scene"]["objects"] if row["name"] == stove.name)
        self.assertEqual([site["name"] for site in stove_row["sites"]], ["flat_stove_1_cook_region"])

    def test_fingerprints_are_stable_and_pose_sensitive_only_for_snapshot(self) -> None:
        first = FakeScene(
            {
                "plate_1_main": _obj("plate_1_main", (0.2, 0.0, 0.80)),
                "akita_black_bowl_1_main": _obj("akita_black_bowl_1_main", (0.0, 0.0, 0.83)),
            }
        )
        moved = FakeScene(
            {
                "akita_black_bowl_1_main": _obj("akita_black_bowl_1_main", (0.1, 0.0, 0.83)),
                "plate_1_main": _obj("plate_1_main", (0.2, 0.0, 0.80)),
            }
        )
        language = "put the black bowl on the plate"
        a = build_task_binding_context(language, first)
        b = build_task_binding_context(language, moved)
        self.assertEqual(a["task_fingerprint"], b["task_fingerprint"])
        self.assertNotEqual(a["snapshot_fingerprint"], b["snapshot_fingerprint"])


if __name__ == "__main__":
    unittest.main()

