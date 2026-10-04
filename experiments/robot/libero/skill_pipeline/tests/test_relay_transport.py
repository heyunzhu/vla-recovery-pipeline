import subprocess
import unittest
from unittest.mock import patch
from scripts.recovery.skill_pipeline.relay_visual_policy_detector import run_transport


class RelayTransportTest(unittest.TestCase):
    def test_transient_transport_error_retries_then_succeeds(self):
        result = subprocess.CompletedProcess(['ssh'], 0, stdout='READY')
        with patch('subprocess.run', side_effect=[subprocess.CalledProcessError(255, ['ssh']), result]) as run, patch('time.sleep') as sleep:
            self.assertIs(run_transport(['ssh'], capture_output=True, text=True), result)
            self.assertEqual(run.call_count, 2)
            self.assertTrue(run.call_args.kwargs['check'])
            sleep.assert_called_once_with(2)

    def test_remote_command_error_is_not_retried(self):
        with patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, ['ssh'])) as run, patch('time.sleep') as sleep:
            with self.assertRaises(subprocess.CalledProcessError):
                run_transport(['ssh'])
            self.assertEqual(run.call_count, 1)
            sleep.assert_not_called()

    def test_repeated_transport_failure_is_bounded(self):
        with patch('subprocess.run', side_effect=subprocess.CalledProcessError(255, ['scp'])) as run, patch('time.sleep') as sleep:
            with self.assertRaises(subprocess.CalledProcessError):
                run_transport(['scp'])
            self.assertEqual(run.call_count, 3)
            self.assertEqual(sleep.call_count, 2)
