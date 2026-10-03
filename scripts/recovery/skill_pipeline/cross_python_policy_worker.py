"""Worker imports OpenPI in its own Python; no LIBERO or simulator imports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def serve_policy(policy, directory, *, metadata=None):
    directory = Path(directory)
    atomic_json(directory / "ready.json", dict(status="ok", python_version=sys.version,
                                               **(metadata or {})))
    sequence = 0
    while True:
        request_path = directory / f"request_{sequence:06d}.json"
        if not request_path.is_file():
            time.sleep(0.02)
            continue
        try:
            request = json.loads(request_path.read_text(encoding="utf-8"))
            if request["sequence"] != sequence:
                raise ValueError("policy request sequence mismatch")
            command = request["command"]
            if command == "infer":
                with np.load(directory / f"request_{sequence:06d}.npz", allow_pickle=False) as data:
                    observation = {"observation/image": data["image"].copy(),
                                   "observation/wrist_image": data["wrist_image"].copy(),
                                   "observation/state": data["state"].copy(), "prompt": request["prompt"]}
                result = policy.infer(observation)
                output = {"actions": np.asarray(result["actions"])}
                if result.get("actions_log_var") is not None:
                    output["actions_log_var"] = np.asarray(result["actions_log_var"])
                np.savez(directory / f"response_{sequence:06d}.npz", **output)
            elif command == "reset":
                if hasattr(policy, "reset"):
                    policy.reset()
            elif command != "close":
                raise ValueError("unknown policy worker command")
            atomic_json(directory / f"response_{sequence:06d}.json", dict(status="ok", sequence=sequence))
            if command == "close":
                return
            sequence += 1
        except Exception:
            atomic_json(directory / f"response_{sequence:06d}.json",
                        dict(status="error", sequence=sequence, error=traceback.format_exc()))
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ipc-dir", type=Path, required=True)
    parser.add_argument("--config-name", required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        from openpi.training import config
        from openpi.policies import policy_config
        policy = policy_config.create_trained_policy(config.get_config(args.config_name), args.checkpoint_dir)
        serve_policy(policy, args.ipc_dir, metadata=dict(config_name=args.config_name,
                     checkpoint=str(args.checkpoint_dir), policy_weights_loaded=True))
    except Exception:
        atomic_json(args.ipc_dir / "ready.json", dict(status="error", error=traceback.format_exc()))
        raise


if __name__ == "__main__":
    main()
