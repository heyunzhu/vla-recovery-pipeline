import dataclasses
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from experiments.robot.libero.skill_pipeline.tests.test_visual_goal_surface import _sample, LANGUAGE
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
from experiments.robot.libero.skill_pipeline.visual_planning_input import (
    build_visual_planning_input, export_visual_planning_input,
)


class VisualPlanningInputTest(unittest.TestCase):
    def setup_evidence(self, conflict=False):
        frame, detections, _ = _sample()
        if conflict:
            detections.append(detections[0])
        calls = []
        def detector(current):
            calls.append(current.env_step)
            return detections
        provider = RGBDSceneProvider(detector, detector_id="test", camera_id=frame.camera_id)
        adapter = VisualDryRunAdapter(provider)
        return frame, detections, calls, provider, adapter.query_state(frame, LANGUAGE)

    def test_actual_observed_arrays_and_desired_goal_do_not_invent_initial_facts(self):
        frame, _, calls, provider, handoff = self.setup_evidence()
        evidence = build_visual_planning_input(frame, handoff, provider)
        report = evidence.report
        self.assertEqual(calls, [0])
        self.assertEqual(report["status"], "evidence_prepared_with_gaps")
        self.assertEqual(report["desired_goal"]["args"], [handoff.binding.target_id, handoff.binding.goal_id])
        self.assertEqual(report["holding_state"], "unknown")
        self.assertFalse(report["free_space_verified"])
        self.assertFalse(report["solver_allowed"])
        self.assertNotIn("init_atoms", report)
        for surface in report["surfaces"]:
            points = evidence.arrays[surface["array_key"]]
            self.assertEqual(points.shape, (surface["point_count"], 3))
            np.testing.assert_allclose(points.mean(axis=0), surface["visible_centroid_world_m"])
            self.assertEqual(surface["object_pose"], "unknown")
        self.assertEqual(report["goal_surface"]["status"], "visible_surface_candidate")

    def test_provider_owns_immutable_masks_not_detector_references(self):
        frame, detections, _, provider, _ = self.setup_evidence()
        original = provider.get_detections(frame)[0].mask.copy()
        detections[0].mask[:] = False
        cached = provider.get_detections(frame)[0].mask
        np.testing.assert_array_equal(cached, original)
        with self.assertRaises(ValueError):
            cached.setflags(write=True)

    def test_point_arrays_are_immutable(self):
        frame, _, _, provider, handoff = self.setup_evidence()
        evidence = build_visual_planning_input(frame, handoff, provider)
        for array in evidence.arrays.values():
            with self.assertRaises(ValueError):
                array.setflags(write=True)

    def test_depth_change_outside_target_mask_is_rejected_by_full_frame_digest(self):
        frame, _, _, provider, handoff = self.setup_evidence()
        depth = frame.depth_m.copy()
        depth[-1, -1] += .01
        with self.assertRaisesRegex(ValueError, "content changed"):
            build_visual_planning_input(dataclasses.replace(frame, depth_m=depth), handoff, provider)

    def test_tampered_handoff_binding_is_rejected(self):
        frame, _, _, provider, handoff = self.setup_evidence()
        modified = dataclasses.replace(handoff, binding=dataclasses.replace(handoff.binding, target_id="obj_fake"))
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            build_visual_planning_input(frame, modified, provider)

    def test_conflicted_scene_cannot_export_planning_masks_or_goal(self):
        frame, _, _, provider, handoff = self.setup_evidence(conflict=True)
        evidence = build_visual_planning_input(frame, handoff, provider)
        self.assertEqual(evidence.report["status"], "refused")
        self.assertIsNone(evidence.report["desired_goal"])
        self.assertFalse(evidence.arrays)
        with self.assertRaisesRegex(ValueError, "no planning masks"):
            provider.get_detections(frame)

    def test_export_round_trip_preserves_arrays_and_artifact_digest(self):
        frame, _, _, provider, handoff = self.setup_evidence()
        evidence = build_visual_planning_input(frame, handoff, provider)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "planning"
            exported = export_visual_planning_input(evidence, root)
            report = json.loads((root / "planning_input.json").read_text())
            self.assertEqual(report["frame_content_sha256"], evidence.report["frame_content_sha256"])
            self.assertEqual(exported["geometry_npz_sha256"], hashlib.sha256((root / "visible_geometry.npz").read_bytes()).hexdigest())
            with np.load(root / "visible_geometry.npz", allow_pickle=False) as arrays:
                self.assertEqual(set(arrays.files), set(evidence.arrays))
                for key in arrays.files:
                    np.testing.assert_array_equal(arrays[key], evidence.arrays[key])
            with self.assertRaises(FileExistsError):
                export_visual_planning_input(evidence, root)


if __name__ == "__main__":
    unittest.main()
