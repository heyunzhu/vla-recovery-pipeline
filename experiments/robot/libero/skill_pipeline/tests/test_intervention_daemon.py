"""Unit tests for the mining intervention daemon (no ssh, no codex, no GPU)."""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[5]
DAEMON_PATH = REPO_ROOT / "scripts/recovery/skill_pipeline/run_codex_intervention_daemon.py"


def _load_daemon():
    spec = importlib.util.spec_from_file_location("run_codex_intervention_daemon", DAEMON_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclass() looks its module up in sys.modules, so register before exec.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


daemon = _load_daemon()


class EventAgeTest(unittest.TestCase):
    """The age gate must be timezone-safe: the watchdog stamps events in UTC."""

    def _ago(self, **delta) -> str:
        when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(**delta)
        return when.strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_fresh_event_is_minutes_old_not_hours(self):
        age = daemon.event_age_minutes({"created_at": self._ago(minutes=5)})
        self.assertAlmostEqual(age, 5.0, delta=1.0)

    def test_age_matches_the_absolute_difference(self):
        self.assertAlmostEqual(daemon.event_age_minutes({"created_at": self._ago(hours=4)}),
                               240.0, delta=1.0)

    def test_missing_and_malformed_timestamps_report_unknown(self):
        self.assertEqual(daemon.event_age_minutes({}), -1.0)
        self.assertEqual(daemon.event_age_minutes({"created_at": "not a timestamp"}), -1.0)
        self.assertEqual(daemon.event_age_minutes({"created_at": ""}), -1.0)

    def test_offset_aware_timestamps_are_accepted(self):
        self.assertAlmostEqual(
            daemon.event_age_minutes({"created_at": self._ago(minutes=30).replace("Z", "+00:00")}),
            30.0, delta=1.0)

    def test_a_fresh_event_survives_the_default_age_limit(self):
        """Regression: on UTC+8 this used to read ~485 minutes and be skipped."""

        age = daemon.event_age_minutes({"created_at": self._ago(minutes=1)})
        self.assertLess(age, 180.0)


class OutputSchemaTest(unittest.TestCase):
    """Strict structured outputs reject a schema whose properties are not all required."""

    def test_every_property_is_also_required(self):
        schema = daemon.output_schema()
        self.assertEqual(set(schema["properties"]), set(schema["required"]))
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(schema["properties"]["status"]["enum"], ["drafted", "failed"])

    def test_the_schema_that_failed_the_first_live_round_is_rejected_locally(self):
        broken = {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "files", "notes"],
            "properties": {
                "status": {"type": "string"},
                "files": {"type": "array", "items": {"type": "string"}},
                "bundle_yaml": {"type": "string"},
                "draft_md": {"type": "string"},
                "code_manifest": {"type": "string"},
                "notes": {"type": "string"},
            },
        }
        problem = daemon.strict_schema_error(broken)
        self.assertIn("bundle_yaml", problem)

    def test_good_schema_reports_no_problem(self):
        self.assertEqual(daemon.strict_schema_error(daemon.output_schema()), "")

    def test_additional_properties_must_be_false(self):
        self.assertIn("additionalProperties",
                      daemon.strict_schema_error({"properties": {}, "required": []}))

    def test_output_stream_helper_is_safe_to_call(self):
        daemon.make_output_streams_utf8_safe()  # must never raise


class FakeRemote:
    """Minimal Remote stand-in: only the read paths pick_event/verify need."""

    def __init__(
        self,
        *,
        waiting: bool,
        events: list[dict],
        resolved: set[str] | None = None,
        manifest: bool = False,
        state: dict | None = None,
    ):
        self.root = "/mnt/fake/root"
        self.waiting = waiting
        self.events = events
        self.resolved = resolved or set()
        self.manifest = manifest
        self.state = state if state is not None else _needs_draft()
        self.commands: list[str] = []

    def exists(self, path: str, **_kwargs) -> bool:
        if path.endswith("mine/WAIT_CODEX.json"):
            return self.waiting
        if path.endswith(daemon.MANIFEST_NAME):
            return self.manifest
        for event in self.events:
            if path == f"{event['event_dir']}/resolved.json":
                return str(event["event_id"]) in self.resolved
        return False

    def cat_json(self, path: str, **_kwargs) -> dict:
        if path.endswith("PENDING_CODEX_EVENTS.json"):
            return {"pending_events": self.events}
        if path.endswith("mine_state.json"):
            return dict(self.state or {})
        return {}

    def run(self, command: str, **_kwargs):
        self.commands.append(command)
        return type("Done", (), {"returncode": 0, "stdout": "", "stderr": ""})()


def _needs_draft(task_id: int = 5) -> dict:
    return {"awaiting_task": task_id, "awaiting_kind": "draft", "tasks": {str(task_id): {"status": "awaiting_draft"}}}


def _event(event_id: str, *, task_id: int = 5, claimed: bool = False, created: str = "2026-09-11T00:00:00Z") -> dict:
    return {
        "event_id": event_id,
        "event_dir": f"/mnt/fake/root/logs/run/codex_interventions/events/{event_id}",
        "task_id": task_id,
        "write_idx": 0,
        "claimed": claimed,
        "created_at": created,
    }


