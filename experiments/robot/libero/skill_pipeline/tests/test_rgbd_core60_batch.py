import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.recovery.skill_pipeline.run_rgbd_core60_batch import run_case, failure_stage


class Core60BatchTest(unittest.TestCase):
    def test_completed_failure_is_not_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);case=run/'cases/example';case.mkdir(parents=True)
            result=dict(valid_episode=True,success=False,case_id='example')
            (case/'finished.json').write_text(json.dumps(result))
            with patch('subprocess.Popen',side_effect=AssertionError('must not rerun')):
                self.assertEqual(run_case(dict(case_id='example'),run,run,1),result)

    def test_launch_error_is_saved_without_becoming_task_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);record=dict(case_id='example')
            result=run_case(record,run,run,1)
            self.assertFalse(result['valid_episode'])
            self.assertIsNone(result['success'])
            self.assertIn('FileNotFoundError',result['launcher_error'])
            self.assertEqual(json.loads((run/'cases/example/finished.json').read_text()),result)

    def test_first_failure_is_not_hidden_by_later_traceback(self):
        self.assertEqual(failure_stage('ValueError: visual binding refused: goal_not_observed\nTraceback'),'binding_detection')
        self.assertEqual(failure_stage('unsupported task language'),'unsupported_language')
        self.assertEqual(failure_stage('CUDA out of memory\nTraceback'),'resource_oom')


if __name__=='__main__':unittest.main()
