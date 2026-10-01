import importlib
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch

from experiments.robot.libero.skill_pipeline.tests.test_visual_goal_surface import _sample, LANGUAGE
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard, FORBIDDEN_MODULES


class VisualDryRunAdapterTest(unittest.TestCase):
    def test_interfaces_share_one_snapshot_and_execution_denied(self):
        frame, detections, _ = _sample()
        calls = []
        def detector(f):
            calls.append(f.env_step)
            return detections
        adapter = VisualDryRunAdapter(RGBDSceneProvider(detector, detector_id="test", camera_id=frame.camera_id))
        first = adapter.query_state(frame, LANGUAGE)
        self.assertIs(first, adapter.perceive(frame, LANGUAGE))
        self.assertIs(first, adapter.executor_scene(frame, LANGUAGE))
        self.assertEqual(calls, [0])
        with self.assertRaisesRegex(PermissionError, "forbids planning"):
            adapter.require_action_authorization(frame, LANGUAGE)
        self.assertFalse(first.planning_allowed)

    def test_changed_frame_or_language_rejected(self):
        frame, detections, _ = _sample()
        adapter = VisualDryRunAdapter(RGBDSceneProvider(lambda _: detections, detector_id="test", camera_id=frame.camera_id))
        adapter.query_state(frame, LANGUAGE)
        with self.assertRaisesRegex(ValueError, "language changed"):
            adapter.perceive(frame, "pick up the plate and place it on the bowl")
        rgb = frame.rgb.copy()
        rgb[0, 0] = 255
        with self.assertRaisesRegex(ValueError, "content changed"):
            adapter.executor_scene(replace(frame, rgb=rgb), LANGUAGE)

    def test_detector_failure_propagates_without_fallback(self):
        frame, _, _ = _sample()
        def unavailable(_):
            raise RuntimeError("detector unavailable")
        adapter = VisualDryRunAdapter(RGBDSceneProvider(unavailable, detector_id="test", camera_id=frame.camera_id))
        with self.assertRaisesRegex(RuntimeError, "detector unavailable"):
            adapter.query_state(frame, LANGUAGE)

    def test_scene_conflict_returns_refusal_and_never_authorizes_action(self):
        frame, detections, _ = _sample()
        conflicting = [detections[0], replace(detections[0], category="plate")]
        adapter = VisualDryRunAdapter(RGBDSceneProvider(lambda _: conflicting, detector_id="test", camera_id=frame.camera_id))
        self.assertEqual(adapter.query_state(frame, LANGUAGE).status, "scene_refused")
        with self.assertRaises(PermissionError):
            adapter.require_action_authorization(frame, LANGUAGE)

    def test_oracle_guard_blocks_imports_and_restores_import_state(self):
        with patch.dict(sys.modules):
            for name in FORBIDDEN_MODULES:
                sys.modules.pop(name, None)
            guard = OracleImportGuard()
            with guard:
                with self.assertRaisesRegex(ImportError, "oracle module forbidden"):
                    importlib.import_module(FORBIDDEN_MODULES[0])
            self.assertEqual(guard.blocked_import_attempts, 1)
            self.assertNotIn(guard, sys.meta_path)


if __name__ == "__main__":
    unittest.main()
