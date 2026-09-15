"""Drive one mining Codex intervention per invocation (Windows scheduled-task friendly).

The mining lane stops with ``WAIT_CODEX.json`` and the remote watchdog turns that
into an event queue. This script is the *mechanical* consumer: it polls the queue,
claims one live event, gets the draft written, verifies the artifacts on disk,
pushes them back, runs ``run_skill_mine.py ingest`` with the code/admission gates
on, resolves the event and relaunches the lane.

``--executor`` picks who writes that draft:

``queue`` (default)
    Hand the round to the Codex *desktop* agent with ``codex queue --thread``.
    That agent runs with the user's own permissions and a working ssh hop, which
    the sandboxed CLI never had. Delivery is fire-and-forget, so a round is only
    finished once the agent writes ``result.json`` next to the drafts: the wait is
    bounded by ``--codex-timeout``, and a timeout counts as a failed attempt.
``exec``
    The original path: ``codex exec --output-schema`` inside a local
    workspace-write sandbox. Needs no running app, and is fully synchronous.

Design rules that keep it honest (no "pretend to look"):

* The trigger is this poll loop, never the model.
* A round only counts as done when the artifacts exist on disk and the remote
  ingest returns ``ok``.
* Retries and caps are recorded in ``attempts.json``; the model never decides them.
* A local lock keeps two scheduled invocations from overlapping.
* Every remote write path must live under the run root (``guard``).

The prompt sent to the model is small by design (actor guidelines + evidence
summary + previous-round verdict); the full traces stay on the remote and the
model greps them on demand over the same ssh hop.

Usage on this machine (registered as a 1-minute scheduled task)::

    python run_codex_intervention_daemon.py --max-runs 4
    python run_codex_intervention_daemon.py --list        # read-only queue view
    python run_codex_intervention_daemon.py --dry-run     # plan only, no writes
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shlex
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
sys.path.insert(0, str(Path(__file__).resolve().parent))
from actor_context import GUIDELINE_FILES, guideline_index

DEFAULT_SSH_HOST = os.environ.get("MINING_SSH_HOST", "")
DEFAULT_SSH_PORT = os.environ.get("MINING_SSH_PORT", "")
DEFAULT_SSH_KEY = os.environ.get("MINING_SSH_KEY", "")
DEFAULT_REMOTE_ROOT = "/mnt/nas/gezuhao/xinghanbo"
DEFAULT_REMOTE_PYTHON = f"{DEFAULT_REMOTE_ROOT}/envs/openpi_jax_py311/bin/python"
def resolve_codex_exe() -> str:
    """The app's current CLI, never the stale alias beside it.

    `bin/codex.exe` is an old install that predates the `queue` subcommand, which
    is how a round reaches the desktop agent. The live build sits in a versioned
    directory next to it, so prefer the newest of those.
    """

    root = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
    versioned = [path for path in root.glob("*/codex.exe") if path.is_file()]
    if versioned:
        return str(max(versioned, key=lambda path: path.stat().st_mtime))
    return str(root / "codex.exe")


DEFAULT_CODEX_EXE = resolve_codex_exe()
DEFAULT_WORKDIR = str(Path(__file__).resolve().parents[3] / "experiments/.pro/daemon_work")
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_REASONING_EFFORT = "xhigh"
# The desktop agent thread that receives rounds in --executor queue mode. No
# default on purpose: queueing into the wrong thread would inject work into a
# conversation that has nothing to do with the mining run.
DEFAULT_AGENT_THREAD = os.environ.get("CODEX_AGENT_THREAD", "")
AGENT_RESULT_NAME = "result.json"
# Nothing on the server outside this tree may be touched, by the daemon or by the
# drafting agent. Audited every round.
REMOTE_BOUNDARY = "/mnt/nas/gezuhao/xinghanbo"
MARK_TOOL = "scripts/recovery/skill_pipeline/mark_mining_intervention.py"
MINE_TOOL = "scripts/recovery/skill_pipeline/run_skill_mine.py"
MAX_ATTEMPTS = 5
LOCK_TIMEOUT_S = 2700
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
QUERY_KEY_WHITELIST = (
    "holding_status",
    "vla_pick_target_status",
    "target_ee_distance_m",
    "target_total_motion_m",
    "target_future_min_xy_distance_m",
    "nearest_pickable_is_target",
    "intent_object_is_target",
    "object_followed",
    "gripper_aperture",
    "label",
)


def run_quiet(*popenargs: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a child process without flashing a Windows console window."""

    if CREATE_NO_WINDOW:
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    return subprocess.run(*popenargs, **kwargs)


# --------------------------------------------------------------------------- ssh


