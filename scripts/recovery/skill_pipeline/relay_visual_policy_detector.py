"""Bounded SSH/SCP relay for each held visual-policy frame and frozen CPU detector."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("host", "identity", "known-hosts", "remote-root", "local-root", "detector-python",
                 "prompts-json", "grounding-model-dir", "sam2-model-dir"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--max-steps", type=int, required=True)
    parser.add_argument("--resume-step", type=int)
    parser.add_argument("--action-chunk", type=int, default=4)
    parser.add_argument("--settle-steps", type=int, default=10)
    parser.add_argument("--wait-timeout-s", type=int, default=720)
    args = parser.parse_args()
    if (not re.fullmatch(r"/[A-Za-z0-9_./-]+", args.remote_root)
            or ".." in Path(args.remote_root).parts or args.max_steps < 1 or args.action_chunk < 1):
        raise ValueError("invalid relay paths or bounds")
    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo))
    local = Path(args.local_root).resolve()
    local.mkdir(parents=True, exist_ok=True)
    options = ["-i", args.identity, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
               "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + args.known_hosts]
    journal = local / "detector_relay.jsonl"
    if journal.exists() and args.resume_step is None:
        raise FileExistsError(journal)
    start = args.settle_steps if args.resume_step is None else args.resume_step
    if start < args.settle_steps or (start - args.settle_steps) % args.action_chunk:
        raise ValueError("resume step must be a query boundary")
    for step in range(start, args.settle_steps + args.max_steps, args.action_chunk):
        remote = args.remote_root + f"/frames/step{step:06d}"
        deadline = time.monotonic() + args.wait_timeout_s
        while True:
            command = (f"if test -f {shlex.quote(args.remote_root + '/abort.json')}; then echo ABORT; "
                       f"elif test -f {shlex.quote(args.remote_root + '/episode.json')}; then echo DONE; "
                       f"elif test -f {shlex.quote(remote + '/summary.json')}; then echo READY; else echo WAIT; fi")
            state = subprocess.run(["ssh", *options, args.host, command], check=True,
                                   capture_output=True, text=True).stdout.strip()
            if state == "ABORT":
                raise RuntimeError("remote visual episode aborted")
            if state == "DONE":
                print("REMOTE_EPISODE_DONE", flush=True)
                return
            if state == "READY":
                break
            if state != "WAIT" or time.monotonic() >= deadline:
                raise TimeoutError("waiting for remote current frame failed")
            time.sleep(5)
        directory = local / "frames" / f"step{step:06d}"
        directory.mkdir(parents=True, exist_ok=args.resume_step == step)
        print("DETECTING_STEP " + str(step), flush=True)
        for path in ("observation", "summary.json"):
            subprocess.run(["scp", "-r", *options, args.host + ":" + remote + "/" + path,
                            str(directory)], check=True)
        previous_detector = directory / "detector"
        if previous_detector.exists():
            previous_detector.rename(directory / ("detector_previous_" + uuid.uuid4().hex))
        started = time.monotonic()
        with (directory / "detector_cpu.log").open("wb") as log:
            result = subprocess.run([args.detector_python, str(repo / "scripts/recovery/skill_pipeline/run_grounded_sam2_snapshot.py"),
                str(directory / "observation"), "--prompts-json", args.prompts_json,
                "--out-dir", str(directory / "detector"), "--grounding-model-dir", args.grounding_model_dir,
                "--sam2-model-dir", args.sam2_model_dir, "--device", "cpu"],
                check=False, cwd=repo, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        refusal = directory / "detector/scene_refusal.json"
        scene_refused = result.returncode != 0 and refusal.is_file()
        if scene_refused:
            report = json.loads(refusal.read_text(encoding="utf-8"))
            scene_refused = report.get("reason") == "overlapping_instance_masks" and bool(report.get("mask_conflicts"))
        if result.returncode and not scene_refused:
            raise RuntimeError("detector failed; inspect detector_cpu.log")
        # Deliver valid detections even when scene admission refuses them.
        # The server independently rejects overlapping masks, while VLA continues.
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
        load_detections(load_observation(directory / "observation"), directory / "detector")
        subprocess.run(["scp", "-r", *options, str(directory / "detector"), args.host + ":" + remote + "/"], check=True)
        subprocess.run(["ssh", *options, args.host, "touch " + shlex.quote(remote + "/detector/READY")], check=True)
        row = dict(env_step=step, detector_processing_and_upload_seconds=time.monotonic() - started,
                   scene_refused=scene_refused,
                   current_frame_detected=True, ready_written_after_upload=True)
        with journal.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        print("DETECTOR_DELIVERED " + json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
