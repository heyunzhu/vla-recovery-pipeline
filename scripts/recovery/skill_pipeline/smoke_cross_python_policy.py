"""Transport-only smoke: fake policy, no checkpoint loading or GPU work."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

import numpy as np


class TransportTestPolicy:
    def reset(self):
        pass

    def infer(self, observation):
        prompt = observation["prompt"]
        if prompt == "raise":
            raise RuntimeError("intentional fake policy error")
        if prompt == "hang":
            time.sleep(30)
        image = observation["observation/image"]
        wrist = observation["observation/wrist_image"]
        state = observation["observation/state"]
        # Encode transported values so the parent can verify the payload.
        values = np.array([image[0, 0, 0], wrist[0, 0, 0], state[0], len(prompt), 0, 0, 1.])
        if prompt == "invalid":
            values[0] = np.nan
        return {"actions": np.tile(values, (2, 1)), "actions_log_var": np.zeros((2, 7))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ipc-dir", type=Path)
    parser.add_argument("--config-name")
    parser.add_argument("--checkpoint-dir")
    parser.add_argument("--worker-python")
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    if args.ipc_dir is not None:
        from cross_python_policy_worker import serve_policy
        serve_policy(TransportTestPolicy(), args.ipc_dir, metadata={
            "scope": "transport_only_fake_policy", "policy_weights_loaded": False,
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")})
        return
    if not args.worker_python or args.out_dir is None:
        parser.error("parent mode requires --worker-python and --out-dir")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.cross_python_policy import CrossPythonPolicyAdapter
    policy = CrossPythonPolicyAdapter(python=args.worker_python, config_name="transport_test",
        checkpoint_dir="unused", ipc_root=args.out_dir, worker_script=__file__,
        startup_timeout_s=30, infer_timeout_s=10)
    try:
        policy.reset()
        observation = {"observation/image": np.full((8, 8, 3), 7, np.uint8),
                       "observation/wrist_image": np.full((8, 8, 3), 11, np.uint8),
                       "observation/state": np.arange(8, dtype=np.float32), "prompt": "smoke"}
        output = policy.infer(observation)
        assert np.array_equal(output["actions"][0], [7, 11, 0, 5, 0, 0, 1])
        assert output["actions"].shape == (2, 7)
        assert output["actions_log_var"].shape == (2, 7)
        result = dict(scope="transport_only_fake_policy", parent_python=sys.version,
                      worker_metadata=policy.worker_metadata, payload_roundtrip=True,
                      policy_weights_loaded=False, gpu_tasks_started=0)
    finally:
        policy.close()
    result["worker_exit_code"] = policy.process.returncode
    (args.out_dir / "smoke_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
