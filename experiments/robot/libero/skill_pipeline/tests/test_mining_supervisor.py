"""Regression tests for actor context, staged code and durable handoffs; no GPU."""

import argparse
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "scripts/recovery/skill_pipeline"))
import actor_context as context
import ingest_actor_candidate as ingest
import run_codex_intervention_daemon as daemon
import supervise_mining as supervisor
import mark_mining_intervention as marker
import actor_remote as transport


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class ContextTest(unittest.TestCase):
    def fixture(self, root):
        run = root / "run"
        ep = run / "val/task07/ep00"
        write(run / "mine/lane_command.json", {"args": {"task_suite_name": "libero_goal_swap",
              "repo_root": str(root), "skill_pack": "test", "num_trials": 15}})
        write(run / "mine/mine_state.json", {"awaiting_task": 7, "tasks": {"7": {"writes": 1}}})
        write(ep / "episode.json", {"source_suite": "libero_goal_swap", "task_id_1based": 7,
                                   "task_description": "put cream cheese in bowl", "success": False})
        write(ep / "query_trace.jsonl", {"query_idx": 12, "bddl_goal": ["in", "cheese", "bowl"]})
        write(ep / "recovery_trace.jsonl", {"query_idx": 12, "error": "no_feasible", "selected_skill": "repair"})
        (ep / "frames").mkdir()
        (ep / "frames/q0012_agentview.jpg").write_bytes(b"test")
        (ep / "cutamp_debug").mkdir()
        (ep / "cutamp_debug/s.stderr.txt").write_text("Collision robot_to_world 0/64 satisfying")
        evidence = run / "mine/evidence.json"
        write(evidence, {"task": "libero_90 task07 wrong legacy label", "failures": [{"episode_dir": str(ep)}]})
        return run, evidence, ep

    def test_identity_and_evidence_are_bound_to_failure_time(self):
        with TemporaryDirectory() as tmp:
            run, evidence, _ = self.fixture(Path(tmp))
            got = context.collect_context(run, evidence, 7)
            self.assertEqual(got["identity"]["suite"], "libero_goal_swap")
            rep = got["representative_episodes"][0]
            self.assertIn("q0012", rep["frames"][0])
            self.assertIn("0/64", rep["constraint_records"][0]["lines"][0])
            self.assertIn("query_idx", got["initial_query_record"])

    def test_mismatched_suite_cannot_be_silently_relabeled(self):
        with TemporaryDirectory() as tmp:
            run, evidence, ep = self.fixture(Path(tmp))
            write(ep / "episode.json", {"source_suite": "libero_goal_task"})
            with self.assertRaisesRegex(ValueError, "disagrees"):
                context.collect_context(run, evidence, 7)

    def test_history_reports_regressions_as_well_as_improvements(self):
        entry = {"attempts": [{"writes": n, "triage": {"episode_diagnoses": rows}} for n, rows in [
            (1, [{"episode_id": "a", "success": True}, {"episode_id": "b", "success": False}]),
            (2, [{"episode_id": "a", "success": False}, {"episode_id": "b", "success": True}])]]}
        result = context.history(entry)[1]
        self.assertEqual(result["improved"], ["b"])
        self.assertEqual(result["regressed"], ["a"])


