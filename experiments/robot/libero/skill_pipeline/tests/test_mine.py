from __future__ import annotations

import json
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.mine import (
    DEFAULT_CUTAMP_RUNNER_PYTHON,
    admit_fail_only_bundle,
    admit_fail_only_draft,
    decide_task,
    ingest_mine_draft,
    load_task_episodes,
    load_mine_state,
    mining_validation_command,
    parse_task_ids,
    resolve_cutamp_runner_python,
    score_mine,
    score_validation_run,
    step_mine,
)
from experiments.robot.libero.skill_pipeline.packer import load_episode
from experiments.robot.libero.skill_pipeline.schema import spec_from_mapping
from experiments.robot.libero.skill_pipeline.trace_schema import EpisodeWriter, make_query_record


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _query(query_idx: int, ee_x: float, aperture: float = 0.04, **kwargs):
    base = {
        "task_id_1based": 1,
        "episode_idx": 0,
        "seed": 90,
        "query_idx": query_idx,
        "env_step": 10 + query_idx,
        "mode": "vla",
        "ee_xyz": [ee_x, 0.0, 0.8],
        "ee_quat": [0, 0, 0, 1],
        "gripper_qpos": [0.04, -0.04],
        "gripper_aperture": aperture,
        "gripper_cmd": -1.0,
        "target_name": "wooden_cabinet_1_cabinet_top",
        "target_xyz": [0.3, 0.0, 0.9],
        "holding_status": "handempty_or_unconfirmed",
        "holding_object": None,
        "bilateral": None,
        "object_followed": None,
        "logvar_gripper_first": None,
        "residual_score": None,
        "hook_fired": False,
        "skill_id": "",
    }
    base.update(kwargs)
    return make_query_record(base)


def _write_episode(
    path: Path,
    *,
    task_id: int,
    ep: int,
    success: bool,
    stalled: bool,
    hook_fired: bool = False,
    **meta,
) -> None:
    writer = EpisodeWriter(path)
    for idx in range(8):
        ee_x = 0.10 + (0.0002 if stalled else 0.05) * idx
        writer.append_query(
            _query(
                idx,
                ee_x,
                task_id_1based=task_id,
                episode_idx=ep,
                hook_fired=hook_fired,
                skill_id="open_hand_stall" if hook_fired else "",
            )
        )
    payload = {
        "task_id_1based": task_id,
        "episode_idx": ep,
        "seed": 90,
        "success": success,
        "task_description": "close the top drawer of the cabinet",
    }
    payload.update(meta)
    writer.write_episode_json(payload)


def _write_five(task_folder: Path, task_id: int, *, success: bool, hook_fired: bool = False) -> None:
    for ep in range(5):
        _write_episode(
            task_folder / f"ep{ep:02d}",
            task_id=task_id,
            ep=ep,
            success=success,
            stalled=not success,
            hook_fired=hook_fired,
        )


def _write_sr(task_folder: Path, task_id: int, n_success: int) -> None:
    for ep in range(5):
        ok = ep < n_success
        _write_episode(
            task_folder / f"ep{ep:02d}",
            task_id=task_id,
            ep=ep,
            success=ok,
            stalled=not ok,
            hook_fired=True,
        )


def _write_runner_failed_validation(task_folder: Path, task_id: int) -> None:
    for ep in range(5):
        ep_dir = task_folder / f"ep{ep:02d}"
        _write_episode(
            ep_dir,
            task_id=task_id,
            ep=ep,
            success=False,
            stalled=True,
            hook_fired=True,
        )
        with (ep_dir / "recovery_trace.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "kind": "plan",
                        "label": "real_cutamp_no_feasible_goal",
                        "query_idx": 5,
                        "success": False,
                        "error": "runner_failed:127: cutamp_runner_py310_overlay.sh: python: No such file or directory\n",
                        "hook_fired": True,
                        "skill_id": "open_hand_stall",
                    }
                )
                + "\n"
            )


def _stall_skill():
    return spec_from_mapping(
        {
            "id": "open_hand_stall",
            "name": "open hand stall",
            "kind": "trigger",
            "track": "fail_only",
            "hook": "after_pi0_query",
            "priority": 40,
            "backend": "cutamp_recover",
            "trigger": {"all": [{"aperture_gt": 0.03}, {"ee_stalled": {"window": 6, "max_disp_m": 0.015}}]},
            "evidence": {"tasks": [], "episodes": []},
        }
    )


