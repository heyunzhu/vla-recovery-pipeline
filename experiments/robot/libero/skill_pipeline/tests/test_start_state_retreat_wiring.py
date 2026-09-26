from __future__ import annotations

import types
import unittest
from unittest import mock

from experiments.robot.libero.tiptop_repro.cutamp_controller_v2 import (
    CuTAMPV2Config,
    CuTAMPV2TipTopController,
)

CONTROLLER = "experiments.robot.libero.tiptop_repro.cutamp_controller_v2"


def _plan(*problems):
    attempt = types.SimpleNamespace
    return types.SimpleNamespace(attempts=[attempt(problem=p) for p in problems])


def _backend(record):
    backend = mock.MagicMock()
    backend.retreat_from_start_collision.return_value = record
    return backend


class DefaultsTests(unittest.TestCase):
    def test_retreat_is_off_unless_asked_for(self):
        cfg = CuTAMPV2Config()
        self.assertFalse(cfg.start_state_retreat)
        self.assertEqual(cfg.start_state_retreat_max_iters, 40)
        self.assertGreater(cfg.start_state_retreat_max_env_steps, 0)


class RetreatDecisionTests(unittest.TestCase):
    def setUp(self):
        self.controller = CuTAMPV2TipTopController(CuTAMPV2Config(start_state_retreat=True))
        self.obs = {"sentinel": True}

    def _run(self, record, plan):
        backend = _backend(record)
        with mock.patch(f"{CONTROLLER}.RealCuTAMPBackend", return_value=backend), mock.patch(
            f"{CONTROLLER}.execute_start_state_retreat"
        ) as execute:
            execute.return_value = ({"after": "retreat"}, {"executed": True, "env_steps": 7})
            obs, out = self.controller._retreat_from_start_collision(
                env=object(),
                obs=self.obs,
                real_plan=plan,
                client_cfg=None,
                step_callback=None,
                holding_latch={},
                max_env_steps=60,
            )
        return backend, execute, obs, out

    def test_no_problem_to_probe_short_circuits(self):
        _, execute, obs, out = self._run({"ok": True}, _plan())
        self.assertFalse(out["executed"])
        self.assertEqual(out["reason"], "no_problem_to_probe")
        self.assertIs(obs, self.obs)
        execute.assert_not_called()

    def test_unavailable_retreat_reports_why(self):
        _, execute, obs, out = self._run({"ok": False, "reason": "no_runner_python"}, _plan("P"))
        self.assertFalse(out["executed"])
        self.assertEqual(out["skip_reason"], "no_runner_python")
        self.assertIs(obs, self.obs)
        execute.assert_not_called()

    def test_a_free_start_state_is_left_alone(self):
        _, execute, obs, out = self._run({"ok": True, "needs_retreat": False}, _plan("P"))
        self.assertFalse(out["executed"])
        self.assertEqual(out["skip_reason"], "start_state_already_free")
        execute.assert_not_called()

    def test_a_retreat_that_did_not_clear_the_state_is_not_executed(self):
        record = {"ok": True, "needs_retreat": True, "free": False, "q": [0.1]}
        _, execute, obs, out = self._run(record, _plan("P"))
        self.assertFalse(out["executed"])
        self.assertEqual(out["skip_reason"], "retreat_did_not_clear_the_start_state")
        execute.assert_not_called()

    def test_a_successful_retreat_is_executed_on_the_robot(self):
        record = {"ok": True, "needs_retreat": True, "free": True, "q": [0.1, 0.2], "iterations": 1}
        backend, execute, obs, out = self._run(record, _plan("THE_PROBLEM"))
        self.assertTrue(out["executed"])
        self.assertEqual(obs, {"after": "retreat"})
        backend.retreat_from_start_collision.assert_called_once()
        self.assertEqual(backend.retreat_from_start_collision.call_args.args[0], "THE_PROBLEM")
        self.assertEqual(execute.call_args.args[2], [0.1, 0.2])
        self.assertEqual(out["execution"]["env_steps"], 7)

    def test_the_first_goal_candidate_supplies_the_problem(self):
        backend, _, _, _ = self._run(
            {"ok": True, "needs_retreat": False}, _plan("FIRST", "SECOND")
        )
        self.assertEqual(backend.retreat_from_start_collision.call_args.args[0], "FIRST")

    def test_a_candidate_without_a_problem_is_skipped(self):
        attempt = types.SimpleNamespace
        plan = types.SimpleNamespace(attempts=[attempt(problem=None), attempt(problem="REAL")])
        backend, _, _, _ = self._run({"ok": True, "needs_retreat": False}, plan)
        self.assertEqual(backend.retreat_from_start_collision.call_args.args[0], "REAL")

    def test_execution_that_reports_done_is_not_marked_executed(self):
        backend = _backend({"ok": True, "needs_retreat": True, "free": True, "q": [0.1]})
        with mock.patch(f"{CONTROLLER}.RealCuTAMPBackend", return_value=backend), mock.patch(
            f"{CONTROLLER}.execute_start_state_retreat"
        ) as execute:
            execute.return_value = ({"after": "retreat"}, {"executed": False, "reason": "no_target_joints"})
            _, out = self.controller._retreat_from_start_collision(
                env=object(),
                obs=self.obs,
                real_plan=_plan("P"),
                client_cfg=None,
                step_callback=None,
                holding_latch={},
                max_env_steps=60,
            )
        self.assertFalse(out["executed"])
        self.assertIn("reason", out["execution"])


if __name__ == "__main__":
    unittest.main()
