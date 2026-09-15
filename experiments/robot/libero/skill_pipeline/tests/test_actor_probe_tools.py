"""Probe protocol and draft-tool regressions. No simulator, SSH or model calls."""

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import yaml

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "scripts/recovery/skill_pipeline"))
import probe_recovery as probe
import actor_patch
import check_actor_drafts as checks
import run_mining_lane as lane


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def fixture(root):
    run, baseline, pack = root / "run", root / "baseline", root / "pack"
    (pack / "skills").mkdir(parents=True)
    args = dict(repo_root=str(REPO), python_bin=sys.executable, model="model_from_lane", task_suite_name="libero_goal_swap",
                skill_pack=str(pack), skills_dir=str(pack / "skills"), capability_registry=str(pack / "capabilities.yaml"),
                baseline_run_dir=str(baseline), tasks="7", gpu="2", config_name="pi0_libero", num_trials=15,
                episode_seed_start=51, seed=51, action_chunk=5, num_steps_wait=10, max_recovery_calls=2,
                fps=10, max_recovery_steps=200, max_replans=1, generated_benchmark_dir="",
                validation_early_stop_first_n_failures=5)
    write(run / "mine/lane_command.json", {"args": args})
    write(run / "mine/mine_state.json", {"awaiting_task": 7, "awaiting_kind": "draft", "tasks": {"7": {"writes": 1}}})
    write(baseline / "summary.json", {"params": {"task_language_source": "filename", "engine_language_source": "bddl"}})
    for i in (0, 6):
        write(baseline / f"task07/ep{i:02d}/episode.json", {"task_id_1based": 7, "seed": 51+i,
              "episode_idx": i, "init_state_idx": i, "source_suite": "libero_goal_swap"})
    return run, args


class ProbePlanTest(unittest.TestCase):
    def test_probe_matches_formal_command_except_explicit_probe_overrides(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {
                "LIBERO_PYTHONPATH_ROOT": "/official/libero", "LIBERO_CONFIG_PATH": "/run/config"}):
            root = Path(tmp); run, args = fixture(root)
            got = probe.build_probe(run, 51, 10, root / "probe")
            wanted_args = argparse.Namespace(**args)
            wanted_args.num_trials = 1; wanted_args.validation_early_stop_first_n_failures = 0
            wanted = lane.eval_command(wanted_args, 7, "rollout", root / "probe", force_recovery_query=10)
            self.assertEqual(got["argv"], wanted)
            self.assertEqual(got["argv"][0], sys.executable)
            self.assertEqual(got["env"]["CUDA_VISIBLE_DEVICES"], "2")
            self.assertIn("--real_cutamp_serialize_trajectories", wanted)
            self.assertEqual(got["formal_num_trials"], 15)
            self.assertFalse(got["probe_counts_as_validation"])
            self.assertEqual(probe.read_json(run / "mine/lane_command.json")["args"]["num_trials"], 15)

    def test_nonfirst_seed_keeps_original_episode_index_and_seed_origin(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {
                "LIBERO_PYTHONPATH_ROOT": "/official/libero", "LIBERO_CONFIG_PATH": "/run/config"}):
            root = Path(tmp); run, _ = fixture(root)
            plan = probe.build_probe(run, 57, 10, root / "probe")
            argv = plan["argv"]
            self.assertEqual(argv[argv.index("--episode_index_start")+1], "6")
            self.assertEqual(argv[argv.index("--episode_seed_start")+1], "51")
            self.assertEqual(plan["init_state_idx"], 6)

    def test_missing_seed_or_wrong_suite_is_rejected_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run, args = fixture(root)
            with self.assertRaisesRegex(ValueError, "found 0"):
                probe.build_probe(run, 60, 10, root / "probe")
            path = Path(args["baseline_run_dir"]) / "task07/ep00/episode.json"
            meta = probe.read_json(path); meta["source_suite"] = "libero_goal_task"; write(path, meta)
            with self.assertRaisesRegex(ValueError, "suite differs"):
                probe.build_probe(run, 51, 10, root / "probe")

    def test_dry_run_never_starts_simulator_or_changes_mine_state(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {
                "LIBERO_PYTHONPATH_ROOT": "/official/libero", "LIBERO_CONFIG_PATH": "/run/config"}):
            run, _ = fixture(Path(tmp)); before=(run / "mine/mine_state.json").read_bytes()
            with mock.patch.object(probe.subprocess, "Popen") as popen, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.main(["--run-root", str(run), "--seed", "51", "--query", "10", "--dry-run"]), 0)
            popen.assert_not_called()
            self.assertEqual(before,(run / "mine/mine_state.json").read_bytes())
            result = probe.read_json(next((run / "mine/probes").glob("*/result.json")))
            self.assertEqual(result["status"], "planned")

    def test_preflight_uses_lane_python_even_if_tool_runs_in_other_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan={"argv":["/eval-venv/bin/python"], "repo":tmp, "env":{}}
            with mock.patch.object(probe.subprocess,"run",return_value=mock.Mock(returncode=0,
                      stdout='{"missing":[],"executable":"/eval-venv/bin/python"}',stderr="")) as proc:
                got=probe.preflight(plan,Path(tmp))
            self.assertTrue(got["ok"])
            self.assertEqual(proc.call_args.args[0][0],"/eval-venv/bin/python")