def _draft_md() -> str:
    return "\n".join(
        [
            "---",
            "id: open_hand_stall",
            "name: open hand stall",
            "kind: trigger",
            "track: fail_only",
            "hook: after_pi0_query",
            "priority: 40",
            "when_to_apply: open empty hand stops near the cabinet",
            "when_not_to_apply: do not promote to online",
            "failure_signature:",
            "  - open gripper",
            "  - ee stalled",
            "recovery_point: first stall after approach",
            "trigger:",
            "  all:",
            "    - aperture_gt: 0.03",
            "    - ee_stalled:",
            "        window: 6",
            "        max_disp_m: 0.015",
            "backend: cutamp_recover",
            "evidence:",
            "  tasks: []",
            "  episodes: []",
            "---",
            "",
            "Fail-only draft for tests.",
            "",
        ]
    )


def _default_grasp_hint_md() -> str:
    return "\n".join(
        [
            "---",
            "id: grasp_default_cabinet_test",
            "name: Default cabinet test grasp",
            "kind: recovery_hint",
            "track: fail_only",
            "scope: grasp",
            "priority: 35",
            "when_to_apply: when test recovery manipulates the cabinet proxy target",
            "when_not_to_apply: outside this unit test fixture",
            "failure_signature:",
            "  - test grasp hint",
            "recovery_point: After a repair/trigger skill has already decided to call recovery.",
            "applies_to:",
            "  all:",
            "    - target_name_matches: wooden_cabinet",
            "recovery_hints:",
            "  grasp_profile: default",
            "  target: target",
            "evidence:",
            "  tasks: []",
            "  episodes: []",
            "---",
            "",
            "Default grasp hint for bundle tests.",
            "",
        ]
    )


