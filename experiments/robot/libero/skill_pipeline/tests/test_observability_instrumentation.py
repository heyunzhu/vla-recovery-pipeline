from __future__ import annotations

import json
import logging
import os
import pathlib
import tempfile
import types
import unittest
from unittest import mock

from experiments.robot.libero.tiptop_repro.recovery_observability import (
    append_recovery_diagnostic,
    recovery_attempt_summary,
)
from experiments.robot.libero.tiptop_repro.real_cutamp_backend import configure_child_logging

BACKEND = "experiments.robot.libero.tiptop_repro.real_cutamp_backend"


class ChildLoggingTests(unittest.TestCase):
    """The log level is what unlocks cuTAMP's own skeleton/residual logging."""

    def setUp(self):
        self._level = logging.root.level
        self._handlers = list(logging.root.handlers)

    def tearDown(self):
        logging.root.handlers = self._handlers
        logging.root.setLevel(self._level)

    def test_no_env_var_leaves_logging_alone(self):
        self.assertEqual(configure_child_logging({}), 0)
        self.assertEqual(logging.root.level, self._level)

    def test_info_turns_the_root_logger_up(self):
        self.assertEqual(configure_child_logging({"CUTAMP_LOG_LEVEL": "info"}), logging.INFO)
        self.assertEqual(logging.root.level, logging.INFO)

    def test_debug_is_accepted_too(self):
        self.assertEqual(configure_child_logging({"CUTAMP_LOG_LEVEL": "DEBUG"}), logging.DEBUG)

    def test_an_unusable_level_is_ignored(self):
        self.assertEqual(configure_child_logging({"CUTAMP_LOG_LEVEL": "shouty"}), 0)
        self.assertEqual(logging.root.level, self._level)

    def test_blank_and_whitespace_are_ignored(self):
        self.assertEqual(configure_child_logging({"CUTAMP_LOG_LEVEL": "   "}), 0)

    def test_the_installed_handler_can_actually_emit(self):
        configure_child_logging({"CUTAMP_LOG_LEVEL": "INFO"})
        records = []
        logging.root.addHandler(_Capture(records))
        logging.getLogger("cutamp.algorithm").info("[Opt 0] Optimizing plan ['MoveFree', 'Pick', 'Place']")
        self.assertTrue(any("[Opt 0]" in record for record in records))


class _Capture(logging.Handler):
    def __init__(self, sink):
        super().__init__()
        self.sink = sink

    def emit(self, record):
        self.sink.append(record.getMessage())


class RecoveryDiagnosticSinkTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self._tmp.name) / "nested" / "recovery.jsonl"
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("CUTAMP_RECOVERY_DIAG_JSONL", None)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def test_without_the_env_var_nothing_is_written(self):
        append_recovery_diagnostic({"outcome": "executed"})
        self.assertFalse(self.path.exists())

    def test_lines_are_appended_as_json(self):
        os.environ["CUTAMP_RECOVERY_DIAG_JSONL"] = str(self.path)
        append_recovery_diagnostic({"outcome": "executed", "attempt_idx": 0})
        append_recovery_diagnostic({"outcome": "no_feasible_plan", "attempt_idx": 1})
        rows = [json.loads(line) for line in self.path.read_text().splitlines()]
        self.assertEqual([row["outcome"] for row in rows], ["executed", "no_feasible_plan"])
        self.assertEqual(rows[1]["attempt_idx"], 1)

    def test_the_parent_directory_is_created(self):
        os.environ["CUTAMP_RECOVERY_DIAG_JSONL"] = str(self.path)
        append_recovery_diagnostic({"outcome": "executed"})
        self.assertTrue(self.path.exists())

    def test_non_serialisable_values_do_not_break_recovery(self):
        os.environ["CUTAMP_RECOVERY_DIAG_JSONL"] = str(self.path)
        append_recovery_diagnostic({"outcome": "executed", "odd": object()})
        self.assertEqual(len(self.path.read_text().splitlines()), 1)

    def test_an_unwritable_target_is_swallowed(self):
        os.environ["CUTAMP_RECOVERY_DIAG_JSONL"] = str(pathlib.Path(self._tmp.name))
        append_recovery_diagnostic({"outcome": "executed"})  # a directory: must not raise


class AttemptSummaryTests(unittest.TestCase):
    def _attempt(self, **backend_overrides):
        backend = {
            "execution_source": "real_cutamp_executable_plan",
            "real_cutamp": {
                "feasible": True,
                "failure_reason": None,
                "diagnostics": {"plan_type": "list"},
            },
            "execution_bridge_diagnostics": {
                "selected_recovery_goal": "regain_target_holding",
            },
        }
        backend.update(backend_overrides)
        return types.SimpleNamespace(
            attempt_idx=0,
            plan_reason="real_cutamp_executable_plan:regain_target_holding:fallback",
            feasible=True,
            planner_backend=backend,
        )

    def test_it_lifts_the_decision_fields(self):
        row = recovery_attempt_summary(self._attempt(), outcome="executed")
        self.assertEqual(row["attempt_idx"], 0)
        self.assertEqual(row["execution_source"], "real_cutamp_executable_plan")
        self.assertEqual(row["selected_recovery_goal"], "regain_target_holding")
        self.assertEqual(row["real_cutamp_feasible"], True)
        self.assertEqual(row["real_cutamp_plan_type"], "list")
        self.assertEqual(row["outcome"], "executed")

    def test_it_survives_a_bare_attempt(self):
        row = recovery_attempt_summary(types.SimpleNamespace(), outcome="no_feasible_plan")
        self.assertIsNone(row["attempt_idx"])
        self.assertEqual(row["execution_source"], "")


if __name__ == "__main__":
    unittest.main()
