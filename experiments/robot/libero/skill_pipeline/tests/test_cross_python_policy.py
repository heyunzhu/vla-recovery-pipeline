import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from experiments.robot.libero.skill_pipeline.cross_python_policy import CrossPythonPolicyAdapter


class CrossPythonPolicyTest(unittest.TestCase):
    def observation(self, prompt="smoke"):
        return {"observation/image": np.full((8, 8, 3), 7, np.uint8),
                "observation/wrist_image": np.full((8, 8, 3), 11, np.uint8),
                "observation/state": np.arange(8, dtype=np.float32), "prompt": prompt}

    def adapter(self, root, timeout=5, worker=None):
        script = Path(__file__).resolve().parents[5] / "scripts/recovery/skill_pipeline/smoke_cross_python_policy.py"
        return CrossPythonPolicyAdapter(python=sys.executable, config_name="test", checkpoint_dir="unused",
            ipc_root=root, startup_timeout_s=5, infer_timeout_s=timeout, worker_script=worker or script)

    def test_real_process_roundtrip_and_clean_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = self.adapter(tmp)
            try:
                policy.reset()
                output = policy.infer(self.observation())
                np.testing.assert_array_equal(output["actions"][0], [7, 11, 0, 5, 0, 0, 1])
                self.assertEqual(output["actions_log_var"].shape, (2, 7))
                self.assertFalse(policy.worker_metadata["policy_weights_loaded"])
                self.assertEqual(policy.worker_metadata["cuda_visible_devices"], "")
            finally:
                policy.close()
            self.assertEqual(policy.process.returncode, 0)
            policy.close()

    def test_invalid_input_does_not_consume_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = self.adapter(tmp)
            try:
                observation = self.observation()
                observation["oracle_scene"] = {}
                with self.assertRaisesRegex(ValueError, "only images"):
                    policy.infer(observation)
                self.assertEqual(policy.sequence, 0)
                self.assertEqual(policy.infer(self.observation())["actions"].shape, (2, 7))
            finally:
                policy.close()

    def test_worker_failure_stops_process_without_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = self.adapter(tmp)
            try:
                with self.assertRaisesRegex(RuntimeError, "intentional fake policy error"):
                    policy.infer(self.observation("raise"))
                self.assertIsNotNone(policy.process.poll())
            finally:
                policy.close()

    def test_inference_timeout_stops_hung_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = self.adapter(tmp, timeout=0.15)
            try:
                with self.assertRaises(TimeoutError):
                    policy.infer(self.observation("hang"))
                self.assertIsNotNone(policy.process.poll())
            finally:
                policy.close()

    def test_nonfinite_worker_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = self.adapter(tmp)
            try:
                with self.assertRaisesRegex(ValueError, "invalid actions"):
                    policy.infer(self.observation("invalid"))
                self.assertIsNotNone(policy.process.poll())
            finally:
                policy.close()

    def test_startup_timeout_stops_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = Path(tmp) / "hang.py"
            worker.write_text("import time\ntime.sleep(30)\n")
            with self.assertRaises(TimeoutError):
                CrossPythonPolicyAdapter(python=sys.executable, config_name="test", checkpoint_dir="unused",
                    ipc_root=tmp, worker_script=worker, startup_timeout_s=0.15)


if __name__ == "__main__":
    unittest.main()
