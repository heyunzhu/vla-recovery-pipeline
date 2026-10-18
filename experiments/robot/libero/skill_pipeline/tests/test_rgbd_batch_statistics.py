import json
from pathlib import Path
import tempfile
import unittest

from scripts.recovery.skill_pipeline.summarize_rgbd_task_batch import classify_artifacts, summarize
from scripts.recovery.skill_pipeline.run_rgbd_expansion_batch import case_finished, preserve_interrupted_case


class RGBDBatchStatisticsTest(unittest.TestCase):
    def test_resume_keeps_completed_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/"case/visual";p.mkdir(parents=True)
            (p/"exitcode.txt").write_text("1")
            self.assertTrue(case_finished(root, {"label":"case"}))

    def test_resume_archives_interruption_without_losing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/"case/oracle";p.mkdir(parents=True)
            (p/"driver.log").write_text("partial run")
            record={"label":"case","oracle_run":{"success":False}}
            preserve_interrupted_case(root,record)
            archive=Path(record["interrupted_attempts"][0])
            self.assertEqual((archive/"oracle/driver.log").read_text(),"partial run")
            self.assertFalse((root/"case").exists())
            self.assertNotIn("oracle_run",record)

    def test_feasible_plan_is_not_complete_recovery(self):
        stage, _ = classify_artifacts(solver={"feasible": True}, visual_exit=1,
            logs="ValueError: current RGB-D bottle tracking unresolved")
        self.assertEqual(stage, "execution_tracking")

    def test_recovery_success_requires_independent_evaluation(self):
        stage, _ = classify_artifacts(replay={"recovery_success": True,
            "final_simulator_success_for_evaluation": False}, visual_exit=0)
        self.assertEqual(stage, "goal_verification")

    def test_actual_binding_refusal_precedes_secondary_stopiteration(self):
        stage, reason = classify_artifacts(binding={"status": "refused", "reason": "goal_not_observed"},
            logs="StopIteration", visual_exit=1)
        self.assertEqual((stage, reason), ("detection", "goal_not_observed"))

    def test_ambiguous_candidates_are_not_counted_as_missing_detection(self):
        stage, _ = classify_artifacts(binding={"status": "refused", "reason": "goal_ambiguous"}, visual_exit=1)
        self.assertEqual(stage, "binding")

    def test_unsupported_geometry_is_separate_from_fitting(self):
        stage, _ = classify_artifacts(logs="bottle fitting requires a visually nominated bottle", visual_exit=1)
        self.assertEqual(stage, "geometry_support")

    def test_language_failure_is_recorded(self):
        stage, _ = classify_artifacts(logs="ValueError: unsupported object phrase: bowl on cabinet", visual_exit=1)
        self.assertEqual(stage, "language")

    def test_partial_artifacts_do_not_mark_running_case_complete(self):
        stage, _ = classify_artifacts(binding={"status": "refused", "reason": "goal_not_observed"})
        self.assertEqual(stage, "pending")

    def test_all_ten_failures_remain_in_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = []
            for i in range(10):
                label = f"task{i}"
                rows.append(dict(label=label,suite="example",task_1based=i+1,episode_idx=0,
                    seed=1,init_state_idx=0,language="Put the bottle on the plate",
                    oracle_run={"success": True,"exitcode": 0}))
                p = root/label/"visual"
                p.mkdir(parents=True)
                (p/"exitcode.txt").write_text("1")
                (p/"driver.log").write_text("unsupported task language")
            (root/"batch_results.json").write_text(json.dumps(rows))
            report = summarize(root)
        self.assertEqual(report["selected_task_count"], 10)
        self.assertEqual(report["completed_task_count"], 10)
        self.assertEqual(report["visual_failure_or_unavailable_count"], 10)
        self.assertEqual(report["oracle_success_count"], 10)
        self.assertEqual(report["first_blocker_counts"], {"language": 10})

if __name__ == "__main__": unittest.main()
