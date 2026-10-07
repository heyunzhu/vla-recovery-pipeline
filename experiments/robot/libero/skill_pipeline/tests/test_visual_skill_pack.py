import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from experiments.robot.libero.skill_pipeline.tests.test_visual_goal_surface import _sample
from experiments.robot.libero.skill_pipeline.visual_skill_pack import (
    load_visual_candidate_pack, select_visual_skill, evaluate_visual_skill_candidate,
)


class VisualSkillPackTest(unittest.TestCase):
    def test_bound_ids_match_but_cannot_enter_online_library(self):
        _, _, handoff = _sample()
        result = select_visual_skill(handoff)
        self.assertEqual(result["target_id"], handoff.binding.target_id)
        self.assertEqual(result["selector_status"], "candidate_match")
        self.assertEqual(result["online_admission"], "refused")
        self.assertFalse(result["execution_allowed"])

    def test_missing_and_ambiguous_binding_do_not_match(self):
        _, _, handoff = _sample()
        for status in ("binding_refused", "scene_refused"):
            result = select_visual_skill(dataclasses.replace(handoff, status=status, binding=None))
            self.assertEqual(result["selector_status"], "refused")

    def test_stale_target_and_wrong_goal_category_do_not_match(self):
        _, _, handoff = _sample()
        for changes in ({"last_seen_step": -1}, {"identity_status": "ambiguous"}, {"category": "box"}):
            objects = tuple(dataclasses.replace(obj, **changes) if obj.id == handoff.binding.target_id else obj
                            for obj in handoff.visible_objects)
            self.assertEqual(select_visual_skill(dataclasses.replace(handoff, visible_objects=objects))["selector_status"], "refused")

    def test_manifest_changes_cannot_enable_online_or_change_frames_or_parameters(self):
        for field, value in (("online_enabled", True), ("parameters", {"rim_depth_offset_m": .02}),
                             ("reference_frames", {"anchor": "body_local"}), ("generator", "arbitrary_module")):
            pack = load_visual_candidate_pack()
            pack[field] = value
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "pack.json"
                path.write_text(json.dumps(pack))
                with self.assertRaises(ValueError):
                    load_visual_candidate_pack(path)

    def test_insufficient_depth_refuses_geometry_without_oracle_fallback(self):
        frame, detections, handoff = _sample()
        result = evaluate_visual_skill_candidate(frame, handoff, detections)
        self.assertEqual(result["selector_status"], "candidate_match")
        self.assertEqual(result["geometry_status"], "refused")
        self.assertIn("insufficient current depth", result["reason"])

    def test_changed_mask_is_rejected_before_sampling(self):
        frame, detections, handoff = _sample()
        mask = detections[0].mask.copy()
        mask[0, 0] = True
        detections[0] = dataclasses.replace(detections[0], mask=mask)
        with self.assertRaisesRegex(ValueError, "mask provenance"):
            evaluate_visual_skill_candidate(frame, handoff, detections)

    def test_changed_target_depth_is_rejected(self):
        frame, detections, handoff = _sample()
        depth = frame.depth_m.copy()
        depth[detections[0].mask] += .01
        with self.assertRaisesRegex(ValueError, "depth geometry changed"):
            evaluate_visual_skill_candidate(dataclasses.replace(frame, depth_m=depth), handoff, detections)

    def test_changed_proprioception_is_rejected(self):
        frame, detections, handoff = _sample()
        state = dict(frame.robot_state)
        state["robot0_eef_pos"] = [1, 2, 3]
        with self.assertRaisesRegex(ValueError, "robot reference"):
            evaluate_visual_skill_candidate(dataclasses.replace(frame, robot_state=state), handoff, detections)

    def test_different_step_and_rgb_are_rejected(self):
        frame, detections, handoff = _sample()
        rgb = frame.rgb.copy()
        rgb[0, 0, 0] ^= 1
        for modified in (dataclasses.replace(frame, env_step=1), dataclasses.replace(frame, rgb=rgb)):
            with self.assertRaisesRegex(ValueError, "does not match"):
                evaluate_visual_skill_candidate(modified, handoff, detections)

    def test_generator_output_remains_candidate_only(self):
        frame, detections, handoff = _sample()
        with patch("experiments.robot.libero.skill_pipeline.visual_skill_pack.make_visible_rim_candidate",
                   return_value={"contact_verified": False}) as generator:
            result = evaluate_visual_skill_candidate(frame, handoff, detections)
        generator.assert_called_once()
        self.assertEqual(result["geometry_status"], "visible_rim_candidate")
        self.assertFalse(result["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
