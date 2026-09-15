#!/usr/bin/env python3
"""Claim, resolve, retry, or mark an error for a mining Codex-intervention event."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Mark a mining intervention event.")
    parser.add_argument("command", choices=["claim", "resolve", "retry", "error"])
    parser.add_argument("--event-root", required=True)
    parser.add_argument("--event-id", default="", help="Default: use LATEST_CODEX_EVENT.json.")
    parser.add_argument("--actor", default=os.environ.get("USER") or os.environ.get("USERNAME") or "codex")
    parser.add_argument("--message", default="")
    parser.add_argument("--draft-md", default="")
    parser.add_argument("--bundle-yaml", default="")
    parser.add_argument("--ingest-result-json", default="")
    parser.add_argument("--resume-command", default="")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def resolve_event_dir(event_root: Path, event_id: str) -> Path:
    if event_id:
        return event_root / "events" / event_id
    latest = read_json(event_root / "LATEST_CODEX_EVENT.json")
    latest_id = str(latest.get("event_id") or "")
    if not latest_id:
        raise ValueError(f"latest event has no event_id: {event_root / 'LATEST_CODEX_EVENT.json'}")
    return event_root / "events" / latest_id


def mark_event(args: argparse.Namespace) -> dict[str, Any]:
    event_root = Path(args.event_root)
    event_dir = resolve_event_dir(event_root, args.event_id)
    event = read_json(event_dir / "event.json")
    event_id = str(event.get("event_id") or event_dir.name)
    base = {
        "schema_version": 1,
        "event_id": event_id,
        "actor": str(args.actor),
        "message": str(args.message or ""),
    }
    if args.command == "claim":
        payload = {**base, "status": "claimed", "claimed_at": now_iso()}
        out_path = event_dir / "claim.json"
        if (event_dir / "resolved.json").exists():
            raise ValueError("Cannot claim a resolved event")
        with out_path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return {"ok": True, "event_id": event_id, "event_dir": str(event_dir), "wrote": str(out_path)}
    elif args.command == "resolve":
        payload = {
            **base,
            "status": "resolved",
            "resolved_at": now_iso(),
            "draft_md": str(args.draft_md or ""),
            "bundle_yaml": str(args.bundle_yaml or ""),
            "ingest_result_json": str(args.ingest_result_json or ""),
            "resume_command": str(args.resume_command or ""),
        }
        out_path = event_dir / "resolved.json"
    elif args.command == "retry":
        removed: list[str] = []
        for name in ("claim.json", "error.json"):
            path = event_dir / name
            if path.exists():
                path.unlink()
                removed.append(name)
        payload = {**base, "status": "retry", "retry_at": now_iso(), "removed": removed}
        out_path = event_dir / "retry.json"
    else:
        payload = {**base, "status": "error", "errored_at": now_iso()}
        out_path = event_dir / "error.json"
    write_json(out_path, payload)
    return {"ok": True, "event_id": event_id, "event_dir": str(event_dir), "wrote": str(out_path)}


def main() -> int:
    args = parse_args()
    print(json.dumps(mark_event(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"mark_mining_intervention.py: ERROR: {exc}", file=sys.stderr)
        raise