class MineTests(unittest.TestCase):
    def test_parse_task_ids(self):
        self.assertEqual(parse_task_ids("1-3,5"), [1, 2, 3, 5])

    def test_empty_library_writes(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_episode(root / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            episode = load_episode(root / "task01" / "ep00")
            decision = decide_task(1, [episode], [])
            self.assertEqual(decision.action, "write")
            self.assertEqual(len(decision.uncovered_dirs), 1)

    def test_empty_library_skips_baseline_pass(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            skills = root / "skills"
            out = root / "mine"
            skills.mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            _write_sr(run / "task01", 1, 3)
            _write_five(run / "task02", 2, success=False)

            result = step_mine(run_dir=run, skills_root=skills, out_dir=out, task_ids=[1, 2])

            self.assertEqual(result["status"], "need_draft")
            self.assertEqual(result["awaiting_task"], 2)
            state = load_mine_state(out / "mine_state.json")
            self.assertEqual(state["tasks"]["1"]["status"], "skip_baseline_pass")
            self.assertEqual(state["completed"], [1])

    def test_covered_failures_reuse(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_episode(root / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            _write_episode(root / "task01" / "ep01", task_id=1, ep=1, success=False, stalled=True)
            episodes = [load_episode(root / "task01" / "ep00"), load_episode(root / "task01" / "ep01")]
            decision = decide_task(1, episodes, [_stall_skill()])
            self.assertEqual(decision.action, "reuse")
            self.assertEqual(decision.uncovered_dirs, [])

    def test_partial_coverage_writes_uncovered(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_episode(root / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            _write_episode(root / "task01" / "ep01", task_id=1, ep=1, success=False, stalled=False)
            episodes = [load_episode(root / "task01" / "ep00"), load_episode(root / "task01" / "ep01")]
            decision = decide_task(1, episodes, [_stall_skill()])
            self.assertEqual(decision.action, "write")
            self.assertEqual(len(decision.uncovered_dirs), 1)
            self.assertIn("ep01", decision.uncovered_dirs[0])

    def test_success_false_fire_requests_refine(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_episode(root / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            _write_episode(root / "task01" / "ep01", task_id=1, ep=1, success=True, stalled=True)
            episodes = [load_episode(root / "task01" / "ep00"), load_episode(root / "task01" / "ep01")]
            decision = decide_task(1, episodes, [_stall_skill()])
            self.assertEqual(decision.action, "refine")

    def test_score_requires_three_of_five_and_hits(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_five(root / "off" / "task01", 1, success=False)
            _write_sr(root / "on" / "task01", 1, 3)
            off = [load_episode(root / "off" / "task01" / f"ep{ep:02d}") for ep in range(5)]
            on = [load_episode(root / "on" / "task01" / f"ep{ep:02d}") for ep in range(5)]
            scored = score_validation_run(off, on)
            self.assertTrue(scored["passed"])
            self.assertEqual(scored["on_success"], 3)

    def test_score_rejects_regression_even_at_sixty(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_sr(root / "off" / "task01", 1, 4)
            _write_sr(root / "on" / "task01", 1, 3)
            off = [load_episode(root / "off" / "task01" / f"ep{ep:02d}") for ep in range(5)]
            on = [load_episode(root / "on" / "task01" / f"ep{ep:02d}") for ep in range(5)]
            scored = score_validation_run(off, on)
            self.assertFalse(scored["passed"])
            self.assertTrue(scored["regressed"])

    def test_step_ingest_then_score_pass(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            skills = root / "skills"
            out = root / "mine"
            (skills / "fail_only" / "trigger").mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            _write_five(run / "task01", 1, success=False)
            _write_five(run / "task02", 2, success=False)
            first = step_mine(run_dir=run, skills_root=skills, out_dir=out, task_ids=[1, 2])
            self.assertEqual(first["status"], "need_draft")
            draft = root / "draft.md"
            draft.write_text(_draft_md(), encoding="utf-8")
            ingested = ingest_mine_draft(
                draft_md=draft,
                run_dir=run,
                skills_root=skills,
                out_dir=out,
                task_id=1,
            )
            self.assertTrue(ingested["ok"])
            self.assertEqual(ingested["status"], "need_validation")
            self.assertEqual(ingested["writes_used"], 1)
            self.assertIn("--use_real_cutamp_backend", ingested["validation"]["argv"])
            self.assertIn("--real_cutamp_curobo_plan", ingested["validation"]["argv"])
            self.assertIn("--prefer_real_cutamp_executable_plan", ingested["validation"]["argv"])
            self.assertIn("--require_real_cutamp_executable_plan", ingested["validation"]["argv"])
            blocked = step_mine(run_dir=run, skills_root=skills, out_dir=out, task_ids=[1, 2])
            self.assertEqual(blocked["status"], "awaiting_validation")
            on = out / "on1"
            _write_sr(on / "task01", 1, 3)
            scored = score_mine(run_dir=run, skills_root=skills, out_dir=out, on_dir=on, task_id=1)
            self.assertEqual(scored["status"], "passed")
            nxt = step_mine(run_dir=run, skills_root=skills, out_dir=out, task_ids=[1, 2])
            self.assertEqual(nxt["status"], "need_validation")
            self.assertEqual(nxt["awaiting_task"], 2)

    def test_five_failed_scores_write_budget_exhausted(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            skills = root / "skills"
            out = root / "mine"
            (skills / "fail_only" / "trigger").mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            _write_five(run / "task01", 1, success=False)
            step_mine(run_dir=run, skills_root=skills, out_dir=out, task_ids=[1])
            draft = root / "draft.md"
            draft.write_text(_draft_md(), encoding="utf-8")
            last = None
            for idx in range(5):
                ingest_mine_draft(draft_md=draft, run_dir=run, skills_root=skills, out_dir=out, task_id=1)
                on = out / f"on{idx}"
                _write_sr(on / "task01", 1, 1)
                last = score_mine(run_dir=run, skills_root=skills, out_dir=out, on_dir=on, task_id=1)
            self.assertEqual(last["status"], "write_budget_exhausted")
            self.assertFalse(last["sr_passed"])
            self.assertEqual(last["writes_used"], 5)

    def test_runner_failed_validation_is_invalid_and_does_not_consume_attempt(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            skills = root / "skills"
            out = root / "mine"
            (skills / "fail_only" / "trigger").mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            _write_five(run / "task01", 1, success=False)
            step_mine(run_dir=run, skills_root=skills, out_dir=out, task_ids=[1])
            draft = root / "draft.md"
            draft.write_text(_draft_md(), encoding="utf-8")
            ingest_mine_draft(draft_md=draft, run_dir=run, skills_root=skills, out_dir=out, task_id=1)

            on = out / "validation" / "mine_val_task01_w1"
            _write_runner_failed_validation(on / "task01", 1)
            result = score_mine(run_dir=run, skills_root=skills, out_dir=out, on_dir=on, task_id=1)

            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "invalid_validation")
            self.assertEqual(result["runner_failure_count"], 5)
            state = load_mine_state(out / "mine_state.json")
            entry = state["tasks"]["1"]
            self.assertEqual(state["awaiting_task"], 1)
            self.assertEqual(state["awaiting_kind"], "validation")
            self.assertEqual(entry["writes"], 1)
            self.assertEqual(entry.get("attempts"), [])
            self.assertEqual(len(entry.get("invalid_validations") or []), 1)
            self.assertTrue((out / "validation" / "mine_val_task01_w1.canonical.json").exists())

    def test_score_writes_canonical_record_for_manual_validation_dir(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            skills = root / "skills"
            out = root / "mine"
            (skills / "fail_only" / "trigger").mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            _write_five(run / "task01", 1, success=False)
            step_mine(run_dir=run, skills_root=skills, out_dir=out, task_ids=[1])
            draft = root / "draft.md"
            draft.write_text(_draft_md(), encoding="utf-8")
            ingest_mine_draft(draft_md=draft, run_dir=run, skills_root=skills, out_dir=out, task_id=1)

            on = out / "validation" / "mine_val_task01_w1_pathfix_gpu3"
            _write_sr(on / "task01", 1, 3)
            result = score_mine(run_dir=run, skills_root=skills, out_dir=out, on_dir=on, task_id=1)

            self.assertEqual(result["status"], "passed")
            record_path = out / "validation" / "mine_val_task01_w1.canonical.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertTrue(record["valid"])
            self.assertEqual(record["canonical_exp_name"], "mine_val_task01_w1")
            self.assertEqual(record["selected_on_dir"], str(on))

    def test_validation_command_includes_real_cutamp(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = mining_validation_command(
                baseline_run_dir=root / "run",
                skills_root=root / "skills",
                val_log_dir=root / "mine" / "validation",
                task_id=1,
                writes=2,
                cutamp_runner_python="/opt/cutamp/bin/python",
            )
            argv = spec["argv"]
            self.assertIn("--enable_mining_skills", argv)
            self.assertEqual(argv[argv.index("--early_stop_first_n_failures") + 1], "5")
            self.assertIn("--use_real_cutamp_backend", argv)
            self.assertIn("--real_cutamp_require_feasible", argv)
            self.assertIn("--real_cutamp_curobo_plan", argv)
            self.assertIn("--real_cutamp_serialize_trajectories", argv)
            self.assertIn("--prefer_real_cutamp_executable_plan", argv)
            self.assertIn("--require_real_cutamp_executable_plan", argv)
            self.assertEqual(argv[argv.index("--max_recovery_calls") + 1], "2")
            self.assertEqual(argv[argv.index("--real_cutamp_grasp_dof") + 1], "6")
            self.assertEqual(argv[argv.index("--real_cutamp_runner_python") + 1], "/opt/cutamp/bin/python")
            self.assertEqual(argv[argv.index("--real_cutamp_runner_timeout_sec") + 1], "360")
            self.assertEqual(argv[argv.index("--max_recovery_steps") + 1], "200")
            self.assertEqual(
                argv[argv.index("--real_cutamp_debug_dir") + 1],
                str(root / "mine" / "validation" / "mine_val_task01_w2" / "cutamp_debug"),
            )
            self.assertNotIn("--enable_residual_trigger", argv)
            self.assertNotIn("--enable_skills", argv)

            previous = os.environ.pop("CUTAMP_RUNNER_PYTHON", None)
            try:
                defaulted = mining_validation_command(
                    baseline_run_dir=root / "run",
                    skills_root=root / "skills",
                    val_log_dir=root / "mine" / "validation",
                    task_id=1,
                    writes=1,
                )
            finally:
                if previous is not None:
                    os.environ["CUTAMP_RUNNER_PYTHON"] = previous
            default_argv = defaulted["argv"]
            self.assertEqual(
                default_argv[default_argv.index("--real_cutamp_runner_python") + 1],
                resolve_cutamp_runner_python(),
            )

            repo_runner = root / "repo" / "scripts" / "recovery" / "skill_pipeline"
            repo_runner.mkdir(parents=True)
            overlay = repo_runner / "cutamp_runner_py310_overlay.sh"
            overlay.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            self.assertEqual(resolve_cutamp_runner_python(repo_root=root / "repo"), str(overlay))

    def test_generated_selector_maps_to_task_directory(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark = root / "generated"
            manifest = benchmark / "manifests"
            manifest.mkdir(parents=True)
            rows = [
                {"task_id": "gen_alpha", "source_task_id_1based": 1, "language": "alpha"},
                {"task_id": "gen_beta", "source_task_id_1based": 2, "language": "beta"},
            ]
            (manifest / "all_tasks.jsonl").write_text(
                "\n".join(json.dumps(row) for row in rows) + "\n",
                encoding="utf-8",
            )
            _write_episode(
                root / "run" / "gen_beta" / "ep00",
                task_id=1,
                ep=0,
                success=False,
                stalled=True,
                generated_task_id="gen_beta",
            )

            episodes = load_task_episodes(
                root / "run",
                2,
                generated_benchmark_dir=benchmark,
                generated_split="all",
            )
            self.assertEqual(len(episodes), 1)
            self.assertIn("gen_beta", str(episodes[0]["dir"]))

            spec = mining_validation_command(
                baseline_run_dir=root / "run",
                skills_root=root / "skills",
                val_log_dir=root / "mine" / "validation",
                task_id=2,
                writes=0,
                generated_benchmark_dir=benchmark,
                generated_split="all",
            )
            argv = spec["argv"]
            self.assertEqual(argv[argv.index("--generated_task_ids") + 1], "2")
            self.assertEqual(argv[argv.index("--generated_split") + 1], "all")
            self.assertEqual(argv[argv.index("--generated_benchmark_dir") + 1], str(benchmark))

    def test_ingest_rejects_non_firing_draft(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            skills = root / "skills"
            skills.mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            _write_episode(run / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            draft = root / "draft.md"
            draft.write_text(
                _draft_md().replace("aperture_gt: 0.03", "aperture_gt: 0.9"),
                encoding="utf-8",
            )
            result = admit_fail_only_draft(
                draft,
                skills_root=skills,
                episodes=[load_episode(run / "task01" / "ep00")],
            )
            self.assertFalse(result["ok"])
            # 2026-09-16: the "recall below 0.60" ratio gate was removed by owner decision; a draft
            # that never fires at all is still rejected, now by the non-vacuity floor.
            self.assertTrue(
                any("does not fire on any current-task failed episode" in item for item in result["errors"])
            )

    def test_ingest_bundle_writes_repair_and_grasp_hint(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            skills = root / "skills"
            out = root / "mine"
            bundle_root = root / "bundle"
            (bundle_root / "drafts" / "repair").mkdir(parents=True)
            (bundle_root / "drafts" / "grasp").mkdir(parents=True)
            skills.mkdir(parents=True)
            (skills / "_index.yaml").write_text(
                "capability_registry: ../capabilities.yaml\nonline: []\nfail_only: []\n",
                encoding="utf-8",
            )
            (root / "capabilities.yaml").write_text(
                "schema_version: 1\nname: test_caps\nmode: strict\ncapabilities:\n"
                "  grasp_profiles: []\n"
                "  place_profiles: []\n"
                "  geometry_hint_keys: []\n"
                "  geometry_hint_intents: []\n"
                "  grounding_hint_keys: []\n"
                "  grounding_hint_intents: []\n"
                "  executor_options: []\n"
                "  place_candidate_policies: []\n"
                "  place_yaw_policies: []\n"
                "  release_modes: []\n",
                encoding="utf-8",
            )
            _write_episode(run / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            step_mine(run_dir=run, skills_root=skills, out_dir=out, task_ids=[1])
            (bundle_root / "drafts" / "repair" / "open_hand_stall.md").write_text(_draft_md(), encoding="utf-8")
            (bundle_root / "drafts" / "grasp" / "grasp_default_cabinet_test.md").write_text(
                _default_grasp_hint_md(),
                encoding="utf-8",
            )
            (bundle_root / "bundle.yaml").write_text(
                "\n".join(
                    [
                        "bundle_id: cabinet_bundle_test",
                        "diagnosis:",
                        "  primary_failure_layer: grasp",
                        "drafts:",
                        "  - file: drafts/repair/open_hand_stall.md",
                        "    role: entrypoint",
                        "    category: repair",
                        "  - file: drafts/grasp/grasp_default_cabinet_test.md",
                        "    role: grasp_hint",
                        "    category: grasp",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = ingest_mine_draft(
                bundle_yaml=bundle_root / "bundle.yaml",
                run_dir=run,
                skills_root=skills,
                out_dir=out,
                task_id=1,
            )

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["status"], "need_validation")
            self.assertEqual(result["bundle_id"], "cabinet_bundle_test")
            self.assertEqual(
                result["skill_ids"],
                ["open_hand_stall", "grasp_default_cabinet_test"],
            )
            self.assertTrue((skills / "fail_only" / "trigger" / "open_hand_stall.md").exists())
            self.assertTrue(
                (skills / "fail_only" / "recovery_hint" / "grasp" / "grasp_default_cabinet_test.md").exists()
            )
            index_text = (skills / "_index.yaml").read_text(encoding="utf-8")
            self.assertIn("capability_registry: ../capabilities.yaml", index_text)
            self.assertIn("fail_only/trigger/open_hand_stall.md", index_text)
            self.assertIn("fail_only/recovery_hint/grasp/grasp_default_cabinet_test.md", index_text)
            state = load_mine_state(out / "mine_state.json")
            self.assertEqual(state["tasks"]["1"]["candidate_bundle_id"], "cabinet_bundle_test")
            self.assertEqual(
                state["tasks"]["1"]["candidate_skill_ids"],
                ["open_hand_stall", "grasp_default_cabinet_test"],
            )

    def test_bundle_rejects_orphan_hint_without_entrypoint(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            skills = root / "skills"
            bundle_root = root / "bundle"
            (bundle_root / "drafts" / "grasp").mkdir(parents=True)
            skills.mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            _write_episode(run / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            (bundle_root / "drafts" / "grasp" / "grasp_default_cabinet_test.md").write_text(
                _default_grasp_hint_md(),
                encoding="utf-8",
            )
            (bundle_root / "bundle.yaml").write_text(
                "bundle_id: orphan_hint_test\n"
                "drafts:\n"
                "  - file: drafts/grasp/grasp_default_cabinet_test.md\n"
                "    role: grasp_hint\n"
                "    category: grasp\n",
                encoding="utf-8",
            )

            result = admit_fail_only_bundle(
                bundle_yaml=bundle_root / "bundle.yaml",
                skills_root=skills,
                episodes=[load_episode(run / "task01" / "ep00")],
            )

            self.assertFalse(result["ok"])
            self.assertTrue(any("entrypoint" in item for item in result["errors"]))

    def test_bundle_rejects_diagnostics_only_candidate(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            skills = root / "skills"
            bundle_root = root / "bundle"
            (bundle_root / "drafts" / "diagnostics").mkdir(parents=True)
            skills.mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            _write_episode(run / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            (bundle_root / "drafts" / "diagnostics" / "planner_blocked.md").write_text(
                "---\n"
                "id: planner_blocked_note\n"
                "kind: diagnostics\n"
                "name: Planner blocked note\n"
                "track: fail_only\n"
                "---\n"
                "这只是诊断说明，不是可执行 skill。\n",
                encoding="utf-8",
            )
            (bundle_root / "bundle.yaml").write_text(
                "bundle_id: diagnostics_only_test\n"
                "uses_existing_entrypoint: true\n"
                "drafts:\n"
                "  - file: drafts/diagnostics/planner_blocked.md\n"
                "    role: blocker_note\n"
                "    category: diagnostics\n",
                encoding="utf-8",
            )

            result = admit_fail_only_bundle(
                bundle_yaml=bundle_root / "bundle.yaml",
                skills_root=skills,
                episodes=[load_episode(run / "task01" / "ep00")],
            )

            self.assertFalse(result["ok"])
            self.assertTrue(any("diagnostics-only" in item for item in result["errors"]))

    def test_ingest_admission_failure_holds_candidate_out_of_index(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            scan = root / "scan"
            skills = root / "skills"
            out = root / "mine"
            (skills / "fail_only" / "trigger").mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            _write_episode(run / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            _write_episode(scan / "task01" / "ep00", task_id=1, ep=0, success=True, stalled=True)
            draft = root / "draft.md"
            draft.write_text(_draft_md(), encoding="utf-8")

            result = ingest_mine_draft(
                draft_md=draft,
                run_dir=run,
                skills_root=skills,
                out_dir=out,
                task_id=1,
                admission_gate=True,
                admission_scan_roots=[scan],
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "admission_failed")
            self.assertFalse((skills / "fail_only" / "trigger" / "open_hand_stall.md").exists())
            self.assertEqual((skills / "_index.yaml").read_text(encoding="utf-8"), "online: []\nfail_only: []\n")
            state = load_mine_state(out / "mine_state.json")
            self.assertEqual(state["awaiting_kind"], "draft")

    def test_ingest_admission_success_keeps_existing_flow(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            corpus = root / "analysis_outputs" / "offline_trigger_corpus" / "corpus1"
            skills = root / "skills"
            out = root / "mine"
            (skills / "fail_only" / "trigger").mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            _write_episode(run / "task01" / "ep00", task_id=1, ep=0, success=False, stalled=True)
            _write_json(corpus / "manifest.json", {"schema_version": 1})
            _write_episode(corpus / "task02" / "ep00", task_id=2, ep=0, success=True, stalled=False)
            draft = root / "draft.md"
            draft.write_text(_draft_md(), encoding="utf-8")

            result = ingest_mine_draft(
                draft_md=draft,
                run_dir=run,
                skills_root=skills,
                out_dir=out,
                task_id=1,
                admission_gate=True,
            )

            self.assertTrue(result["ok"], result)
            self.assertEqual(result["status"], "need_validation")
            self.assertTrue((skills / "fail_only" / "trigger" / "open_hand_stall.md").exists())
            self.assertIn("fail_only/trigger/open_hand_stall.md", (skills / "_index.yaml").read_text(encoding="utf-8"))
            self.assertEqual(result["admission"]["ok"], True)

    def test_step_ingest_admission_then_score_dry_run(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            corpus = root / "analysis_outputs" / "offline_trigger_corpus" / "corpus1"
            skills = root / "skills"
            out = root / "mine"
            (skills / "fail_only" / "trigger").mkdir(parents=True)
            (skills / "_index.yaml").write_text("online: []\nfail_only: []\n", encoding="utf-8")
            _write_five(run / "task01", 1, success=False)
            _write_json(corpus / "manifest.json", {"schema_version": 1})
            _write_episode(corpus / "task02" / "ep00", task_id=2, ep=0, success=True, stalled=False)

            first = step_mine(run_dir=run, skills_root=skills, out_dir=out, task_ids=[1])
            self.assertEqual(first["status"], "need_draft")

            draft = root / "draft.md"
            draft.write_text(_draft_md(), encoding="utf-8")
            ingested = ingest_mine_draft(
                draft_md=draft,
                run_dir=run,
                skills_root=skills,
                out_dir=out,
                task_id=1,
                admission_gate=True,
            )
            self.assertTrue(ingested["ok"], ingested)
            self.assertEqual(ingested["status"], "need_validation")
            self.assertTrue((out / "task01" / "admission_w1" / "skill_admission_result.json").exists())

            on = out / "on1"
            _write_sr(on / "task01", 1, 3)
            scored = score_mine(run_dir=run, skills_root=skills, out_dir=out, on_dir=on, task_id=1)
            self.assertEqual(scored["status"], "passed")
            self.assertEqual(scored["on_success"], 3)
            state = load_mine_state(out / "mine_state.json")
            self.assertEqual(state["completed"], [1])


if __name__ == "__main__":
    unittest.main()
