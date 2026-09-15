from __future__ import annotations

import json
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.mine import score_mine, score_validation_run
from experiments.robot.libero.skill_pipeline.packer import load_episode
from experiments.robot.libero.skill_pipeline.trace_schema import EpisodeWriter, make_query_record
from experiments.robot.libero.skill_pipeline.triage import (
    STATUS_COVERED,
    STATUS_NEEDS_CAPABILITY,
    STATUS_SKILL_REPAIRABLE,
    inspect_cutamp_debug,
    triage_validation_run,
)


def _query(task_id: int, ep: int, idx: int, *, hook_fired: bool = False) -> dict:
    return make_query_record(
        {
            "task_id_1based": task_id,
            "episode_idx": ep,
            "seed": 90,
            "query_idx": idx,
            "env_step": idx,
            "mode": "recovery" if hook_fired else "vla",
            "ee_xyz": [0.0, 0.0, 0.8],
            "ee_quat": [0.0, 0.0, 0.0, 1.0],
            "gripper_qpos": [0.04, -0.04],
            "gripper_aperture": 0.04,
            "gripper_cmd": -1.0,
            "target_name": "akita_black_bowl_1_main",
            "target_xyz": [0.1, 0.0, 0.9],
            "holding_status": "handempty_or_unconfirmed",
            "holding_object": None,
            "bilateral": None,
            "object_followed": None,
            "logvar_gripper_first": None,
            "residual_score": None,
            "hook_fired": hook_fired,
            "skill_id": "bowl_pick_empty_close_stall" if hook_fired else "",
            "recovery_hints": {},
        }
    )


def _write_episode(
    path: Path,
    *,
    task_id: int = 1,
    ep: int = 0,
    success: bool = False,
    hook_fired: bool = False,
    recovery_rows: list[dict] | None = None,
) -> None:
    writer = EpisodeWriter(path)
    writer.append_query(_query(task_id, ep, 0, hook_fired=hook_fired))
    writer.append_query(_query(task_id, ep, 1, hook_fired=False))
    for row in recovery_rows or []:
        payload = dict(row)
        payload.setdefault("query_idx", 0)
        payload.setdefault("skill_id", "bowl_pick_empty_close_stall")
        writer.append_recovery(payload)
    writer.write_episode_json(
        {
            "task_id_1based": task_id,
            "task_id": task_id - 1,
            "episode_idx": ep,
            "seed": 90,
            "task_description": "put the black bowl on the plate",
            "success": success,
            "recovery_calls": int(hook_fired),
        }
    )


def _episodes(root: Path, task_id: int, n_success: int, *, hook_fired: bool = False, rows: list[dict] | None = None):
    for ep in range(5):
        _write_episode(
            root / f"task{task_id:02d}" / f"ep{ep:02d}",
            task_id=task_id,
            ep=ep,
            success=ep < n_success,
            hook_fired=hook_fired and ep >= n_success,
            recovery_rows=rows if ep >= n_success else None,
        )
    return [load_episode(root / f"task{task_id:02d}" / f"ep{ep:02d}") for ep in range(5)]


