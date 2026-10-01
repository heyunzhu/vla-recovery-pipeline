import unittest
from unittest.mock import patch

from experiments.robot.libero.skill_pipeline import runner
from experiments.robot.libero.skill_pipeline.tests.test_visual_goal_surface import _sample, LANGUAGE
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter


def _args():
    return runner.parse_args([
        "--visual_dry_run", "--task_goal_source", "language_rgbd",
        "--task_suite_name", "libero_spatial", "--task_ids", "1",
        "--visual_prompts_json", "frozen.json", "--visual_output_dir", "new-output",
    ])


class RunnerVisualDryRunTest(unittest.TestCase):
    def test_main_dispatches_before_torch_policy_and_evaluation_loop(self):
        with patch.object(runner, "_run_visual_dry_run", return_value={"dry_run": True}) as route:
            with patch.object(runner, "_patch_torch_load", side_effect=AssertionError("policy path entered")):
                self.assertEqual(runner.main(_args()), {"dry_run": True})
        route.assert_called_once()

    def test_visual_query_and_binding_share_adapter_without_env_access(self):
        frame, detections, _ = _sample()
        class NoEnvironmentAccess:
            def __getattribute__(self, name):
                raise AssertionError("environment was accessed: " + name)
        env = NoEnvironmentAccess()
        adapter = VisualDryRunAdapter(RGBDSceneProvider(lambda _: detections, detector_id="test", camera_id=frame.camera_id))
        binding = runner._parse_episode_task(env, None, LANGUAGE, "language_rgbd",
                                            visual_adapter=adapter, rgbd_frame=frame)
        state = runner._query_state(env, None, LANGUAGE, scene_source="rgbd",
                                    visual_adapter=adapter, rgbd_frame=frame)
        self.assertIs(binding, state["visual_handoff"].binding)
        self.assertIs(state["visual_handoff"], adapter.perceive(frame, LANGUAGE))
        self.assertFalse(state["planning_allowed"])
        self.assertIn("holding", state["unavailable_oracle_fields"])
        self.assertNotIn("target_xyz", state)
        self.assertNotIn("bddl_goal_atoms", state)

    def test_missing_visual_inputs_or_mixed_inputs_never_fall_back(self):
        with self.assertRaisesRegex(ValueError, "visual adapter"):
            runner._parse_episode_task(None, None, LANGUAGE, "language_rgbd")
        with self.assertRaisesRegex(ValueError, "RGB-D query"):
            runner._query_state(None, None, LANGUAGE, scene_source="rgbd")
        with self.assertRaisesRegex(ValueError, "mixed"):
            runner._query_state(None, None, LANGUAGE, visual_adapter=object())

    def test_visual_mode_requires_explicit_scope_and_language_source(self):
        args = _args()
        args.task_goal_source = "bddl"
        with self.assertRaisesRegex(ValueError, "language_rgbd"):
            runner.validate_visual_dry_run_args(args)
        args.task_goal_source = "language_rgbd"
        args.task_ids = "1,2"
        with self.assertRaisesRegex(ValueError, "one explicit"):
            runner.validate_visual_dry_run_args(args)

    def test_rgbd_mode_without_dry_run_rejected_before_policy(self):
        args = _args()
        args.visual_dry_run = False
        with self.assertRaisesRegex(ValueError, "oracle routing is forbidden"):
            runner.main(args)


if __name__ == "__main__":
    unittest.main()
