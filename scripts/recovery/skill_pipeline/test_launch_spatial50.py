import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import launch_spatial50 as run


class ProtocolTests(unittest.TestCase):
    def test_command_preserves_natural_protocol(self):
        cmd = run.command({'task': 3, 'pack': '/frozen/C3'}, Path('/attempt'), 17, 33)
        def value(flag):
            return cmd[cmd.index(flag) + 1]
        self.assertEqual(value('--episode_seed_start'), '1')
        self.assertEqual(value('--episode_index_start'), '17')
        self.assertEqual(value('--num_trials_per_task'), '33')
        self.assertEqual(value('--seed'), '90')
        self.assertEqual(value('--max_recovery_calls'), '2')
        self.assertEqual(value('--max_recovery_steps'), '200')
        self.assertNotIn('--force_recovery_query', cmd)

    def sample(self, root, seed=8, error=None):
        d = root/'attempts/C3_t03/session_from00'
        e = d/'run/task03/ep07'
        e.mkdir(parents=True)
        (d/'command.json').write_text(json.dumps({'launcher_sha256': run.digest(run.__file__)}))
        (e/'episode.json').write_text(json.dumps({'seed': seed, 'init_state_idx': 7, 'success': False}))
        (e/'video.mp4').write_bytes(b'test')
        (e/'query_trace.jsonl').write_text('{}\n')
        (e/'recovery_trace.jsonl').write_text(json.dumps({'error': error})+'\n')

    def test_complete_failures_are_valid_samples(self):
        with tempfile.TemporaryDirectory() as t, patch.object(run, 'O', Path(t)):
            self.sample(Path(t))
            self.assertEqual(list(run.completed({'id': 'C3_t03', 'task': 3})), [7])

    def test_identity_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as t, patch.object(run, 'O', Path(t)):
            self.sample(Path(t), seed=9)
            with self.assertRaises(AssertionError):
                run.completed({'id': 'C3_t03', 'task': 3})

    def test_infrastructure_failure_not_robot_failure(self):
        with tempfile.TemporaryDirectory() as t, patch.object(run, 'O', Path(t)):
            self.sample(Path(t), error='runner_failed: missing runtime')
            with self.assertRaises(AssertionError):
                run.completed({'id': 'C3_t03', 'task': 3})


if __name__ == '__main__':
    unittest.main()
