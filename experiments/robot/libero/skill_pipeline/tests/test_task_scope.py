"""Task scope screen: pick-place vs articulated/push goals from the BDDL."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.robot.libero.skill_pipeline.task_scope import (
    OUT_OF_SCOPE,
    SCOPE_ARTICULATED,
    SCOPE_MIXED,
    SCOPE_PICK_PLACE,
    SCOPE_PUSH,
    SCOPE_UNKNOWN,
    bddl_root_from_libero_config,
    classify_bddl_file,
    classify_bddl_text,
    screen_bddl_dir,
)


REPO_ROOT = Path(__file__).resolve().parents[5]


def bddl(language: str, goal: str, *, interest: str = "a_1 b_1") -> str:
    return (
        "(define (problem LIBERO_Kitchen_Tabletop_Manipulation)\n"
        "  (:domain robosuite)\n"
        f"  (:language {language})\n"
        f"  (:obj_of_interest\n    {interest}\n  )\n"
        f"  (:goal\n    {goal}\n  )\n"
        ")\n"
    )


class TaskScopeTests(unittest.TestCase):
    def test_placement_goals_are_in_scope(self):
        cases = {
            "put the bowl on the plate": "(And (On akita_black_bowl_1_main plate_1_main))",
            "put the cream cheese in the bowl": "(And (In cream_cheese_1_main akita_black_bowl_1_main))",
            "put the bowl on top of the cabinet": "(And (On akita_black_bowl_1_main wooden_cabinet_1_top))",
        }
        for language, goal in cases.items():
            row = classify_bddl_text(bddl(language, goal), path="x.bddl")
            self.assertEqual(row.scope, SCOPE_PICK_PLACE, row)
            self.assertTrue(row.in_scope)

    def test_stack_is_in_scope_with_a_note(self):
        row = classify_bddl_text(
            bddl(
                "stack the black bowl at the front on the black bowl in the middle",
                "(And (On black_bowl_front black_bowl_middle) (On black_bowl_middle black_bowl_back))",
            )
        )
        self.assertEqual(row.scope, SCOPE_PICK_PLACE)
        self.assertIn("stack", row.notes)

    def test_articulated_goals_are_out_of_scope(self):
        open_row = classify_bddl_text(bddl("open the middle drawer of the cabinet", "(And (Open wooden_cabinet_1_middle_level))"))
        self.assertEqual(open_row.scope, SCOPE_ARTICULATED)
        # The goal parser drops TurnOn, so the raw goal section has to catch it.
        stove_row = classify_bddl_text(bddl("turn on the stove", "(And (TurnOn flat_stove_1))"))
        self.assertEqual(stove_row.scope, SCOPE_ARTICULATED)
        self.assertIn("turnon", stove_row.reason)

    def test_push_language_is_out_of_scope(self):
        row = classify_bddl_text(
            bddl("push the plate to the front of the stove", "(And (On plate_1 flat_stove_1))")
        )
        self.assertEqual(row.scope, SCOPE_PUSH)
        self.assertIn("push_language", row.notes)
        # The placement atom is still reported, so the call stays auditable.
        self.assertEqual([atom["predicate"] for atom in row.goal_atoms], ["on"])

    def test_mixed_goal_is_out_of_scope(self):
        row = classify_bddl_text(
            bddl(
                "open the top drawer and put the bowl inside",
                "(And (Open wooden_cabinet_1_top_level) (On akita_black_bowl_1_main wooden_cabinet_1_top_level))",
            )
        )
        self.assertEqual(row.scope, SCOPE_MIXED)

    def test_unsupported_goal_is_unknown_and_out_of_scope(self):
        row = classify_bddl_text(bddl("do something else", "(And (Toggle widget_1))"))
        self.assertEqual(row.scope, SCOPE_UNKNOWN)
        self.assertIn(row.scope, OUT_OF_SCOPE)

    def test_screen_bddl_dir_counts_and_order(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td) / "libero_goal_swap"
            root.mkdir(parents=True)
            (root / "a_bowl_on_plate.bddl").write_text(
                bddl("put the bowl on the plate", "(And (On akita_black_bowl_1_main plate_1_main))"), encoding="utf-8"
            )
            (root / "b_turn_on_stove.bddl").write_text(
                bddl("turn on the stove", "(And (TurnOn flat_stove_1))"), encoding="utf-8"
            )
            (root / "c_push_plate.bddl").write_text(
                bddl("push the plate to the front of the stove", "(And (On plate_1 flat_stove_1))"), encoding="utf-8"
            )

            result = screen_bddl_dir(root)
            self.assertEqual(result["task_count"], 3)
            self.assertEqual(result["in_scope_count"], 1)
            self.assertEqual(result["counts"], {SCOPE_PICK_PLACE: 1, SCOPE_ARTICULATED: 1, SCOPE_PUSH: 1})
            self.assertEqual(
                [Path(row["path"]).name for row in result["tasks"]],
                ["a_bowl_on_plate.bddl", "b_turn_on_stove.bddl", "c_push_plate.bddl"],
            )

    def test_libero_config_resolves_bddl_root(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            config = Path(td) / "config.yaml"
            config.write_text(json.dumps({"bddl_files": "bddl_files"}), encoding="utf-8")
            self.assertEqual(bddl_root_from_libero_config(config), Path(td) / "bddl_files")
            self.assertIsNone(bddl_root_from_libero_config(Path(td) / "missing.yaml"))

    def test_local_generated_bddls_stay_in_scope(self):
        root = REPO_ROOT / "benchmarks/libero90_generated_v1_envfiltered_304"
        files = sorted(root.rglob("*.bddl")) if root.is_dir() else []
        if not files:
            self.skipTest("local generated benchmark BDDLs are not present")
        rows = [classify_bddl_file(path) for path in files]
        self.assertEqual([row.scope for row in rows].count(SCOPE_PICK_PLACE), len(rows))


if __name__ == "__main__":
    unittest.main()