class TriageTests(unittest.TestCase):
    def test_three_of_five_is_covered_even_when_remaining_failures_are_unhit(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = _episodes(root / "off", 1, 0)
            on = _episodes(root / "on", 1, 3, hook_fired=False)
            scored = score_validation_run(baseline, on)
            report = triage_validation_run(
                task_id=1,
                baseline_episodes=baseline,
                on_episodes=on,
                scored=scored,
                on_dir=root / "on",
                success_min=0.60,
            )
            self.assertTrue(scored["passed"])
            self.assertFalse(scored["stable_hit"])
            self.assertEqual(report.status, STATUS_COVERED)
            self.assertFalse(report.skill_attempt_allowed)

    def test_missing_trigger_is_skill_repairable(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = _episodes(root / "off", 1, 0)
            on = _episodes(root / "on", 1, 1, hook_fired=False)
            scored = score_validation_run(baseline, on)
            report = triage_validation_run(
                task_id=1,
                baseline_episodes=baseline,
                on_episodes=on,
                scored=scored,
                on_dir=root / "on",
                success_min=0.60,
            )
            self.assertEqual(report.status, STATUS_SKILL_REPAIRABLE)
            self.assertTrue(report.skill_attempt_allowed)
            self.assertEqual(report.primary_signature, "trigger_missing_or_late")

    def test_grasp_lift_probe_failure_is_skill_repairable(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {
                    "kind": "lift_probe",
                    "event": "grasp_lift_probe",
                    "success": True,
                    "confirmed": False,
                    "object_followed": False,
                    "object_lift_m": 0.0,
                    "error": "",
                }
            ]
            baseline = _episodes(root / "off", 1, 0)
            on = _episodes(root / "on", 1, 1, hook_fired=True, rows=rows)
            scored = score_validation_run(baseline, on)
            report = triage_validation_run(
                task_id=1,
                baseline_episodes=baseline,
                on_episodes=on,
                scored=scored,
                on_dir=root / "on",
                success_min=0.60,
            )
            self.assertEqual(report.status, STATUS_SKILL_REPAIRABLE)
            self.assertEqual(report.primary_signature, "grasp_candidate_or_timing")

    def test_place_lift_executor_failure_requests_capability_draft(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {
                    "kind": "place",
                    "event": "execute",
                    "label": "Place(akita_black_bowl_1_main, grasp1, pose1, plate_1_main, q2)",
                    "success": False,
                    "error": "place_lift_too_low",
                }
            ]
            baseline = _episodes(root / "off", 1, 0)
            on = _episodes(root / "on", 1, 1, hook_fired=True, rows=rows)
            scored = score_validation_run(baseline, on)
            report = triage_validation_run(
                task_id=1,
                baseline_episodes=baseline,
                on_episodes=on,
                scored=scored,
                on_dir=root / "on",
                success_min=0.60,
            )
            self.assertEqual(report.status, STATUS_NEEDS_CAPABILITY)
            self.assertTrue(report.skill_attempt_allowed)
            self.assertEqual(report.primary_signature, "place_lift_too_low")
            self.assertIn("place_profile", report.recommended_artifacts)

    def test_cutamp_zero_constraints_are_prioritized_over_result_summaries(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            debug = Path(tmp) / "cutamp_debug"
            debug.mkdir()
            for idx in range(20):
                (debug / f"solve_{idx}.result.json").write_text(
                    json.dumps(
                        {
                            "available": True,
                            "feasible": False,
                            "num_satisfying": 0,
                            "failure_reason": "No satisfying particles found after optimizing all 1 plan(s)",
                            "diagnostics": {"grasp_sampler_profile": "libero_topdown"},
                        }
                    ),
                    encoding="utf-8",
                )
            (debug / "solve_0.stderr.txt").write_text(
                "\n".join(
                    [
                        "[Collision] robot_to_movables <= 0.001 has 0/64 satisfying, 0 remaining",
                        "[StablePlacement] flat_stove_1_cook_region_in_xy <= 0.01 has 0/64 satisfying, 0 remaining",
                        "[StablePlacement] flat_stove_1_cook_region_in_xy <= 0.01 has 0/64 satisfying, 0 remaining",
                    ]
                ),
                encoding="utf-8",
            )

            evidence = inspect_cutamp_debug(Path(tmp), max_items=4)

            self.assertEqual(evidence[0].kind, "cutamp_zero_constraint")
            self.assertEqual(evidence[0].data["name"], "flat_stove_1_cook_region_in_xy")
            self.assertEqual(evidence[0].data["count"], 2)
            self.assertTrue(any(item.kind == "cutamp_result" for item in evidence))

    def test_score_mine_requests_codex_for_capability_failure_before_cap(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {
                    "kind": "trajectory",
                    "event": "execute",
                    "label": "MoveFree(q0, traj1, q1)",
                    "success": False,
                    "error": "optimized_motion_tracking_stalled",
                }
            ]
            _episodes(root / "off", 1, 0)
            _episodes(root / "on", 1, 1, hook_fired=True, rows=rows)
            skills = root / "skills"
            skills.mkdir()
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            result = score_mine(
                run_dir=root / "off",
                skills_root=skills,
                out_dir=root / "mine",
                on_dir=root / "on",
                task_id=1,
            )
            self.assertEqual(result["status"], "need_draft")
            self.assertEqual(result["triage"]["task_id"], 1)
            self.assertEqual(result["triage"]["status"], STATUS_NEEDS_CAPABILITY)
            state = json.loads((root / "mine" / "mine_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["awaiting_task"], 1)
            self.assertEqual(state["awaiting_kind"], "draft")
            self.assertEqual(state.get("completed") or [], [])

    def test_score_mine_reopens_previously_completed_capability_failure_task(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {
                    "kind": "trajectory",
                    "event": "execute",
                    "label": "MoveFree(q0, traj1, q1)",
                    "success": False,
                    "error": "optimized_motion_tracking_stalled",
                }
            ]
            _episodes(root / "off", 1, 0)
            _episodes(root / "on", 1, 1, hook_fired=True, rows=rows)
            skills = root / "skills"
            skills.mkdir()
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            mine = root / "mine"
            mine.mkdir()
            (mine / "mine_state.json").write_text(
                json.dumps(
                    {
                        "completed": [1],
                        "awaiting_task": None,
                        "awaiting_kind": None,
                        "tasks": {"1": {"writes": 1, "attempts": []}},
                    }
                ),
                encoding="utf-8",
            )

            result = score_mine(
                run_dir=root / "off",
                skills_root=skills,
                out_dir=mine,
                on_dir=root / "on",
                task_id=1,
            )

            self.assertEqual(result["status"], "need_draft")
            state = json.loads((mine / "mine_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["awaiting_task"], 1)
            self.assertEqual(state["awaiting_kind"], "draft")
            self.assertEqual(state.get("completed") or [], [])


if __name__ == "__main__":
    unittest.main()
