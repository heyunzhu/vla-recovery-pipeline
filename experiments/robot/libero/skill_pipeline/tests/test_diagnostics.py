from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.diagnostics.registry import (
    DiagnosticRegistryError,
    default_registry_path,
    load_registry,
)
from experiments.robot.libero.skill_pipeline.diagnostics.replay import replay_query_rows
from experiments.robot.libero.skill_pipeline.diagnostics.runtime import DiagnosticSignalRuntime, parse_active_statuses


class DiagnosticRegistryTests(unittest.TestCase):
    def test_load_default_registry(self):
        registry = load_registry(default_registry_path())
        self.assertEqual([spec.id for spec in registry.signals], ["target_approach_window_v1"])
        spec = registry.signals[0]
        self.assertEqual(spec.status, "shadow")
        self.assertIn("diag_target_approach_window_v1", spec.outputs)

    def test_rejects_unsafe_provider_and_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.yaml"
            path.write_text(
                """
signals:
  - id: bad_signal
    status: shadow
    hook: after_pi0_query
    provider: other.package.provider
    outputs: [diag_bad_signal]
""",
                encoding="utf-8",
            )
            with self.assertRaises(DiagnosticRegistryError):
                load_registry(path)

            path.write_text(
                """
signals:
  - id: bad_output
    status: shadow
    hook: after_pi0_query
    provider: experiments.robot.libero.skill_pipeline.diagnostics.providers.target_approach_window_v1
    outputs: [target_ee_distance_m]
""",
                encoding="utf-8",
            )
            with self.assertRaises(DiagnosticRegistryError):
                load_registry(path)

    def test_online_requires_online_safe(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "registry.yaml"
            path.write_text(
                """
signals:
  - id: online_without_gate
    status: online
    hook: after_pi0_query
    provider: experiments.robot.libero.skill_pipeline.diagnostics.providers.target_approach_window_v1
    outputs: [diag_online_without_gate]
""",
                encoding="utf-8",
            )
            with self.assertRaises(DiagnosticRegistryError):
                load_registry(path)


class DiagnosticRuntimeTests(unittest.TestCase):
    def test_shadow_runtime_records_values_without_mutating_state(self):
        registry = load_registry(default_registry_path())
        runtime = DiagnosticSignalRuntime.from_registry(registry, active_statuses={"shadow"})
        state = {
            "gripper_aperture": 0.04,
            "holding_status": "handempty_or_unconfirmed",
            "target_ee_distance_m": 0.08,
            "nearest_pickable_is_target": True,
            "intent_object_is_target": None,
            "target_future_min_xy_distance_m": 0.05,
        }
        result = runtime.compute("after_pi0_query", state)
        self.assertTrue(result["values"]["diag_target_approach_window_v1"])
        self.assertGreater(result["values"]["diag_target_approach_window_v1_score"], 0.0)
        self.assertNotIn("diagnostic_signals", state)

    def test_replay_query_rows(self):
        registry = load_registry(default_registry_path())
        runtime = DiagnosticSignalRuntime.from_registry(registry, active_statuses=parse_active_statuses("shadow"))
        rows = [
            {
                "gripper_aperture": 0.04,
                "holding_status": "handempty_or_unconfirmed",
                "target_ee_distance_m": 0.08,
                "nearest_pickable_is_target": True,
                "target_future_min_xy_distance_m": 0.05,
            }
        ]
        out = replay_query_rows(rows, runtime)
        self.assertIn("diagnostic_signals", out[0])
        self.assertTrue(out[0]["diagnostic_signals"]["values"]["diag_target_approach_window_v1"])

    def test_parse_statuses_rejects_unknown(self):
        with self.assertRaises(ValueError):
            parse_active_statuses("shadow,experimental")


if __name__ == "__main__":
    unittest.main()
