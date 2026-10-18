"""Matched oracle / unchanged RGB-D-anchor trials on historical successful cases.

Run inside the authorized evaluation notebook. Frozen sources and benchmark
assets remain external; each case writes to a new directory. This probes the
existing anchor's scope, without substituting oracle object geometry on failure.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import shutil
import subprocess
import time

CASES = [
    ("goal_plate_init1", "libero_goal_task", 4, 1, "lane2/026_C4_libero_goal_task"),
    ("goal_bottle_bowl", "libero_goal_task", 7, 1, "lane2/026_C4_libero_goal_task"),
    ("swap_bowl_plate", "libero_goal_swap", 4, 0, "lane0/024_C4_libero_goal_swap"),
    ("goal_cheese_rack", "libero_goal_task", 8, 0, "lane2/026_C4_libero_goal_task"),
]


def case_finished(batch, record):
    case = batch / record["label"]
    return (case / "visual/exitcode.txt").exists() or (
        record.get("visual_run", {}).get("status") == "not_run_no_recovery_fixture"
        and (case / "oracle/exitcode.txt").exists())


def preserve_interrupted_case(batch, record):
    case = batch / record["label"]
    if not case.exists():
        return
    batch = batch.resolve()
    archive = batch / "interrupted_runs" / f"{record['label']}_{time.time_ns()}"
    if case.resolve().parent != batch or not archive.resolve().is_relative_to(batch):
        raise ValueError("interrupted case paths must remain inside the batch")
    archive.parent.mkdir(exist_ok=True)
    case.rename(archive)
    record.setdefault("interrupted_attempts", []).append(str(archive))
    for key in ("oracle_run", "visual_run", "language_preflight_error"):
        record.pop(key, None)


def launch(command, env, directory, timeout):
    directory.mkdir(exist_ok=True)
    (directory / "command.sh").write_text("#!/usr/bin/env bash\n" +
        "\n".join("export " + k + "=" + shlex.quote(v) for k, v in sorted(env.items())
                  if k.startswith(("ANCHOR_", "CUTAMP_")) or k in
                  {"ROOT", "PYTHONPATH", "LIBERO_CONFIG_PATH", "ORACLE_ENTRYPOINT", "CUDA_VISIBLE_DEVICES", "MUJOCO_GL", "PYOPENGL_PLATFORM", "OMP_NUM_THREADS", "XLA_PYTHON_CLIENT_PREALLOCATE", "XLA_PYTHON_CLIENT_MEM_FRACTION"}) +
        "\ncd " + shlex.quote(env["REPLAY_RUNTIME"]) + "\n" + shlex.join(command) + "\n")
    started = time.time()
    with (directory / "driver.log").open("wb") as log:
        process = subprocess.Popen(command, env=env, cwd=env["REPLAY_RUNTIME"],
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            rc = 124
    (directory / "exitcode.txt").write_text(str(rc) + "\n")
    return dict(exitcode=rc, elapsed_sec=time.time() - started)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out-root", type=Path, required=True)
    ap.add_argument("--visual-code", type=Path, required=True)
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--cases-json", type=Path,
                    help="Explicit list of [label, suite, 1-based task, episode, historical job]")
    ap.add_argument("--resume", action="store_true",
                    help="Keep completed successes and failures; archive interrupted cases before rerunning")
    args = ap.parse_args()
    root, batch, code = args.root.resolve(), args.out_root.resolve(), args.visual_code.resolve()
    hist = root / "logs/continual_skill_core60_pilot_20261006"
    runtime = hist / "runtime_repo"
    support = root / "logs/rgbd_visual_ids_replay_v3_20261009/capture_support"
    python = root / "envs/rlinf-openpi/bin/python"
    batch.mkdir(exist_ok=True)
    if (batch / "batch_manifest.json").exists() and not args.resume:
        raise FileExistsError("batch already started; preserve its evidence")
    import sys
    sys.path.insert(0, str(code))
    from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANCHOR_")}
    env.update(ROOT=str(root), CUDA_VISIBLE_DEVICES="0", MUJOCO_GL="egl", PYOPENGL_PLATFORM="egl",
        LIBERO_CONFIG_PATH=str(hist / "libero_config"), XLA_PYTHON_CLIENT_PREALLOCATE="false",
        XLA_PYTHON_CLIENT_MEM_FRACTION="0.50", OMP_NUM_THREADS="2",
        PYTHONPATH=str(runtime) + ":" + str(root / "third_party/LIBERO-PRO"), REPLAY_RUNTIME=str(runtime),
        CUTAMP_REAL_RUNNER=str(runtime / "scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh"))
    records = []
    cases = json.loads(args.cases_json.read_text()) if args.cases_json else CASES
    if len({(row[1], row[2]) for row in cases}) != len(cases):
        raise ValueError("each selected task must be unique within its suite")
    for label, suite, task, ep, oldjob in cases:
        old = hist / "lanes" / oldjob / "run" / f"task{task:02d}" / f"ep{ep:02d}"
        previous = json.loads((old / "episode.json").read_text())
        assert previous["success"] and previous["recovery_calls"] > 0, label
        files = sorted((hist / "bddl_files" / suite).glob("*.bddl"))
        bddl = files[task - 1]
        records.append(dict(label=label, suite=suite, task_1based=task, episode_idx=ep,
            seed=previous["seed"], init_state_idx=previous["init_state_idx"],
            language=previous["task_description"], historical_episode=str(old / "episode.json"),
            historical_success=True, historical_recovery_calls=previous["recovery_calls"], bddl=str(bddl)))
    hashes = {str(p.relative_to(code)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (code / "scripts/recovery/skill_pipeline").glob("*.py")
              if p.name in {"capture_oracle_recovery_rgbd.py", "replay_anchor_recovery.py",
                  "inspect_recovery_rgbd_capture.py", "visual_selection_oracle_geometry_hook.py"}}
    if args.resume:
        manifest = json.loads((batch / "batch_manifest.json").read_text())
        identity = lambda rows: [(r["label"], r["suite"], r["task_1based"], r["episode_idx"]) for r in rows]
        if identity(records) != identity(manifest["cases"]) or hashes != manifest["source_hashes"]:
            raise ValueError("resume requires the same task selection and frozen visual pipeline")
        try:
            records = json.loads((batch / "batch_results.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            records = manifest["cases"]
        with (batch / "resume_events.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(time_unix=time.time(),reason="resume interrupted process",
                                        driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())) + "\n")
    else:
        (batch / "batch_manifest.json").write_text(json.dumps(dict(cases=records, code=str(code),
            source_hashes=hashes, policy_and_trigger="frozen_oracle_for_fixture_collection",
            visual_mode="all_six_anchor_replacements_and_reward_done_hidden",
            note="selected historical successes; diagnostic sample, not benchmark success rate"), indent=2))
    def save():
        temporary = batch / "batch_results.json.tmp"
        temporary.write_text(json.dumps(records, indent=2))
        temporary.replace(batch / "batch_results.json")
    save()
    for rec in records:
        label, suite, task, ep = rec["label"], rec["suite"], rec["task_1based"], rec["episode_idx"]
        if args.resume and case_finished(batch, rec):
            oracle = batch / label / "oracle"
            episodes = list((oracle / "run").glob("task*/ep*/episode.json"))
            if episodes:
                result = json.loads(episodes[0].read_text())
                rec.setdefault("oracle_run", {}).update(success=result["success"], recovery_calls=result["recovery_calls"],
                    episode_path=str(episodes[0]), exitcode=int((oracle / "exitcode.txt").read_text()))
            print("KEEP_COMPLETED", label, flush=True)
            save()
            continue
        if args.resume:
            preserve_interrupted_case(batch, rec)
            save()
        print("START", label, flush=True)
        case = batch / label
        case.mkdir(exist_ok=False)
        oracle, visual = case / "oracle", case / "visual"
        oracle.mkdir(); visual.mkdir()
        for run in (oracle, visual):
            shutil.copytree(support, run / "capture_support")
            for filename in ("capture_oracle_recovery_rgbd.py", "visual_selection_oracle_geometry_hook.py"):
                shutil.copy2(code / "scripts/recovery/skill_pipeline" / filename, run / "capture_support" / filename)
            (run / "visual_code").symlink_to(code, target_is_directory=True)
        episode_id = f"{suite}:task{task:02d}:ep{ep:02d}"
        oenv = dict(env, ORACLE_ENTRYPOINT=str(hist / "core60_entrypoint.py"),
            ANCHOR_CAPTURE_DIR=str(oracle / "snapshots"), ANCHOR_EPISODE_ID=episode_id,
            ANCHOR_SAVE_REPLAY_FIXTURE="1", CUTAMP_FLOCK_LOCK=str(oracle / "cutamp.lock"))
        command = [str(python), str(oracle / "capture_support/capture_oracle_recovery_rgbd.py"),
            "--pretrained_path", str(root / "models/pi0_libero_openpi"), "--config_name", "pi0_libero",
            "--task_suite_name", suite, "--task_ids", str(task), "--num_trials_per_task", "1",
            "--episode_index_start", str(ep), "--episode_seed_start", "1", "--seed", "90",
            "--policy_in_process", "--save_video", "--openvla_repo_root", str(runtime),
            "--task_language_source", "bddl", "--engine_language_source", "bddl",
            "--max_recovery_calls", "2", "--max_recovery_steps", "200", "--max_replans", "1",
            "--log_dir", str(oracle), "--exp_name", "run", "--enable_mining_skills",
            "--skill_pack", str(hist / "checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918"),
            "--use_real_cutamp_backend", "--real_cutamp_require_feasible", "--real_cutamp_curobo_plan",
            "--real_cutamp_serialize_trajectories", "--prefer_real_cutamp_executable_plan",
            "--require_real_cutamp_executable_plan", "--real_cutamp_grasp_dof", "6",
            "--real_cutamp_runner_python", str(hist / "cutamp_flock.sh"), "--real_cutamp_runner_timeout_sec", "900",
            "--real_cutamp_debug_dir", str(oracle / "cutamp_debug")]
        rec["oracle_run"] = launch(command, oenv, oracle, args.timeout)
        episodes = list((oracle / "run").glob("task*/ep*/episode.json"))
        if episodes:
            result = json.loads(episodes[0].read_text())
            rec["oracle_run"].update(success=result["success"], recovery_calls=result["recovery_calls"],
                                     episode_path=str(episodes[0]))
        save()
        fixture = oracle / "replay_fixture"
        if not fixture.exists():
            rec["visual_run"] = dict(status="not_run_no_recovery_fixture")
            save(); continue
        try:
            task_categories = set(prompts_from_task_language(rec["language"]))
        except ValueError as error:
            # Still run the visual entrypoint: preserve its actual language
            # refusal, sensor inputs and evaluation label, then continue.
            task_categories = set()
            rec["language_preflight_error"] = str(error)
        distractors = json.loads((support.parent / "distractor_prompts.json").read_text())
        (visual / "distractor_prompts.json").write_text(json.dumps(
            {k: v for k, v in distractors.items() if k not in task_categories}, indent=2))
        venv = dict(env, ORACLE_ENTRYPOINT=str(hist / "core60_entrypoint.py"),
            ANCHOR_CAPTURE_DIR=str(visual / "snapshots"), ANCHOR_EPISODE_ID=episode_id,
            ANCHOR_DIAGNOSTIC_HOOK=str(visual / "capture_support/visual_selection_oracle_geometry_hook.py"),
            ANCHOR_VISUAL_CODE=str(code), CUTAMP_FLOCK_LOCK=str(visual / "cutamp.lock"))
        for flag in ("PROPRIO_HAND_STATE", "RGBD_OBSTACLES", "VISUAL_EXECUTOR", "VISUAL_IDS",
                     "REPLACE_BOTTLE_GEOMETRY", "REPLACE_PLATE_GEOMETRY"):
            venv["ANCHOR_" + flag] = "1"
        command = [str(python), str(code / "scripts/recovery/skill_pipeline/replay_anchor_recovery.py"),
            "--fixture", str(fixture), "--bddl", rec["bddl"], "--run-dir", str(visual),
            "--capture-every", "5", "--restore-open-gripper-command", "--evaluation-done-only"]
        rec["visual_run"] = launch(command, venv, visual, args.timeout)
        result_path = visual / "replay_result.json"
        if result_path.exists():
            result = json.loads(result_path.read_text())
            rec["visual_run"].update({k: v for k, v in result.items() if k != "attempts"})
        else:
            rec["visual_run"]["status"] = "failed_before_result"
            failure_path = visual / "failure_result.json"
            if failure_path.exists():
                rec["visual_run"].update(json.loads(failure_path.read_text()))
            for f in [visual / "driver.log", *visual.glob("visual_nomination_step*.log")]:
                rec["visual_run"].setdefault("failure_logs", {})[f.name] = f.read_text(errors="replace")[-6500:]
        save()
        print("DONE", label, rec["oracle_run"].get("success"), rec["visual_run"].get("recovery_success"), flush=True)
    (batch / "batch_finished.txt").write_text("finished\n")
    print("ALL_DONE", flush=True)

if __name__ == "__main__": main()
