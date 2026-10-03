"""Bounded file transport to a policy worker in a different Python environment."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import signal
import time
import uuid

import numpy as np


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


class CrossPythonPolicyAdapter:
    def __init__(self, *, python, config_name, checkpoint_dir, ipc_root,
                 startup_timeout_s=600, infer_timeout_s=120, worker_script=None, gpu=None):
        if startup_timeout_s <= 0 or infer_timeout_s <= 0:
            raise ValueError("positive policy worker timeouts required")
        self.directory = Path(ipc_root).resolve() / ("worker_" + uuid.uuid4().hex)
        self.directory.mkdir(parents=True)
        self.timeout = infer_timeout_s
        self.sequence = 0
        self.process = None
        self.log = (self.directory / "worker.log").open("wb")
        script = (Path(worker_script).resolve() if worker_script else
                  Path(__file__).resolve().parents[4] / "scripts/recovery/skill_pipeline/cross_python_policy_worker.py")
        environment = os.environ.copy()
        environment["XLA_PYTHON_CLIENT_PREALLOCATE"] = "false"
        environment["CUDA_VISIBLE_DEVICES"] = "" if gpu is None else str(gpu)
        environment["JAX_PLATFORMS"] = "cpu" if gpu is None else "cuda"
        try:
            self.process = subprocess.Popen(
                [str(python), str(script), "--ipc-dir", str(self.directory),
                 "--config-name", config_name, "--checkpoint-dir", str(checkpoint_dir)],
                stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
                env=environment, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt")
            self.worker_metadata = self._wait(self.directory / "ready.json", startup_timeout_s)
        except BaseException:
            self.close()
            raise

    def _wait(self, path, timeout):
        deadline = time.monotonic() + timeout
        while not path.is_file():
            if self.process.poll() is not None:
                raise RuntimeError("policy worker exited; see " + str(self.directory / "worker.log"))
            if time.monotonic() >= deadline:
                self._stop()
                raise TimeoutError("policy worker timed out; see " + str(self.directory / "worker.log"))
            time.sleep(0.02)
        response = json.loads(path.read_text(encoding="utf-8"))
        if response.get("status") != "ok":
            self._stop()
            raise RuntimeError("policy worker failed: " + str(response.get("error")))
        return response

    def _request(self, command, observation=None):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("policy worker is not running")
        sequence = self.sequence
        prefix = self.directory / f"request_{sequence:06d}"
        request = dict(command=command, sequence=sequence)
        if observation is not None:
            keys = ("observation/image", "observation/wrist_image", "observation/state", "prompt")
            if set(observation) != set(keys):
                raise ValueError("policy bridge requires only images, robot state and prompt")
            arrays = {"image": np.asarray(observation[keys[0]]),
                      "wrist_image": np.asarray(observation[keys[1]]),
                      "state": np.asarray(observation[keys[2]])}
            if (any(arrays[k].dtype != np.uint8 or arrays[k].ndim != 3
                    or arrays[k].shape[2] != 3 for k in ("image", "wrist_image"))
                    or arrays["state"].shape != (8,) or not np.isfinite(arrays["state"]).all()
                    or not isinstance(observation["prompt"], str)):
                raise ValueError("invalid policy bridge observation")
            np.savez(str(prefix) + ".npz", **arrays)
            request["prompt"] = observation["prompt"]
        atomic_json(str(prefix) + ".json", request)
        self.sequence += 1
        response = self._wait(self.directory / f"response_{sequence:06d}.json", self.timeout)
        if response.get("sequence") != sequence:
            self._stop()
            raise ValueError("policy worker response sequence mismatch")
        if command != "infer":
            return None
        try:
            with np.load(self.directory / f"response_{sequence:06d}.npz", allow_pickle=False) as data:
                output = {name: data[name].copy() for name in data.files}
        except Exception:
            self._stop()
            raise
        actions = output.get("actions")
        if (actions is None or actions.ndim != 2 or actions.shape[1] != 7
                or not len(actions) or not np.isfinite(actions).all()):
            self._stop()
            raise ValueError("policy worker returned invalid actions")
        return output

    def reset(self):
        self._request("reset")

    def infer(self, observation):
        return self._request("infer", observation)

    def _stop(self):
        if self.process is not None and self.process.poll() is None:
            if os.name == "nt":
                # Windows venv launchers may have a child interpreter holding
                # log handles; stop this worker's process tree, not just its stub.
                subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                               capture_output=True, timeout=5,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    os.killpg(self.process.pid, signal.SIGKILL)
                else:
                    self.process.kill()
                self.process.wait(timeout=2)

    def close(self):
        try:
            if self.process is not None and self.process.poll() is None:
                # Close is bounded separately from model inference timeout.
                previous = self.timeout
                self.timeout = 2
                try:
                    self._request("close")
                    self.process.wait(timeout=2)
                except Exception:
                    self._stop()
                finally:
                    self.timeout = previous
        finally:
            self.log.close()
            if os.name == "nt":
                # taskkill can return before child stdout handles are released.
                # Wait for the worker's own log to allow a rename, preserving it.
                path = self.directory / "worker.log"
                closed = self.directory / "worker.closed.log"
                deadline = time.monotonic() + 2
                while path.is_file():
                    try:
                        path.rename(closed)
                        closed.rename(path)
                        break
                    except PermissionError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("worker log is still held after shutdown")
                        time.sleep(0.02)
