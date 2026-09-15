"""Bounded recovery probe using the current lane's actual eval command and Python.

Outputs are diagnostic artifacts only; this module never runs mining step/ingest/score.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_lane_module(repo: Path):
    path = repo / "scripts/recovery/skill_pipeline/run_mining_lane.py"
    spec = importlib.util.spec_from_file_location("probe_lane", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_flag(argv: list[str], name: str, value: str) -> None:
    if name in argv:
        argv[argv.index(name) + 1] = value
    else:
        argv.extend([name, value])


def build_probe(run: Path, seed: int, query: int, output: Path, *, task: int | None = None) -> dict:
    lane_path = run / "mine/lane_command.json"
    lane = read_json(lane_path)
    args = argparse.Namespace(**lane["args"])
    state = read_json(run / "mine/mine_state.json")
    task = task or int(state.get("awaiting_task") or 0)
    if not task:
        raise ValueError("No active task; pass an explicit recorded task id")
    if query < 0:
        raise ValueError("query must be nonnegative")
    repo = Path(args.repo_root).absolute()
    python = Path(args.python_bin)
    # Do not resolve a venv symlink: executing its resolved target loses the venv.
    if not python.is_absolute() or not python.is_file():
        raise ValueError(f"Missing absolute eval Python from lane: {python}")
    if not getattr(args, "task_suite_name", None) or not getattr(args, "model", None):
        raise ValueError("Lane is missing suite/model; refusing to guess")
    baseline = Path(args.baseline_run_dir)
    matches = []
    for path in baseline.glob("*/ep*/episode.json"):
        episode = read_json(path)
        if episode.get("task_id_1based") == task and episode.get("seed") == seed:
            matches.append((path, episode))
    if len(matches) != 1:
        raise ValueError(f"Expected one baseline episode for task={task}, seed={seed}, found {len(matches)}")
    source, episode = matches[0]
    if episode.get("source_suite") != args.task_suite_name:
        raise ValueError("Recorded baseline suite differs from lane")
    idx = int(episode["episode_idx"])
    if getattr(args, "episode_seed_start", 0):
        if int(args.episode_seed_start) + idx != seed:
            raise ValueError("Lane seed mapping differs from recorded baseline")
    elif int(args.seed) != seed:
        raise ValueError("Lane seed differs from recorded baseline")
    if "init_state_idx" not in episode:
        raise ValueError("Baseline has no init_state_idx; cannot claim same-init probe")
    pack = Path(args.skill_pack)
    if not pack.is_absolute():
        pack = repo / "skill_packs" / pack
    if not pack.is_dir():
        raise ValueError(f"Missing active pack: {pack}")
    args.skills_dir = str(pack / "skills")
    args.capability_registry = str(pack / "capabilities.yaml")
    args.num_trials = 1
    args.validation_early_stop_first_n_failures = 0
    module = load_lane_module(repo)
    argv = module.eval_command(args, task, "rollout", output)
    set_flag(argv, "--force_recovery_query", str(query))
    if idx:
        runner = repo / "experiments/robot/libero/skill_pipeline/runner.py"
        if "--episode_index_start" not in runner.read_text(encoding="utf-8"):
            raise ValueError("Snapshot cannot preserve nonzero episode index; update snapshot before this probe")
        set_flag(argv, "--episode_index_start", str(idx))
    env = module.build_child_env(args, repo)
    if not env.get("LIBERO_PYTHONPATH_ROOT") or not env.get("LIBERO_CONFIG_PATH"):
        raise ValueError("Missing pinned LIBERO environment; use remote.py probe-recovery or source the run launcher")
    # Capture the contract, not credentials or the entire inherited environment.
    selected_env = {k: env[k] for k in ("ROOT", "PYTHONPATH", "LIBERO_PYTHONPATH_ROOT", "LIBERO_CONFIG_PATH",
                    "OVERLAY_ROOT", "CUTAMP_RUNNER_PYTHON", "CUDA_VISIBLE_DEVICES", "MUJOCO_GL",
                    "PYOPENGL_PLATFORM", "XLA_PYTHON_CLIENT_PREALLOCATE") if k in env}
    hashes = {str(p.relative_to(pack)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(pack.rglob("*")) if p.is_file() and p.suffix in {".py", ".md", ".yaml"}}
    return {"argv": argv, "env": selected_env, "repo": str(repo), "pack": str(pack),
            "task": task, "seed": seed, "query": query, "episode_idx": idx,
            "init_state_idx": episode["init_state_idx"], "baseline_episode": str(source),
            "lane_sha256": hashlib.sha256(lane_path.read_bytes()).hexdigest(), "pack_sha256": hashes,
            "formal_num_trials": lane["args"]["num_trials"], "formal_success_fraction": 0.60,
            "probe_counts_as_validation": False}


def trace(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
        except ValueError:
            continue
    return rows


def classify(output: Path, returncode: int, plan: dict) -> dict:
    rollout = output / "rollout"
    episodes = sorted(rollout.glob("*/ep*/episode.json"))
    recovery = [row for p in rollout.glob("*/ep*/recovery_trace.jsonl") for row in trace(p)]
    debug = rollout / "cutamp_debug"
    solvers, constraints = [], []
    for f in sorted(debug.glob("*.result.json")):
        try:
            d = read_json(f)
            solvers.append({"path": str(f), "num_satisfying": d.get("num_satisfying"),
                            "has_executable_plan": bool(d.get("executable_plan")),
                            "failure_reason": d.get("failure_reason")})
        except (ValueError, OSError):
            pass
    for f in sorted(debug.glob("*.stderr.txt")):
        lines = [s for s in f.read_text(errors="replace").splitlines()
                 if not s.lstrip().startswith("Loss:")
                 and any(t in s for t in ("satisfying", "Constraint", "Collision", "planning failed", "runner_failed", "No such file"))]
        constraints.append({"path": str(f), "lines": lines[-20:]})
    errors = [str(row["error"]) for row in recovery if row.get("error")]
    facts = {"returncode": returncode, "episode_paths": [str(p) for p in episodes], "errors": errors,
             "solvers": solvers, "constraints": constraints, "log": str(output / "eval.log"),
             "frames": [str(p) for p in rollout.glob("*/ep*/frames")],
             "probe_counts_as_validation": False}
    def result(status, valid=False, **details):
        return {**facts, "status": status, "valid_physical_observation": valid, **details}
    if returncode or len(episodes) != 1:
        return result("infrastructure_error", reason="Process/episode incomplete; inspect eval.log and interpreter, do not score")
    ep = read_json(episodes[0])
    if ep.get("seed") != plan["seed"] or ep.get("init_state_idx") != plan["init_state_idx"]:
        return result("infrastructure_error", reason="Probe did not preserve baseline seed/init")
    if any("runner_failed" in e for e in errors):
        return result("infrastructure_error", reason="cuTAMP subprocess failure")
    if not ep.get("recovery_calls"):
        return result("recovery_not_entered", task_success=bool(ep.get("success")))
    if ep.get("success"):
        return result("recovery_succeeded", True)
    execution = [r for r in recovery if r.get("kind") == "trajectory"
                 or (r.get("event") == "execute" and r.get("env_steps", 0))]
    text = " ".join(errors + [str(r.get("failure_reason") or "") for r in solvers]).lower()
    if execution:
        return result("execution_failed", True, execution_events=execution[-5:])
    if "motion planning failed" in text:
        return result("motion_planning_failed", True)
    if "missing_real_cutamp_executable_plan" in text or any(
            (r.get("num_satisfying") or 0) > 0 and not r["has_executable_plan"] for r in solvers):
        return result("executable_plan_missing", True)
    if "no satisfying" in text or "no_feasible" in text or (solvers and all(r.get("num_satisfying") == 0 for r in solvers)):
        return result("optimization_infeasible", True)
    return result("unknown_failure", bool(recovery))


def preflight(plan: dict, output: Path) -> dict:
    # Check the eval environment, not cuTAMP's distinct Python. Never install dependencies here.
    script = "import sys,json,importlib.util; names=['etils','jax','openpi','mujoco']; print(json.dumps({'executable':sys.executable,'version':sys.version,'missing':[n for n in names if importlib.util.find_spec(n) is None]}))"
    proc = subprocess.run([plan["argv"][0], "-c", script], env={**os.environ, **plan["env"]},
                          cwd=plan["repo"], text=True, capture_output=True, timeout=60)
    result = {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    try:
        data = json.loads(proc.stdout)
        result.update(data, ok=proc.returncode == 0 and not data["missing"])
    except ValueError:
        result["ok"] = False
    (output / "preflight.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--query", type=int)
    parser.add_argument("--task", type=int)
    parser.add_argument("--draft-dir", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    run = args.run_root.resolve()
    parent = run / "mine/probes"
    parent.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="probe_", dir=parent))
    result = {}
    try:
        lane = read_json(run / "mine/lane_command.json")
        repo = Path(lane["args"]["repo_root"])
        sys.path.insert(0, str(repo))
        from check_actor_drafts import prepare_candidate, check_candidate
        if args.check_only:
            pack = Path(lane["args"]["skill_pack"])
            if not pack.is_absolute():
                pack = repo / "skill_packs" / pack
            candidate = prepare_candidate(repo, pack, args.draft_dir, output)
            result = check_candidate(repo, candidate, args.draft_dir, output, pack)
            result["status"] = "checks_passed" if result["ok"] else "check_failed"
        else:
            if args.seed is None or args.query is None:
                raise ValueError("probe requires --seed and --query")
            plan = build_probe(run, args.seed, args.query, output, task=args.task)
            (output / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
            if args.dry_run:
                result = {"status": "planned", "plan": plan}
            else:
                health = preflight(plan, output)
                if not health["ok"]:
                    result = {"status": "infrastructure_error", "preflight": health, "valid_physical_observation": False}
                elif args.preflight_only:
                    result = {"status": "preflight_passed", "preflight": health, "valid_physical_observation": False}
                else:
                    # Respect the same lock as formal validation, without changing mining state.
                    import fcntl
                    with (run / "mine/lane.lock").open("a") as lock:
                        try:
                            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            result = {"status": "busy", "reason": "Formal validation/probe owns the lane lock"}
                        else:
                            if args.draft_dir:
                                pack = Path(plan["pack"])
                                candidate = prepare_candidate(repo, pack, args.draft_dir, output)
                                check = check_candidate(repo, candidate, args.draft_dir, output, pack)
                                (output / "checks.json").write_text(json.dumps(check, indent=2), encoding="utf-8")
                                if not check["ok"]:
                                    result = {"status": "check_failed", "checks": check}
                                else:
                                    for flag, value in (("--skill_pack", str(candidate)), ("--skill_index", str(candidate / "skills/_index.yaml")),
                                                        ("--capability_registry", str(candidate / "capabilities.yaml"))):
                                        set_flag(plan["argv"], flag, value)
                                    (output / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
                            if not result:
                                with (output / "eval.log").open("w") as log:
                                    proc = subprocess.Popen(plan["argv"], cwd=plan["repo"], env={**os.environ, **plan["env"]},
                                                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                                    try:
                                        code = proc.wait(timeout=args.timeout)
                                    except subprocess.TimeoutExpired:
                                        import signal
                                        os.killpg(proc.pid, signal.SIGTERM)
                                        try:
                                            proc.wait(timeout=30)
                                        except subprocess.TimeoutExpired:
                                            os.killpg(proc.pid, signal.SIGKILL)
                                            proc.wait(timeout=10)
                                        code = -1
                                result = classify(output, code, plan)
    except Exception as exc:
        result = {"status": "check_failed" if args.check_only else "infrastructure_error", "valid_physical_observation": False,
                  "error": f"{type(exc).__name__}: {exc}"}
    result.update(output_dir=str(output), probe_counts_as_validation=False)
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] in {"infrastructure_error", "check_failed"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