class MarkCommandQuotingTest(unittest.TestCase):
    """A failed round's message must survive the shell hop as one argument."""

    def _config(self):
        return {"repo": "/repo", "python": "/py", "run_root": "/mnt/fake/root/logs/run"}

    def test_spaced_message_stays_one_argument(self):
        import shlex as _shlex

        command = daemon.mark_command(object(), self._config(), "error", "task07_w0_x",
                                      "--message 'attempt 3 failed: drafts directory is empty'")
        argv = _shlex.split(command)
        self.assertEqual(argv.count("--message"), 1)
        self.assertEqual(argv[argv.index("--message") + 1],
                         "attempt 3 failed: drafts directory is empty")

    def test_embedded_quotes_cannot_break_out(self):
        import shlex as _shlex

        command = daemon.mark_command(object(), self._config(), "error", "task07_w0_x",
                                      "--message \"oops'; rm -rf /\"")
        argv = _shlex.split(command)
        self.assertNotIn("rm", argv)
        self.assertEqual(argv[argv.index("--message") + 1], "oops; rm -rf /")


class IngestFeedbackTest(unittest.TestCase):
    """A refused draft must not leave the next round guessing."""

    def _prompt(self, **kwargs):
        args = dict(guidelines="g", capability_excerpt="", library_index="", summary="s",
                    verdict="", ssh_command="ssh", run_root="/r", drafts_dir="/d", write_idx=0)
        args.update(kwargs)
        return daemon.compose_prompt(**args)

    def test_rejection_reason_reaches_the_next_prompt(self):
        text = self._prompt(
            previous_failure="SkillSchemaError: skill file must start with YAML front matter (---)")
        self.assertIn("## Your previous draft was rejected", text)
        self.assertIn("must start with YAML front matter", text)

    def test_no_section_without_a_rejection(self):
        self.assertNotIn("## Your previous draft was rejected", self._prompt())

    def test_helper_reports_the_latest_refusal(self):
        state = {"attempts": [
            {"ok": True},
            {"ok": True, "ingest": {"ok": False, "raw": "first failure"}},
            {"ok": True, "ingest": {"ok": False, "errors": ["second failure"]}},
        ]}
        self.assertEqual(daemon.previous_ingest_failure(state), "second failure")

    def test_helper_falls_back_to_the_raw_tail(self):
        state = {"attempts": [{"ingest": {"ok": False, "raw": "Traceback ... SkillSchemaError"}}]}
        self.assertIn("SkillSchemaError", daemon.previous_ingest_failure(state))

    def test_helper_is_silent_when_nothing_was_refused(self):
        self.assertEqual(daemon.previous_ingest_failure({}), "")
        self.assertEqual(
            daemon.previous_ingest_failure({"attempts": [{"ingest": {"ok": True}}]}), "")


class QueuedPromptGuidelineTest(unittest.TestCase):
    """The queue daemon must not drift from the offline actor's authoring docs."""

    def test_queue_prompt_guidelines_include_all_skill_type_docs(self):
        repo = Path(__file__).resolve().parents[5]
        text = daemon.actor_guidelines_with_type_docs(repo)
        for rel in (
            "docs/repair_skill_authoring_guidelines.md",
            "docs/grasp_skill_authoring_guidelines.md",
            "docs/grounding_skill_authoring_guidelines.md",
            "docs/geometry_skill_authoring_guidelines.md",
            "docs/place_skill_authoring_guidelines.md",
        ):
            self.assertIn(rel, text)


