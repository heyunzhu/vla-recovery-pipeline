import dataclasses
import subprocess
import sys
import unittest

from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
from experiments.robot.libero.skill_pipeline.tests.test_visual_goal_surface import _sample, LANGUAGE
from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
from experiments.robot.libero.tiptop_repro.visual_recovery_controller import RGBDRecoveryAdmissionController


class VisualRecoveryControllerTest(unittest.TestCase):
    def setup_controller(self, empty=False):
        frame, detections, _ = _sample()
        calls = []
        def detector(current):
            calls.append(current.env_step)
            return [] if empty else detections
        adapter = VisualDryRunAdapter(RGBDSceneProvider(detector, detector_id="test", camera_id=frame.camera_id))
        return frame, calls, adapter, RGBDRecoveryAdmissionController(adapter)

    def test_recovery_uses_shared_provider_once_without_oracle_import(self):
        # Oracle compatibility tests share the parent process; preserve the strict
        # production guard by checking this boundary in an uncontaminated child.
        code='from experiments.robot.libero.skill_pipeline.tests.test_visual_recovery_controller import VisualRecoveryControllerTest; VisualRecoveryControllerTest()._assert_shared_provider_without_oracle()'
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)

    def _assert_shared_provider_without_oracle(self):
        frame, calls, adapter, controller = self.setup_controller()
        with OracleImportGuard() as guard:
            before = adapter.query_state(frame, LANGUAGE)
            result = controller.recover(frame=frame, task_description=LANGUAGE)
        self.assertEqual(calls, [frame.env_step])
        self.assertEqual(result.snapshot_id, before.snapshot_id)
        self.assertEqual(result.target_id, before.binding.target_id)
        self.assertEqual(result.goal_id, before.binding.goal_id)
        self.assertTrue(result.shared_snapshot_verified)
        self.assertEqual(result.decision, "refused")
        self.assertEqual(result.recovery_actions, 0)
        self.assertEqual(guard.blocked_import_attempts, 0)

    def test_modified_same_step_frame_is_refused(self):
        frame, _, adapter, controller = self.setup_controller()
        adapter.query_state(frame, LANGUAGE)
        depth = frame.depth_m.copy()
        depth[frame.depth_valid] += 0.001
        with self.assertRaises(ValueError):
            controller.recover(frame=dataclasses.replace(frame, depth_m=depth), task_description=LANGUAGE)

    def test_missing_binding_is_a_structured_refusal(self):
        frame, _, _, controller = self.setup_controller(empty=True)
        result = controller.recover(frame=frame, task_description=LANGUAGE)
        self.assertIsNone(result.target_id)
        self.assertIn("task_binding", result.blockers)

    def test_environment_is_rejected_before_detection(self):
        _, calls, _, controller = self.setup_controller()
        class Poison:
            def __getattribute__(self, name):
                raise AssertionError("oracle accessed")
        with self.assertRaises(TypeError):
            controller.recover(frame=Poison(), task_description=LANGUAGE)
        self.assertFalse(calls)


if __name__ == "__main__":
    unittest.main()