class TransactionTest(unittest.TestCase):
    def test_interrupted_admission_rolls_back_when_no_write_was_accepted(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = root / "skill_packs/test"
            pack.mkdir(parents=True)
            (pack / "current.py").write_text("partial")
            txn = root / "txn"
            (txn / "pack_before").mkdir(parents=True)
            (txn / "pack_before/original.py").write_text("original")
            state = root / "mine/mine_state.json"
            write(state, {"awaiting_kind": "draft", "tasks": {"7": {"writes": 1}}})
            write(txn / "transaction.json", {"status": "applying", "state_path": str(state), "task_id": "7", "writes_before": 1})
            result = ingest.recover_transaction(txn, pack)
            self.assertEqual(result["status"], "rolled_back_interruption")
            self.assertTrue((pack / "original.py").exists())
            self.assertFalse((pack / "current.py").exists())

    def test_interrupted_admission_keeps_accepted_write_and_new_pack(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = root / "skill_packs/test"
            pack.mkdir(parents=True)
            (pack / "new.py").write_text("accepted")
            state = root / "mine/mine_state.json"
            write(state, {"awaiting_kind": "validation", "tasks": {"7": {"writes": 2}}})
            txn = root / "txn"
            write(txn / "transaction.json", {"status": "applying", "state_path": str(state), "task_id": "7", "writes_before": 1})
            self.assertEqual(ingest.recover_transaction(txn, pack)["status"], "committed")
            self.assertEqual((pack / "new.py").read_text(), "accepted")

    def fixture(self, root):
        pack = root / "skill_packs/test"
        dest = pack / "code/grasp_profiles.py"
        dest.parent.mkdir(parents=True)
        dest.write_text("OLD = 1\n")
        drafts = root / "drafts"
        src = drafts / "patch/skill_packs/test/code/grasp_profiles.py"
        src.parent.mkdir(parents=True)
        src.write_text("NEW = 2\n")
        (drafts / "code_patch_manifest.yaml").write_text(
            "touched_files: [skill_packs/test/code/grasp_profiles.py]\n")
        return pack, drafts, dest

    def test_gate_sees_code_then_rejection_restores_pack(self):
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            pack, drafts, dest = self.fixture(repo)
            def check(argv, **kwargs):
                self.assertIn("NEW", dest.read_text())
                self.assertIn("--code_base_snapshot", argv)
                baseline = json.loads(Path(argv[-1]).read_text())
                self.assertIn("OLD", baseline["skill_packs/test/code/grasp_profiles.py"])
                return mock.Mock(returncode=1, stdout='{"ok":false}', stderr="")
            with mock.patch.object(ingest.subprocess, "run", side_effect=check):
                code = ingest.apply_and_ingest(drafts, repo, pack, repo / "transaction", ["ingest"])
            self.assertEqual(code, 1)
            self.assertEqual(dest.read_text(), "OLD = 1\n")

    def test_success_commits_and_duplicate_does_not_ingest_twice(self):
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            pack, drafts, dest = self.fixture(repo)
            with mock.patch.object(ingest.subprocess, "run", return_value=mock.Mock(
                    returncode=0, stdout='{"ok":true}', stderr="")) as runner:
                for _ in range(2):
                    self.assertEqual(ingest.apply_and_ingest(drafts, repo, pack, repo / "txn", ["ingest"]), 0)
                self.assertEqual(runner.call_count, 1)
            self.assertEqual(dest.read_text(), "NEW = 2\n")

    def test_other_pack_patch_is_rejected_before_write(self):
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            pack, drafts, _ = self.fixture(repo)
            extra = drafts / "patch/skill_packs/other/code/bad.py"
            extra.parent.mkdir(parents=True)
            extra.write_text("BAD = 1")
            with self.assertRaisesRegex(ValueError, "escapes"):
                ingest.patch_files(drafts, repo, pack)


class LifecycleTest(unittest.TestCase):
    def test_supervisor_replacement_does_not_stop_an_active_actor(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            write(root / "supervisor/daemon.lock", {"pid":123})
            round_dir=root / "event/attempt1"
            write(round_dir / "actor_process.json", {"pid":456})
            write(root / "attempts/event.json", {"attempts":[{"in_progress":True,"round_dir":str(round_dir)}]})
            with (
                mock.patch.object(daemon,"process_alive",return_value=True),
                mock.patch.object(daemon,"acquire_lock",return_value=True),
                mock.patch.object(daemon,"release_lock") as release,
                mock.patch.object(daemon,"run_quiet") as stop,
                mock.patch.object(supervisor.time,"sleep",side_effect=RuntimeError("waited")),
            ):
                with self.assertRaisesRegex(RuntimeError,"waited"):
                    supervisor.wait_for_idle_replacement(root,123)
            stop.assert_not_called();release.assert_called_once_with(root)

    def test_supervisor_replacement_rejects_unrelated_pid(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);write(root / "supervisor/daemon.lock",{"pid":321})
            with mock.patch.object(daemon,"process_alive",return_value=True),mock.patch.object(daemon,"run_quiet") as stop:
                with self.assertRaisesRegex(RuntimeError,"does not own"):
                    supervisor.wait_for_idle_replacement(root,123)
            stop.assert_not_called()

    def test_transport_keeps_server_key_and_path_as_distinct_arguments(self):
        cfg = {"host": "203.0.113.9", "port": "2222", "key": "E:/a path/key"}
        cmd = transport.ssh_args(cfg)
        self.assertEqual(cmd[cmd.index("-i") + 1], "E:/a path/key")
        self.assertEqual(cmd[-1], "root@203.0.113.9")
        self.assertIn("BatchMode=yes", cmd)
        self.assertEqual(transport.bounded("/workspace/a'b.txt", "/workspace"), "/workspace/a'b.txt")
        for path in ("/workspace2/private", "/workspace/../secret"):
            with self.assertRaises(ValueError):
                transport.bounded(path, "/workspace")

    def test_live_lock_never_expires_due_to_elapsed_time(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "daemon.lock", {"pid": 123, "started_at": 1})
            with mock.patch.object(daemon, "process_alive", return_value=True):
                self.assertFalse(daemon.acquire_lock(root, timeout_s=1))

    def test_actor_failure_is_not_draft_success_even_when_exit_is_zero(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prompt.md").write_text("test")
            write(root / "actor_final.json", {"status": "failed", "notes": "no candidate"})
            with mock.patch.object(daemon.subprocess, "Popen", return_value=mock.Mock(
                    returncode=0, pid=321, poll=lambda: 0)) as popen:
                code, _ = daemon.run_codex(codex_exe="codex", workdir=root, prompt_path=root / "prompt.md",
                    schema_path=root / "schema.json", model="gpt-5.5", reasoning_effort="xhigh", timeout=10)
            self.assertNotEqual(code, 0)
            argv = popen.call_args.args[0]
            self.assertEqual(argv[argv.index("-m") + 1], "gpt-5.5")
            self.assertIn('model_reasoning_effort="xhigh"', argv)

    def test_changed_pack_or_round_prevents_late_ingest(self):
        ident = {"task_id": 7, "writes_used": 1, "repo": "/repo", "evidence_path": "/e"}
        old = {"identity": ident, "pack_files_sha256": {"profiles/x.yaml": "old"}}
        remote = mock.Mock()
        remote.exists.return_value = False
        with mock.patch.object(daemon, "mine_state", return_value={"awaiting_task": 7, "awaiting_kind": "draft",
                     "tasks": {"7": {"writes": 1}}}), mock.patch.object(daemon, "collect_remote_context",
                     return_value={"identity": ident, "pack_files_sha256": {"profiles/x.yaml": "new"}}):
            self.assertFalse(daemon.context_is_current(remote, "/run", old))

    def test_user_stop_prevents_completed_actor_from_ingesting(self):
        remote = mock.Mock()
        remote.exists.return_value = True
        self.assertFalse(daemon.context_is_current(remote, "/run", {}))
        remote.cat_json.assert_not_called()

    def test_live_orphan_actor_is_not_redelivered(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            round_dir = root / "event/attempt1"
            write(round_dir / "actor_process.json", {"pid": 99})
            write(root / "attempts/event.json", {"event_id": "event", "attempts": [{
                "run_root": "/run", "executor": "exec", "round_dir": str(round_dir),
                "owner_pid": 98, "in_progress": True}]})
            remote = mock.Mock()
            with mock.patch.object(daemon, "process_alive", side_effect=lambda pid: pid == 99):
                self.assertTrue(supervisor.recover_owned_attempts(remote, {"run_root": "/run"}, root))
            remote.run.assert_not_called()

    def test_only_one_remote_claim_can_win(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "events/e/event.json", {"event_id": "e"})
            args = argparse.Namespace(event_root=str(root), event_id="e", actor="a", message="", command="claim")
            self.assertTrue(marker.mark_event(args)["ok"])
            with self.assertRaises(FileExistsError):
                marker.mark_event(args)


if __name__ == "__main__":
    unittest.main()
