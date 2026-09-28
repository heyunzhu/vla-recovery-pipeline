from __future__ import annotations

import unittest

from experiments.robot.libero.skill_pipeline.rgbd_scene import VisualObject, VisualSceneSnapshot
from experiments.robot.libero.skill_pipeline.visual_task_binding import bind_visual_pick_place


LANGUAGE = "pick up the black bowl between the plate and the ramekin and place it on the plate"


def _object(object_id: str, category: str, x: float, y: float, *, validity: str = "observed") -> VisualObject:
    return VisualObject(
        id=object_id, category=category, validity=validity, identity_status="new",
        last_seen_step=0, visible_centroid_world_m=(x, y, 1.0),
        visible_bounds_world_m=None, pixel_bbox_xyxy=None, depth_valid_fraction=1.0,
        raw_detection_score=0.5, mask_source="text_guided_segmentation",
    )


def _scene(*objects: VisualObject, source: str = "rgbd") -> VisualSceneSnapshot:
    return VisualSceneSnapshot(
        snapshot_id="episode:step0:agentview", episode_id="episode", env_step=0,
        timestamp_s=0.0, camera_id="agentview", source=source, objects=objects,
        perception_backend_id="test_detector",
    )


class VisualTaskBindingTest(unittest.TestCase):
    def test_between_selects_one_bowl_but_does_not_verify_color(self) -> None:
        scene = _scene(
            _object("obj_001", "bowl", -0.20, 0.33),
            _object("obj_002", "bowl", -0.08, 0.20),
            _object("obj_003", "plate", 0.05, 0.20),
            _object("obj_004", "ramekin", -0.20, 0.19),
        )
        result = bind_visual_pick_place(LANGUAGE, scene)
        self.assertEqual(result.status, "candidate_requires_attribute_check")
        self.assertEqual((result.target_id, result.goal_id), ("obj_002", "obj_003"))
        self.assertEqual(result.reference_ids, ("obj_003", "obj_004"))
        self.assertEqual(result.unverified_descriptors, ("black bowl",))

    def test_missing_reference_or_ambiguous_target_refuses(self) -> None:
        missing = _scene(_object("obj_001", "bowl", -0.08, 0.20), _object("obj_003", "plate", 0.05, 0.20))
        self.assertEqual(bind_visual_pick_place(LANGUAGE, missing).reason, "reference_not_observed")
        ambiguous = _scene(
            _object("obj_001", "bowl", -0.08, 0.20),
            _object("obj_002", "bowl", -0.09, 0.21),
            _object("obj_003", "plate", 0.05, 0.20),
            _object("obj_004", "ramekin", -0.20, 0.19),
        )
        self.assertEqual(bind_visual_pick_place(LANGUAGE, ambiguous).reason, "target_ambiguous")

    def test_next_to_requires_a_close_and_distinct_candidate(self) -> None:
        language = "pick up the black bowl next to the ramekin and place it on the plate"
        scene = _scene(
            _object("obj_001", "bowl", 0.08, 0.01),
            _object("obj_002", "bowl", 0.38, 0.01),
            _object("obj_003", "plate", 0.5, 0.1),
            _object("obj_004", "ramekin", 0.0, 0.0),
        )
        result = bind_visual_pick_place(language, scene)
        self.assertEqual(result.target_id, "obj_001")
        self.assertEqual(result.status, "candidate_requires_attribute_check")
        unclear = _scene(
            _object("obj_001", "bowl", 0.08, 0.01),
            _object("obj_002", "bowl", -0.09, 0.01),
            _object("obj_003", "plate", 0.5, 0.1),
            _object("obj_004", "ramekin", 0.0, 0.0),
        )
        self.assertEqual(bind_visual_pick_place(language, unclear).reason, "target_ambiguous")

    def test_unobserved_objects_do_not_bind_and_oracle_scene_rejected(self) -> None:
        scene = _scene(
            _object("obj_001", "mug", 0.0, 0.0, validity="not_observed"),
            _object("obj_002", "caddy", 0.1, 0.0),
        )
        self.assertEqual(
            bind_visual_pick_place("take the mug and put it into the caddy", scene).reason,
            "target_not_observed",
        )
        with self.assertRaisesRegex(ValueError, "RGB-D scene"):
            bind_visual_pick_place(LANGUAGE, _scene(source="mujoco"))

    def test_simple_unique_objects_bind_ids_only(self) -> None:
        scene = _scene(_object("obj_001", "mug", 0.0, 0.0), _object("obj_002", "caddy", 0.1, 0.0))
        result = bind_visual_pick_place("take the mug and put it into the caddy", scene)
        self.assertEqual(result.status, "bound_ids")
        self.assertEqual(result.goal_relation, "inside")
        self.assertEqual((result.target_id, result.goal_id), ("obj_001", "obj_002"))


if __name__ == "__main__":
    unittest.main()
