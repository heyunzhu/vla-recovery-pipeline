from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from experiments.robot.libero.skill_pipeline.perception_artifact import save_detections
from experiments.robot.libero.skill_pipeline.rgbd_observation import RGBDObservation, save_observation
from experiments.robot.libero.skill_pipeline.rgbd_scene import VisualDetection
from scripts.recovery.skill_pipeline.evaluate_rgbd_sequence import evaluate_sequence


LANGUAGE = "pick up the bowl and place it on the plate"


def _frame(step: int) -> RGBDObservation:
    return RGBDObservation(
        episode_id="probe",
        env_step=step,
        timestamp_s=step * 0.05,
        camera_id="agentview",
        rgb=np.zeros((32, 32, 3), dtype=np.uint8),
        depth_m=np.full((32, 32), 0.5, dtype=np.float32),
        depth_valid=np.ones((32, 32), dtype=bool),
        K=np.asarray([[32.0, 0.0, 16.0], [0.0, 32.0, 16.0], [0.0, 0.0, 1.0]]),
        T_world_camera=np.eye(4),
        robot_state={
            "robot0_joint_pos": [0.0] * 7,
            "robot0_gripper_qpos": [0.0, 0.0],
            "robot0_eef_pos": [0.0, 0.0, 0.0],
            "robot0_eef_quat": [0.0, 0.0, 0.0, 1.0],
        },
        calibration_version="test",
    )


class EvaluateRGBDSequenceTest(unittest.TestCase):
    def test_frozen_prompt_variant_requires_matching_config_on_every_frame(self) -> None:
        prompts = {"bowl": "black bowl", "plate": "white plate"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "summary.json").write_text(json.dumps({
                "kind": "rgbd_motion_probe", "language": LANGUAGE, "probe_env_steps": 1,
            }), encoding="utf-8")
            for step in range(2):
                frame = _frame(step)
                frame_dir = root / f"step{step:03d}" / "agentview"
                run_dir = frame_dir / "variant"
                save_observation(frame, frame_dir)
                run_dir.mkdir()
                (run_dir / "run_config.json").write_text(json.dumps({
                    "prompt_source": "prompts_json", "task_language": None, "prompts": prompts,
                }), encoding="utf-8")
                save_detections(frame, [], run_dir, detector_id="frozen-variant")
            report = evaluate_sequence(root, "agentview", "variant", prompts_override=prompts)
            self.assertEqual(report["prompt_source"], "prompts_json")
            self.assertEqual(report["scene_refusal_count"], 0)
            self.assertEqual(report["target_candidate_frame_count"], 0)
            with self.assertRaisesRegex(ValueError, "frozen prompt policy"):
                evaluate_sequence(root, "agentview", "variant", prompts_override={"bowl": "bowl"})

    def test_conflict_gap_preserves_target_id_without_claiming_task_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "summary.json").write_text(json.dumps({
                "kind": "rgbd_motion_probe", "language": LANGUAGE, "probe_env_steps": 2,
            }), encoding="utf-8")
            bowl = np.zeros((32, 32), dtype=bool)
            bowl[4:10, 4:10] = True
            plate = np.zeros((32, 32), dtype=bool)
            plate[20:26, 20:26] = True
            for step in range(3):
                frame = _frame(step)
                frame_dir = root / f"step{step:03d}" / "agentview"
                run_dir = frame_dir / "grounded_sam2_language_v1"
                save_observation(frame, frame_dir)
                run_dir.mkdir()
                (run_dir / "run_config.json").write_text(json.dumps({
                    "prompt_source": "task_language", "task_language": LANGUAGE,
                    "prompts": {"bowl": "bowl", "plate": "plate"},
                }), encoding="utf-8")
                conflicting_plate = bowl if step == 1 else plate
                save_detections(frame, [
                    VisualDetection(bowl, "bowl", 0.7, "text_guided_segmentation"),
                    VisualDetection(conflicting_plate, "plate", 0.7, "text_guided_segmentation"),
                ], run_dir, detector_id="frozen-test")

            report = evaluate_sequence(root, "agentview", "grounded_sam2_language_v1")
            self.assertEqual(report["frame_count"], 3)
            self.assertEqual(report["scene_refusal_count"], 1)
            self.assertEqual(report["target_candidate_frame_count"], 2)
            self.assertTrue(report["same_target_id_across_candidate_frames"])
            self.assertEqual(report["frames"][1]["scene_reason"], "overlapping_instance_masks")
            self.assertNotIn("binding", report["frames"][1])
            self.assertNotIn("success", report)


if __name__ == "__main__":
    unittest.main()
