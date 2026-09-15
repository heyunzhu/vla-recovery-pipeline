from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.grasp_static import (
    check_grasp_skill_library,
    render_grasp_static_markdown,
)


def _write_skill(path: Path, *, applies_to: str, params: str = "    source: test\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                "id: test_grasp",
                "name: Test grasp",
                "kind: recovery_hint",
                "track: pair",
                "scope: grasp",
                "priority: 10",
                "when_to_apply: test",
                "when_not_to_apply: test",
                "recovery_point: test",
                "applies_to:",
                applies_to.rstrip(),
                "recovery_hints:",
                "  grasp_profile: bowl_rim_diagonal_mixed_topdown_v1",
                "  target: target",
                "  params:",
                params.rstrip(),
                "evidence:",
                "  tasks:",
                "    - test",
                "  episodes:",
                "    - test",
                "---",
                "",
                "## Intent",
                "",
                "Test fixture.",
            ]
        ),
        encoding="utf-8",
    )


class GraspStaticTests(unittest.TestCase):
    def test_repo_online_grasp_skills_have_no_static_errors(self):
        index = Path(__file__).resolve().parents[5] / "skill_packs/libero90_legacy/skills/_index.yaml"
        report = check_grasp_skill_library(index)
        errors = [item.to_dict() for item in report.findings if item.severity == "ERROR"]
        self.assertEqual(errors, [])
        self.assertGreaterEqual(len(report.online_grasp_skill_ids), 10)
        self.assertEqual(report.online_grasp_skill_ids, report.checked_grasp_skill_ids)
        markdown = render_grasp_static_markdown(report)
        self.assertIn("Grasp Skill Static Gate", markdown)
        self.assertIn("black_bowl_generic", markdown)

    def test_current_canary_winners_are_stable(self):
        index = Path(__file__).resolve().parents[5] / "skill_packs/libero90_legacy/skills/_index.yaml"
        report = check_grasp_skill_library(index)
        winners = {row.name: row.winner_skill_id for row in report.canary_results}
        self.assertEqual(winners["black_bowl_generic"], "grasp_bowl_rim_diagonal_mixed_topdown")
        self.assertEqual(winners["black_bowl_cabinet_top"], "grasp_bowl_rim_away_from_open_drawer_topdown")
        self.assertEqual(winners["white_bowl_right_plate"], "grasp_task38_white_bowl_microwave_high_lift")
        self.assertEqual(winners["cream_cheese_flat_box"], "grasp_flat_box_topdown_short_side_deep")
        self.assertEqual(winners["milk_upright"], "grasp_carton_upright_body_side")
        self.assertEqual(winners["milk_fallen"], "grasp_carton_fallen_body_side")

    def test_unregistered_pair_grasp_requires_draft_or_retired_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / "skills"
            _write_skill(
                skills / "pair" / "recovery_hint" / "grasp" / "test_grasp.md",
                applies_to='  all:\n    - target_name_matches: "bowl"\n    - target_name_excludes: "white_bowl|white bowl"',
            )
            index = skills / "_index.yaml"
            index.write_text("online: []\n", encoding="utf-8")
            report = check_grasp_skill_library(index)
            self.assertIn("unregistered_grasp_skill_file", {item.code for item in report.findings})

    def test_online_grasp_requires_target_name_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / "skills"
            rel = "pair/recovery_hint/grasp/test_grasp.md"
            _write_skill(
                skills / rel,
                applies_to='  all:\n    - task_language_matches: "bowl"',
            )
            index = skills / "_index.yaml"
            index.write_text(f"online:\n  - {rel}\n", encoding="utf-8")
            report = check_grasp_skill_library(index)
            codes = {item.code for item in report.findings if item.severity == "ERROR"}
            self.assertIn("grasp_missing_target_name_match", codes)
            self.assertIn("grasp_task_language_only_scope", codes)

    def test_unknown_grasp_executor_key_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / "skills"
            rel = "pair/recovery_hint/grasp/test_grasp.md"
            _write_skill(
                skills / rel,
                applies_to='  all:\n    - target_name_matches: "bowl"\n    - target_name_excludes: "white_bowl|white bowl"',
                params="    executor:\n      teleport_to_grasp: 1\n    source: test\n",
            )
            index = skills / "_index.yaml"
            index.write_text(f"online:\n  - {rel}\n", encoding="utf-8")
            report = check_grasp_skill_library(index)
            codes = {item.code for item in report.findings if item.severity == "ERROR"}
            self.assertIn("unknown_grasp_executor_key", codes)

    def test_extra_candidate_grasp_skill_is_checked_before_indexing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills = root / "skills"
            (skills / "pair" / "recovery_hint" / "grasp").mkdir(parents=True)
            index = skills / "_index.yaml"
            index.write_text("online: []\n", encoding="utf-8")
            candidate = root / "candidate.md"
            _write_skill(
                candidate,
                applies_to='  all:\n    - target_name_matches: "bowl"\n    - target_name_excludes: "white_bowl|white bowl"',
                params="    executor:\n      teleport_to_grasp: 1\n    source: test\n",
            )
            report = check_grasp_skill_library(index, extra_skill_files=[candidate])
            codes = {item.code for item in report.findings if item.severity == "ERROR"}
            self.assertIn("unknown_grasp_executor_key", codes)
            self.assertIn("test_grasp", report.checked_grasp_skill_ids)


if __name__ == "__main__":
    unittest.main()
