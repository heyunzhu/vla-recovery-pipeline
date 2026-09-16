from __future__ import annotations

import argparse
import pathlib
import unittest

from experiments.robot.libero.skill_pipeline.runner import (
    EvalTask,
    apply_language_sources,
    bddl_language,
    parse_args,
    resolve_language_source_defaults,
)

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
TASK_AXIS_BDDL = FIXTURES / "libero_goal_task_axis.bddl"
NO_LANGUAGE_BDDL = FIXTURES / "libero_goal_no_language.bddl"

# What LIBERO reports for this file (derived from the BDDL *filename*) ...
POLICY_LANGUAGE = "put the cream cheese in the bowl"
# ... versus what the LIBERO-Pro task axis wrote inside it.
BDDL_LANGUAGE = "put the wine bottle in the bowl"


def _task(bddl_path: pathlib.Path = TASK_AXIS_BDDL) -> EvalTask:
    return EvalTask(
        task_id_1based=7,
        task_dir_name="task07",
        language=POLICY_LANGUAGE,
        bddl_path=bddl_path,
        initial_states=[],
        max_steps=300,
        source_suite="libero_goal_task",
        source_task_id_1based=7,
    )


def _args(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


class BddlLanguageTest(unittest.TestCase):
    def test_reads_the_language_section(self):
        self.assertEqual(bddl_language(TASK_AXIS_BDDL), BDDL_LANGUAGE)

    def test_missing_file_yields_empty(self):
        self.assertEqual(bddl_language(FIXTURES / "does_not_exist.bddl"), "")

    def test_missing_section_yields_empty(self):
        self.assertEqual(bddl_language(NO_LANGUAGE_BDDL), "")


class ApplyLanguageSourcesTest(unittest.TestCase):
    def setUp(self):
        self.task = _task()

    def test_auto_keeps_historical_behaviour_for_non_task_suite(self):
        """Non-task suites keep the legacy filename prompt and policy engine language."""

        tasks = [self.task]
        out = apply_language_sources(tasks, _args(task_suite_name="libero_goal_swap"))
        self.assertIs(out, tasks)
        self.assertEqual(out[0].engine_language, "")

    def test_auto_task_axis_uses_bddl_for_policy_and_engine(self):
        args = _args(task_suite_name="libero_goal_task")
        out = apply_language_sources([self.task], args)
        self.assertEqual(out[0].language, BDDL_LANGUAGE)
        self.assertEqual(out[0].engine_language, BDDL_LANGUAGE)
        self.assertEqual(args.task_language_source, "bddl")
        self.assertEqual(args.engine_language_source, "bddl")

    def test_engine_from_bddl_keeps_the_policy_prompt(self):
        out = apply_language_sources(
            [self.task],
            _args(task_language_source="filename", engine_language_source="bddl"),
        )
        self.assertEqual(out[0].language, POLICY_LANGUAGE)
        self.assertEqual(out[0].engine_language, BDDL_LANGUAGE)

    def test_bddl_policy_moves_both_sides(self):
        out = apply_language_sources(
            [self.task],
            _args(task_language_source="bddl", engine_language_source="policy"),
        )
        self.assertEqual(out[0].language, BDDL_LANGUAGE)
        self.assertEqual(out[0].engine_language, BDDL_LANGUAGE)

    def test_engine_falls_back_when_the_bddl_has_no_language(self):
        out = apply_language_sources(
            [_task(NO_LANGUAGE_BDDL)],
            _args(task_language_source="filename", engine_language_source="bddl"),
        )
        self.assertEqual(out[0].language, POLICY_LANGUAGE)
        self.assertEqual(out[0].engine_language, POLICY_LANGUAGE)

    def test_policy_falls_back_when_the_bddl_has_no_language(self):
        out = apply_language_sources(
            [_task(NO_LANGUAGE_BDDL)],
            _args(task_language_source="bddl", engine_language_source="policy"),
        )
        self.assertEqual(out[0].language, POLICY_LANGUAGE)
        self.assertEqual(out[0].engine_language, POLICY_LANGUAGE)

    def test_untouched_task_fields_survive(self):
        out = apply_language_sources(
            [self.task],
            _args(task_language_source="filename", engine_language_source="bddl"),
        )
        self.assertEqual(out[0].task_id_1based, self.task.task_id_1based)
        self.assertEqual(out[0].bddl_path, self.task.bddl_path)
        self.assertEqual(out[0].source_suite, self.task.source_suite)
        self.assertEqual(out[0].max_steps, self.task.max_steps)


class SwapAxisRegressionTest(unittest.TestCase):
    """On the swap axis the BDDL language and the filename language describe the same task,
    so an engine override must not change which objects are involved."""

    def test_engine_override_is_additive(self):
        task = _task(TASK_AXIS_BDDL)
        out = apply_language_sources(
            [task],
            _args(task_language_source="filename", engine_language_source="bddl"),
        )
        self.assertIn("wine bottle", out[0].engine_language)
        self.assertIn("cream cheese", out[0].language)


class ResolveLanguageSourceDefaultsTest(unittest.TestCase):
    def test_task_axis_auto_uses_bddl(self):
        self.assertEqual(resolve_language_source_defaults("libero_goal_task"), ("bddl", "bddl"))

    def test_non_task_axis_auto_keeps_legacy(self):
        self.assertEqual(resolve_language_source_defaults("libero_goal_swap"), ("filename", "policy"))

    def test_explicit_values_are_preserved(self):
        self.assertEqual(
            resolve_language_source_defaults("libero_goal_task", "filename", "bddl"),
            ("filename", "bddl"),
        )


class CliTest(unittest.TestCase):
    _BASE = ["--log_dir", "/tmp/x", "--exp_name", "x", "--pretrained_path", "/tmp/model"]

    def test_defaults_are_auto(self):
        args = parse_args(self._BASE)
        self.assertEqual(args.task_language_source, "auto")
        self.assertEqual(args.engine_language_source, "auto")
        self.assertEqual(args.task_goal_source, "bddl")

    def test_flags_are_accepted(self):
        args = parse_args(self._BASE + [
            "--task_language_source", "bddl",
            "--engine_language_source", "bddl",
            "--task_goal_source", "language_mujoco",
        ])
        self.assertEqual(args.task_language_source, "bddl")
        self.assertEqual(args.engine_language_source, "bddl")
        self.assertEqual(args.task_goal_source, "language_mujoco")


if __name__ == "__main__":
    unittest.main()
