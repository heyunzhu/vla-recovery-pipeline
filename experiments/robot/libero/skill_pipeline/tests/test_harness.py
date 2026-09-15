from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.robot.libero.skill_pipeline.harness.benchmark_registry import load_benchmark
from experiments.robot.libero.skill_pipeline.harness.collector import summarize_run
from experiments.robot.libero.skill_pipeline.harness.comparator import compare_summaries
from experiments.robot.libero.skill_pipeline.harness.gates import evaluate_gates
from experiments.robot.libero.skill_pipeline.harness.launcher import HarnessPaths, prepare_run
from experiments.robot.libero.skill_pipeline.harness.report import render_markdown, write_report
from experiments.robot.libero.skill_pipeline.harness.run_spec import HarnessSpec, parse_task_ids, split_tasks


class HarnessSpecTests(unittest.TestCase):
    def test_parse_task_ids_and_split(self):
        self.assertEqual(parse_task_ids("47-49, 52,49"), [47, 48, 49, 52])
        self.assertEqual(parse_task_ids(["10-11", 14]), [10, 11, 14])
        self.assertEqual(split_tasks(list(range(47, 55)), [0, 1, 2, 3]), [(0, [47, 48]), (1, [49, 50]), (2, [51, 52]), (3, [53, 54])])

    def test_load_registered_benchmark(self):
        spec = load_benchmark("libero90_smoke")
        self.assertEqual(spec.task_suite_name, "libero_90")
        self.assertEqual(spec.tasks, list(range(47, 55)))
        self.assertTrue(spec.real_cutamp.serialize_trajectories)
        self.assertEqual(spec.skill_pack, "libero90_legacy")
        self.assertEqual(spec.max_recovery_steps, 280)
        self.assertTrue(spec.archive_offline_scan_corpus)
        self.assertTrue(spec.offline_skill_scan)

        known_good = load_benchmark("libero90_online_recovery_known_good")
        self.assertEqual(known_good.task_suite_name, "libero_90")
        self.assertEqual(known_good.tasks, [74, 75])
        self.assertEqual(known_good.skill_pack, "libero90_legacy")
        self.assertEqual(known_good.max_recovery_steps, 280)
        self.assertTrue(known_good.save_video)
        self.assertTrue(known_good.export_annotated)
        self.assertTrue(known_good.real_cutamp.serialize_trajectories)
        self.assertEqual(known_good.real_cutamp.static_context_collision_mode, "all")

        generated = load_benchmark("generated_validation_generalization_pi0_known_good")
        self.assertEqual(generated.generated_split, "validation")
        self.assertIn("libero90_generated_v1_envfiltered_304", generated.generated_benchmark_dir)
        self.assertEqual(generated.tasks, [1, 3, 4, 10, 12, 15, 18, 19, 22, 25, 29, 35])

        scratch_baseline = load_benchmark("generated_phase1_train_scratch_baseline_pi0_known_good")
        self.assertEqual(scratch_baseline.skills, "off")
        self.assertFalse(scratch_baseline.recovery)
        self.assertEqual(scratch_baseline.skill_pack, "generated_v1")

    def test_skill_enabled_spec_requires_explicit_pack(self):
        with self.assertRaisesRegex(ValueError, "require skill_pack or skill_index"):
            HarnessSpec.from_mapping({"name": "unsafe", "tasks": [1], "skills": "online"})

        spec = HarnessSpec.from_mapping({"name": "baseline", "tasks": [1], "skills": "off"})
        self.assertEqual(spec.skills, "off")


