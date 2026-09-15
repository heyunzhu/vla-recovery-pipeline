from __future__ import annotations

import argparse
import importlib.util
import json
import unittest
from pathlib import Path


def _load_run_mining_lane():
    repo = Path(__file__).resolve().parents[5]
    path = repo / "scripts" / "recovery" / "skill_pipeline" / "run_mining_lane.py"
    spec = importlib.util.spec_from_file_location("run_mining_lane", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_run_codex_actor():
    repo = Path(__file__).resolve().parents[5]
    path = repo / "scripts" / "recovery" / "skill_pipeline" / "run_codex_actor.py"
    spec = importlib.util.spec_from_file_location("run_codex_actor", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MiningLaneScriptTests(unittest.TestCase):
    def test_actor_prompt_labels_rollout_evidence_not_pack_json(self):
        module = _load_run_codex_actor()
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td)
            (skills_dir / "_index.yaml").write_text("online: []\n", encoding="utf-8")

            prompt = module.render_actor_prompt('{"pack_kind": "fail_set"}', skills_dir)

        self.assertIn("## Rollout evidence JSON", prompt)
        self.assertIn('"pack_kind": "fail_set"', prompt)
        self.assertNotIn("## pack.json", prompt)

    def test_archive_command_resolves_corpus_root_under_repo(self):
        module = _load_run_mining_lane()
        root = Path("C:/tmp/workspace/openvla-oft")
        args = argparse.Namespace(
            python_bin="python",
            repo_root=str(root),
            offline_scan_corpus_root="analysis_outputs/offline_trigger_corpus",
        )

        cmd = module.archive_command(args, root / "logs" / "val", "sample")

        self.assertIn(str(root / "scripts/recovery/skill_pipeline/archive_offline_scan_corpus.py"), cmd)
        self.assertIn(str(root / "analysis_outputs/offline_trigger_corpus"), cmd)
        self.assertEqual(cmd[-2:], ["--name", "sample"])

    def test_lane_command_payload_records_resume_command(self):
        module = _load_run_mining_lane()
        root = Path("C:/tmp/workspace/openvla-oft")
        mine_dir = Path("C:/tmp/workspace/logs/lane/mine")
        args = argparse.Namespace(
            baseline_run_dir="baseline",
            mine_dir=str(mine_dir),
            skill_pack="generated_v1",
            skills_dir=str(root / "skill_packs/generated_v1/skills"),
            tasks="68,98",
            repo_root=str(root),
            python_bin="python",
            model="pi0_libero_openpi",
            gpu="0",
        )

        payload = module.lane_command_payload(
            args,
            root,
            mine_dir,
            argv=["python", "run_mining_lane.py", "--tasks", "68,98"],
            cwd=root,
        )

        self.assertEqual(payload["kind"], "skill_mining_lane_command")
        self.assertEqual(payload["repo_root"], str(root))
        self.assertEqual(payload["mine_dir"], str(mine_dir))
        self.assertEqual(payload["argv"], ["python", "run_mining_lane.py", "--tasks", "68,98"])
        self.assertIn("--tasks 68,98", payload["command_preview"])
        self.assertEqual(payload["args"]["skill_pack"], "generated_v1")

    def test_wait_codex_payload_infers_prompt_and_lane_command(self):
        module = _load_run_mining_lane()
        mine_dir = Path("C:/tmp/workspace/logs/lane/mine")
        evidence_json = mine_dir / "task68" / "fail_set.json"

        payload = module.wait_codex_payload(
            mine_dir,
            {
                "status": "need_draft",
                "awaiting_task": 68,
                "writes_used": 1,
                "writes_max": 5,
                "evidence_json": str(evidence_json),
            },
            source="step",
        )

        self.assertEqual(payload["event_type"], "codex_intervention_required")
        self.assertEqual(payload["source"], "step")
        self.assertEqual(payload["actor_prompt"], str(evidence_json.parent / "actor_prompt.md"))
        self.assertEqual(payload["lane_command_json"], str(mine_dir / "lane_command.json"))
        self.assertEqual(payload["evidence_json"], str(evidence_json))
        self.assertNotIn("pack_json", payload)

    def test_wait_codex_payload_accepts_legacy_pack_json(self):
        module = _load_run_mining_lane()
        mine_dir = Path("C:/tmp/workspace/logs/lane/mine")
        evidence_json = mine_dir / "task68" / "fail_set.json"

        payload = module.wait_codex_payload(
            mine_dir,
            {
                "status": "need_draft",
                "awaiting_task": 68,
                "writes_used": 1,
                "writes_max": 5,
                "pack_json": str(evidence_json),
            },
            source="step",
        )

        self.assertEqual(payload["actor_prompt"], str(evidence_json.parent / "actor_prompt.md"))
        self.assertEqual(payload["evidence_json"], str(evidence_json))
        self.assertNotIn("pack_json", payload)

    def test_child_env_treats_code_snapshots_parent_as_workspace_container(self):
        module = _load_run_mining_lane()
        root = Path("C:/tmp/workspace")
        repo = root / "code_snapshots" / "openvla-oft_abc123"
        args = argparse.Namespace(gpu=3)

        env = module.build_child_env(args, repo)

        entries = env["PYTHONPATH"].split(";")
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "3")
        self.assertEqual(env["OVERLAY_ROOT"], str(repo))
        self.assertEqual(env["CUTAMP_RUNNER_PYTHON"], str(repo / "scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh"))
        self.assertIn(str(root / "LIBERO_src"), entries)
        self.assertIn(str(root / "openpi" / "src"), entries)

    def test_quarantine_invalid_validation_dir_moves_canonical_result(self):
        module = _load_run_mining_lane()
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            on_dir = root / "validation" / "mine_val_task05_w1"
            on_dir.mkdir(parents=True)
            (on_dir / "summary.json").write_text('{"success": 0}', encoding="utf-8")

            moved = Path(
                module.quarantine_invalid_validation_dir(
                    on_dir,
                    {"status": "invalid_validation", "reason": "runner_failed"},
                )
            )

            self.assertFalse(on_dir.exists())
            self.assertTrue(moved.exists())
            self.assertTrue(moved.name.startswith("mine_val_task05_w1_invalid_"))
            marker = json.loads((moved / "INVALID_VALIDATION.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["original_on_dir"], str(on_dir))
            self.assertEqual(marker["status"], "invalid_validation")


def _load_watch_mining_interventions():
    repo = Path(__file__).resolve().parents[5]
    path = repo / "scripts" / "recovery" / "skill_pipeline" / "watch_mining_interventions.py"
    spec = importlib.util.spec_from_file_location("watch_mining_interventions", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_mark_mining_intervention():
    repo = Path(__file__).resolve().parents[5]
    path = repo / "scripts" / "recovery" / "skill_pipeline" / "mark_mining_intervention.py"
    spec = importlib.util.spec_from_file_location("mark_mining_intervention", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MiningInterventionWatchdogTests(unittest.TestCase):
    def test_scan_once_publishes_wait_codex_as_event(self):
        module = _load_watch_mining_interventions()
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mine_dir = root / "gpu0" / "mine"
            task_dir = mine_dir / "task68"
            task_dir.mkdir(parents=True)
            (task_dir / "fail_set.json").write_text("{}", encoding="utf-8")
            (task_dir / "actor_prompt.md").write_text("prompt", encoding="utf-8")
            (mine_dir / "lane_command.json").write_text(
                json.dumps({"argv": ["python", "run_mining_lane.py"]}),
                encoding="utf-8",
            )
            (mine_dir / "mine_state.json").write_text(
                json.dumps({"awaiting_task": 68, "awaiting_kind": "draft"}),
                encoding="utf-8",
            )
            (mine_dir / "WAIT_CODEX.json").write_text(
                json.dumps(
                    {
                        "status": "need_draft",
                        "awaiting_task": 68,
                        "writes_used": 1,
                        "writes_max": 5,
                        "evidence_json": str(task_dir / "fail_set.json"),
                        "actor_prompt": str(task_dir / "actor_prompt.md"),
                        "lane_command_json": str(mine_dir / "lane_command.json"),
                        "reason": "baseline failed",
                    }
                ),
                encoding="utf-8",
            )
            event_root = root / "codex_interventions"

            first = module.scan_once(
                run_root=root,
                mine_dirs=[mine_dir],
                event_root=event_root,
                scan_count=1,
            )
            second = module.scan_once(
                run_root=root,
                mine_dirs=[mine_dir],
                event_root=event_root,
                scan_count=2,
            )

            self.assertEqual(len(first["created"]), 1)
            self.assertEqual(len(second["created"]), 0)
            event = first["created"][0]
            self.assertEqual(event["status"], "codex_required")
            self.assertEqual(event["task_id"], 68)
            self.assertEqual(event["write_idx"], 1)
            self.assertEqual(event["evidence_json"], str(task_dir / "fail_set.json"))
            self.assertNotIn("pack_json", event)
            self.assertNotIn("pack_json", event["wait_payload"])
            self.assertTrue(Path(event["event_dir"], "event.json").exists())
            latest = json.loads((event_root / "LATEST_CODEX_EVENT.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["event_id"], event["event_id"])
            self.assertNotIn("pack_json", latest)
            pending = json.loads((event_root / "PENDING_CODEX_EVENTS.json").read_text(encoding="utf-8"))
            self.assertEqual(pending["pending_event_count"], 1)
            status = json.loads((event_root / "watchdog_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["pending_event_count"], 1)

            (Path(event["event_dir"]) / "resolved.json").write_text(
                json.dumps({"event_id": event["event_id"], "status": "resolved"}),
                encoding="utf-8",
            )
            third = module.scan_once(
                run_root=root,
                mine_dirs=[mine_dir],
                event_root=event_root,
                scan_count=3,
            )
            self.assertEqual(len(third["pending"]), 0)
            latest = json.loads((event_root / "LATEST_CODEX_EVENT.json").read_text(encoding="utf-8"))
            self.assertEqual(latest["lifecycle_status"], "resolved")
            pending = json.loads((event_root / "PENDING_CODEX_EVENTS.json").read_text(encoding="utf-8"))
            self.assertEqual(pending["pending_event_count"], 0)

    def test_scan_once_treats_error_event_as_terminal_by_default(self):
        module = _load_watch_mining_interventions()
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mine_dir = root / "gpu0" / "mine"
            task_dir = mine_dir / "task68"
            task_dir.mkdir(parents=True)
            (task_dir / "fail_set.json").write_text("{}", encoding="utf-8")
            (task_dir / "actor_prompt.md").write_text("prompt", encoding="utf-8")
            (mine_dir / "lane_command.json").write_text(
                json.dumps({"argv": ["python", "run_mining_lane.py"]}),
                encoding="utf-8",
            )
            (mine_dir / "mine_state.json").write_text(
                json.dumps({"awaiting_task": 68, "awaiting_kind": "draft"}),
                encoding="utf-8",
            )
            (mine_dir / "WAIT_CODEX.json").write_text(
                json.dumps(
                    {
                        "status": "need_draft",
                        "awaiting_task": 68,
                        "writes_used": 1,
                        "writes_max": 5,
                        "evidence_json": str(task_dir / "fail_set.json"),
                        "actor_prompt": str(task_dir / "actor_prompt.md"),
                        "lane_command_json": str(mine_dir / "lane_command.json"),
                    }
                ),
                encoding="utf-8",
            )
            event_root = root / "codex_interventions"
            first = module.scan_once(run_root=root, mine_dirs=[mine_dir], event_root=event_root, scan_count=1)
            event_dir = Path(first["created"][0]["event_dir"])
            (event_dir / "error.json").write_text(
                json.dumps({"event_id": first["created"][0]["event_id"], "status": "error"}),
                encoding="utf-8",
            )

            terminal = module.scan_once(run_root=root, mine_dirs=[mine_dir], event_root=event_root, scan_count=2)
            self.assertEqual(terminal["status"]["pending_event_count"], 0)
            self.assertEqual(len(terminal["pending"]), 0)

            retry = module.scan_once(
                run_root=root,
                mine_dirs=[mine_dir],
                event_root=event_root,
                scan_count=3,
                retry_errors=True,
            )
            self.assertEqual(retry["status"]["pending_event_count"], 1)
            self.assertTrue(retry["pending"][0]["errored"])

    def test_scan_once_marks_missing_prompt_as_invalid_event(self):
        module = _load_watch_mining_interventions()
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mine_dir = root / "gpu0" / "mine"
            mine_dir.mkdir(parents=True)
            (mine_dir / "mine_state.json").write_text(
                json.dumps({"awaiting_task": 68, "awaiting_kind": "draft"}),
                encoding="utf-8",
            )
            (mine_dir / "WAIT_CODEX.json").write_text(
                json.dumps({"status": "need_draft", "awaiting_task": 68, "writes_used": 1}),
                encoding="utf-8",
            )

            result = module.scan_once(
                run_root=root,
                mine_dirs=[mine_dir],
                event_root=root / "codex_interventions",
                scan_count=1,
            )

            self.assertEqual(result["created"][0]["status"], "codex_event_invalid")
            self.assertIn("evidence_json", result["created"][0]["missing_files"])
            self.assertIn("actor_prompt", result["created"][0]["missing_files"])

    def test_mark_event_claim_and_resolve_latest(self):
        module = _load_mark_mining_intervention()
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            event_root = Path(td) / "codex_interventions"
            event_dir = event_root / "events" / "task68_w1_abcdef"
            event_dir.mkdir(parents=True)
            event = {"event_id": "task68_w1_abcdef", "status": "codex_required"}
            (event_dir / "event.json").write_text(json.dumps(event), encoding="utf-8")
            (event_root / "LATEST_CODEX_EVENT.json").write_text(json.dumps(event), encoding="utf-8")

            claim = module.mark_event(
                argparse.Namespace(
                    command="claim",
                    event_root=str(event_root),
                    event_id="",
                    actor="codex",
                    message="taking it",
                    draft_md="",
                    bundle_yaml="",
                    ingest_result_json="",
                    resume_command="",
                )
            )
            resolved = module.mark_event(
                argparse.Namespace(
                    command="resolve",
                    event_root=str(event_root),
                    event_id="task68_w1_abcdef",
                    actor="codex",
                    message="ingested",
                    draft_md="draft.md",
                    bundle_yaml="",
                    ingest_result_json="result.json",
                    resume_command="python run_mining_lane.py ...",
                )
            )

            self.assertTrue(Path(claim["wrote"]).exists())
            self.assertTrue(Path(resolved["wrote"]).exists())
            self.assertEqual(json.loads((event_dir / "claim.json").read_text(encoding="utf-8"))["status"], "claimed")
            self.assertEqual(json.loads((event_dir / "resolved.json").read_text(encoding="utf-8"))["status"], "resolved")

    def test_mark_event_retry_clears_claim_and_error(self):
        module = _load_mark_mining_intervention()
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            event_root = Path(td) / "codex_interventions"
            event_dir = event_root / "events" / "task05_w2_retry"
            event_dir.mkdir(parents=True)
            event = {"event_id": "task05_w2_retry", "status": "codex_required"}
            (event_dir / "event.json").write_text(json.dumps(event), encoding="utf-8")
            (event_dir / "claim.json").write_text(json.dumps({"status": "claimed"}), encoding="utf-8")
            (event_dir / "error.json").write_text(json.dumps({"status": "error"}), encoding="utf-8")

            retry = module.mark_event(
                argparse.Namespace(
                    command="retry",
                    event_root=str(event_root),
                    event_id="task05_w2_retry",
                    actor="codex",
                    message="admission rejected; retry",
                    draft_md="",
                    bundle_yaml="",
                    ingest_result_json="",
                    resume_command="",
                )
            )

            self.assertFalse((event_dir / "claim.json").exists())
            self.assertFalse((event_dir / "error.json").exists())
            payload = json.loads(Path(retry["wrote"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "retry")
            self.assertEqual(sorted(payload["removed"]), ["claim.json", "error.json"])


if __name__ == "__main__":
    unittest.main()
