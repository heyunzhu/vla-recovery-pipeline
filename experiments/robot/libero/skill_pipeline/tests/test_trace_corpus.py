from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.trace_corpus import archive_run_for_offline_scan


class TraceCorpusTests(unittest.TestCase):
    def test_archive_run_copies_only_lightweight_trace_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            run = root / "logs" / "sample_run"
            ep = run / "lane_tasks47_gpu0_deadbee" / "task47" / "ep00"
            ep.mkdir(parents=True)
            (run / "resolved_spec.json").write_text(json.dumps({"name": "sample"}), encoding="utf-8")
            (run / "git_head.txt").write_text("deadbee\n", encoding="utf-8")
            (ep / "episode.json").write_text(
                json.dumps({"success": True, "task_id_1based": 47, "episode_idx": 0, "seed": 90}),
                encoding="utf-8",
            )
            (ep / "query_trace.jsonl").write_text(
                json.dumps({"query_idx": 0, "target_name": "bowl_1_main"}) + "\n",
                encoding="utf-8",
            )
            (ep / "recovery_trace.jsonl").write_text(
                json.dumps({"skill_id": "bowl_pick_empty_close_stall"}) + "\n",
                encoding="utf-8",
            )
            (ep / "video.mp4").write_bytes(b"large-video-placeholder")

            annotated_ep = run / "lane_tasks47_gpu0_deadbee_annotated_recovery_marked" / "task47" / "ep01"
            annotated_ep.mkdir(parents=True)
            (annotated_ep / "episode.json").write_text(json.dumps({"success": False}), encoding="utf-8")

            manifest = archive_run_for_offline_scan(
                run,
                repo_root=repo,
                corpus_root=repo / "analysis_outputs" / "offline_trigger_corpus",
                name="sample_run",
            )

            corpus = Path(manifest["corpus_dir"])
            copied_ep = corpus / "lane_tasks47_gpu0_deadbee" / "task47" / "ep00"
            self.assertEqual(manifest["overall"]["episodes"], 1)
            self.assertEqual(manifest["overall"]["queries"], 1)
            self.assertTrue((copied_ep / "episode.json").exists())
            self.assertTrue((copied_ep / "query_trace.jsonl").exists())
            self.assertTrue((copied_ep / "recovery_trace.jsonl").exists())
            self.assertFalse((copied_ep / "video.mp4").exists())
            self.assertTrue((corpus / "_run_metadata" / "resolved_spec.json").exists())
            self.assertTrue((corpus / "manifest.json").exists())

    def test_overwrite_drops_stale_episode_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            run = root / "logs" / "sample_run"
            ep = run / "lane_tasks47_gpu0_deadbee" / "task47" / "ep00"
            ep.mkdir(parents=True)
            (ep / "episode.json").write_text(json.dumps({"success": True}), encoding="utf-8")

            first = archive_run_for_offline_scan(run, repo_root=repo, name="sample_run")
            stale_ep = Path(first["corpus_dir"]) / "lane_tasks47_gpu0_deadbee" / "task47" / "ep99"
            stale_ep.mkdir(parents=True)
            (stale_ep / "episode.json").write_text(json.dumps({"success": False}), encoding="utf-8")

            second = archive_run_for_offline_scan(run, repo_root=repo, name="sample_run")
            self.assertFalse((Path(second["corpus_dir"]) / "lane_tasks47_gpu0_deadbee" / "task47" / "ep99").exists())
            self.assertEqual(second["overall"]["episodes"], 1)

    def test_archive_accepts_generated_task_directories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "repo"
            ep = root / "run" / "libero_90_gen_t078_caddy_compartment_deadbeef" / "ep00"
            ep.mkdir(parents=True)
            (ep / "episode.json").write_text(
                json.dumps(
                    {
                        "generated_task_id": "libero_90_gen_t078_caddy_compartment_deadbeef",
                        "success": False,
                    }
                ),
                encoding="utf-8",
            )
            (ep / "query_trace.jsonl").write_text("{}\n", encoding="utf-8")

            manifest = archive_run_for_offline_scan(root / "run", repo_root=repo, name="generated")

            self.assertEqual(manifest["overall"]["episodes"], 1)
            self.assertEqual(
                manifest["episodes"][0]["task"],
                "libero_90_gen_t078_caddy_compartment_deadbeef",
            )


if __name__ == "__main__":
    unittest.main()
