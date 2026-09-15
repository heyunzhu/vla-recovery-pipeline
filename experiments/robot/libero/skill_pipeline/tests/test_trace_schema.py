from __future__ import annotations

import unittest

from experiments.robot.libero.skill_pipeline.trace_schema import (
    TraceSchemaError,
    make_query_record,
    recover_without_execution_event,
    recovery_events_from_trace,
)


class RecoveryTraceTests(unittest.TestCase):
    def test_query_record_defaults_diagnostic_signals(self):
        record = make_query_record(
            {
                "task_id_1based": 1,
                "episode_idx": 0,
                "seed": 90,
                "query_idx": 0,
                "env_step": 0,
                "mode": "vla",
                "object_followed": None,
            }
        )
        self.assertEqual(record["diagnostic_signals"], {})

    def test_query_record_rejects_bad_diagnostic_signals(self):
        with self.assertRaises(TraceSchemaError):
            make_query_record(
                {
                    "task_id_1based": 1,
                    "episode_idx": 0,
                    "seed": 90,
                    "query_idx": 0,
                    "env_step": 0,
                    "mode": "vla",
                    "object_followed": None,
                    "diagnostic_signals": [],
                }
            )

    def test_records_optimized_and_stop_events(self):
        rows = recovery_events_from_trace(
            [
                {
                    "event": "execute_optimized_operator",
                    "label": "MoveFree(q0, traj1, q1)",
                    "result": {"success": False, "error": "optimized_joint_interpolation_too_large"},
                },
                {"event": "execution_failed_stop", "step": "MoveFree(q0, traj1, q1)", "reason": "optimized_joint_interpolation_too_large"},
            ],
            query_idx=16,
            skill_id="bowl_pick_empty_close_stall",
        )
        self.assertEqual([row["kind"] for row in rows], ["trajectory", "trajectory"])
        self.assertEqual(rows[0]["error"], "optimized_joint_interpolation_too_large")
        self.assertFalse(rows[1]["success"])

    def test_plan_row_uses_motiongen_failure_reason(self):
        row = recover_without_execution_event(
            {
                "plan_reason": "missing_real_cutamp_executable_plan:place_on:x",
                "planner_backend": {
                    "execution_source": "real_cutamp_executable_plan_missing",
                    "real_cutamp": {
                        "attempts": [
                            {
                                "result": {
                                    "failure_reason": "Motion planning failed for 9/9 satisfying particle(s)",
                                    "num_satisfying": 9,
                                }
                            }
                        ]
                    },
                },
            },
            query_idx=16,
            skill_id="bowl_pick_empty_close_stall",
        )
        self.assertEqual(row["kind"], "plan")
        self.assertIn("Motion planning failed", row["error"])
        self.assertEqual(row["num_satisfying"], 9)
        self.assertFalse(row["success"])


if __name__ == "__main__":
    unittest.main()