class ClassificationTest(unittest.TestCase):
    def classify(self, status, result=None, returncode=0, success=False, recovery=None, calls=1, init=0):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ep=root / "rollout/task07/ep00"
            write(ep / "episode.json", {"seed":51,"init_state_idx":init,"success":success,"recovery_calls":calls})
            write(ep / "recovery_trace.jsonl", recovery or {"kind":"plan","error":status})
            if result is not None:write(root / "rollout/cutamp_debug/test.result.json",result)
            return probe.classify(root,returncode,{"seed":51,"init_state_idx":0})

    def test_startup_failure_is_invalid_even_with_partial_recovery_records(self):
        r=self.classify("",returncode=1)
        self.assertEqual(r["status"],"infrastructure_error");self.assertFalse(r["valid_physical_observation"])

    def test_mismatched_init_is_invalid(self):
        self.assertEqual(self.classify("",init=6)["status"],"infrastructure_error")

    def test_optimizer_motion_serialization_and_execution_failures_are_distinct(self):
        self.assertEqual(self.classify("No satisfying particles",{"num_satisfying":0})["status"],"optimization_infeasible")
        self.assertEqual(self.classify("Motion planning failed for all skeletons",{"num_satisfying":5})["status"],"motion_planning_failed")
        self.assertEqual(self.classify("",{"num_satisfying":2,"executable_plan":[]})["status"],"executable_plan_missing")
        self.assertEqual(self.classify("",recovery={"kind":"trajectory","event":"execute","error":"place_hover_xy_not_aligned"})["status"],"execution_failed")

    def test_success_and_no_intervention_are_not_conflated(self):
        self.assertEqual(self.classify("",success=True)["status"],"recovery_succeeded")
        r=self.classify("",success=True,calls=0)
        self.assertEqual(r["status"],"recovery_not_entered");self.assertFalse(r["valid_physical_observation"])


DRAFT = """---
id: probe_repair
name: Probe repair
kind: repair
track: fail_only
hook: after_pi0_query
priority: 60
when_to_apply: A stalled wrong-object approach before pick.
when_not_to_apply: Already holding the target.
failure_signature: [wrong object]
recovery_point: Before another wrong-object attempt.
applies_to:
  all:
    - target_name_matches: cream_cheese
trigger:
  all:
    - holding_status_is: handempty_or_unconfirmed
    - vla_pick_target_status_is: off_target_unknown
backend: cutamp_recover
evidence:
  tasks: [sample]
  episodes: [ep00]
---
Test candidate.
"""


