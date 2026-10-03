import dataclasses
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from experiments.robot.libero.skill_pipeline import runner
from experiments.robot.libero.skill_pipeline.perception_artifact import save_detections
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
from experiments.robot.libero.skill_pipeline.visual_policy_loop import ExternalFrameDetector, run_visual_policy_episode
from experiments.robot.libero.skill_pipeline.tests.test_visual_goal_surface import _sample, LANGUAGE


class VisualPolicyLoopTest(unittest.TestCase):
    def setup_loop(self, *, detector_error=False, invalid_actions=False, done_after=None):
        frame, detections, _ = _sample()
        calls, rows, actions = [], [], []
        obs = dict(agentview_image=frame.rgb, robot0_eye_in_hand_image=frame.rgb,
                   robot0_eef_pos=np.zeros(3), robot0_eef_quat=np.array([0., 0., 0., 1.]),
                   robot0_gripper_qpos=np.array([0.02, 0.02]))
        class Env:
            def step(self, action):
                actions.append(action)
                return obs, 0, done_after is not None and len(actions) >= done_after, {}
            @property
            def sim(self):
                raise AssertionError("oracle sim accessed")
        class Policy:
            def reset(self):
                pass
            def infer(self, observation):
                assert "prompt" in observation
                value = np.zeros((3, 7))
                if invalid_actions:
                    value[0, 0] = np.nan
                return {"actions": value}
        def detector(current):
            calls.append(current.env_step)
            if detector_error:
                raise RuntimeError("detector failed")
            return detections
        adapter = VisualDryRunAdapter(RGBDSceneProvider(detector, detector_id="test", camera_id=frame.camera_id))
        kwargs = dict(env=Env(), policy=Policy(), initial_obs=obs, language=LANGUAGE,
            capture_frame=lambda obs, step: dataclasses.replace(frame, env_step=step, timestamp_s=step * 0.05),
            adapter=adapter, write_query=rows.append, max_steps=5, action_chunk=2,
            settle_steps=0, force_recovery_query=0)
        return kwargs, calls, rows, actions

    def test_policy_chunks_continue_after_refused_forced_recovery(self):
        kwargs, calls, rows, actions = self.setup_loop()
        with patch.object(runner, "_make_controller", side_effect=AssertionError("oracle recovery entered")):
            result = run_visual_policy_episode(**kwargs)
        self.assertEqual(len(actions), 5)
        self.assertEqual(calls, [0, 2, 4])
        self.assertEqual(result["queries"], 3)
        self.assertEqual(result["recovery_actions"], 0)
        self.assertEqual(rows[0]["recovery_decision"], "refused")
        self.assertEqual(rows[1]["recovery_decision"], "not_requested")
        for row in rows:
            self.assertEqual(row["mode"], "vla")
            self.assertFalse(row["execution_readiness"]["execution_allowed"])
            self.assertNotIn("target_xyz", row)
            self.assertNotIn("holding_status", row)

    def test_detector_failure_aborts_before_any_policy_action(self):
        kwargs, _, rows, actions = self.setup_loop(detector_error=True)
        with self.assertRaisesRegex(RuntimeError, "detector failed"):
            run_visual_policy_episode(**kwargs)
        self.assertFalse(actions)
        self.assertFalse(rows)

    def test_invalid_policy_actions_abort_before_execution(self):
        kwargs, _, rows, actions = self.setup_loop(invalid_actions=True)
        with self.assertRaisesRegex(ValueError, "finite nonempty"):
            run_visual_policy_episode(**kwargs)
        self.assertFalse(actions)
        self.assertFalse(rows)

    def test_benchmark_done_is_separate_from_visual_success(self):
        kwargs, calls, rows, actions = self.setup_loop(done_after=1)
        result = run_visual_policy_episode(**kwargs)
        self.assertTrue(result["benchmark_done"])
        self.assertFalse(result["visual_success_verified"])
        self.assertEqual(result["policy_actions"], 1)

    def test_runner_visual_policy_dispatch_does_not_enter_old_setup(self):
        args = runner.parse_args(["--visual_policy_eval", "--task_goal_source", "language_rgbd",
            "--task_suite_name", "libero_spatial", "--task_ids", "1",
            "--pretrained_path", "checkpoint", "--visual_prompts_json", "frozen.json",
            "--visual_output_dir", "new-output"])
        with patch("experiments.robot.libero.skill_pipeline.visual_policy_loop.run_from_args", return_value={"branch": "visual"}):
            with patch.object(runner, "_patch_torch_load", side_effect=AssertionError("old setup entered")):
                self.assertEqual(runner.main(args), {"branch": "visual"})
        args.visual_dry_run = True
        with self.assertRaisesRegex(ValueError, "one visual"):
            runner.main(args)

    def test_visual_policy_requires_checkpoint_and_disallows_skills(self):
        from experiments.robot.libero.skill_pipeline.tests.test_runner_visual_dry_run import _args
        args = _args()
        args.visual_dry_run = False
        with self.assertRaisesRegex(ValueError, "pretrained_path"):
            runner.validate_visual_policy_args(args)
        args.pretrained_path = "checkpoint"
        args.enable_skills = True
        with self.assertRaisesRegex(ValueError, "cannot execute skills"):
            runner.validate_visual_policy_args(args)

    def test_external_detector_verifies_config_and_refuses_change(self):
        frame, detections, _ = _sample()
        prompts = {"bowl": "black bowl"}
        with tempfile.TemporaryDirectory() as tmp:
            detector = ExternalFrameDetector(tmp, prompts, LANGUAGE, 1)
            def publish(current, version):
                output = Path(tmp) / f"step{current.env_step:06d}" / "detector"
                config = dict(prompts=prompts, prompt_source="prompts_json",
                              image_shape_hw=list(frame.rgb.shape[:2]), version=version)
                digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
                save_detections(current, detections, output, detector_id="grounded-sam2-" + digest[:12])
                (output / "run_config.json").write_text(json.dumps(config))
                (output / "READY").touch()
            with patch("experiments.robot.libero.skill_pipeline.visual_policy_loop.time.sleep", side_effect=lambda _: publish(frame, 1)):
                self.assertEqual(len(detector(frame)), len(detections))
            second = dataclasses.replace(frame, env_step=1)
            with patch("experiments.robot.libero.skill_pipeline.visual_policy_loop.time.sleep", side_effect=lambda _: publish(second, 2)):
                with self.assertRaisesRegex(ValueError, "configuration changed"):
                    detector(second)

    def test_external_detector_timeout_is_explicit(self):
        frame, _, _ = _sample()
        with tempfile.TemporaryDirectory() as tmp:
            detector = ExternalFrameDetector(tmp, {}, LANGUAGE, 0)
            with self.assertRaises(TimeoutError):
                detector(frame)


if __name__ == "__main__":
    unittest.main()