class ClaimLeaseTest(unittest.TestCase):
    """Claimed or locally in-progress events must not be auto-requeued."""

    def _remote(self):
        return FakeRemote(waiting=True, events=[_event("task05_w0_abc", task_id=5, claimed=True)])

    def test_claim_without_a_local_attempt_is_left_alone(self):
        """Someone else's live claim stays untouched."""

        with mock.patch.object(daemon, "load_attempts", return_value={"attempts": []}):
            self.assertIsNone(daemon.pick_event(self._remote(), "/mnt/fake/root/logs/run",
                                                Path("workdir"), max_attempts=5))

    def test_force_stale_recovers_a_claim_without_a_local_attempt(self):
        """A daemon crash after remote claim but before local attempt creation must be recoverable."""

        with mock.patch.object(daemon, "load_attempts", return_value={"attempts": []}):
            event = daemon.pick_event(
                self._remote(),
                "/mnt/fake/root/logs/run",
                Path("workdir"),
                max_attempts=5,
                force_stale=True,
            )
        self.assertIsNotNone(event)
        self.assertEqual(event["event_id"], "task05_w0_abc")

    def test_claim_we_already_attempted_is_left_alone(self):
        with mock.patch.object(daemon, "load_attempts", return_value={"attempts": [{"ok": False}]}):
            event = daemon.pick_event(self._remote(), "/mnt/fake/root/logs/run",
                                      Path("workdir"), max_attempts=5)
        self.assertIsNone(event)

    def test_local_in_progress_lease_is_left_alone(self):
        remote = FakeRemote(waiting=True, events=[_event("task05_w0_abc", task_id=5, claimed=False)])
        state = {"attempts": [{"in_progress": True, "result_path": "C:/tmp/result.json"}]}
        with mock.patch.object(daemon, "load_attempts", return_value=state):
            self.assertIsNone(daemon.pick_event(remote, "/mnt/fake/root/logs/run",
                                                Path("workdir"), max_attempts=5))

    def test_errored_event_is_terminal_by_default(self):
        remote = FakeRemote(waiting=True, events=[dict(_event("task05_w0_abc", task_id=5), errored=True)])
        with mock.patch.object(daemon, "load_attempts", return_value={"attempts": []}):
            self.assertIsNone(daemon.pick_event(remote, "/mnt/fake/root/logs/run",
                                                Path("workdir"), max_attempts=5))

    def test_errored_event_can_be_retried_explicitly(self):
        remote = FakeRemote(waiting=True, events=[dict(_event("task05_w0_abc", task_id=5), errored=True)])
        with mock.patch.object(daemon, "load_attempts", return_value={"attempts": []}):
            event = daemon.pick_event(remote, "/mnt/fake/root/logs/run",
                                      Path("workdir"), max_attempts=5, retry_errors=True)
        self.assertIsNotNone(event)
        self.assertEqual(event["event_id"], "task05_w0_abc")

    def test_retry_cap_still_wins_over_the_lease(self):
        state = {"attempts": [{"ok": False}] * 5, "needs_human": True}
        with mock.patch.object(daemon, "load_attempts", return_value=state):
            self.assertIsNone(daemon.pick_event(self._remote(), "/mnt/fake/root/logs/run",
                                                Path("workdir"), max_attempts=5))


