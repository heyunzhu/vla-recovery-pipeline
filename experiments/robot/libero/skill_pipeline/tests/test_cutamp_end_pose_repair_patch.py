from __future__ import annotations

import pathlib
import tempfile
import unittest

from scripts.recovery.skill_pipeline.patch_cutamp_end_pose_repair import (
    FALLBACK_OLD,
    HELPER_ANCHOR,
    IMPORTS_OLD,
    MARKER,
    apply,
    latest_backup,
    revert,
)

PRISTINE = (
    '"""Solving motions with cuRobo."""\n'
    "\n"
    + IMPORTS_OLD
    + "from typing import List, Optional\n"
    "\n"
    "import torch\n"
    "\n"
    "\n"
    "def solve_curobo(plan_info, best_particle, world, config, timer, visualizer, obj_to_initial_pose):\n"
    '    """Solve for full motion plan."""\n'
    "    accum_plans = []\n"
    "\n"
    + HELPER_ANCHOR
    + "    for idx, ground_op in enumerate(plan_skeleton):\n"
    "        if ground_op.operator.name == Pick.name:\n"
    "            approach_result = traced_plan_single('approach', start_js, goal, plan_config)\n"
    + FALLBACK_OLD
    + "            if not end_result.success:\n"
    "                raise MotionPlanningError(f'Failed for {ground_op.name}')\n"
    "    return accum_plans\n"
)


class PatchMechanicsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = pathlib.Path(self._tmp.name) / "motion_solver.py"
        self.target.write_text(PRISTINE, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_three_edits_land(self):
        self.assertEqual(apply(self.target), 0)
        text = self.target.read_text(encoding="utf-8")
        self.assertIn("import math\n", text)
        self.assertIn(f"def {MARKER}(base_matrix):", text)
        self.assertIn(f"for repair_label, repair_matrix in {MARKER}(world_from_ee):", text)
        self.assertIn('"event": "end_pose_repair"', text)

    def test_the_original_fallback_survives(self):
        apply(self.target)
        text = self.target.read_text(encoding="utf-8")
        self.assertIn("partial_pose_fallback", text)
        self.assertEqual(text.count("end_unconstrained_fallback"), 1)

    def test_the_repair_loop_runs_before_the_failure_check(self):
        apply(self.target)
        text = self.target.read_text(encoding="utf-8")
        self.assertLess(
            text.index("end_pose_repair"),
            text.index("raise MotionPlanningError"),
            "the repair has to happen before the stage gives up",
        )

    def test_applying_twice_is_a_no_op(self):
        apply(self.target)
        first = self.target.read_text(encoding="utf-8")
        self.assertEqual(apply(self.target), 0)
        self.assertEqual(self.target.read_text(encoding="utf-8"), first)
        self.assertEqual(len(list(self.target.parent.glob("*.bak_*"))), 1)

    def test_revert_restores_the_pristine_file(self):
        apply(self.target)
        self.assertNotEqual(self.target.read_text(encoding="utf-8"), PRISTINE)
        self.assertEqual(revert(self.target), 0)
        self.assertEqual(self.target.read_text(encoding="utf-8"), PRISTINE)

    def test_a_missing_anchor_is_refused_without_touching_anything(self):
        broken = PRISTINE.replace(FALLBACK_OLD, "            pass\n")
        self.target.write_text(broken, encoding="utf-8")
        self.assertEqual(apply(self.target), 1)
        self.assertEqual(self.target.read_text(encoding="utf-8"), broken)
        self.assertIsNone(latest_backup(self.target))

    def test_revert_without_a_backup_reports_failure(self):
        self.assertEqual(revert(self.target), 1)


if __name__ == "__main__":
    unittest.main()