class DraftToolsTest(unittest.TestCase):
    def test_expanded_place_option_must_be_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pack=root / "repo/skill_packs/test_pack"
            (pack / "skills").mkdir(parents=True);(pack / "profiles").mkdir()
            (pack / "skills/_index.yaml").write_text("online: []\nfail_only: []\ncapability_registry: ../capabilities.yaml\nplace_profile_registry: ../profiles/place.yaml\n")
            caps={"schema_version":1,"name":"test_pack","mode":"strict",
                  "capabilities":{"place_profiles":["hover_v1"],"executor_options":[]}}
            (pack / "capabilities.yaml").write_text(yaml.safe_dump(caps))
            (pack / "profiles/place.yaml").write_text(yaml.safe_dump({"schema_version":1,"profiles":{
                "hover_v1":{"executor":{"place_hover_max_steps":50}}}}))
            drafts=root / "drafts";drafts.mkdir()
            data=yaml.safe_load(DRAFT.split("---")[1])
            for key in ("backend", "hook", "trigger"):
                data.pop(key)
            data.update(kind="recovery_hint",scope="place",recovery_hints={"params":{"place_profile":"hover_v1"}})
            (drafts / "draft.md").write_text("---\n"+yaml.safe_dump(data)+"---\nTest place hint.\n")
            candidate=checks.prepare_candidate(root / "repo",pack,drafts,root / "check")
            result=checks.check_candidate(REPO,candidate,drafts,root / "check",pack)
            self.assertFalse(result["ok"])
            self.assertIn("place_hover_max_steps",str(result["errors"]))
            caps["capabilities"]["executor_options"]=["place_hover_max_steps"]
            (pack / "capabilities.yaml").write_text(yaml.safe_dump(caps))
            candidate=checks.prepare_candidate(root / "repo",pack,drafts,root / "check_ok")
            result=checks.check_candidate(REPO,candidate,drafts,root / "check_ok",pack)
            self.assertTrue(result["ok"],result["errors"])

    def test_real_parser_checks_copy_and_active_pack_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pack=root / "repo/skill_packs/test_pack"
            (pack / "skills").mkdir(parents=True)
            (pack / "skills/_index.yaml").write_text("online: []\nfail_only: []\n",encoding="utf-8")
            drafts=root / "drafts";drafts.mkdir();(drafts / "draft.md").write_text(DRAFT)
            candidate=checks.prepare_candidate(root / "repo",pack,drafts,root / "check")
            result=checks.check_candidate(REPO,candidate,drafts,root / "check",pack)
            self.assertTrue(result["ok"],result["errors"])
            self.assertFalse(result["offline_scan_run"])
            self.assertEqual((pack / "skills/_index.yaml").read_text(),"online: []\nfail_only: []\n")
            (drafts / "draft.md").write_text(DRAFT.replace("holding_status_is", "invented_predicate"))
            with self.assertRaises(Exception):
                checks.prepare_candidate(root / "repo",pack,drafts,root / "check_bad")

    def test_patch_argument_preserves_chinese_newlines_and_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root / "edit.patch"
            text="*** Begin Patch\n*** Add File: drafts/test.md\n+中文 'quote' $variable\n*** End Patch\n"
            p.write_text(text,encoding="utf-8-sig")
            with mock.patch.object(actor_patch.subprocess,"run",return_value=mock.Mock(returncode=0)) as run:
                actor_patch.apply_file(p,root,"codex.exe")
            self.assertEqual(run.call_args.args[0],["codex.exe","--codex-run-as-apply-patch",text])

    def test_patch_cannot_touch_absolute_parent_or_other_drive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for target in ("../outside", "E:/outside", "/outside", "E:relative", "..\\outside"):
                with self.subTest(target=target),self.assertRaises(ValueError):
                    actor_patch.validate_paths(f"*** Add File: {target}\n",root)
            actor_patch.validate_paths("*** Add File: drafts/profile.py\n",root)


if __name__ == "__main__":
    unittest.main()
