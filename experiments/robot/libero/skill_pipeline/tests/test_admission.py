from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.admission import (
    SkillAdmissionConfig,
    resolve_admission_scan_roots,
    run_skill_admission,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _write_episode(
    run: Path,
    ep: str,
    *,
    success: bool,
    matching: bool,
    first_match_q: int = 5,
    task: str = "task01",
    task_id: int = 1,
    task_description: str = "put the black bowl on the plate",
) -> None:
    ep_dir = run / task / ep
    _write_json(
        ep_dir / "episode.json",
        {
            "success": success,
            "task_id_1based": task_id,
            "episode_idx": int(ep.replace("ep", "")),
            "seed": 90,
            "task_description": task_description,
        },
    )
    rows = []
    for qidx in range(max(1, first_match_q + 1)):
        active = matching and qidx >= first_match_q
        rows.append(
            {
                "query_idx": qidx,
                "target_name": "akita_black_bowl_1_main",
                "gripper_aperture": 0.04,
                "holding_status": "handempty_or_unconfirmed" if active else "confirmed_holding",
                "target_ee_distance_m": 0.08,
                "vla_pick_target_status": "close_attempt_no_hold" if active else "normal",
            }
        )
    _write_jsonl(ep_dir / "query_trace.jsonl", rows)


def _candidate(
    path: Path,
    *,
    skill_id: str = "test_bowl_preclose",
    priority: int = 50,
    applies_to_task_language: str = "",
) -> None:
    applies_to = []
    if applies_to_task_language:
        applies_to = [
            "applies_to:",
            "  all:",
            f"    - task_language_matches: {applies_to_task_language}",
        ]
    path.write_text(
        "\n".join(
            [
                "---",
                f"id: {skill_id}",
                "name: Test bowl preclose",
                "kind: repair",
                "track: fail_only",
                "hook: after_pi0_query",
                f"priority: {priority}",
                "backend: cutamp_recover",
                *applies_to,
                "when_to_apply: open gripper approaches the target bowl without confirmed holding",
                "when_not_to_apply: after the target is already held",
                "failure_signature:",
                "  - open gripper near target",
                "recovery_point: before the failed close",
                "trigger:",
                "  all:",
                "    - aperture_gt: 0.03",
                "    - holding_status_is: handempty_or_unconfirmed",
                "    - target_ee_distance_lt: 0.11",
                "    - vla_pick_target_status_is: close_attempt_no_hold",
                "evidence:",
                "  tasks:",
                "    - test",
                "  episodes:",
                "    - task1_ep0_seed90",
                "---",
                "",
                "Test repair skill.",
            ]
        ),
        encoding="utf-8",
    )


class SkillAdmissionTests(unittest.TestCase):
    def test_resolve_scan_roots_prefers_explicit_then_recent_corpus_then_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            explicit = root / "explicit"
            fallback = root / "fallback"
            explicit.mkdir()
            fallback.mkdir()
            corpus = root / "analysis_outputs" / "offline_trigger_corpus"
            old = corpus / "old"
            new = corpus / "new"
            old.mkdir(parents=True)
            new.mkdir()
            _write_json(old / "manifest.json", {"schema_version": 1})
            _write_json(new / "manifest.json", {"schema_version": 1})

            with_explicit = resolve_admission_scan_roots([explicit], repo_root=root, fallback_scan_root=fallback)
            self.assertEqual(with_explicit[:2], [fallback, explicit])
            self.assertEqual(set(with_explicit[2:]), {old, new})
            resolved = resolve_admission_scan_roots(
                [],
                repo_root=root,
                corpus_root="analysis_outputs/offline_trigger_corpus",
                max_corpus_runs=2,
                fallback_scan_root=fallback,
            )
            self.assertEqual(set(resolved), {fallback, old, new})

            self.assertEqual(
                resolve_admission_scan_roots(
                    [],
                    repo_root=root,
                    corpus_root="missing",
                    fallback_scan_root=fallback,
                ),
                [fallback],
            )

    def test_admission_passes_when_candidate_only_hits_failures(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / "skills"
            skills.mkdir()
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            run = root / "run"
            corpus = root / "analysis_outputs" / "offline_trigger_corpus" / "corpus1"
            _write_json(corpus / "manifest.json", {"schema_version": 1})
            _write_episode(run, "ep00", success=False, matching=True)
            _write_episode(run, "ep01", success=True, matching=False)
            _write_episode(corpus, "ep00", success=True, matching=False)
            draft = root / "draft.md"
            _candidate(draft)

            report = run_skill_admission(
                draft,
                config=SkillAdmissionConfig(
                    index_path=skills / "_index.yaml",
                    out_dir=root / "admission",
                    scan_roots=[run, corpus],
                    current_scan_roots=[run],
                    mining=True,
                ),
            )

            self.assertTrue(report["ok"], report)
            self.assertEqual(report["candidate_offline_scan"]["failed_episode_matches"], 1)
            self.assertEqual(report["candidate_offline_scan"]["success_episode_matches"], 0)
            self.assertEqual(
                report["candidate_offline_scan"]["current_task_effectiveness"]["failed_episode_recall"],
                1.0,
            )
            self.assertEqual(report["candidate_offline_scan"]["global_safety"]["non_current_episodes"], 1)
            self.assertEqual(report["candidate_offline_scan"]["early_fire_episode_count"], 0)
            self.assertTrue(Path(report["result_json"]).exists())
            self.assertTrue(Path(report["result_markdown"]).exists())

    def test_admission_rejects_current_only_global_scan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / "skills"
            skills.mkdir()
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            run = root / "run"
            _write_episode(run, "ep00", success=False, matching=True)
            draft = root / "draft.md"
            _candidate(draft)

            report = run_skill_admission(
                draft,
                config=SkillAdmissionConfig(
                    index_path=skills / "_index.yaml",
                    out_dir=root / "admission",
                    scan_roots=[run],
                    current_scan_roots=[run],
                    mining=True,
                ),
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(any("non-current episodes" in item for item in report["errors"]))

    def test_admission_allows_current_success_matches_when_validation_will_decide(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / "skills"
            skills.mkdir()
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            run = root / "run"
            corpus = root / "analysis_outputs" / "offline_trigger_corpus" / "corpus1"
            _write_json(corpus / "manifest.json", {"schema_version": 1})
            _write_episode(run, "ep00", success=False, matching=True)
            _write_episode(run, "ep01", success=True, matching=True)
            _write_episode(corpus, "ep00", success=True, matching=False)
            draft = root / "draft.md"
            _candidate(draft)

            report = run_skill_admission(
                draft,
                config=SkillAdmissionConfig(
                    index_path=skills / "_index.yaml",
                    out_dir=root / "admission",
                    scan_roots=[run, corpus],
                    current_scan_roots=[run],
                    mining=True,
                ),
            )

            self.assertTrue(report["ok"], report)
            self.assertEqual(report["candidate_offline_scan"]["success_episode_matches"], 1)
            self.assertEqual(
                report["candidate_offline_scan"]["global_safety"]["non_current_success_winner_episode_matches"],
                0,
            )

    def test_admission_rejects_candidate_that_wins_on_non_current_success(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / "skills"
            skills.mkdir()
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            run = root / "run"
            corpus = root / "analysis_outputs" / "offline_trigger_corpus" / "corpus1"
            _write_json(corpus / "manifest.json", {"schema_version": 1})
            _write_episode(run, "ep00", success=False, matching=True)
            _write_episode(corpus, "ep00", success=True, matching=True)
            draft = root / "draft.md"
            _candidate(draft)

            report = run_skill_admission(
                draft,
                config=SkillAdmissionConfig(
                    index_path=skills / "_index.yaml",
                    out_dir=root / "admission",
                    scan_roots=[run, corpus],
                    current_scan_roots=[run],
                    mining=True,
                ),
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(any("non-current success episodes" in item for item in report["errors"]))
            self.assertEqual(
                report["candidate_offline_scan"]["global_safety"]["non_current_success_winner_episode_matches"],
                1,
            )

    def test_same_run_other_task_is_non_current_when_task_id_is_set(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / "skills"
            skills.mkdir()
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            run = root / "run"
            _write_episode(run, "ep00", success=False, matching=True, task="task01", task_id=1)
            _write_episode(
                run,
                "ep00",
                success=True,
                matching=True,
                task="task02",
                task_id=2,
                task_description="task two distractor success",
            )
            draft = root / "draft.md"
            _candidate(draft)

            report = run_skill_admission(
                draft,
                config=SkillAdmissionConfig(
                    index_path=skills / "_index.yaml",
                    out_dir=root / "admission",
                    scan_roots=[run],
                    current_scan_roots=[run],
                    current_task_ids=(1,),
                    current_task_names=("task01",),
                    mining=True,
                ),
            )

            self.assertFalse(report["ok"], report)
            self.assertEqual(report["candidate_offline_scan"]["current_task_effectiveness"]["episodes"], 1)
            self.assertEqual(report["candidate_offline_scan"]["global_safety"]["non_current_episodes"], 1)
            self.assertEqual(
                report["candidate_offline_scan"]["global_safety"]["non_current_success_winner_episode_matches"],
                1,
            )

    def test_shadowed_non_current_success_match_is_warning_not_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / "skills"
            high = skills / "fail_only" / "trigger" / "higher_priority_existing.md"
            high.parent.mkdir(parents=True)
            _candidate(
                high,
                skill_id="higher_priority_existing",
                priority=100,
                applies_to_task_language="task two",
            )
            (skills / "_index.yaml").write_text(
                "online: []\nfail_only:\n  - fail_only/trigger/higher_priority_existing.md\n",
                encoding="utf-8",
            )
            run = root / "run"
            _write_episode(run, "ep00", success=False, matching=True, task="task01", task_id=1)
            _write_episode(
                run,
                "ep00",
                success=True,
                matching=True,
                task="task02",
                task_id=2,
                task_description="task two distractor success",
            )
            draft = root / "draft.md"
            _candidate(draft)

            report = run_skill_admission(
                draft,
                config=SkillAdmissionConfig(
                    index_path=skills / "_index.yaml",
                    out_dir=root / "admission",
                    scan_roots=[run],
                    current_scan_roots=[run],
                    current_task_ids=(1,),
                    current_task_names=("task01",),
                    mining=True,
                ),
            )

            self.assertTrue(report["ok"], report)
            self.assertEqual(
                report["candidate_offline_scan"]["global_safety"]["non_current_success_winner_episode_matches"],
                0,
            )
            self.assertEqual(
                report["candidate_offline_scan"]["global_safety"]["non_current_shadowed_success_matches"],
                ["task02/ep00"],
            )
            self.assertTrue(any("shadowed" in item for item in report["warnings"]))

    def test_admission_rejects_candidate_that_first_fires_before_query_five(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / "skills"
            skills.mkdir()
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            run = root / "run"
            corpus = root / "analysis_outputs" / "offline_trigger_corpus" / "corpus1"
            _write_json(corpus / "manifest.json", {"schema_version": 1})
            _write_episode(run, "ep00", success=False, matching=True, first_match_q=4)
            _write_episode(corpus, "ep00", success=True, matching=False)
            draft = root / "draft.md"
            _candidate(draft)

            report = run_skill_admission(
                draft,
                config=SkillAdmissionConfig(
                    index_path=skills / "_index.yaml",
                    out_dir=root / "admission",
                    scan_roots=[run, corpus],
                    current_scan_roots=[run],
                    mining=True,
                ),
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(any("before query 5" in item for item in report["errors"]))
            self.assertEqual(report["candidate_offline_scan"]["early_fire_episode_count"], 1)

    def test_admission_rejects_target_approach_only_repair(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / "skills"
            skills.mkdir()
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            run = root / "run"
            corpus = root / "analysis_outputs" / "offline_trigger_corpus" / "corpus1"
            _write_json(corpus / "manifest.json", {"schema_version": 1})
            _write_episode(run, "ep00", success=False, matching=True)
            _write_episode(corpus, "ep00", success=True, matching=False)
            draft = root / "draft.md"
            _candidate(draft)
            text = draft.read_text(encoding="utf-8")
            text = text.replace("    - vla_pick_target_status_is: close_attempt_no_hold\n", "")
            draft.write_text(text, encoding="utf-8")

            report = run_skill_admission(
                draft,
                config=SkillAdmissionConfig(
                    index_path=skills / "_index.yaml",
                    out_dir=root / "admission",
                    scan_roots=[run, corpus],
                    current_scan_roots=[run],
                    mining=True,
                ),
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(
                any("negative failure-evidence predicate" in item for item in report["errors"]),
                report,
            )

    def test_admission_rejects_inline_executor_on_repair(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / "skills"
            skills.mkdir()
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            run = root / "run"
            corpus = root / "analysis_outputs" / "offline_trigger_corpus" / "corpus1"
            _write_json(corpus / "manifest.json", {"schema_version": 1})
            _write_episode(run, "ep00", success=False, matching=True)
            _write_episode(corpus, "ep00", success=True, matching=False)
            draft = root / "draft.md"
            _candidate(draft)
            text = draft.read_text(encoding="utf-8")
            text = text.replace(
                "evidence:\n",
                "recovery_hints:\n"
                "  params:\n"
                "    executor:\n"
                "      recovery_entry_lift_m: 0.05\n"
                "evidence:\n",
            )
            draft.write_text(text, encoding="utf-8")

            report = run_skill_admission(
                draft,
                config=SkillAdmissionConfig(
                    index_path=skills / "_index.yaml",
                    out_dir=root / "admission",
                    scan_roots=[run, corpus],
                    current_scan_roots=[run],
                    mining=True,
                ),
            )

            self.assertFalse(report["ok"], report)
            self.assertTrue(any("params.repair_profile" in item for item in report["errors"]))

    def test_admission_accepts_repair_profile_on_repair(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills = root / "skills"
            skills.mkdir()
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            run = root / "run"
            corpus = root / "analysis_outputs" / "offline_trigger_corpus" / "corpus1"
            _write_json(corpus / "manifest.json", {"schema_version": 1})
            _write_episode(run, "ep00", success=False, matching=True)
            _write_episode(corpus, "ep00", success=True, matching=False)
            draft = root / "draft.md"
            _candidate(draft)
            text = draft.read_text(encoding="utf-8")
            text = text.replace(
                "evidence:\n",
                "recovery_hints:\n"
                "  params:\n"
                "    repair_profile: entry_lift_open_hand_small_v1\n"
                "evidence:\n",
            )
            draft.write_text(text, encoding="utf-8")

            report = run_skill_admission(
                draft,
                config=SkillAdmissionConfig(
                    index_path=skills / "_index.yaml",
                    out_dir=root / "admission",
                    scan_roots=[run, corpus],
                    current_scan_roots=[run],
                    mining=True,
                ),
            )

            self.assertTrue(report["ok"], report)
            self.assertEqual(report["static"]["repair_profile"], "entry_lift_open_hand_small_v1")


if __name__ == "__main__":
    unittest.main()