@dataclass
class Remote:
    host: str = DEFAULT_SSH_HOST
    port: str = DEFAULT_SSH_PORT
    key: str = DEFAULT_SSH_KEY
    root: str = DEFAULT_REMOTE_ROOT
    python: str = DEFAULT_REMOTE_PYTHON
    dry_run: bool = False

    def base(self) -> list[str]:
        if not self.host or not self.key:
            raise RuntimeError(
                "mining ssh endpoint is unset: export MINING_SSH_HOST / MINING_SSH_KEY "
                "(and MINING_SSH_PORT) or pass --ssh-host / --ssh-key / --ssh-port"
            )
        return [
            "ssh",
            "-p",
            self.port,
            "-i",
            self.key,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "ConnectionAttempts=1",
            "-o",
            "ServerAliveInterval=10",
            "-o",
            "ServerAliveCountMax=2",
            f"root@{self.host}",
        ]

    def guard(self, path: str) -> str:
        from pathlib import PurePosixPath
        candidate = PurePosixPath(path)
        if ".." in candidate.parts or not candidate.is_relative_to(PurePosixPath(self.root)):
            raise SystemExit(f"refusing to touch a path outside {self.root}: {path}")
        return str(path)

    def run(self, command: str, *, check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
        if self.dry_run and not command.strip().startswith(("cat ", "ls ", "test ", "awk ")):
            print(f"[dry-run] ssh would run: {command[:180]}")
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
        done = run_quiet(
            [*self.base(), command], capture_output=True, encoding="utf-8", errors="replace", timeout=timeout
        )
        if check and done.returncode != 0:
            raise SystemExit(f"remote command failed ({done.returncode}): {command[:180]}\n{done.stderr[-600:]}")
        return done

    def run_script(self, script: str, *, check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
        """Send a python script over stdin; avoids nested quoting entirely."""
        done = run_quiet(
            [*self.base(), f"{self.python} -"],
            input=script,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if check and done.returncode != 0:
            raise SystemExit(f"remote script failed ({done.returncode})\n{done.stderr[-600:]}")
        return done

    def cat_json(self, path: str, *, timeout: int = 120) -> dict[str, Any]:
        text = self.run(f"cat {self.guard(path)}", timeout=timeout).stdout.strip()
        return json.loads(text) if text else {}

    def cat_text(self, path: str, *, timeout: int = 120, check: bool = True) -> str:
        return self.run(f"cat {self.guard(path)}", check=check, timeout=timeout).stdout

    def exists(self, path: str, *, timeout: int = 20) -> bool:
        try:
            return self.run(f"test -e {self.guard(path)}", check=False, timeout=timeout).returncode == 0
        except subprocess.TimeoutExpired:
            return False

    def push_dir(self, local_dir: Path, remote_dir: str, *, timeout: int = 600) -> None:
        """Copy ``local_dir`` to exactly ``remote_dir``.

        ``scp -r`` copies a directory *into* an existing target, so the push is
        staged under a temp name and renamed; otherwise a retry would end up with
        the drafts nested one level too deep and ingest would find nothing.
        """
        self.guard(remote_dir)
        if self.dry_run:
            print(f"[dry-run] scp -r {local_dir} -> {remote_dir}")
            return
        parent, name = remote_dir.rsplit("/", 1)
        staging = f"{parent}/.{name}.incoming"
        self.run(f"rm -rf {staging} && mkdir -p {staging}", timeout=timeout)
        done = run_quiet(
            [
                "scp",
                "-P",
                self.port,
                "-i",
                self.key,
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=no",
                "-r",
                str(local_dir),
                f"root@{self.host}:{staging}/",
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if done.returncode != 0:
            raise SystemExit(f"scp failed ({done.returncode})\n{done.stderr[-600:]}")
        self.run(
            f"rm -rf {remote_dir} && mv {staging}/{local_dir.name} {remote_dir} && rm -rf {staging}", timeout=timeout
        )


# ------------------------------------------------------------------ run discovery


def find_runs(remote: Remote, *, pattern: str = "*mining*", limit: int = 4, timeout: int = 120) -> list[str]:
    """Newest-first run directories under <remote-root>/logs matching the pattern."""
    glob_path = f"{remote.root}/logs/{pattern}"
    script = (
        "import glob, os, json\n"
        f"runs = [r for r in glob.glob({glob_path!r}) if os.path.isdir(r) and "
        "os.path.exists(os.path.join(r, 'codex_interventions'))]\n"
        "runs.sort(key=os.path.getmtime, reverse=True)\n"
        f"print(json.dumps(runs[:{int(limit)}]))\n"
    )
    raw = remote.run_script(script, timeout=timeout).stdout.strip()
    try:
        return [str(item) for item in json.loads(raw or "[]")]
    except Exception:
        return []


def run_config(remote: Remote, run_root: str) -> dict[str, str]:
    config: dict[str, str] = {"run_root": run_root}
    for line in remote.cat_text(f"{run_root}/run_config.txt", check=False).splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()
    try:
        lane = remote.cat_json(f"{run_root}/mine/lane_command.json", timeout=60)
    except Exception:
        lane = {}
    if isinstance(lane, dict):
        args = lane.get("args") if isinstance(lane.get("args"), dict) else {}
        repo = str(lane.get("repo_root") or lane.get("cwd") or args.get("repo_root") or "")
        python = str(args.get("python_bin") or "")
        if repo and not config.get("repo"):
            config["repo"] = repo
        if python and not config.get("python"):
            config["python"] = python
    return config


def lane_args(remote: Remote, run_root: str) -> dict[str, Any]:
    return dict(remote.cat_json(f"{run_root}/mine/lane_command.json").get("args") or {})


def run_status(remote: Remote, run_root: str) -> str:
    return remote.cat_text(f"{run_root}/status.txt", check=False).strip()


def is_waiting(remote: Remote, run_root: str) -> bool:
    """Hint only: a finished run leaves ``WAIT_CODEX.json`` behind, so never gate on this."""
    return remote.exists(f"{run_root}/mine/WAIT_CODEX.json")


def mine_state(remote: Remote, run_root: str) -> dict[str, Any]:
    try:
        return remote.cat_json(f"{run_root}/mine/mine_state.json", timeout=90)
    except (Exception, SystemExit):
        return {}


def liveness(remote: Remote, run_root: str) -> tuple[str, str, int]:
    """Authoritative verdict from ``mine_state.json``.

    ``status.txt`` and ``WAIT_CODEX.json`` both go stale (a finished run keeps the
    wait file and its ``wait_codex`` status), so the state machine is the only
    thing worth gating on. Returns ``(verdict, detail, awaiting_task)`` with
    verdict in ``needs_draft | awaiting_validation | finished | unknown``.
    """
    state = mine_state(remote, run_root)
    if not state:
        return "unknown", "mine_state.json missing or unreadable", 0
    awaiting = state.get("awaiting_task")
    if awaiting in (None, ""):
        return "finished", "mine_state has no awaiting task (stale WAIT_CODEX is expected)", 0
    task_id = int(awaiting)
    kind = str(state.get("awaiting_kind") or "")
    if kind == "draft":
        return "needs_draft", f"task{task_id:02d} is waiting for a draft", task_id
    if kind == "validation":
        return "awaiting_validation", f"task{task_id:02d} needs a validation run (resume the lane)", task_id
    return "unknown", f"awaiting_kind={kind!r}", task_id


# ----------------------------------------------------------------------- queue IO


def load_events(remote: Remote, run_root: str) -> list[dict[str, Any]]:
    data = remote.cat_json(f"{run_root}/codex_interventions/PENDING_CODEX_EVENTS.json", timeout=60)
    return [dict(item) for item in (data.get("pending_events") or [])]


def attempts_path(workdir: Path, event_id: str) -> Path:
    return workdir / "attempts" / f"{event_id}.json"


def load_attempts(workdir: Path, event_id: str) -> dict[str, Any]:
    path = attempts_path(workdir, event_id)
    if not path.exists():
        return {"event_id": event_id, "attempts": [], "needs_human": False}
    return json.loads(path.read_text(encoding="utf-8"))


def save_attempts(workdir: Path, event_id: str, payload: Mapping[str, Any]) -> Path:
    path = attempts_path(workdir, event_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, dict(payload))
    return path


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        output = run_quiet(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True).stdout
        return f'"{pid}"' in output
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def has_in_progress_attempt(state: Mapping[str, Any]) -> bool:
    for attempt in state.get("attempts") or []:
        if isinstance(attempt, Mapping) and bool(attempt.get("in_progress")):
            return True
    return False


def event_age_minutes(event: Mapping[str, Any]) -> float:
    """Age of an event in minutes, or -1 when the timestamp cannot be read.

    The watchdog writes ``created_at`` in UTC with a trailing ``Z``. Parsing that with
    ``time.strptime`` and diffing against ``time.mktime`` treats the UTC fields as
    *local* time, which inflated every age by the machine's UTC offset (8 h here) and made
    fresh events look older than ``--max-event-age-minutes``, so they were skipped.
    """

    created = str(event.get("created_at") or "").strip()
    if not created:
        return -1.0
    text = created[:-1] + "+00:00" if created.endswith("Z") else created
    try:
        when = datetime.datetime.fromisoformat(text)
    except ValueError:
        return -1.0
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - when).total_seconds() / 60.0


def pick_event(
    remote: Remote,
    run_root: str,
    workdir: Path,
    *,
    max_attempts: int,
    max_age_minutes: float = 0.0,
    force_stale: bool = False,
    retry_errors: bool = False,
) -> dict[str, Any] | None:
    """Oldest pending, unclaimed event for a run whose state machine wants a draft."""
    verdict, detail, awaiting = liveness(remote, run_root)
    if verdict != "needs_draft":
        print(f"{Path(run_root).name[:60]}: {verdict} - {detail}")
        return None
    current = mine_state(remote, run_root)
    writes = int(((current.get("tasks") or {}).get(str(awaiting)) or {}).get("writes") or 0)
    for event in sorted(load_events(remote, run_root), key=lambda item: str(item.get("created_at") or "")):
        event_id = str(event.get("event_id") or "")
        if not event_id:
            continue
        if int(event.get("task_id") or 0) != awaiting:
            continue
        if int(event.get("write_idx") or 0) != writes:
            continue
        state = load_attempts(workdir, event_id)
        attempts = len(state.get("attempts") or [])
        if (event.get("errored") or remote.exists(f"{event.get('event_dir')}/error.json")) and not retry_errors:
            continue
        if has_in_progress_attempt(state):
            continue
        if state.get("needs_human") or attempts >= max_attempts:
            continue
        if event.get("claimed"):
            if attempts == 0 and force_stale:
                print(f"recover stale claimed event with no local attempt: {event_id}")
            else:
                # A claim is an active lease. Do not auto-retry claimed events;
                # manual cleanup can clear a stale claim after confirming the
                # queued actor is no longer running.
                continue
        age = event_age_minutes(event)
        if max_age_minutes and age >= 0 and age > max_age_minutes and not force_stale:
            print(f"skip {event_id}: {age:.0f} min old (limit {max_age_minutes:.0f}); use --force-stale to override")
            continue
        if remote.exists(f"{event.get('event_dir')}/resolved.json"):
            continue
        return event
    return None


def scan_runs(
    remote: Remote,
    workdir: Path,
    *,
    pattern: str,
    max_runs: int,
    max_attempts: int,
    max_age_minutes: float = 0.0,
    force_stale: bool = False,
    retry_errors: bool = False,
) -> list[tuple[str, dict[str, Any] | None]]:
    """(run_root, event|None) for the newest runs, newest first."""
    return [
        (
            run_root,
            pick_event(
                remote,
                run_root,
                workdir,
                max_attempts=max_attempts,
                max_age_minutes=max_age_minutes,
                force_stale=force_stale,
                retry_errors=retry_errors,
            ),
        )
        for run_root in find_runs(remote, pattern=pattern, limit=max_runs)
    ]


# ---------------------------------------------------------------- local locking


def acquire_lock(workdir: Path, *, timeout_s: int = LOCK_TIMEOUT_S) -> bool:
    lock = workdir / "daemon.lock"
    if lock.exists():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
            started = float(data.get("started_at") or 0)
            pid = int(data.get("pid") or 0)
            if process_alive(pid):
                return False
            lock.unlink()
        except Exception:
            return False
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive creation prevents two schedulers claiming the same workdir.
        with lock.open("x", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "started_at": time.time()}, handle)
    except FileExistsError:
        return False
    return True


def release_lock(workdir: Path) -> None:
    try:
        (workdir / "daemon.lock").unlink()
    except OSError:
        pass


# ------------------------------------------------------------------ evidence pack


def summarize_fail_set(fail_set: Mapping[str, Any], *, max_episodes: int = 15) -> str:
    """Compact, greppable summary; the full traces stay remote."""
    mine = dict(fail_set.get("mine") or {})
    lines = [
        f"- task: {fail_set.get('task')}",
        f"- track: {fail_set.get('track')}  pack_kind: {fail_set.get('pack_kind')}",
        f"- mine action/reason: {mine.get('action')} / {mine.get('reason')}",
        f"- library skill ids: {mine.get('library_skill_ids')}",
        f"- mine instruction: {str(mine.get('instruction') or '')[:600]}",
        f"- failures: {len(fail_set.get('failures') or [])}",
        "",
        "| ep | seed | success | recovery_events | queries | last-query signals |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in list(fail_set.get("failures") or [])[:max_episodes]:
        queries = list(row.get("queries") or [])
        last = queries[-1] if queries else {}
        signals = ", ".join(f"{key}={last.get(key)}" for key in QUERY_KEY_WHITELIST if key in last)
        lines.append(
            f"| {row.get('episode_idx')} | {row.get('seed')} | {row.get('success')} | "
            f"{row.get('recovery_event_count')} | {len(queries)} | {signals[:180]} |"
        )
    for frame in list(fail_set.get("aligned_frames") or [])[:6]:
        lines.append(
            f"- aligned frame slot={frame.get('slot')} query_idx={frame.get('query_idx')} fail={frame.get('fail_frame')}"
        )
    lines.append("")
    lines.append("Full evidence stays on the remote host; read it on demand (do not copy the whole corpus):")
    for row in list(fail_set.get("failures") or [])[:3]:
        if row.get("episode_dir"):
            lines.append(f"- {row['episode_dir']}  (query_trace.jsonl, recovery_trace.jsonl, frames/)")
    return "\n".join(lines)


def verdict_section(remote: Remote, run_root: str, task_id: int) -> str:
    path = f"{run_root}/mine/task{task_id:02d}/actor_prompt.md"
    return remote.run(
        f"awk '/^## Verdict on the previous rounds/,/^## Rollout evidence/' {remote.guard(path)} 2>/dev/null | head -c 4000",
        check=False,
        timeout=30,
    ).stdout.strip()


# --------------------------------------------------------------------- the prompt


def strict_schema_error(schema: Mapping[str, Any]) -> str:
    """Return why a strict structured-output schema would be rejected, or "" when it is fine.

    Strict mode requires every key in ``properties`` to also appear in ``required``; violating
    that makes the API answer ``invalid_json_schema`` before the model ever runs.
    """

    properties = dict(schema.get("properties") or {})
    required = [str(item) for item in (schema.get("required") or [])]
    missing = sorted(set(properties) - set(required))
    if missing:
        return f"properties missing from required: {missing}"
    unknown = sorted(set(required) - set(properties))
    if unknown:
        return f"required keys without properties: {unknown}"
    if schema.get("additionalProperties") is not False:
        return "additionalProperties must be false"
    return ""


def output_schema() -> dict[str, Any]:
    """Structured-output schema for one drafting round, validated before it is sent."""

    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "files", "bundle_yaml", "draft_md", "code_manifest", "notes"],
        "properties": {
            "status": {"type": "string", "enum": ["drafted", "failed"]},
            "files": {"type": "array", "items": {"type": "string"}},
            "bundle_yaml": {"type": "string"},
            "draft_md": {"type": "string"},
            "code_manifest": {"type": "string"},
            "notes": {"type": "string"},
        },
    }
    problem = strict_schema_error(schema)
    if problem:
        raise ValueError(f"output schema would be rejected by strict structured outputs: {problem}")
    return schema


def previous_ingest_failure(state: Mapping[str, Any]) -> str:
    """What the ingest gate said about the most recent refused draft, if anything."""

    for attempt in reversed(list(state.get("attempts") or [])):
        ingest = attempt.get("ingest") or {}
        if ingest.get("ok"):
            return ""
        if not ingest:
            continue
        errors = ingest.get("errors") or []
        text = "; ".join(str(item) for item in errors) if errors else str(ingest.get("raw") or "")
        return text.strip()[-1500:]
    return ""


def previous_findings(workdir: Path, run_root: str, task_id: int) -> str:
    records = []
    for path in (workdir / "attempts").glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for attempt in payload.get("attempts") or []:
            if attempt.get("run_root") != run_root or attempt.get("task_id") != task_id:
                continue
            finding = Path(attempt["round_dir"]) / "drafts/findings.md"
            if finding.is_file():
                records.append((attempt.get("at", ""), finding, attempt.get("phase", "unknown")))
    return "\n\n".join(f"{p} (phase={phase})\n{p.read_text(encoding='utf-8')}"
                         for _, p, phase in sorted(records)[-3:])


def collect_remote_context(remote: Remote, repo: str, run_root: str, evidence: str, task_id: int) -> dict:
    cmd = [remote.python, f"{repo}/scripts/recovery/skill_pipeline/actor_context.py",
           "--run-root", remote.guard(run_root), "--evidence", remote.guard(evidence), "--task", str(task_id)]
    return json.loads(remote.run(shlex.join(cmd), timeout=180).stdout)


def context_is_current(remote: Remote, run_root: str, context: Mapping[str, Any]) -> bool:
    if remote.exists(f"{run_root}/mine/STOPPED_BY_USER.txt"):
        return False
    identity = context["identity"]
    state = mine_state(remote, run_root)
    task_id = int(identity["task_id"])
    entry = (state.get("tasks") or {}).get(str(task_id)) or {}
    if (state.get("awaiting_kind") != "draft" or int(state.get("awaiting_task") or 0) != task_id
            or int(entry.get("writes") or 0) != identity["writes_used"]):
        return False
    fresh = collect_remote_context(remote, identity["repo"], run_root, identity["evidence_path"], task_id)
    return (fresh["identity"] == identity and fresh["pack_files_sha256"] == context["pack_files_sha256"])


def predicate_vocabulary() -> tuple[str, str]:
    """The trigger / applies_to predicate names this pipeline actually accepts.

    Read from the registry source instead of importing it, so the daemon needs
    neither the package on sys.path nor its dependencies. Empty strings mean the
    registry could not be read, and the prompt then omits the section rather than
    claiming an empty vocabulary.
    """

    path = (Path(__file__).resolve().parents[3]
            / "experiments/robot/libero/skill_pipeline/predicate_registry.py")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "", ""

    def names(constant: str) -> str:
        match = re.search(rf"^{constant}\s*=\s*frozenset\(", text, re.M)
        if not match:
            return ""
        tail = text[match.end():]
        stop = tail.find("\n)")
        block = tail[: stop if stop >= 0 else len(tail)]
        return ", ".join(sorted(set(re.findall(r'"([a-z0-9_]+)"', block))))

    return names("BUILTIN_TRIGGER_PREDICATES"), names("BUILTIN_APPLIES_PREDICATES")


def draft_format_sections() -> list[str]:
    """The file format the gate demands, plus the predicate names it will accept.

    Both were measured rejections in the first live rounds: a body with no `---`
    front matter, and an invented trigger predicate. Stating them costs a few
    hundred tokens and removes a whole class of refused drafts.
    """
    trigger, applies = predicate_vocabulary()
    parts = [
        "## Draft file format (the gate is strict)",
        "",
        "A skill markdown file must begin with a line containing exactly `---`, then the YAML block,",
        "then a closing `---` line, and only then the prose body. A file that starts with `id:` and no",
        "opening fence is rejected outright as `skill file must start with YAML front matter`.",
        "",
    ]
    if trigger or applies:
        parts.extend(["## Predicate names you may use", ""])
        if trigger:
            parts.extend([
                "`trigger:` conditions. Use these names verbatim; any other name is a schema error:",
                "",
                f"  {trigger}",
                "",
            ])
        if applies:
            parts.extend([
                "`applies_to:` conditions. Same rule:",
                "",
                f"  {applies}",
                "",
            ])
    return parts


def output_language_sections() -> list[str]:
    """The operator reads these rounds, so the prose is Chinese.

    Identifiers stay English: a translated predicate name or YAML key is a schema
    error, not a translation.
    """
    return [
        "## 输出语言（重要）",
        "",
        "- 用**中文**写：`findings.md`、`draft.md` 的正文说明、最终回复，以及 `result.json` 的 `summary`。",
        "- 但 `id`、YAML 键名、判定词名（predicate）、`hook`、`backend`、文件名等**代码标识符保持英文原样**；",
        "  翻译它们会导致校验或加载失败。",
        "- 说明性文字、结论、判断理由一律中文，让不看代码的人也能读懂这一轮发生了什么。",
        "",
    ]


def server_boundary_sections(allowed_prefix: str = REMOTE_BOUNDARY) -> list[str]:
    """One hard boundary, stated once and audited every round afterwards."""
    return [
        "## 远端硬边界（违反即视为失败）",
        "",
        f"- 只允许访问 `{allowed_prefix}` **之下**的路径。",
        "- 除此之外的任何远端路径：`ls`、`cat`、`find`、`cd`、读取、写入、删除，**一律不允许**。",
        "- 远端只允许写两个地方：本 run 的 `mine/` 目录，和本 run 自己的 skill pack。",
        "- 不要碰别人的目录，不要安装软件包，不要修改系统文件，不要重启任何服务。",
        "- 每轮结束前自检：把你这一轮执行过的每条远端命令里的路径列出来，确认全部在允许范围内；",
        "  一旦越界，立刻停止，并在 `result.json` 里写 `status: failed` 和越界内容。",
        "",
    ]


SYSTEM_READ_ONLY_PATHS = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/fd", "/proc/self")

WRITE_HINTS = ("rm ", "mv ", "mkdir", "cp ", "touch ", "chmod", "chown", "sed -i",
               "tee ", "truncate", "dd ", "ln -s", "install ", ">>", ">")

POSIX_PATH = re.compile(r"(?<![\w.-])/(?:[\w.@+-]+/)*[\w.@+-]*")


def collect_agent_commands(rollout_path: Path, since_epoch: float = 0.0) -> list[str]:
    """Every shell command the drafting agent ran, newest rollout first."""
    commands: list[str] = []
    for line in rollout_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = event.get("payload") or {}
        if payload.get("type") != "function_call":
            continue
        name = str(payload.get("name") or "").lower()
        if "command" not in name and "shell" not in name:
            continue
        if since_epoch:
            stamp = event.get("timestamp")
            try:
                when = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
            except (TypeError, ValueError):
                when = 0.0
            if when and when < since_epoch:
                continue
        try:
            parsed = json.loads(payload.get("arguments") or "{}")
        except json.JSONDecodeError:
            parsed = {"cmd": str(payload.get("arguments"))}
        commands.append(str(parsed.get("cmd") or parsed.get("command") or parsed))
    return commands


def find_thread_rollout(thread_id: str) -> Path | None:
    root = Path(os.environ.get("USERPROFILE", "")) / ".codex" / "sessions"
    if not root.is_dir() or not thread_id:
        return None
    matches = [path for path in root.rglob(f"*{thread_id}.jsonl") if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def audit_commands(commands: Sequence[str], *, allowed_prefix: str = REMOTE_BOUNDARY) -> dict[str, Any]:
    """Which paths the commands mention, and which outside ones look like writes.

    Reads of system files are reported but not called violations; a path outside
    the allowed prefix inside a write-like command is.
    """
    outside: set[str] = set()
    outside_writes: set[str] = set()
    for command in commands:
        writes = any(hint in command for hint in WRITE_HINTS)
        for match in POSIX_PATH.findall(command):
            path = match.rstrip("/")
            if path.count("/") < 2 or path.startswith(allowed_prefix):
                continue
            if path.startswith(SYSTEM_READ_ONLY_PATHS):
                continue
            outside.add(path)
            if writes:
                outside_writes.add(path)
    return {
        "commands": len(commands),
        "outside_paths": sorted(outside),
        "outside_writes": sorted(outside_writes),
        "clean": not outside_writes,
    }


def parse_launcher_env(text: str) -> str:
    """The assignment/export preamble of a rendered launch script.

    The launcher sets WORKSPACE/REPO/RUN_ROOT first and exports PYTHONPATH from
    them, so both halves are required. `set -u`, comments and blanks are skipped;
    the first line that is neither an assignment nor an export is the script's
    real work and ends the scan.
    """

    kept: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("set "):
            continue
        if line.startswith("export ") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", line):
            kept.append(raw.rstrip())
            continue
        break
    return "\n".join(kept) + ("\n" if kept else "")


def launcher_env_body(remote: Remote, run_root: str) -> str:
    """Read the run's own launcher and return the environment it used."""
    script = (
        "import glob, os\n"
        f"files = sorted(glob.glob({run_root!r} + '/launch_*.sh'), "
        "key=os.path.getmtime, reverse=True)\n"
        "print(files[0] if files else '')\n"
    )
    name = (remote.run_script(script, check=False).stdout or "").strip()
    if not name:
        return ""
    return parse_launcher_env(remote.cat_text(name, check=False))


def resume_command(*, run_root: str, repo: str, argv: str, log: str, env_body: str) -> str:
    """Relaunch the lane with the launcher's environment, not the daemon's.

    A resumed lane that inherits the wrong PYTHONPATH imports a different LIBERO:
    measured, that is what produced `KeyError: 'libero_goal_task'`.
    """

    env_file = f"{run_root}/mine/lane_env.sh"
    body = f"{argv}; rc=$?; printf '%s\\n' \"$rc\" > {run_root}/mine/mining_lane.exit_code; exit $rc"
    return (
        f"mkdir -p {run_root}/mine/lane_logs; "
        f"cat > {env_file} <<'CODEX_LANE_ENV'\n{env_body}CODEX_LANE_ENV\n"
        f"if ! grep -q PYTHONPATH {env_file}; then "
        f"echo 'WARNING: lane_env.sh carries no PYTHONPATH; the lane may import the wrong LIBERO'"
        f" >> {log}; fi; "
        f"cd {repo}; set -a; . {env_file}; set +a; "
        f"nohup flock -n {run_root}/mine/lane.lock bash -c {shlex.quote(body)} >> {log} 2>&1 < /dev/null & "
        f"echo $! > {run_root}/mine/lane.pid"
    )


def _read_prompt_limited(path: Path, *, max_chars: int = 24000) -> str:
    text = path.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[truncated for actor prompt]\n"


def _guideline_excerpt(repo: Path) -> str:
    return guideline_index(repo)


def actor_guidelines_with_type_docs(repo: Path) -> str:
    """Return the same authoring guidance used by the offline actor prompt.

    Keep this loader self-contained. Queue delivery often runs the daemon from a
    work directory where ``scripts`` is not importable as a package, and an
    import-based loader silently dropped the per-skill-type docs from prompts.
    """

    prompt_path = repo / "scripts/recovery/skill_pipeline/prompts/actor.md"
    chunks = []
    if prompt_path.exists():
        chunks.append(prompt_path.read_text(encoding="utf-8"))
    else:
        chunks.append(f"(missing actor prompt: {prompt_path})")
    chunks.extend(["## Skill-type authoring guidelines", "", _guideline_excerpt(repo)])
    return "\n\n".join(chunk for chunk in chunks if chunk)


def stage_actor_tools(remote: Remote, repo: Path, run_root: str, round_dir: Path) -> str:
    names = ("probe_recovery.py", "check_actor_drafts.py", "ingest_actor_candidate.py")
    contents = {name: (repo / "scripts/recovery/skill_pipeline" / name).read_bytes().replace(b"\r\n", b"\n")
                for name in names}
    digest = hashlib.sha256(b"".join(name.encode() + contents[name] for name in names)).hexdigest()[:20]
    target = f"{run_root}/mine/actor_tools/{digest}"
    source = round_dir / "tooling"
    source.mkdir(exist_ok=True)
    for name, data in contents.items():
        (source / name).write_bytes(data)
    if not remote.exists(f"{target}/probe_recovery.py"):
        remote.push_dir(source, target)
    return target + "/probe_recovery.py"


def compose_prompt(
    *,
    guidelines: str,
    capability_excerpt: str,
    library_index: str,
    summary: str,
    verdict: str,
    previous_failure: str = "",
    ssh_command: str,
    run_root: str,
    drafts_dir: str,
    write_idx: int,
    finish_instruction: str = "Finish by printing the JSON object required by the output schema.",
    context_path: str = "",
    handoff: str = "",
) -> str:
    """Small by design: guidelines + summary + verdict; evidence is grepped on demand."""
    parts = [
        "# Mining actor run (harness-driven)",
        "",
        "## Hard constraints for this harness run",
        "",
        f"- You are round `w{write_idx}` of the mining run `{run_root}`.",
        f"- Write the deliverable bundle into: `{drafts_dir}`. Keep research/probe files in its parent work directory or this run's mine/probes/.",
        "  Required: `findings.md`, plus either `bundle.yaml` (+ `drafts/**`) or `draft.md`.",
        "  If you change Python or profile YAML, also write `code_patch_manifest.yaml`.",
        "  Put complete replacement code/profile/registry files under `drafts/patch/skill_packs/<active-pack>/...`.",
        "  Manifest touched_files use repository-relative paths. Markdown skill files are listed in bundle.yaml,",
        "  with paths relative to drafts/. Do not directly modify the live pack; the daemon applies patch/",
        "  before admission and rolls it back on rejection. Never copy skills/_index.yaml or pack.yaml into patch/.",
        "- A diagnostics-only or blocker-only answer is invalid. The bundle must contain at least",
        "  one executable repair/trigger skill or recovery_hint. If the failure looks like planner,",
        "  grounding, geometry, place or executor trouble, write a pack-local profile/adapter/code",
        "  change that the admission gate can ingest and validate.",
        "- Never create, modify or delete any other remote file. The only remote locations this",
        "  run may touch are its own `mine/` directory and its own skill pack.",
        "- The rollout evidence is **not** inlined. Read it on demand, for example:",
        "  Use the provided local Python transport, which pins the host, key and run environment:",
        "  python remote.py read /absolute/remote/file --start 1 --lines 160",
        "  python remote.py list /absolute/remote/directory",
        "  python remote.py get /absolute/remote/frame.jpg evidence/frame.jpg",
        "  For analysis, write inspect.py locally, then: python remote.py script inspect.py",
        "  For forced recovery use ONLY: python remote.py probe-recovery --seed 51 --query 10",
        "  Add --dry-run to inspect the exact inherited command, --preflight-only to check the eval interpreter.",
        "  Test draft profiles without changing the active pack: add --draft-dir drafts.",
        "  Run existing schema/static/runtime checks: python remote.py check-drafts --draft-dir drafts",
        "  Write a UTF-8 patch file locally, then apply it using: python apply_patch.py change.patch",
        "  Do not rebuild predicate allowlists or hand-write a rollout CLI. --planning is only for",
        "  saved cuTAMP problem replay; never use it to launch Pi0, JAX or run_skill_eval.py.",
        "  Use view_image on downloaded frames. Do not assume jq is installed or nest Python/Bash",
        "  inside PowerShell strings. Prefer this transport to multi-shell commands.",
        f"  `{ssh_command} \"sed -n '1,80p' <file>\"` or `... \"grep -n <pattern> <file> | head\"`",
        f"- {finish_instruction.strip()}",
        "- Own the diagnosis and repair, not just file submission. Read relevant type guides, inspect",
        "  frames and traces, trace the failing operation into code, and test a concrete hypothesis.",
        "  You may run small deterministic replays and pack-local checks inside this intervention.",
        "  Fix schema/registration/test failures here. They are not new skill versions.",
        "  Do not ingest or launch the formal validation yourself; the daemon owns that transaction.",
        "  Do not change shared engine code, benchmark goals, scoring or environment to make a task pass.",
        "  Use this run's baseline/validation and active pack. Do not inspect other packs, archived skills,",
        "  or later successful validations from the historical source run; they are not this intervention's evidence.",
        "- Persist findings.md as you work: hypothesis, evidence paths, code inspected, guides read,",
        "  tests/replays actually run and observed results, remaining uncertainty, and expected change",
        "  in the next validation. Distinguish observations from untested hypotheses.",
        f"- Read the authoritative context JSON first: `{context_path}`. Its suite/BDDL/pack identity overrides legacy display labels.",
        "",
        "## Task authoring guidelines (actor.md + skill-type docs)",
        "",
        guidelines.strip(),
        "",
        "## Capability registry of the active pack",
        "",
        capability_excerpt.strip() or "(none declared)",
        "",
        "## Current skill library index",
        "",
        library_index.strip() or "(empty library)",
        "",
    ]
    parts.extend(draft_format_sections())
    parts.extend(output_language_sections())
    parts.extend(server_boundary_sections())
    if verdict:
        parts.extend(["## Previous rounds in this run", "", verdict.strip(), ""])
    if handoff:
        parts.extend(["## Previous intervention findings (check against validation)", handoff, ""])
    if previous_failure:
        parts.extend([
            "## Your previous draft was rejected",
            "",
            "The ingest gate refused the previous draft. Fix exactly this before drafting:",
            "",
            "```",
            previous_failure.strip()[:1500],
            "```",
            "",
        ])
    parts.extend(["## Evidence summary (fail_set)", "", summary.strip(), ""])
    return "\n".join(parts)


# ------------------------------------------------------------------- codex runner


MANIFEST_NAME = "code_patch_manifest.yaml"


def run_codex(
    *,
    codex_exe: str,
    workdir: Path,
    prompt_path: Path,
    schema_path: Path,
    model: str,
    timeout: int,
    sandbox: str = "workspace-write",
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> tuple[int, str]:
    cmd = [
        codex_exe,
        "exec",
        "--json",
        "--skip-git-repo-check",
        "-s",
        sandbox,
        "-C",
        str(workdir),
        "--output-schema",
        str(schema_path),
        "-c", f'model_reasoning_effort="{reasoning_effort}"',
        "-c", 'approval_policy="never"',
        "--output-last-message", str(workdir / "actor_final.json"),
    ]
    if model:
        cmd.extend(["-m", model])
    cmd.append("-")
    stream = workdir / "codex_output.jsonl"
    lifecycle = workdir / "actor_process.json"
    with prompt_path.open("r", encoding="utf-8") as handle, stream.open("w", encoding="utf-8") as output, \
            (workdir / "codex_stderr.log").open("w", encoding="utf-8") as errors:
        proc = subprocess.Popen(cmd, stdin=handle, stdout=output, stderr=errors, creationflags=CREATE_NO_WINDOW)
        record = {"pid": proc.pid, "owner_pid": os.getpid(), "model": model,
                  "reasoning_effort": reasoning_effort, "phase": "agent_running", "started_at": time.time()}
        atomic_json(lifecycle, record)
        deadline = time.monotonic() + timeout
        while proc.poll() is None:
            record["heartbeat_at"] = time.time()
            record["output_bytes"] = stream.stat().st_size
            atomic_json(lifecycle, record)
            if time.monotonic() >= deadline:
                proc.terminate()
                proc.wait()
                record.update(phase="agent_timeout", exit_code=proc.returncode)
                atomic_json(lifecycle, record)
                return -1, f"codex exec timed out after {timeout}s; work files preserved"
            time.sleep(2)
        record.update(phase="agent_finished", exit_code=proc.returncode, completed_at=time.time())
        atomic_json(lifecycle, record)
    tail = stream.read_text(encoding="utf-8", errors="replace")[-4000:]
    final = workdir / "actor_final.json"
    if proc.returncode == 0:
        try:
            payload = json.loads(final.read_text(encoding="utf-8"))
            if payload.get("status") != "drafted":
                return 1, str(payload.get("notes") or "actor did not finish a candidate")
        except (OSError, ValueError) as exc:
            return 1, f"missing or invalid actor final result: {exc}"
    return proc.returncode, tail


def queue_message(
    *, event_id: str, write_idx: int, prompt_path: Path, drafts_dir: Path, result_path: Path
) -> str:
    """The short message handed to the desktop agent; the task itself stays in prompt_path."""
    return "\n".join(
        [
            f"[mining intervention] event {event_id}, round w{write_idx}.",
            "",
            f"Read this file and follow it exactly; it is the complete task: {prompt_path}",
            "",
            f"Write every artifact into: {drafts_dir}",
            f"Write the completion marker LAST: {result_path}",
            '  content: {"status": "ok", "summary": "<one line>"}   (use "failed" if you could not)',
            "",
            "The ssh command, the evidence paths and the rules are inside the prompt file.",
            "Touch nothing on the remote except the run's own mine/ directory and its own skill",
            "pack, and nothing at all outside /mnt/nas/gezuhao/xinghanbo.",
            "Do not return a blocker-only or diagnostics-only bundle; write an executable skill,",
            "hint, profile or pack-local adapter that admission can ingest.",
            "Write findings.md, your final message and the result.json summary in Chinese (中文);",
            "keep ids, YAML keys and predicate names in English.",
            "Do not ask questions: nobody is watching this run, and the daemon is blocked",
            "on the marker file.",
        ]
    )


def deliver_via_queue(
    *, codex_exe: str, thread: str, message: str, timeout: int = 180,
    model: str = DEFAULT_MODEL, reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> tuple[bool, str]:
    """Hand one round to the desktop agent. Returns (delivered, detail)."""
    try:
        done = run_quiet(
            [codex_exe, "queue", "--thread", thread, "--message", message,
             "-m", model, "-c", f'model_reasoning_effort="{reasoning_effort}"'],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"codex queue timed out after {timeout}s"
    text = ((done.stdout or "") + (done.stderr or "")).strip()
    if done.returncode == 0:
        return True, text[-400:] or "queued"
    return False, f"codex queue exited {done.returncode}: {text[-600:]}"


def wait_for_agent_result(
    *, result_path: Path, timeout: int, poll_seconds: int = 15, sleep: Any = time.sleep
) -> tuple[bool, str]:
    """Block until the agent writes result.json. Returns (ok, detail).

    The marker is the only completion signal available over `codex queue`, so a
    missing marker is a failed attempt rather than a silent success.
    """
    deadline = time.monotonic() + max(1, timeout)
    while True:
        if result_path.is_file():
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError as exc:
                return False, f"{result_path.name} is not valid JSON: {exc}"
            if not isinstance(payload, Mapping):
                return False, f"{result_path.name} must be a JSON object"
            status = str(payload.get("status") or "").strip().lower()
            summary = " ".join(str(payload.get("summary") or "").split())[:400]
            if status == "ok":
                return True, summary or "agent reported ok"
            return False, f"agent reported {status or 'no status'}: {summary}"
        if time.monotonic() >= deadline:
            return False, f"agent did not write {result_path.name} within {timeout}s"
        sleep(poll_seconds)


def verify_drafts(drafts: Path) -> tuple[bool, str]:
    if not drafts.is_dir():
        return False, "drafts directory was not created"
    files = [path for path in drafts.rglob("*") if path.is_file()]
    if not files:
        return False, "drafts directory is empty"
    names = {path.name for path in files}
    if "findings.md" not in names:
        return False, "findings.md is missing"
    if "bundle.yaml" not in names and not any(path.suffix == ".md" and path.name != "findings.md" for path in files):
        return False, "neither bundle.yaml nor a draft markdown was produced"
    bundle = drafts / "bundle.yaml"
    if bundle.is_file():
        try:
            payload = yaml.safe_load(bundle.read_text(encoding="utf-8")) or {}
        except Exception as exc:  # noqa: BLE001 - report YAML/parser failures to the agent.
            return False, f"bundle.yaml is not valid YAML: {exc}"
        if not isinstance(payload, Mapping):
            return False, "bundle.yaml must be a YAML mapping"
        for idx, item in enumerate(payload.get("drafts") or []):
            if not isinstance(item, Mapping):
                return False, f"bundle.yaml drafts[{idx}] must be a mapping"
            raw_file = str(item.get("file") or "").strip()
            if not raw_file:
                return False, f"bundle.yaml drafts[{idx}] is missing file"
            ref = Path(raw_file)
            if ref.is_absolute() or ".." in ref.parts:
                return False, f"bundle.yaml drafts[{idx}] has unsafe file path: {raw_file}"
            if not (drafts / ref).is_file():
                return False, f"bundle.yaml references missing file: {raw_file}"
    return True, f"{len(files)} file(s)"


# ------------------------------------------------------------------------- ingest


def ingest_command(
    *,
    remote: Remote,
    config: Mapping[str, str],
    args: Mapping[str, Any],
    task_id: int,
    draft_dir: str,
    write_idx: int,
) -> str:
    repo = str(config.get("repo") or "")
    python = str(config.get("python") or remote.python)
    run_root = str(config["run_root"])
    mine_dir = f"{run_root}/mine"
    skill_pack = str(args.get("skill_pack") or config.get("skill_pack") or "")
    baseline = str(args.get("baseline_run_dir") or f"{run_root}/baseline_task{task_id:02d}")
    skills_dir = str(args.get("skills_dir") or f"{repo}/skill_packs/{skill_pack}/skills")
    max_writes = int(args.get("max_writes_per_task") or MAX_ATTEMPTS)
    flags = [
        f"{python} scripts/recovery/skill_pipeline/ingest_actor_candidate.py ingest",
        f"--run_dir {baseline}",
        f"--out_dir {mine_dir}",
        f"--skill_pack {skill_pack}",
        f"--skills_dir {skills_dir}",
        f"--task_ids {task_id}",
        f"--task_id {task_id}",
        f"--draft_dir {draft_dir}",
        f"--max_writes_per_task {max_writes}",
    ]
    if remote.exists(f"{draft_dir}/{MANIFEST_NAME}"):
        # Only run the code gate when the round actually shipped a manifest; a pure
        # skill-markdown draft has nothing to check and must not be rejected.
        flags.extend(
            [
                f"--code_manifest {draft_dir}/{MANIFEST_NAME}",
                "--enable_code_admission_gate",
                f"--code_admission_out_dir {mine_dir}/task{task_id:02d}/code_admission_w{write_idx}",
            ]
        )
    flags.extend(
        [
            "--enable_admission_gate",
            f"--admission_out_dir {mine_dir}/task{task_id:02d}/admission_w{write_idx}",
        ]
    )
    corpus = config.get("admission_corpus_root") or args.get("offline_scan_corpus_root")
    if corpus:
        flags.extend(["--admission_corpus_root", shlex.quote(remote.guard(str(corpus)))])
    rolling = args.get("offline_scan_corpus_root")
    if rolling and corpus != rolling:
        flags.extend(["--admission_scan_root", shlex.quote(remote.guard(str(rolling)))])
    return f"cd {repo} && " + " ".join(flags)


def mark_command(remote: Remote, config: Mapping[str, str], action: str, event_id: str, extra: str = "") -> str:
    repo = str(config.get("repo") or "")
    python = str(config.get("python") or remote.python)
    run_root = str(config["run_root"])
    # The extra args are pasted into a single-quoted shell string, so quotes inside
    # a message or a JSON blob would break the command.
    safe_extra = " ".join(str(extra).split())
    # Free-text values must survive one shell hop: quote them rather than stripping the caller's
    # quotes, which used to split the message into extra positional arguments.
    if safe_extra.startswith("--message "):
        value = safe_extra[len("--message "):].replace("'", "").replace('"', "")
        safe_extra = f"--message {shlex.quote(value)}"
    return (
        f"cd {repo} && {python} {MARK_TOOL} {action} "
        f"--event-root {run_root}/codex_interventions --event-id {event_id} {safe_extra}"
    ).strip()


# --------------------------------------------------------------------------- main


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser("Drive one mining Codex intervention.")
    parser.add_argument("--run-root", default="", help="Single remote run dir (default: scan newest runs).")
    parser.add_argument("--run-pattern", default="*mining*")
    parser.add_argument("--max-runs", type=int, default=4, help="How many newest runs to scan for waiting events.")
    parser.add_argument("--ssh-host", default=DEFAULT_SSH_HOST)
    parser.add_argument("--ssh-port", default=DEFAULT_SSH_PORT)
    parser.add_argument("--ssh-key", default=DEFAULT_SSH_KEY)
    parser.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT)
    parser.add_argument("--codex-exe", default=DEFAULT_CODEX_EXE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high", "xhigh"), default=DEFAULT_REASONING_EFFORT)
    parser.add_argument("--workdir", default=DEFAULT_WORKDIR)
    parser.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS)
    parser.add_argument(
        "--max-event-age-minutes",
        type=float,
        default=180.0,
        help="Skip events older than this (finished runs leave stale wait files behind); 0 disables.",
    )
    parser.add_argument("--force-stale", action="store_true", help="Process an event even if it looks stale.")
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Retry events already marked with error.json. Default: errored events are terminal.",
    )
    parser.add_argument(
        "--executor",
        choices=("queue", "exec"),
        default="exec",
        help="Who writes the draft: the Codex desktop agent via `codex queue` (default), "
        "or the sandboxed `codex exec`.",
    )
    parser.add_argument(
        "--agent-thread",
        default=DEFAULT_AGENT_THREAD,
        help="Desktop-agent thread id that receives rounds in --executor queue mode "
        "(or set CODEX_AGENT_THREAD).",
    )
    parser.add_argument("--agent-poll-seconds", type=int, default=15)
    parser.add_argument(
        "--exec-sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default="danger-full-access",
        help="exec mode: sandbox for the drafting agent. Defaults to full access because the ssh "
        "key lives outside any workspace, which workspace-write cannot read (measured).",
    )
    parser.add_argument(
        "--codex-timeout",
        type=int,
        default=7200,
        help="exec mode: wall clock for `codex exec`. queue mode: how long to wait for result.json.",
    )
    parser.add_argument("--lock-timeout", type=int, default=LOCK_TIMEOUT_S)
    parser.add_argument(
        "--resume-stalled",
        action="store_true",
        help="Also relaunch the lane for runs stuck in awaiting_validation (no draft needed).",
    )
    parser.add_argument("--stalled-minutes", type=float, default=30.0)
    parser.add_argument("--list", action="store_true", help="Read-only queue view; writes nothing.")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; writes nothing.")
    return parser.parse_args(argv)


def cmd_list(remote: Remote, workdir: Path, args: argparse.Namespace) -> int:
    for run_root in find_runs(remote, pattern=args.run_pattern, limit=args.max_runs):
        verdict, detail, awaiting = liveness(remote, run_root)
        events = load_events(remote, run_root)
        live = (
            [
                str(item.get("event_id"))
                for item in events
                if not item.get("claimed") and int(item.get("task_id") or 0) == awaiting
            ]
            if verdict == "needs_draft"
            else []
        )
        print(f"{Path(run_root).name[:62]:<62} {verdict:<20} events={len(events)} live={live or '-'}")
        print(f"    status.txt={run_status(remote, run_root)!r} wait_file={is_waiting(remote, run_root)} :: {detail}")
    return 0


def cmd_resume_stalled(remote: Remote, args: argparse.Namespace, workdir: Path) -> int:
    """Relaunch lanes that exited in the middle of a validation run."""
    resumed = 0
    for run_root in find_runs(remote, pattern=args.run_pattern, limit=args.max_runs):
        verdict, detail, _ = liveness(remote, run_root)
        if verdict != "awaiting_validation":
            continue
        step_path = f"{run_root}/mine/last_step.json"
        if not remote.exists(step_path):
            continue
        script = (
            "import os, time, sys\n"
            f"p = {step_path!r}\n"
            "print(int((time.time() - os.path.getmtime(p)) / 60))\n"
        )
        age = float((remote.run_script(script, check=False).stdout or "0").strip() or 0)
        if age < args.stalled_minutes:
            print(f"{Path(run_root).name[:60]}: awaiting_validation but only {age:.0f} min old; leaving it alone")
            continue
        config = run_config(remote, run_root)
        repo = str(config.get("repo") or "")
        argv = " ".join(str(item) for item in (remote.cat_json(f"{run_root}/mine/lane_command.json").get("argv") or []))
        if not argv:
            print(f"{Path(run_root).name[:60]}: no lane_command argv; cannot resume")
            continue
        log = f"{run_root}/mine/lane_logs/resume_stalled_{time.strftime('%Y%m%d_%H%M')}.log"
        if args.dry_run:
            print(f"[dry-run] would resume stalled lane: {Path(run_root).name}")
            continue
        env_body = launcher_env_body(remote, run_root)
        if not env_body:
            print(f"{Path(run_root).name[:60]}: no launcher environment found; the lane may import the wrong LIBERO")
        remote.run(
            resume_command(run_root=run_root, repo=repo, argv=argv, log=log, env_body=env_body),
            check=False,
        )
        print(f"resumed stalled lane {Path(run_root).name[:56]} ({age:.0f} min idle) -> {log}")
        resumed += 1
    if not resumed:
        print("no stalled validation runs found")
    return 0


def make_output_streams_utf8_safe() -> None:
    """Keep printing from crashing under the scheduled task's GBK console.

    The task redirects stdout to a file under a legacy codepage; a single character the console
    cannot encode (a U+FFFD from decoding model output) used to abort the failure path with
    UnicodeEncodeError, which lost the round report.
    """

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv: Sequence[str] | None = None) -> int:
    make_output_streams_utf8_safe()
    args = parse_args(argv)
    if args.executor == "queue" and not args.agent_thread and not args.list:
        print(
            "CONFIG: --executor queue needs --agent-thread <uuid> (or CODEX_AGENT_THREAD)",
            file=sys.stderr,
        )
        return 2

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    remote = Remote(
        host=args.ssh_host, port=args.ssh_port, key=args.ssh_key, root=args.remote_root, dry_run=args.dry_run
    )

    if args.list:
        return cmd_list(remote, workdir, args)
    if args.resume_stalled:
        if args.dry_run:
            return cmd_resume_stalled(remote, args, workdir)
        if not acquire_lock(workdir, timeout_s=args.lock_timeout):
            print("BUSY: another daemon invocation holds the lock")
            return 1
        try:
            return cmd_resume_stalled(remote, args, workdir)
        finally:
            release_lock(workdir)

    if not args.dry_run and not acquire_lock(workdir, timeout_s=args.lock_timeout):
        print("BUSY: another daemon invocation holds the lock")
        return 1
    try:
        if args.run_root:
            candidates: list[tuple[str, dict[str, Any] | None]] = [
                (
                    args.run_root,
                    pick_event(
                        remote,
                        args.run_root,
                        workdir,
                        max_attempts=args.max_attempts,
                        max_age_minutes=args.max_event_age_minutes,
                        force_stale=args.force_stale,
                        retry_errors=args.retry_errors,
                    ),
                )
            ]
        else:
            candidates = scan_runs(
                remote,
                workdir,
                pattern=args.run_pattern,
                max_runs=args.max_runs,
                max_attempts=args.max_attempts,
                max_age_minutes=args.max_event_age_minutes,
                force_stale=args.force_stale,
                retry_errors=args.retry_errors,
            )
        chosen = next(((run_root, event) for run_root, event in candidates if event), None)
        if chosen is None:
            for run_root, _ in candidates:
                verdict, detail, _ = liveness(remote, run_root)
                print(f"idle: {Path(run_root).name[:58]:<58} {verdict:<20} {detail}")
            print("IDLE: no run is waiting for a draft")
            return 0

        run_root, event = chosen
        assert event is not None
        config = run_config(remote, run_root)
        event_id = str(event["event_id"])
        task_id = int(event.get("task_id") or 0)
        write_idx = int(event.get("write_idx") or 0)
        event_dir = str(event["event_dir"])
        state = load_attempts(workdir, event_id)
        attempt_no = len(state.get("attempts") or []) + 1
        round_dir = workdir / event_id / f"attempt{attempt_no}"
        drafts_dir = round_dir / "drafts"
        print(f"run root : {run_root}")
        print(f"event    : {event_id} (task{task_id:02d} w{write_idx}) attempt {attempt_no}")
        print(f"evidence : {event.get('evidence_json')}")

        if args.dry_run:
            print(
                f"[dry-run] plan: claim -> {args.executor} -> verify -> push drafts -> "
                "ingest -> resolve -> resume lane"
            )
            return 0

        fail_set = remote.cat_json(str(event.get("evidence_json")), timeout=600)
        lane = lane_args(remote, run_root)
        repo = str(config.get("repo") or "")
        skill_pack = str(event.get("skill_pack") or lane.get("skill_pack") or config.get("skill_pack") or "")
        repo_path = Path(__file__).resolve().parents[3]
        context = collect_remote_context(remote, repo, run_root, str(event["evidence_json"]), task_id)
        round_dir.mkdir(parents=True, exist_ok=True)
        context_path = round_dir / "context.json"
        atomic_json(context_path, context)
        probe_tool = stage_actor_tools(remote, repo_path, run_root, round_dir)
        shutil.copy2(repo_path / "scripts/recovery/skill_pipeline/actor_patch.py", round_dir / "apply_patch.py")
        shutil.copy2(repo_path / "scripts/recovery/skill_pipeline/actor_remote.py", round_dir / "remote.py")
        atomic_json(round_dir / "remote_config.json", {
            "host": args.ssh_host, "port": args.ssh_port, "key": args.ssh_key, "root": remote.root,
            "run_root": run_root, "probe_tool": probe_tool, "codex_exe": args.codex_exe,
            "python": config.get("python") or remote.python,
            "planner": f"{repo}/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh",
            "env": {"ROOT": remote.root, "OVERLAY_ROOT": repo,
                    "LIBERO_CONFIG_PATH": f"{run_root}/libero_config", "LIBERO_PYTHONPATH_ROOT": f"{remote.root}/LIBERO-PRO",
                    "PYTHONPATH": f"{repo}:{remote.root}/LIBERO-PRO:{remote.root}/openpi/src",
                    "CUDA_VISIBLE_DEVICES": str(lane.get("gpu") or ""), "MUJOCO_GL": "egl",
                    "XLA_PYTHON_CLIENT_PREALLOCATE": "false"},
        })
        # Pin documentation per intervention. Later local edits cannot change the agent's contract.
        docs_root = round_dir / "guidance"
        for rel in (*GUIDELINE_FILES, "scripts/recovery/skill_pipeline/prompts/actor.md"):
            dest = docs_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo_path / rel, dest)
        fail_set["task"] = f"{context['identity']['suite']} task{task_id:02d} " + "; ".join(context['identity']['task_descriptions'])
        result_path = round_dir / AGENT_RESULT_NAME
        if result_path.exists():
            # A marker left by an earlier round would be read as this round's answer.
            result_path.unlink()
        if args.executor == "queue":
            finish_instruction = (
                f"Finish by writing `{result_path}` containing "
                '{"status": "ok", "summary": "<one line>"} — write it last, after every other '
                'artifact. Use "failed" instead of "ok" if you could not complete the round. '
                "The daemon is blocked on that file."
            )
        else:
            finish_instruction = "Finish by printing the JSON object required by the output schema."
        prompt = compose_prompt(
            guidelines=actor_guidelines_with_type_docs(docs_root),
            capability_excerpt=remote.cat_text(f"{repo}/skill_packs/{skill_pack}/capabilities.yaml", check=False),
            library_index=remote.cat_text(f"{repo}/skill_packs/{skill_pack}/skills/_index.yaml", check=False),
            summary=summarize_fail_set(fail_set),
            verdict=json.dumps({"identity": context["identity"], "candidate": context["current_candidate"],
                                "rounds": context["rounds"], "invalid_validations": context["invalid_validations"]},
                               ensure_ascii=False, indent=2),
            previous_failure=previous_ingest_failure(state),
            ssh_command=f'ssh -p {args.ssh_port} -i "{args.ssh_key}" root@{args.ssh_host}',
            run_root=run_root,
            drafts_dir=str(drafts_dir),
            write_idx=write_idx,
            finish_instruction=finish_instruction,
            context_path=str(context_path),
            handoff=previous_findings(workdir, run_root, task_id),
        )
        round_dir.mkdir(parents=True, exist_ok=True)
        drafts_dir.mkdir(parents=True, exist_ok=True)
        reuse_dir = str(state.get("reuse_drafts_from") or "")
        if reuse_dir:
            shutil.copytree(Path(reuse_dir) / "drafts", drafts_dir, dirs_exist_ok=True)
        prompt_path = round_dir / "prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        schema_path = round_dir / "schema.json"
        schema_path.write_text(json.dumps(output_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"prompt   : {prompt_path} ({len(prompt)} chars)")

        attempts_list = state.setdefault("attempts", [])
        attempt_record = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "executor": args.executor,
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "run_root": run_root,
            "task_id": task_id,
            "write_idx": write_idx,
            "owner_pid": os.getpid(),
            "phase": "prepared",
            "attempt_no": attempt_no,
            "round_dir": str(round_dir),
            "result_path": str(result_path),
            "in_progress": True,
            "status": "in_progress",
            "ok": False,
        }
        attempts_list.append(attempt_record)
        save_attempts(workdir, event_id, state)
        claimed = remote.run(mark_command(remote, config, "claim", event_id, "--actor codex-daemon"), check=False)
        if claimed.returncode:
            attempt_record.update(in_progress=False, phase="claim_contended")
            save_attempts(workdir, event_id, state)
            return 1
        attempt_record["phase"] = "agent_running"
        save_attempts(workdir, event_id, state)

        if reuse_dir:
            code, tail = 0, f"Recovered completed candidate from {reuse_dir}; no second actor invocation"
            state.pop("reuse_drafts_from", None)
        elif args.executor == "queue":
            message = queue_message(
                event_id=event_id,
                write_idx=write_idx,
                prompt_path=prompt_path,
                drafts_dir=drafts_dir,
                result_path=result_path,
            )
            (round_dir / "queue_message.md").write_text(message, encoding="utf-8")
            delivered_at = time.time()
            delivered, delivery_detail = deliver_via_queue(
                codex_exe=args.codex_exe, thread=args.agent_thread, message=message,
                model=args.model, reasoning_effort=args.reasoning_effort,
            )
            (round_dir / "queue_delivery.json").write_text(
                json.dumps(
                    {
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "thread": args.agent_thread,
                        "delivered": delivered,
                        "detail": delivery_detail,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            attempt_record["queue_delivery"] = {
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "thread": args.agent_thread,
                "delivered": delivered,
                "detail": delivery_detail,
            }
            save_attempts(workdir, event_id, state)
            if not delivered:
                code, tail = -2, f"could not hand the round to the agent: {delivery_detail}"
            else:
                print(f"handed to agent : thread {args.agent_thread}, waiting for {AGENT_RESULT_NAME}")
                agent_ok, agent_detail = wait_for_agent_result(
                    result_path=result_path,
                    timeout=args.codex_timeout,
                    poll_seconds=args.agent_poll_seconds,
                )
                code, tail = (0 if agent_ok else -1), agent_detail
                audit_path = round_dir / "queue_audit.json"
                try:
                    rollout = find_thread_rollout(args.agent_thread)
                    commands = (
                        collect_agent_commands(rollout, since_epoch=delivered_at)
                        if rollout
                        else []
                    )
                    audit = audit_commands(commands)
                    audit["rollout"] = str(rollout) if rollout else ""
                    audit_path.write_text(
                        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    if not audit["clean"]:
                        print(f"BOUNDARY WARNING: see {audit['outside_writes']} in {audit_path}")
                    else:
                        print(
                            f"boundary ok : {audit['commands']} command(s), "
                            f"{len(audit['outside_paths'])} path(s) outside the tree, none written"
                        )
                except Exception as error:  # noqa: BLE001 - an audit must never kill the round
                    print(f"boundary audit failed: {type(error).__name__}: {error}")
        else:
            code, tail = run_codex(
                codex_exe=args.codex_exe,
                workdir=round_dir,
                prompt_path=prompt_path,
                schema_path=schema_path,
                model=args.model,
                timeout=args.codex_timeout,
                sandbox=args.exec_sandbox,
                reasoning_effort=args.reasoning_effort,
            )
        ok, detail = verify_drafts(drafts_dir)
        attempt_record.update(
            {
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "codex_exit": code,
                "verify": detail,
                "ok": bool(ok and code == 0),
                "in_progress": False,
                "status": "ok" if bool(ok and code == 0) else "failed",
                "phase": "draft_ready" if bool(ok and code == 0) else "agent_failed",
            }
        )
        state["needs_human"] = len(state["attempts"]) >= args.max_attempts
        save_attempts(workdir, event_id, state)
        if not (ok and code == 0):
            print(f"round failed: exit={code} verify={detail}\n{tail[-600:]}")
            # Keep the executor's own words: a delivery failure (-2) is not the same
            # thing as an agent that produced nothing, and the record must say which.
            reason = " ".join(f"{detail} :: {tail}".split())[:400]
            remote.run(
                mark_command(remote, config, "error", event_id, f"--message 'attempt {attempt_no} failed: {reason}'")
            )
            return 2

        if (workdir / "STOP").exists() or not context_is_current(remote, run_root, context):
            attempt_record.update(phase="stale_result", ok=False)
            save_attempts(workdir, event_id, state)
            print("STALE: task/evidence/pack changed; candidate preserved, not ingested")
            return 4

        remote_drafts = f"{run_root}/mine/actor_attempts/{event_id}/attempt{attempt_no}/drafts"
        attempt_record["remote_drafts"] = remote_drafts
        remote.push_dir(drafts_dir, remote_drafts)
        attempt_record["phase"] = "admitting"
        save_attempts(workdir, event_id, state)
        # check=False: a crashing ingest (e.g. a schema traceback) must still be recorded, or the
        # next round is told nothing about why its draft was refused.
        ingest = remote.run(
            ingest_command(
                remote=remote,
                config=config,
                args=lane,
                task_id=task_id,
                draft_dir=remote_drafts,
                write_idx=write_idx + 1,
            ),
            timeout=1800,
            check=False,
        )
        text = (ingest.stdout or "") + ("\n" + ingest.stderr if ingest.stderr else "")
        try:
            ingest_result, _ = json.JSONDecoder().raw_decode(text[text.find("{") :])
        except Exception:
            ingest_result = {"ok": False, "returncode": ingest.returncode, "raw": text[-1500:]}
        if ingest.returncode != 0:
            ingest_result["ok"] = False
        if not ingest_result.get("ok"):
            state["attempts"][-1]["ingest"] = ingest_result
            state["attempts"][-1]["phase"] = "admission_rejected"
            save_attempts(workdir, event_id, state)
            print(f"ingest rejected: {ingest_result.get('errors')}")
            remote.run(
                mark_command(
                    remote, config, "retry", event_id,
                    f"--message 'ingest rejected: {str(ingest_result.get('errors'))[:400]}'",
                )
            )
            return 3

        attempt_record.update(phase="ingested", ingest=ingest_result)
        state["needs_human"] = False
        save_attempts(workdir, event_id, state)
        remote.run(
            mark_command(
                remote,
                config,
                "resolve",
                event_id,
                f"--bundle-yaml {shlex.quote(remote_drafts + '/bundle.yaml')} --message 'ingested attempt {attempt_no}'",
            )
        )
        # Housekeeping: a finished run keeps its WAIT_CODEX.json forever, which is
        # exactly what made finished runs look like they were still waiting.
        remote.run(f"rm -f {run_root}/mine/WAIT_CODEX.json", check=False)
        argv = shlex.join([str(item) for item in (lane.get("argv") or remote.cat_json(f"{run_root}/mine/lane_command.json").get("argv") or [])])
        if argv:
            log = f"{run_root}/mine/lane_logs/resume_w{write_idx}_codex.log"
            env_body = launcher_env_body(remote, run_root)
            if not env_body or "PYTHONPATH" not in env_body:
                raise RuntimeError(f"No pinned launcher environment for {run_root}; refusing to resume")
            command = resume_command(run_root=run_root, repo=repo, argv=argv, log=log, env_body=env_body)
            remote.run(command, check=False)
            print(f"lane resumed -> {log} (with the launcher's environment)")
        print(f"OK: {event_id} ingested")
        attempt_record["phase"] = "validation_requested"
        save_attempts(workdir, event_id, state)
        return 0
    finally:
        if not args.dry_run:
            release_lock(workdir)


if __name__ == "__main__":
    raise SystemExit(main())
