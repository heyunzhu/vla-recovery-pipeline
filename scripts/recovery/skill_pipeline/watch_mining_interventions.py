#!/usr/bin/env python3
"""Watch mining lanes and publish durable Codex-intervention events.

This script runs on the remote eval host next to the mining lanes. It does not
call Codex. It only turns ``mine/WAIT_CODEX.json`` files into an event queue that
the local heartbeat can read reliably.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Watch skill-mining lanes for Codex intervention points.")
    parser.add_argument("--run-root", default="", help="Run root containing one or more lane */mine directories.")
    parser.add_argument(
        "--mine-dir",
        action="append",
        default=[],
        help="Explicit mine directory to watch. May be passed more than once.",
    )
    parser.add_argument(
        "--mine-dir-glob",
        action="append",
        default=[],
        help="Glob relative to --run-root. Default: */mine and mine.",
    )
    parser.add_argument(
        "--event-root",
        default="",
        help="Directory for codex_interventions. Default: <run-root>/codex_interventions.",
    )
    parser.add_argument("--poll-sec", type=float, default=15.0)
    parser.add_argument("--once", action="store_true", help="Scan once and exit.")
    parser.add_argument("--quiet", action="store_true", help="Only print errors and explicit --once summaries.")
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Include errored events in PENDING_CODEX_EVENTS.json. Default: errored events are terminal.",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"missing file: {path}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(data, dict):
        return None, f"expected JSON object: {path}"
    return data, ""


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_maybe_relative(value: str, *, base: Path) -> Path | None:
    if not str(value or "").strip():
        return None
    path = Path(value)
    return path if path.is_absolute() else base / path


def discover_mine_dirs(
    *,
    run_root: Path | None,
    explicit_mine_dirs: Iterable[str | Path],
    patterns: Iterable[str],
) -> list[Path]:
    found: dict[str, Path] = {}
    for raw in explicit_mine_dirs:
        path = Path(raw)
        found[str(path.resolve())] = path
    if run_root is not None:
        search_patterns = list(patterns) or ["mine", "*/mine"]
        for pattern in search_patterns:
            for path in run_root.glob(pattern):
                if path.is_dir():
                    found[str(path.resolve())] = path
    return [found[key] for key in sorted(found)]


def stable_event_id(mine_dir: Path, wait_payload: Mapping[str, Any], wait_sha256: str) -> str:
    task_id = int(wait_payload.get("awaiting_task") or wait_payload.get("task_id") or 0)
    writes_used = int(wait_payload.get("writes_used") or 0)
    # Accept pack_json from old WAIT_CODEX files, but keep new event material canonical.
    evidence_json = str(wait_payload.get("evidence_json") or wait_payload.get("pack_json") or "")
    material = {
        "mine_dir": str(mine_dir.resolve()),
        "awaiting_task": task_id,
        "awaiting_kind": wait_payload.get("awaiting_kind") or "draft",
        "writes_used": writes_used,
        "evidence_json": evidence_json,
        "state_path": str(wait_payload.get("state_path") or ""),
        "reason": str(wait_payload.get("reason") or ""),
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()[:16]
    prefix = f"task{task_id:02d}_w{writes_used}" if task_id else "unknown"
    return f"{prefix}_{digest}"


def _event_missing_files(wait_payload: Mapping[str, Any], mine_dir: Path) -> list[str]:
    missing: list[str] = []
    evidence_json = str(wait_payload.get("evidence_json") or wait_payload.get("pack_json") or "")
    for key, value in (
        ("evidence_json", evidence_json),
        ("actor_prompt", str(wait_payload.get("actor_prompt") or "")),
        ("lane_command_json", str(wait_payload.get("lane_command_json") or "")),
    ):
        path = resolve_maybe_relative(value, base=mine_dir)
        if path is None or not path.exists():
            missing.append(key)
    return missing


def build_event(mine_dir: Path, event_root: Path) -> dict[str, Any] | None:
    wait_path = mine_dir / "WAIT_CODEX.json"
    if not wait_path.exists():
        return None
    wait_payload, error = read_json(wait_path)
    wait_hash = file_sha256(wait_path) if wait_path.exists() else ""
    if wait_payload is None:
        wait_payload = {}
    mine_state, mine_state_error = read_json(mine_dir / "mine_state.json")
    lane_command, lane_command_error = read_json(mine_dir / "lane_command.json")
    missing_files = [] if error else _event_missing_files(wait_payload, mine_dir)
    invalid_reasons = [item for item in (error, mine_state_error if mine_state is None else "") if item]
    if missing_files:
        invalid_reasons.append("missing referenced files: " + ", ".join(missing_files))

    event_id = stable_event_id(mine_dir, wait_payload, wait_hash)
    event_dir = event_root / "events" / event_id
    task_id = int(wait_payload.get("awaiting_task") or wait_payload.get("task_id") or 0)
    writes_used = int(wait_payload.get("writes_used") or 0)
    status = "codex_event_invalid" if invalid_reasons else "codex_required"
    evidence_json = str(wait_payload.get("evidence_json") or wait_payload.get("pack_json") or "")
    canonical_wait_payload = dict(wait_payload)
    if evidence_json:
        canonical_wait_payload["evidence_json"] = evidence_json
    canonical_wait_payload.pop("pack_json", None)
    event = {
        "schema_version": 1,
        "event_type": "skill_mining_codex_intervention",
        "event_id": event_id,
        "status": status,
        "created_at": now_iso(),
        "task_id": task_id,
        "write_idx": writes_used,
        "writes_used": writes_used,
        "writes_max": int(wait_payload.get("writes_max") or 0),
        "mine_dir": str(mine_dir),
        "event_dir": str(event_dir),
        "wait_codex_json": str(wait_path),
        "wait_sha256": wait_hash,
        "evidence_json": evidence_json,
        "actor_prompt": str(wait_payload.get("actor_prompt") or ""),
        "lane_command_json": str(wait_payload.get("lane_command_json") or (mine_dir / "lane_command.json")),
        "reason": str(wait_payload.get("reason") or ""),
        "source": str(wait_payload.get("source") or ""),
        "missing_files": missing_files,
        "invalid_reasons": invalid_reasons,
        "wait_payload": canonical_wait_payload,
        "mine_state": mine_state or {},
        "lane_command": lane_command or {},
    }
    if lane_command is None and lane_command_error:
        event["lane_command_error"] = lane_command_error
    return event


def publish_event(event_root: Path, event: Mapping[str, Any]) -> tuple[bool, Path]:
    event_dir = Path(str(event["event_dir"]))
    event_path = event_dir / "event.json"
    created = False
    try:
        event_dir.mkdir(parents=True, exist_ok=False)
        write_json(event_path, event)
        created = True
    except FileExistsError:
        if not event_path.exists():
            write_json(event_path, event)
            created = True
    latest = dict(event)
    latest["event_status"] = latest.get("status", "")
    latest["claimed"] = (event_dir / "claim.json").exists()
    latest["resolved"] = (event_dir / "resolved.json").exists()
    latest["errored"] = (event_dir / "error.json").exists()
    if latest["resolved"]:
        latest["lifecycle_status"] = "resolved"
    elif latest["errored"]:
        latest["lifecycle_status"] = "error"
    elif latest["claimed"]:
        latest["lifecycle_status"] = "claimed"
    else:
        latest["lifecycle_status"] = str(latest.get("status") or "")
    latest["event_json"] = str(event_path)
    write_json(event_root / "LATEST_CODEX_EVENT.json", latest)
    return created, event_path


def pending_events(event_root: Path, *, retry_errors: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    events_dir = event_root / "events"
    if not events_dir.exists():
        return out
    for event_path in sorted(events_dir.glob("*/event.json")):
        data, error = read_json(event_path)
        if data is None or error:
            continue
        event_dir = event_path.parent
        if (event_dir / "resolved.json").exists():
            continue
        if (event_dir / "error.json").exists() and not retry_errors:
            continue
        if str(data.get("status") or "") != "codex_required":
            continue
        data = dict(data)
        data["event_json"] = str(event_path)
        data["claimed"] = (event_dir / "claim.json").exists()
        data["errored"] = (event_dir / "error.json").exists()
        data["resolved"] = False
        out.append(data)
    return out


def scan_once(
    *,
    run_root: Path | None,
    mine_dirs: list[Path],
    event_root: Path,
    scan_count: int,
    retry_errors: bool = False,
) -> dict[str, Any]:
    event_root.mkdir(parents=True, exist_ok=True)
    created: list[dict[str, Any]] = []
    seen_waits: list[str] = []
    for mine_dir in mine_dirs:
        event = build_event(mine_dir, event_root)
        if event is None:
            continue
        seen_waits.append(str(mine_dir / "WAIT_CODEX.json"))
        was_created, event_path = publish_event(event_root, event)
        if was_created:
            item = dict(event)
            item["event_json"] = str(event_path)
            created.append(item)

    pending = pending_events(event_root, retry_errors=retry_errors)
    latest_id = ""
    latest_path = event_root / "LATEST_CODEX_EVENT.json"
    latest, _ = read_json(latest_path) if latest_path.exists() else ({}, "")
    if latest:
        latest_id = str(latest.get("event_id") or "")
    status = {
        "schema_version": 1,
        "kind": "skill_mining_intervention_watchdog_status",
        "last_checked_at": now_iso(),
        "scan_count": scan_count,
        "run_root": str(run_root or ""),
        "event_root": str(event_root),
        "mine_dirs": [str(path) for path in mine_dirs],
        "wait_codex_files_seen": seen_waits,
        "created_event_count": len(created),
        "created_event_ids": [str(item.get("event_id") or "") for item in created],
        "pending_event_count": len(pending),
        "pending_event_ids": [str(item.get("event_id") or "") for item in pending],
        "latest_event_id": latest_id,
        "retry_errors": bool(retry_errors),
    }
    write_json(
        event_root / "PENDING_CODEX_EVENTS.json",
        {
            "schema_version": 1,
            "updated_at": status["last_checked_at"],
            "pending_event_count": len(pending),
            "pending_events": pending,
        },
    )
    write_json(event_root / "watchdog_status.json", status)
    return {"created": created, "pending": pending, "status": status}


def main() -> int:
    args = parse_args()
    run_root = Path(args.run_root) if args.run_root else None
    if run_root is None and not args.mine_dir:
        raise SystemExit("provide --run-root or at least one --mine-dir")
    event_root = Path(args.event_root) if args.event_root else (run_root / "codex_interventions" if run_root else Path(args.mine_dir[0]).parent / "codex_interventions")
    scan_count = 0
    while True:
        scan_count += 1
        mine_dirs = discover_mine_dirs(
            run_root=run_root,
            explicit_mine_dirs=args.mine_dir,
            patterns=args.mine_dir_glob,
        )
        result = scan_once(
            run_root=run_root,
            mine_dirs=mine_dirs,
            event_root=event_root,
            scan_count=scan_count,
            retry_errors=bool(args.retry_errors),
        )
        if args.once or not args.quiet:
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        if args.once:
            return 0
        time.sleep(max(1.0, float(args.poll_sec)))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"watch_mining_interventions.py: ERROR: {exc}", file=sys.stderr, flush=True)
        raise
