from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import json

import numpy as np

from experiments.robot.libero.skill_pipeline.perception_artifact import save_detections
from experiments.robot.libero.skill_pipeline.rgbd_observation import save_observation
from experiments.robot.libero.skill_pipeline.rgbd_scene import VisualDetection
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.tests.test_rgbd_scene import _frame
from experiments.robot.libero.skill_pipeline.visual_geometry import WorkspaceBounds
from experiments.robot.libero.skill_pipeline.visual_goal_surface import goal_surface_evidence
from experiments.robot.libero.skill_pipeline.visual_recovery_handoff import build_visual_recovery_handoff
from scripts.recovery.skill_pipeline.export_visual_handoff import export_handoff


LANGUAGE = "pick up the bowl and place it on the plate"
BOUNDS = WorkspaceBounds((-1, 1), (-1, 1), (0.8, 1.2))


def _sample():
    frame = _frame(0)
    plate = np.zeros((32, 32), dtype=bool)
    plate[8:28, 10:30] = True
    bowl = np.zeros_like(plate)
    bowl[2:8, 2:8] = True
    # Most of the image is a raised obstacle; it must never enter plate fitting.
    depth = np.full_like(frame.depth_m, 0.3)
    depth[plate] = 0.5
    frame = replace(frame, depth_m=depth)
    detections = [VisualDetection(bowl, "bowl", 0.7, "text_guided_segmentation"),
                  VisualDetection(plate, "plate", 0.7, "text_guided_segmentation")]
    provider = RGBDSceneProvider(lambda _: detections, detector_id="test", camera_id=frame.camera_id)
    handoff = build_visual_recovery_handoff(LANGUAGE, frame, provider.get_admission(frame))
    return frame, detections, handoff


class VisualGoalSurfaceTest(unittest.TestCase):
    def test_mask_limits_fit_and_erosion_keeps_observed_bounds(self):
        frame, detections, handoff = _sample()
        result = goal_surface_evidence(frame, handoff, detections, BOUNDS)
        self.assertEqual(result["status"], "visible_surface_candidate")
        self.assertEqual(result["mask_pixels"], 400)
        self.assertEqual(result["interior_pixels"], 256)
        self.assertEqual(result["plane"]["inlier_points"], 256)
        self.assertAlmostEqual(result["plane"]["z_at_world_origin_m"], 1.0)
        self.assertFalse(result["planning_allowed"])
        self.assertIn("support_extent_and_object_footprint", result["unresolved_checks"])

    def test_depth_and_workspace_shortfalls_refuse(self):
        frame, detections, handoff = _sample()
        no_depth = replace(frame, depth_valid=np.zeros_like(frame.depth_valid))
        self.assertEqual(goal_surface_evidence(no_depth, handoff, detections, BOUNDS)["reason"],
                         "insufficient_interior_depth")
        off_height = WorkspaceBounds((-1, 1), (-1, 1), (0.8, 0.9))
        self.assertEqual(goal_surface_evidence(frame, handoff, detections, off_height)["reason"],
                         "horizontal_plane_not_found")

    def test_changed_masks_and_wrong_frame_are_rejected(self):
        frame, detections, handoff = _sample()
        mask = detections[1].mask.copy()
        mask[9, 11] = False
        altered = [detections[0], replace(detections[1], mask=mask)]
        with self.assertRaisesRegex(ValueError, "scene provenance"):
            goal_surface_evidence(frame, handoff, altered, BOUNDS)
        with self.assertRaisesRegex(ValueError, "RGB-D frame"):
            goal_surface_evidence(replace(frame, env_step=1), handoff, detections, BOUNDS)

    def test_surface_with_large_raised_patch_fails_coverage_gate(self):
        frame, detections, _ = _sample()
        depth = frame.depth_m.copy()
        depth[11:18, 13:20] = 0.45
        frame = replace(frame, depth_m=depth)
        provider = RGBDSceneProvider(lambda _: detections, detector_id="test", camera_id=frame.camera_id)
        handoff = build_visual_recovery_handoff(LANGUAGE, frame, provider.get_admission(frame))
        result = goal_surface_evidence(frame, handoff, detections, BOUNDS, min_inlier_fraction=0.9)
        self.assertEqual(result["reason"], "plane_fit_insufficient")
        self.assertLess(result["inlier_fraction_of_valid_interior"], 0.9)

    def test_history_and_nonplate_goals_cannot_supply_surface(self):
        frame, detections, handoff = _sample()
        goal_id = handoff.binding.goal_id
        history = tuple(replace(o, validity="not_observed", detection_index=None)
                        if o.id == goal_id else o for o in handoff.visible_objects)
        self.assertEqual(goal_surface_evidence(frame, replace(handoff, visible_objects=history),
                                              detections, BOUNDS)["reason"], "goal_not_currently_observed")
        not_plate = tuple(replace(o, category="bowl") if o.id == goal_id else o
                          for o in handoff.visible_objects)
        self.assertEqual(goal_surface_evidence(frame, replace(handoff, visible_objects=not_plate),
                                              detections, BOUNDS)["reason"], "unsupported_goal_surface")

    def test_export_requires_explicit_matching_frozen_variant(self):
        frame, detections, _ = _sample()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_observation(frame, root / "frame")
            save_detections(frame, detections, root / "detector", detector_id="test")
            prompts = {"bowl": "bowl", "plate": "white plate"}
            (root / "detector" / "run_config.json").write_text(json.dumps({
                "prompt_source": "prompts_json", "prompts": prompts}), encoding="utf-8")
            (root / "summary.json").write_text(json.dumps({"language": LANGUAGE}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "prompt configuration"):
                export_handoff(root / "frame", root / "detector", root / "summary.json")
            result = export_handoff(root / "frame", root / "detector", root / "summary.json",
                                    prompts_override=prompts,
                                    goal_surface_workspace={"x": [-1, 1], "y": [-1, 1], "z": [0.8, 1.2]})
            self.assertEqual(result["schema_version"], 2)
            self.assertEqual(result["goal_surface_evidence"]["status"], "visible_surface_candidate")
            self.assertFalse(result["handoff"]["planning_allowed"])


if __name__ == "__main__":
    unittest.main()