class HarnessLauncherTests(unittest.TestCase):
    def test_prepare_run_writes_reproducible_script(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "openvla-oft"
            repo.mkdir()
            pack = repo / "skill_packs" / "generated_v1"
            (pack / "skills").mkdir(parents=True)
            (pack / "skills" / "_index.yaml").write_text("online: []\n", encoding="utf-8")
            (pack / "pack.yaml").write_text(
                "name: generated_v1\nskills_dir: skills\nskill_index: skills/_index.yaml\n",
                encoding="utf-8",
            )
            paths = HarnessPaths.from_workspace(root, repo_root=repo, python_bin=root / "env/bin/python")
            spec = HarnessSpec.from_mapping(
                {
                    "name": "smoke",
                    "tasks": "47-50",
                    "gpus": [0, 1],
                    "save_video": True,
                    "skills": "online",
                    "skill_pack": "generated_v1",
                    "diagnostic_signals": {"enabled": True, "statuses": "shadow"},
                    "real_cutamp": {"enabled": True, "serialize_trajectories": True},
                }
            )
            plan = prepare_run(spec, paths, run_dir=root / "logs/run")
            script = Path(plan["launch_script"]).read_text(encoding="utf-8")
            self.assertIn("LIBERO_CONFIG_PATH", script)
            self.assertIn("LIBERO_PYTHONPATH_ROOT=", script)
            self.assertIn("LIBERO_src", script)
            self.assertIn("--enable_skills", script)
            self.assertIn("SKILL_INDEX=", script)
            self.assertIn("SKILL_PACK=", script)
            self.assertIn("PREDICATE_REGISTRY=", script)
            self.assertIn("DIAGNOSTIC_SIGNAL_STATUSES=shadow", script)
            self.assertIn("skill_packs/generated_v1/skills/_index.yaml", script.replace("\\", "/"))
            self.assertIn("--diagnostic_signal_statuses shadow", script)
            self.assertIn('--skill-pack "${SKILL_PACK}"', script)
            self.assertIn('--diagnostic-signal-statuses "${DIAGNOSTIC_SIGNAL_STATUSES}"', script)
            self.assertIn("--real_cutamp_serialize_trajectories", script)
            self.assertIn("preflight_real_cutamp_runner", script)
            self.assertIn("real_cutamp_preflight.log", script)
            self.assertIn("PREFLIGHT_MISSING", script)
            self.assertIn("third_party/cuTAMP", script)
            self.assertIn("third_party/curobo", script)
            self.assertIn("archive_offline_scan_corpus.py", script)
            self.assertIn("scan_skill_triggers.py", script)
            self.assertIn('for pidfile in "${PID_DIR}"/*.pid', script)
            self.assertNotIn('for pidfile in "${BASE}"/*.pid', script)
            self.assertTrue((root / "logs/run/resolved_spec.json").exists())

    def test_prepare_run_can_override_libero_pythonpath_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "openvla-oft"
            repo.mkdir()
            paths = HarnessPaths.from_workspace(
                root,
                repo_root=repo,
                python_bin=root / "env/bin/python",
                libero_config_path=root / "libero_config_pro",
                libero_pythonpath_root=root / "LIBERO-PRO",
            )
            spec = HarnessSpec.from_mapping(
                {
                    "name": "libero-pro",
                    "suite": "libero_pro",
                    "tasks": [1],
                    "gpus": [0],
                    "skills": "off",
                    "recovery": False,
                    "real_cutamp": False,
                }
            )
            plan = prepare_run(spec, paths, run_dir=root / "logs/libero-pro")
            script = Path(plan["launch_script"]).read_text(encoding="utf-8")
            self.assertIn("LIBERO_CONFIG=", script)
            self.assertIn("libero_config_pro", script)
            self.assertIn("LIBERO_PYTHONPATH_ROOT=", script)
            self.assertIn("LIBERO-PRO", script)

    def test_prepare_run_passes_generated_benchmark_selection(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = root / "openvla-oft"
            repo.mkdir()
            paths = HarnessPaths.from_workspace(root, repo_root=repo, python_bin=root / "env/bin/python")
            spec = HarnessSpec.from_mapping(
                {
                    "name": "generated",
                    "tasks": [1, 3],
                    "generated_benchmark_dir": "benchmarks/libero90_generated_v1_envfiltered_304",
                    "generated_split": "validation",
                    "gpus": [0],
                    "skills": "off",
                    "real_cutamp": False,
                }
            )
            plan = prepare_run(spec, paths, run_dir=root / "logs/generated")
            script = Path(plan["launch_script"]).read_text(encoding="utf-8")
            self.assertIn("--generated_benchmark_dir benchmarks/libero90_generated_v1_envfiltered_304", script)
            self.assertIn("--generated_split validation", script)
            self.assertIn('--generated_task_ids "${tasks}"', script)


class HarnessCollectorTests(unittest.TestCase):
    def test_summarize_run_and_gates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lane = root / "lane_tasks47_gpu0_deadbee"
            ep = lane / "task47/ep00"
            ep.mkdir(parents=True)
            (ep / "episode.json").write_text(
                json.dumps({"success": True, "recovery_calls": 1}), encoding="utf-8"
            )
            (ep / "recovery_trace.jsonl").write_text(
                json.dumps({"skill_id": "bowl_pick"}) + "\n" + json.dumps({"selected_skill_id": "bowl_pick"}) + "\n",
                encoding="utf-8",
            )
            (ep / "video.mp4").write_bytes(b"")
            ann = Path(str(lane) + "_annotated_recovery_marked") / "task47/ep00"
            ann.mkdir(parents=True)
            (ann / "video_annotated_recovery.mp4").write_bytes(b"")
            (root / f"{lane.name}.exitcode").write_text("0\n", encoding="utf-8")

            summary = summarize_run(root)
            self.assertEqual(summary["overall"]["episodes"], 1)
            self.assertEqual(summary["overall"]["success"], 1)
            self.assertEqual(summary["overall"]["videos"], 1)
            self.assertEqual(summary["overall"]["annotated_videos"], 1)
            self.assertEqual(summary["skill_episode_counts"], {"bowl_pick": 1})
            self.assertEqual(summary["skill_event_counts"], {"bowl_pick": 2})
            self.assertEqual(evaluate_gates(summary, {"min_overall_success_rate": 1.0})["status"], "pass")
            self.assertIn("| task47 | 1/1 |", render_markdown(summary))

            (root / "resolved_spec.json").write_text(
                json.dumps({"gates": {"min_overall_success_rate": 1.0}}), encoding="utf-8"
            )
            outputs = write_report(root)
            gate_result = json.loads(Path(outputs["gates_json"]).read_text(encoding="utf-8"))
            self.assertEqual(gate_result["gates"], {"min_overall_success_rate": 1.0})

    def test_summarize_generated_task_directories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lane = root / "generated_validation_tasks01_03_gpu0_deadbee"
            task = lane / "libero_90_gen_t014_pick_place_on_surface_6d0267cf"
            ep = task / "ep00"
            ep.mkdir(parents=True)
            (ep / "episode.json").write_text(
                json.dumps({"success": False, "recovery_calls": 1}), encoding="utf-8"
            )
            (ep / "recovery_trace.jsonl").write_text(
                json.dumps({"selected_skill_id": "bowl_pick"}) + "\n",
                encoding="utf-8",
            )
            (ep / "video.mp4").write_bytes(b"")
            ann = Path(str(lane) + "_annotated_recovery_marked") / task.name / "ep00"
            ann.mkdir(parents=True)
            (ann / "video_annotated_recovery.mp4").write_bytes(b"")
            (root / f"{lane.name}.exitcode").write_text("0\n", encoding="utf-8")

            summary = summarize_run(root)
            self.assertEqual(summary["overall"]["episodes"], 1)
            self.assertEqual(summary["overall"]["success"], 0)
            self.assertEqual(summary["overall"]["videos"], 1)
            self.assertEqual(summary["overall"]["annotated_videos"], 1)
            self.assertEqual(summary["tasks"][0]["task"], task.name)
            self.assertEqual(summary["skill_episode_counts"], {"bowl_pick": 1})

    def test_compare_summaries(self):
        baseline = {"overall": {"success_rate": 0.25}, "tasks": [{"task": "task47", "success_rate": 0.2}]}
        candidate = {"overall": {"success_rate": 0.75}, "tasks": [{"task": "task47", "success_rate": 0.6}]}
        result = compare_summaries(baseline, candidate)
        self.assertAlmostEqual(result["overall"]["delta"], 0.5)
        self.assertAlmostEqual(result["tasks"][0]["delta"], 0.4)


if __name__ == "__main__":
    unittest.main()
