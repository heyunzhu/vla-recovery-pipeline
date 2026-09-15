"""Single-run persistent supervisor. Owns delivery, recovery and validation handoff."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import run_codex_intervention_daemon as daemon


def remote_processes(remote: daemon.Remote, run: str) -> list[str]:
    script = (
        "import json, subprocess\n"
        "rows = subprocess.check_output(['ps','-eo','pid,args'],text=True).splitlines()\n"
        f"print(json.dumps([r for r in rows if {run!r} in r and "
        "('run_mining_lane.py' in r or 'run_skill_eval.py' in r or 'ingest_actor_candidate.py' in r or 'probe_recovery.py' in r)]))\n"
    )
    return json.loads(remote.run_script(script, timeout=30).stdout)


def refresh_events(remote: daemon.Remote, config: dict) -> None:
    argv = [config.get("python") or remote.python,
            f"{config['repo']}/scripts/recovery/skill_pipeline/watch_mining_interventions.py",
            "--run-root", config["run_root"], "--once", "--retry-errors", "--quiet"]
    remote.run(shlex.join(argv), timeout=60)


def recover_owned_attempts(remote: daemon.Remote, config: dict, workdir: Path) -> bool:
    """Never expire a live actor by elapsed time. Recover only our dead exec owner."""
    waiting = False
    for path in (workdir / "attempts").glob("*.json"):
        state = json.loads(path.read_text(encoding="utf-8"))
        attempts = state.get("attempts") or []
        if not attempts:
            continue
        last = attempts[-1]
        if last.get("run_root") != config["run_root"] or last.get("executor") != "exec":
            continue
        if not last.get("in_progress") and last.get("phase") not in {"draft_ready", "admitting", "agent_failed"}:
            continue
        proc_path = Path(last["round_dir"]) / "actor_process.json"
        proc = json.loads(proc_path.read_text()) if proc_path.exists() else {}
        owner = int(last.get("owner_pid") or 0)
        actor_live = proc.get("phase") not in {"agent_finished", "agent_timeout"} and daemon.process_alive(int(proc.get("pid") or 0))
        if (owner != os.getpid() and daemon.process_alive(owner)) or actor_live:
            waiting = True
            continue
        final_path = Path(last["round_dir"]) / "actor_final.json"
        final = json.loads(final_path.read_text(encoding="utf-8")) if final_path.exists() else {}
        if last.get("phase") == "admitting" and last.get("remote_drafts"):
            lane = daemon.lane_args(remote, config["run_root"])
            cmd = [config.get("python") or remote.python,
                   f"{config['repo']}/scripts/recovery/skill_pipeline/ingest_actor_candidate.py",
                   "--skill_pack", lane["skill_pack"], "--draft_dir", last["remote_drafts"],
                   "--out_dir", config["run_root"] + "/mine", "--recover_transaction"]
            remote.run(shlex.join(cmd))
        # A finished candidate can be admitted after an SSH/daemon interruption without redrafting.
        if final.get("status") == "drafted" and not last.get("ingest"):
            old = json.loads((Path(last["round_dir"]) / "context.json").read_text(encoding="utf-8"))
            if daemon.context_is_current(remote, config["run_root"], old):
                state["reuse_drafts_from"] = last["round_dir"]
        state["interrupted_workdir"] = last["round_dir"]
        last.update(in_progress=False, phase="recovered_interruption", ok=False)
        state["needs_human"] = False
        daemon.save_attempts(workdir, state["event_id"], state)
        remote.run(daemon.mark_command(remote, config, "retry", state["event_id"],
                                      "--message 'local exec owner exited; preserved work available'"))
    return waiting


def tick(remote: daemon.Remote, args, workdir: Path) -> dict:
    run = remote.guard(args.run_root)
    if remote.exists(f"{run}/mine/STOPPED_BY_USER.txt") or (workdir / "STOP").exists():
        return {"phase": "stopped", "terminal": True}
    config = daemon.run_config(remote, run)
    live = remote_processes(remote, run)
    state = daemon.mine_state(remote, run)
    if not state:
        raise RuntimeError("mine_state.json absent/unreadable; do not infer completion")
    verdict, detail, task = daemon.liveness(remote, run)
    if live:
        phase = ("admission_running" if any("ingest_actor_candidate.py" in r for r in live)
                 else "probe_running" if any("/mine/probes/" in r or "probe_recovery.py" in r for r in live)
                 else "validation_running")
        return {"phase": phase, "processes": live, "detail": detail, "terminal": False}
    if verdict == "finished":
        return {"phase": "completed", "terminal": True, "tasks": state.get("tasks"), "completed": state.get("completed")}
    if verdict == "awaiting_validation":
        last_invalid = remote.cat_text(f"{run}/mine/last_invalid_validation.json", check=False)
        exit_code = remote.cat_text(f"{run}/mine/mining_lane.exit_code", check=False).strip()
        if exit_code and exit_code not in {"0", "20"}:
            return {"phase": "validation_error", "terminal": True, "exit_code": exit_code,
                    "invalid_validation": last_invalid, "detail": "No valid score; candidate preserved, no new write consumed"}
        lane = remote.cat_json(f"{run}/mine/lane_command.json")
        argv = shlex.join([str(s) for s in lane["argv"]])
        env = daemon.launcher_env_body(remote, run)
        if not env or "PYTHONPATH" not in env:
            raise RuntimeError("Missing launcher environment; refusing to resume with a different LIBERO")
        remote.run(daemon.resume_command(run_root=run, repo=config["repo"], argv=argv,
                   log=f"{run}/mine/lane_logs/supervisor_resume.log", env_body=env))
        return {"phase": "validation_starting", "terminal": False}
    if verdict != "needs_draft":
        raise RuntimeError(detail)
    if recover_owned_attempts(remote, config, workdir):
        return {"phase": "agent_running", "terminal": False}
    refresh_events(remote, config)
    code = daemon.main([
        "--run-root", run, "--workdir", str(workdir), "--executor", "exec",
        "--model", args.model, "--reasoning-effort", args.reasoning_effort,
        "--ssh-host", args.ssh_host, "--ssh-port", args.ssh_port, "--ssh-key", args.ssh_key,
        "--max-attempts", str(args.max_attempts), "--retry-errors", "--max-event-age-minutes", "0",
        "--codex-timeout", str(args.codex_timeout),
    ])
    # A phase receipt is a factual handoff record, not an assertion of skill quality.
    exhausted = any(json.loads(p.read_text(encoding="utf-8")).get("needs_human")
                    for p in (workdir / "attempts").glob("*.json"))
    return {"phase": "candidate_submitted" if code == 0 else "stale_result" if code == 4 else "intervention_retry",
            "daemon_exit": code, "terminal": exhausted or code == 4, "attempts_exhausted": exhausted}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--model", default=daemon.DEFAULT_MODEL)
    parser.add_argument("--reasoning-effort", default=daemon.DEFAULT_REASONING_EFFORT,
                        choices=("low", "medium", "high", "xhigh"))
    parser.add_argument("--ssh-host", default=daemon.DEFAULT_SSH_HOST)
    parser.add_argument("--ssh-port", default=daemon.DEFAULT_SSH_PORT)
    parser.add_argument("--ssh-key", default=daemon.DEFAULT_SSH_KEY)
    parser.add_argument("--max-attempts", type=int, default=15, help="Delivery/admission attempts per event, not skill writes")
    parser.add_argument("--codex-timeout", type=int, default=7200)
    parser.add_argument("--poll-seconds", type=float, default=30)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--replace-idle-pid", type=int, default=0,
                        help="Replace this workdir's old supervisor only after its active intervention ends")
    args = parser.parse_args()
    args.workdir.mkdir(parents=True, exist_ok=True)
    lockdir = args.workdir / "supervisor"
    lockdir.mkdir(exist_ok=True)
    if args.replace_idle_pid:
        wait_for_idle_replacement(args.workdir, args.replace_idle_pid)
    if not daemon.acquire_lock(lockdir):
        raise SystemExit("Supervisor already running for this workdir")
    remote = daemon.Remote(host=args.ssh_host, port=args.ssh_port, key=args.ssh_key)
    try:
        while True:
            try:
                daemon.atomic_json(args.workdir / "supervisor_status.json", {
                    "phase": "checking", "at": time.time(), "pid": os.getpid(), "run_root": args.run_root,
                    "model": args.model, "reasoning_effort": args.reasoning_effort,
                    "active_actor_status_glob": "*/attempt*/actor_process.json"})
                record = tick(remote, args, args.workdir)
            except (Exception, SystemExit) as exc:
                record = {"phase": "transport_or_supervisor_error", "error": str(exc), "terminal": False}
            record.update(at=time.time(), run_root=args.run_root, model=args.model, reasoning_effort=args.reasoning_effort)
            daemon.atomic_json(args.workdir / "supervisor_status.json", record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
            if record.get("terminal") or args.once:
                return
            time.sleep(max(1, min(60, args.poll_seconds)))
    finally:
        daemon.release_lock(lockdir)


def wait_for_idle_replacement(workdir: Path, pid: int) -> None:
    lock = workdir / "supervisor/daemon.lock"
    while daemon.process_alive(pid):
        owner = json.loads(lock.read_text(encoding="utf-8")) if lock.exists() else {}
        if int(owner.get("pid") or 0) != pid:
            raise RuntimeError("Replacement PID does not own this supervisor workdir")
        if (workdir / "STOP").exists():
            raise RuntimeError("Stopped run; replacement cancelled")
        daemon.atomic_json(workdir / "replacement_status.json", {
            "phase": "waiting_for_intervention_boundary", "old_pid": pid, "replacement_pid": os.getpid(), "at": time.time()})
        if daemon.acquire_lock(workdir):
            try:
                # Holding the daemon lock prevents a new actor from starting while we replace the parent.
                active = False
                for p in (workdir / "attempts").glob("*.json"):
                    state = json.loads(p.read_text(encoding="utf-8"))
                    for attempt in state.get("attempts") or []:
                        if not attempt.get("in_progress"):
                            continue
                        proc = Path(attempt["round_dir"]) / "actor_process.json"
                        record = json.loads(proc.read_text(encoding="utf-8")) if proc.exists() else {}
                        if daemon.process_alive(int(record.get("pid") or 0)):
                            active = True
                if not active:
                    if os.name == "nt":
                        daemon.run_quiet(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=True)
                    else:
                        import signal
                        os.kill(pid, signal.SIGTERM)
                    for _ in range(20):
                        if not daemon.process_alive(pid):
                            break
                        time.sleep(0.5)
                    if daemon.process_alive(pid):
                        raise RuntimeError("Old supervisor did not exit")
                    daemon.atomic_json(workdir / "replacement_status.json", {
                        "phase": "replaced_at_idle_boundary", "old_pid": pid, "replacement_pid": os.getpid(), "at": time.time()})
                    return
            finally:
                daemon.release_lock(workdir)
        time.sleep(2)


if __name__ == "__main__":
    main()
