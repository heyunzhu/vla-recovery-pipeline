import unittest
from dataclasses import replace

from experiments.robot.libero.skill_pipeline.tests.test_visual_goal_surface import _sample, LANGUAGE
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
from experiments.robot.libero.tiptop_repro.visual_diagnostic_interfaces import (
    CuTAMPVisualDiagnosticPerceiver, VisualDiagnosticRobotClient, VisualExecutionReadiness,
)


class VisualDiagnosticInterfacesTest(unittest.TestCase):
    def make_interfaces(self, detector=None):
        frame, detections, _ = _sample()
        calls = []
        def backend(current):
            calls.append(current.env_step)
            return detector(current) if detector is not None else detections
        adapter = VisualDryRunAdapter(RGBDSceneProvider(backend, detector_id="test", camera_id=frame.camera_id))
        return frame, calls, adapter, CuTAMPVisualDiagnosticPerceiver(adapter), VisualDiagnosticRobotClient(adapter)

    def test_consumers_share_frame_and_readiness_never_authorizes(self):
        frame, calls, adapter, perceiver, client = self.make_interfaces()
        handoff = adapter.query_state(frame, LANGUAGE)
        self.assertIs(handoff, perceiver.perceive(frame=frame, task_description=LANGUAGE))
        self.assertIs(handoff, client.get_scene(frame=frame, task_description=LANGUAGE))
        readiness = client.check_execution_readiness(frame=frame, task_description=LANGUAGE)
        self.assertEqual(calls, [0])
        self.assertEqual(readiness.snapshot_id, handoff.snapshot_id)
        self.assertFalse(readiness.planning_allowed)
        self.assertFalse(readiness.execution_allowed)
        self.assertIn("legacy_scene_state_unavailable", readiness.blockers)
        self.assertIn("holding_and_goal_verification", readiness.blockers)

    def test_legacy_signatures_and_environment_inputs_rejected_before_detection(self):
        frame, calls, _, perceiver, client = self.make_interfaces()
        class PoisonEnvironment:
            def __getattribute__(self, name):
                raise AssertionError("environment accessed")
        with self.assertRaises(TypeError):
            perceiver.perceive(PoisonEnvironment(), {}, LANGUAGE)
        with self.assertRaisesRegex(TypeError, "RGBDObservation"):
            client.get_scene(frame=PoisonEnvironment(), task_description=LANGUAGE)
        with self.assertRaises(TypeError):
            perceiver.perceive(frame=frame, task_description=LANGUAGE, holding_latch={})
        self.assertEqual(calls, [])

    def test_step_denied_without_reading_action_or_calling_detector(self):
        _, calls, _, _, client = self.make_interfaces()
        class PoisonAction:
            def __iter__(self):
                raise AssertionError("action read")
        with self.assertRaisesRegex(PermissionError, "forbids environment actions"):
            client.step(PoisonAction())
        self.assertEqual(calls, [])

    def test_changed_depth_invalidates_executor_read(self):
        frame, calls, _, perceiver, client = self.make_interfaces()
        perceiver.perceive(frame=frame, task_description=LANGUAGE)
        depth = frame.depth_m.copy()
        depth[0, 0] += 0.1
        with self.assertRaisesRegex(ValueError, "content changed"):
            client.check_execution_readiness(frame=replace(frame, depth_m=depth), task_description=LANGUAGE)
        self.assertEqual(calls, [0])

    def test_detector_failure_propagates_and_overlap_never_authorizes(self):
        def failed(_):
            raise RuntimeError("detector offline")
        frame, _, _, _, client = self.make_interfaces(failed)
        with self.assertRaisesRegex(RuntimeError, "detector offline"):
            client.check_execution_readiness(frame=frame, task_description=LANGUAGE)
        _, detections, _ = _sample()
        frame, _, _, _, client = self.make_interfaces(lambda _: [detections[0], replace(detections[0], category="plate")])
        readiness = client.check_execution_readiness(frame=frame, task_description=LANGUAGE)
        self.assertEqual(readiness.perception_status, "visual_id_candidate")
        self.assertFalse(readiness.planning_allowed)
        self.assertFalse(readiness.execution_allowed)
        self.assertIn("holding_and_goal_verification", readiness.blockers)

    def test_readiness_cannot_be_constructed_as_authorized(self):
        for flag in ("planning_allowed", "execution_allowed"):
            with self.assertRaises(ValueError):
                VisualExecutionReadiness("snapshot", "visual_id_candidate", ("diagnostic_mode",), **{flag: True})


if __name__ == "__main__":
    unittest.main()