class InterventionDaemonTests(unittest.TestCase):
    def test_exists_timeout_is_treated_as_absent(self):
        remote = daemon.Remote(host="example.invalid", port="22", key="k", root="/mnt/fake/root")
        with mock.patch.object(remote, "run", side_effect=subprocess.TimeoutExpired(["ssh"], 60)):
            self.assertFalse(remote.exists("/mnt/fake/root/logs/run/mine/task10/actor_prompt.md"))

    def test_summarize_fail_set_is_compact_and_points_at_the_remote_evidence(self):
        fail_set = {
            "task": "libero_90 task10 put the wine bottle on the rack",
            "track": "fail_only",
            "pack_kind": "fail_set",
            "mine": {"action": "write", "reason": "library is empty", "instruction": "x" * 5000},
            "failures": [
                {
                    "episode_idx": idx,
                    "seed": 51 + idx,
                    "success": False,
                    "recovery_event_count": 0,
                    "episode_dir": f"/mnt/fake/root/logs/run/baseline/task10/ep{idx:02d}",
                    "queries": [{"query_idx": 60, "holding_status": "handempty_or_unconfirmed"}],
                }
                for idx in range(15)
            ],
            "aligned_frames": [{"slot": "approach", "query_idx": 3, "fail_frame": "/mnt/.../q0003.jpg"}],
        }
        summary = daemon.summarize_fail_set(fail_set)
        self.assertIn("libero_90 task10", summary)
        self.assertIn("- failures: 15", summary)
        self.assertIn("| ep | seed |", summary)
        self.assertIn("handempty_or_unconfirmed", summary)
        self.assertIn("/mnt/fake/root/logs/run/baseline/task10/ep00", summary)
        self.assertLess(len(summary), 4000, "summary must stay small; the traces are grepped on demand")

    def test_compose_prompt_stays_small_and_carries_the_constraints(self):
        prompt = daemon.compose_prompt(
            guidelines="actor guidelines " * 500,
            capability_excerpt="capabilities: {}",
            library_index="online: []",
            summary="- failures: 15",
            verdict="### Round 1\n- same-init validation: 6/15",
            ssh_command="ssh -p 5488 -i key root@host",
            run_root="/mnt/fake/root/logs/run",
            drafts_dir=r"C:\work\evt\drafts",
            write_idx=1,
        )
        self.assertIn("Hard constraints", prompt)
        self.assertIn(r"C:\work\evt\drafts", prompt)
        self.assertIn("Previous rounds in this run", prompt)
        self.assertIn("same-init validation: 6/15", prompt)
        self.assertIn("ssh -p 5488", prompt)
        self.assertLess(len(prompt), 40_000, "the 2MB evidence JSON must not be inlined")

    def test_verify_drafts_requires_artifacts_on_disk(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td)
            ok, detail = daemon.verify_drafts(root / "missing")
            self.assertFalse(ok)
            self.assertIn("not created", detail)

            empty = root / "empty"
            empty.mkdir()
            self.assertFalse(daemon.verify_drafts(empty)[0])

            findings_only = root / "findings_only"
            findings_only.mkdir()
            (findings_only / "findings.md").write_text("x", encoding="utf-8")
            ok, detail = daemon.verify_drafts(findings_only)
            self.assertFalse(ok)
            self.assertIn("bundle.yaml", detail)

            good = root / "good"
            good.mkdir()
            (good / "findings.md").write_text("x", encoding="utf-8")
            (good / "bundle.yaml").write_text("drafts: []", encoding="utf-8")
            self.assertTrue(daemon.verify_drafts(good)[0])

            missing_ref = root / "missing_ref"
            missing_ref.mkdir()
            (missing_ref / "findings.md").write_text("x", encoding="utf-8")
            (missing_ref / "bundle.yaml").write_text(
                "drafts:\n  - file: drafts/grasp/missing.md\n",
                encoding="utf-8",
            )
            ok, detail = daemon.verify_drafts(missing_ref)
            self.assertFalse(ok)
            self.assertIn("references missing file", detail)

            good_ref = root / "good_ref"
            (good_ref / "grasp").mkdir(parents=True)
            (good_ref / "findings.md").write_text("x", encoding="utf-8")
            (good_ref / "grasp" / "skill.md").write_text("x", encoding="utf-8")
            (good_ref / "bundle.yaml").write_text(
                "drafts:\n  - file: grasp/skill.md\n",
                encoding="utf-8",
            )
            self.assertTrue(daemon.verify_drafts(good_ref)[0])

    def test_pick_event_skips_stale_claimed_and_exhausted_events(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            workdir = Path(td)
            live = _event("task05_w0_live", created="2026-09-11T01:00:00Z")
            claimed = _event("task05_w0_claimed", claimed=True, created="2026-09-11T00:30:00Z")
            resolved = _event("task05_w0_resolved", created="2026-09-11T00:20:00Z")
            exhausted = _event("task05_w0_exhausted", created="2026-09-11T00:10:00Z")
            remote = FakeRemote(waiting=True, events=[claimed, resolved, exhausted, live], resolved={resolved["event_id"]})
            daemon.save_attempts(
                workdir,
                exhausted["event_id"],
                {"event_id": exhausted["event_id"], "attempts": [{"ok": False}] * 5, "needs_human": True},
            )

            picked = daemon.pick_event(remote, "/mnt/fake/root/logs/run", workdir, max_attempts=5)
            self.assertIsNotNone(picked)
            self.assertEqual(picked["event_id"], live["event_id"])

    def test_pick_event_returns_none_for_finished_runs(self):
        """The real trap: a finished run keeps WAIT_CODEX.json and a stale wait_codex status."""
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            remote = FakeRemote(
                waiting=True,
                events=[_event("task05_w0_live")],
                state={"awaiting_task": None, "awaiting_kind": None, "tasks": {"5": {"status": "passed"}}},
            )
            self.assertIsNone(daemon.pick_event(remote, "/mnt/fake/root/logs/run", Path(td), max_attempts=5))
            verdict, detail, _ = daemon.liveness(remote, "/mnt/fake/root/logs/run")
            self.assertEqual(verdict, "finished")
            self.assertIn("stale WAIT_CODEX", detail)

    def test_pick_event_returns_none_when_a_validation_is_pending(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            remote = FakeRemote(
                waiting=False,
                events=[_event("task03_w2_live", task_id=3)],
                state={"awaiting_task": 3, "awaiting_kind": "validation"},
            )
            self.assertIsNone(daemon.pick_event(remote, "/mnt/fake/root/logs/run", Path(td), max_attempts=5))
            self.assertEqual(daemon.liveness(remote, "/mnt/fake/root/logs/run")[0], "awaiting_validation")

    def test_pick_event_ignores_events_for_another_task(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            remote = FakeRemote(waiting=True, events=[_event("task07_w0_other", task_id=7)], state=_needs_draft(5))
            self.assertIsNone(daemon.pick_event(remote, "/mnt/fake/root/logs/run", Path(td), max_attempts=5))

    def test_pick_event_skips_events_older_than_the_age_limit(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            workdir = Path(td)
            old = _event("task05_w0_old", created="2020-01-01T00:00:00Z")
            remote = FakeRemote(waiting=True, events=[old])
            self.assertEqual(daemon.event_age_minutes(old) > 1000, True)
            self.assertIsNone(
                daemon.pick_event(remote, "/mnt/fake/root/logs/run", workdir, max_attempts=5, max_age_minutes=180)
            )
            self.assertIsNotNone(
                daemon.pick_event(
                    remote, "/mnt/fake/root/logs/run", workdir, max_attempts=5, max_age_minutes=180, force_stale=True
                )
            )

    def test_lock_ignores_stale_holders_and_releases(self):
        with TemporaryDirectory(ignore_cleanup_errors=True) as td:
            workdir = Path(td)
            (workdir / "daemon.lock").write_text(json.dumps({"pid": 0, "started_at": 0}), encoding="utf-8")
            self.assertTrue(daemon.acquire_lock(workdir, timeout_s=60))
            daemon.release_lock(workdir)
            self.assertFalse((workdir / "daemon.lock").exists())
            self.assertTrue(daemon.acquire_lock(workdir, timeout_s=60))
            daemon.release_lock(workdir)

    def test_ingest_command_carries_the_gates_and_stays_in_the_run_root(self):
        remote = FakeRemote(waiting=True, events=[], manifest=True)
        config = {
            "run_root": "/mnt/fake/root/logs/run",
            "repo": "/mnt/fake/root/code_snapshots/repo",
            "python": "/mnt/fake/root/envs/py/bin/python",
        }
        lane = {"skill_pack": "pack_v1", "baseline_run_dir": "/mnt/fake/root/logs/run/baseline_task05"}
        command = daemon.ingest_command(
            remote=remote, config=config, args=lane, task_id=5, draft_dir="/mnt/fake/root/logs/run/evt/drafts", write_idx=1
        )
        self.assertIn("--enable_code_admission_gate", command)
        self.assertIn("--enable_admission_gate", command)
        self.assertIn("--code_manifest", command)
        self.assertIn("/mnt/fake/root/logs/run/evt/drafts", command)

    def test_skill_only_draft_does_not_force_the_code_gate(self):
        """A round that ships no manifest has no code to check and must not be rejected."""
        remote = FakeRemote(waiting=True, events=[], manifest=False)
        config = {
            "run_root": "/mnt/fake/root/logs/run",
            "repo": "/mnt/fake/root/code_snapshots/repo",
            "python": "/mnt/fake/root/envs/py/bin/python",
        }
        command = daemon.ingest_command(
            remote=remote, config=config, args={"skill_pack": "pack_v1"}, task_id=5,
            draft_dir="/mnt/fake/root/logs/run/evt/drafts", write_idx=2,
        )
        self.assertNotIn("--code_manifest", command)
        self.assertNotIn("--enable_code_admission_gate", command)
        self.assertIn("--enable_admission_gate", command)

    def test_mark_command_strips_quotes_that_would_break_the_shell(self):
        remote = FakeRemote(waiting=True, events=[])
        config = {"run_root": "/mnt/fake/root/logs/run", "repo": "/mnt/fake/root/repo", "python": "/py"}
        command = daemon.mark_command(remote, config, "error", "evt", "--message 'it's broken'")
        self.assertNotIn("it's", command)
        self.assertIn("its broken", command)

    def test_guard_refuses_paths_outside_the_remote_root(self):
        remote = daemon.Remote(root="/mnt/fake/root")
        with self.assertRaises(SystemExit):
            remote.guard("/etc/passwd")


class QueueExecutorTest(unittest.TestCase):
    """`codex queue` is fire-and-forget, so the round is only done at result.json."""

    def test_message_points_at_the_prompt_the_drafts_and_the_marker(self):
        message = daemon.queue_message(
            event_id="task07_w0_abc",
            write_idx=1,
            prompt_path=Path(r"C:\work\task07_w0_abc\attempt1\prompt.md"),
            drafts_dir=Path(r"C:\work\task07_w0_abc\attempt1\drafts"),
            result_path=Path(r"C:\work\task07_w0_abc\attempt1\result.json"),
        )
        self.assertIn("task07_w0_abc", message)
        self.assertIn("prompt.md", message)
        self.assertIn("drafts", message)
        self.assertIn("result.json", message)
        self.assertIn('"status": "ok"', message)

    def test_prompt_finish_instruction_follows_the_executor(self):
        common = dict(
            guidelines="", capability_excerpt="", library_index="", summary="",
            verdict="", ssh_command="ssh fake", run_root="/mnt/fake/run",
            drafts_dir="/tmp/drafts", write_idx=0,
        )
        queued = daemon.compose_prompt(
            **common, finish_instruction="Finish by writing `result.json`."
        )
        self.assertIn("Finish by writing `result.json`.", queued)
        self.assertNotIn("output schema", queued)
        old = daemon.compose_prompt(**common)
        self.assertIn("output schema", old)

    def test_marker_with_status_ok_completes_the_round(self):
        with TemporaryDirectory() as tmp:
            marker = Path(tmp) / "result.json"
            marker.write_text(json.dumps({"status": "ok", "summary": "draft written"}),
                              encoding="utf-8")
            ok, detail = daemon.wait_for_agent_result(result_path=marker, timeout=5)
        self.assertTrue(ok)
        self.assertIn("draft written", detail)

    def test_marker_with_status_failed_fails_the_round(self):
        with TemporaryDirectory() as tmp:
            marker = Path(tmp) / "result.json"
            marker.write_text(json.dumps({"status": "failed", "summary": "no ssh"}),
                              encoding="utf-8")
            ok, detail = daemon.wait_for_agent_result(result_path=marker, timeout=5)
        self.assertFalse(ok)
        self.assertIn("no ssh", detail)

    def test_missing_marker_times_out_instead_of_pretending_success(self):
        with TemporaryDirectory() as tmp:
            marker = Path(tmp) / "result.json"
            ticks = []
            ok, detail = daemon.wait_for_agent_result(
                result_path=marker, timeout=1, poll_seconds=1,
                sleep=lambda seconds: ticks.append(seconds),
            )
        self.assertFalse(ok)
        self.assertIn("did not write result.json", detail)
        self.assertTrue(ticks)

    def test_malformed_marker_is_rejected(self):
        with TemporaryDirectory() as tmp:
            marker = Path(tmp) / "result.json"
            marker.write_text("{not json", encoding="utf-8")
            ok, detail = daemon.wait_for_agent_result(result_path=marker, timeout=5)
        self.assertFalse(ok)
        self.assertIn("not valid JSON", detail)

    def test_delivery_failure_is_reported_not_swallowed(self):
        with mock.patch.object(daemon.subprocess, "run") as runner:
            runner.return_value = mock.Mock(returncode=1, stdout="", stderr="no app server")
            ok, detail = daemon.deliver_via_queue(
                codex_exe="codex.exe", thread="thread-1", message="hi"
            )
        self.assertFalse(ok)
        self.assertIn("no app server", detail)

    def test_delivery_passes_the_thread_and_message_through(self):
        with mock.patch.object(daemon.subprocess, "run") as runner:
            runner.return_value = mock.Mock(returncode=0, stdout="Queued message abc", stderr="")
            ok, detail = daemon.deliver_via_queue(
                codex_exe="codex.exe", thread="01a01a62", message="do the round"
            )
            argv = runner.call_args[0][0]
        self.assertTrue(ok)
        self.assertEqual(argv[:2], ["codex.exe", "queue"])
        self.assertIn("--thread", argv)
        self.assertEqual(argv[argv.index("--thread") + 1], "01a01a62")
        self.assertEqual(argv[argv.index("--message") + 1], "do the round")


class PromptFormatTest(unittest.TestCase):
    """The first live rounds were refused for format and vocabulary, not for reasoning."""

    def _prompt(self) -> str:
        return daemon.compose_prompt(
            guidelines="", capability_excerpt="", library_index="", summary="",
            verdict="", ssh_command="ssh fake", run_root="/mnt/fake/run",
            drafts_dir="/tmp/drafts", write_idx=0,
        )

    def test_front_matter_rule_is_stated(self):
        self.assertIn("must begin with a line containing exactly `---`", self._prompt())

    def test_registry_predicate_names_are_listed(self):
        trigger, applies = daemon.predicate_vocabulary()
        self.assertIn("vla_pick_target_status_is", trigger)
        self.assertIn("wrong_progress_target_static", trigger)
        self.assertIn("task_language_matches", applies)

    def test_the_invented_predicate_is_not_sanctioned(self):
        """`target_total_motion_m_below` was the name the first rounds made up."""

        prompt = self._prompt()
        self.assertNotIn("target_total_motion_m_below", prompt)

    def test_a_missing_registry_omits_the_section_instead_of_lying(self):
        with mock.patch.object(daemon.Path, "read_text", side_effect=OSError("gone")):
            trigger, applies = daemon.predicate_vocabulary()
        self.assertEqual((trigger, applies), ("", ""))
        with mock.patch.object(daemon.Path, "read_text", side_effect=OSError("gone")):
            sections = "\n".join(daemon.draft_format_sections())
        self.assertIn("Draft file format", sections)
        self.assertNotIn("Predicate names you may use", sections)


class ExecSandboxTest(unittest.TestCase):
    """workspace-write cannot read an ssh key outside the workspace; full access can."""

    def _run(self, sandbox: str):
        with TemporaryDirectory() as tmp:
            round_dir = Path(tmp)
            prompt = round_dir / "prompt.md"
            prompt.write_text("do it", encoding="utf-8")
            (round_dir / "actor_final.json").write_text('{"status":"drafted"}', encoding="utf-8")
            with mock.patch.object(daemon.subprocess, "Popen") as runner:
                runner.return_value = mock.Mock(returncode=0, pid=123, poll=lambda: 0)
                daemon.run_codex(
                    codex_exe="codex.exe", workdir=round_dir, prompt_path=prompt,
                    schema_path=round_dir / "schema.json", model="", timeout=5,
                    sandbox=sandbox,
                )
                return runner.call_args[0][0]

    def test_full_access_reaches_the_cli(self):
        argv = self._run("danger-full-access")
        self.assertEqual(argv[argv.index("-s") + 1], "danger-full-access")
        self.assertIn('model_reasoning_effort="xhigh"', argv)
        self.assertNotIn("--ephemeral", argv)

    def test_the_sandbox_can_still_be_locked_down(self):
        argv = self._run("workspace-write")
        self.assertEqual(argv[argv.index("-s") + 1], "workspace-write")


class CodexExeTest(unittest.TestCase):
    """The first real round died on the stale alias: it has no `queue` subcommand."""

    def _binroot(self, tmp: str) -> Path:
        root = Path(tmp) / "OpenAI" / "Codex" / "bin"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def test_a_versioned_cli_wins_over_the_alias(self):
        with TemporaryDirectory() as tmp:
            root = self._binroot(tmp)
            (root / "codex.exe").write_text("", encoding="utf-8")
            versioned = root / "fd4c151a749f3ab4" / "codex.exe"
            versioned.parent.mkdir(parents=True, exist_ok=True)
            versioned.write_text("", encoding="utf-8")
            with mock.patch.dict(daemon.os.environ, {"LOCALAPPDATA": tmp}):
                self.assertEqual(Path(daemon.resolve_codex_exe()), versioned)

    def test_the_newest_versioned_cli_wins(self):
        with TemporaryDirectory() as tmp:
            root = self._binroot(tmp)
            older = root / "aaaaaaaaaaaaaaaa" / "codex.exe"
            newer = root / "bbbbbbbbbbbbbbbb" / "codex.exe"
            for path, offset in ((older, -100), (newer, 0)):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
                stamp = time.time() + offset
                os.utime(path, (stamp, stamp))
            with mock.patch.dict(daemon.os.environ, {"LOCALAPPDATA": tmp}):
                self.assertEqual(Path(daemon.resolve_codex_exe()), newer)

    def test_the_alias_is_the_fallback_when_nothing_else_exists(self):
        with TemporaryDirectory() as tmp:
            root = self._binroot(tmp)
            alias = root / "codex.exe"
            alias.write_text("", encoding="utf-8")
            with mock.patch.dict(daemon.os.environ, {"LOCALAPPDATA": tmp}):
                self.assertEqual(Path(daemon.resolve_codex_exe()), alias)

    def test_the_shipped_default_is_not_the_stale_alias(self):
        binroot = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
        if not any(binroot.glob("*/codex.exe")):
            self.skipTest("this machine has no versioned cli")
        self.assertNotEqual(Path(daemon.DEFAULT_CODEX_EXE).parent, binroot)


class OutputLanguageTest(unittest.TestCase):
    """The operator reads these rounds, so the prose must be Chinese."""

    def _prompt(self) -> str:
        return daemon.compose_prompt(
            guidelines="", capability_excerpt="", library_index="", summary="",
            verdict="", ssh_command="ssh fake", run_root="/mnt/fake/run",
            drafts_dir="/tmp/drafts", write_idx=0,
        )

    def test_chinese_output_is_requested(self):
        prompt = self._prompt()
        self.assertIn("输出语言", prompt)
        self.assertIn("中文", prompt)

    def test_identifiers_are_told_to_stay_english(self):
        self.assertIn("代码标识符保持英文原样", self._prompt())

    def test_the_server_boundary_is_stated(self):
        prompt = self._prompt()
        self.assertIn("远端硬边界", prompt)
        self.assertIn("/mnt/nas/gezuhao/xinghanbo", prompt)
        self.assertIn("一律不允许", prompt)

    def test_the_queue_message_asks_for_chinese_too(self):
        message = daemon.queue_message(
            event_id="e", write_idx=0, prompt_path=Path("prompt.md"),
            drafts_dir=Path("drafts"), result_path=Path("result.json"),
        )
        self.assertIn("中文", message)
        self.assertIn("/mnt/nas/gezuhao/xinghanbo", message)


class BoundaryAuditTest(unittest.TestCase):
    """A prompt is not a security boundary; every round records what it ran."""

    def test_reads_inside_the_tree_are_clean(self):
        audit = daemon.audit_commands([
            "ssh root@host \"cat /mnt/nas/gezuhao/xinghanbo/logs/run/status.txt\"",
            "ssh root@host \"find /mnt/nas/gezuhao/xinghanbo/logs/run -maxdepth 2\"",
        ])
        self.assertTrue(audit["clean"])
        self.assertEqual(audit["outside_paths"], [])

    def test_a_write_outside_the_tree_is_a_violation(self):
        audit = daemon.audit_commands([
            "ssh root@host \"rm -rf /mnt/other/data\"",
        ])
        self.assertFalse(audit["clean"])
        self.assertIn("/mnt/other/data", audit["outside_writes"])

    def test_a_read_outside_the_tree_is_reported_but_not_a_violation(self):
        audit = daemon.audit_commands([
            "ssh root@host \"cat /mnt/other/data/notes.txt\"",
        ])
        self.assertTrue(audit["clean"])
        self.assertIn("/mnt/other/data/notes.txt", audit["outside_paths"])

    def test_dev_null_is_not_a_violation(self):
        audit = daemon.audit_commands(["ssh root@host \"cmd > /dev/null 2>&1\""])
        self.assertTrue(audit["clean"])

    def test_commands_are_read_from_a_rollout(self):
        with TemporaryDirectory() as tmp:
            rollout = Path(tmp) / "rollout-x.jsonl"
            rollout.write_text(
                "\n".join([
                    json.dumps({"type": "response_item", "timestamp": "2026-09-11T11:00:00Z",
                                "payload": {"type": "function_call", "name": "exec_command",
                                            "arguments": json.dumps({"cmd": "ssh a b"})}}),
                    json.dumps({"type": "response_item", "timestamp": "2026-09-11T11:05:00Z",
                                "payload": {"type": "function_call", "name": "exec_command",
                                            "arguments": json.dumps({"cmd": "ssh c d"})}}),
                    "not json at all",
                ]),
                encoding="utf-8",
            )
            everything = daemon.collect_agent_commands(rollout)
            since = datetime.datetime.fromisoformat("2026-09-11T11:02:00+00:00").timestamp()
            recent = daemon.collect_agent_commands(rollout, since_epoch=since)
        self.assertEqual(everything, ["ssh a b", "ssh c d"])
        self.assertEqual(recent, ["ssh c d"])


LAUNCHER_SAMPLE = """#!/usr/bin/env bash
# Rendered by start_cell.py - do not edit on the server.
set -u
WORKSPACE=/mnt/nas/gezuhao/xinghanbo
REPO=/mnt/nas/gezuhao/xinghanbo/code_snapshots/openvla-oft_1cb091e
PY=/mnt/nas/gezuhao/xinghanbo/envs/openpi_jax_py311/bin/python
RUN_ROOT=/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task_task07_seed51_65_mining
LABEL=task07
BASE_DIR=$RUN_ROOT/baseline_${LABEL}_seed51_65
MINE_DIR=$RUN_ROOT/mine

export LIBERO_PYTHONPATH_ROOT="$WORKSPACE/LIBERO-PRO"
export LIBERO_CONFIG_PATH="$RUN_ROOT/libero_config"
export PYTHONPATH="$REPO:$WORKSPACE/LIBERO-PRO:$WORKSPACE/openpi/src:${PYTHONPATH:-}"
export MUJOCO_GL=egl

mkdir -p "$RUN_ROOT" "$MINE_DIR" "$LIBERO_CONFIG_PATH"
cat > "$LIBERO_CONFIG_PATH/config.yaml" <<YAML
benchmark_root: $WORKSPACE/LIBERO-PRO/libero/libero
YAML
nohup "$PY" "$REPO/scripts/recovery/skill_pipeline/run_mining_lane.py" >> log 2>&1 &
"""


class LauncherEnvTest(unittest.TestCase):
    """Two resumes died on this: the env the lane inherits decides which LIBERO loads."""

    def test_the_preamble_keeps_assignments_and_exports(self):
        body = daemon.parse_launcher_env(LAUNCHER_SAMPLE)
        self.assertIn("WORKSPACE=/mnt/nas/gezuhao/xinghanbo", body)
        self.assertIn("RUN_ROOT=", body)
        self.assertIn('export PYTHONPATH="$REPO:$WORKSPACE/LIBERO-PRO', body)
        self.assertIn("export MUJOCO_GL=egl", body)

    def test_the_scan_stops_at_the_scripts_real_work(self):
        body = daemon.parse_launcher_env(LAUNCHER_SAMPLE)
        self.assertNotIn("mkdir", body)
        self.assertNotIn("benchmark_root", body)
        self.assertNotIn("nohup", body)

    def test_set_lines_and_comments_are_skipped_not_fatal(self):
        """The awk version exited on `set -u` and truncated the file to empty."""

        body = daemon.parse_launcher_env(LAUNCHER_SAMPLE)
        self.assertNotIn("set -u", body)
        self.assertNotIn("# Rendered by", body)
        self.assertTrue(body.startswith("WORKSPACE="))

    def test_an_empty_launcher_yields_an_empty_body(self):
        self.assertEqual(daemon.parse_launcher_env(""), "")


class ResumeEnvironmentTest(unittest.TestCase):
    """A resumed lane must not import a different LIBERO than the launcher did."""

    ENV = 'WORKSPACE=/mnt/fake/root\nexport PYTHONPATH="$WORKSPACE/LIBERO-PRO"\n'

    def _command(self) -> str:
        return daemon.resume_command(
            run_root="/mnt/fake/root/logs/run",
            repo="/mnt/fake/root/repo",
            argv="python run_mining_lane.py --mine_dir /mnt/fake/root/logs/run/mine",
            log="/mnt/fake/root/logs/run/mine/lane_logs/resume_w0_codex.log",
            env_body=self.ENV,
        )

    def test_the_environment_is_written_as_a_heredoc(self):
        command = self._command()
        self.assertIn("cat > /mnt/fake/root/logs/run/mine/lane_env.sh <<'CODEX_LANE_ENV'", command)
        self.assertIn("WORKSPACE=/mnt/fake/root", command)
        self.assertIn("CODEX_LANE_ENV", command)

    def test_a_missing_pythonpath_is_announced_in_the_lane_log(self):
        command = self._command()
        self.assertIn("grep -q PYTHONPATH", command)
        self.assertIn("WARNING", command)

    def test_the_environment_is_exported_not_merely_read(self):
        command = self._command()
        self.assertIn("set -a", command)
        self.assertIn("set +a", command)

    def test_the_resume_lands_inside_the_run_root(self):
        command = self._command()
        self.assertIn("/mnt/fake/root/logs/run/mine/lane_env.sh", command)
        self.assertNotIn("/tmp/", command)

    def test_the_lane_is_still_detached_and_logged(self):
        command = self._command()
        self.assertIn("nohup", command)
        self.assertIn("& echo $!", command)
        self.assertIn("flock -n", command)
        self.assertIn("mining_lane.exit_code", command)
        self.assertIn("resume_w0_codex.log", command)


if __name__ == "__main__":
    unittest.main()
