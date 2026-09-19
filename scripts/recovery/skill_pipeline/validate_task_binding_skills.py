"""Replay mined task-binding skills on cached language + MuJoCo contexts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.task_binding_skills import (
    load_task_binding_resolver,
    scene_from_context,
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate task-binding skills without running a policy or episode."
    )
    parser.add_argument("--skill-index", required=True)
    parser.add_argument("--contexts", required=True, help="Context JSON file or directory.")
    parser.add_argument("--mining", action="store_true", help="Include task_binding_fail_only candidates.")
    parser.add_argument("--report", default="", help="Optional JSON report path.")
    return parser.parse_args()


def _context_paths(raw: str) -> list[Path]:
    path = Path(raw)
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(path)
    return sorted(path.rglob("*.json"))


def validate(index: str, contexts: str, *, mining: bool = False) -> dict[str, Any]:
    resolver = load_task_binding_resolver(index, mining=mining)
    hit_counts = {skill.id: 0 for skill in resolver.skills}
    capability_counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for path in _context_paths(contexts):
        context = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(context, dict) or not isinstance(context.get("scene"), dict):
            continue
        if "language" not in context or not context.get("task_fingerprint"):
            continue
        language = str(context.get("language") or "")
        result = resolver.resolve(language, scene_from_context(context))
        matches = list((result or {}).get("binding_skill_matches") or [])
        for skill_id in matches:
            if skill_id in hit_counts:
                hit_counts[skill_id] += 1
        capability = None if result is None else result.get("binding_capability")
        if result is not None and not result.get("failure_reason") and capability:
            capability_counts[str(capability)] = capability_counts.get(str(capability), 0) + 1
        rows.append(
            {
                "path": str(path),
                "task_fingerprint": context.get("task_fingerprint"),
                "language": language,
                "status": "unmatched" if result is None else ("failed" if result.get("failure_reason") else "bound"),
                "target": None if result is None else result.get("target"),
                "goal": None if result is None else result.get("goal"),
                "relation": None if result is None else ((result.get("goal_atoms") or [{}])[0].get("predicate")),
                "failure_reason": None if result is None else result.get("failure_reason"),
                "failure_detail": None if result is None else result.get("failure_detail"),
                "binding_skill_matches": matches,
                "binding_capability": capability,
            }
        )
    failed = [row for row in rows if row["status"] == "failed"]
    untested = sorted(skill_id for skill_id, count in hit_counts.items() if count == 0)
    return {
        "kind": "task_binding_offline_admission",
        "skill_index": str(Path(index)),
        "contexts": len(rows),
        "bound": sum(row["status"] == "bound" for row in rows),
        "unmatched": sum(row["status"] == "unmatched" for row in rows),
        "failed": len(failed),
        "skill_hit_counts": hit_counts,
        "binding_capability_counts": capability_counts,
        "untested_skills": untested,
        "passed": not failed and not untested,
        "rows": rows,
    }


def main() -> int:
    args = _args()
    report = validate(args.skill_index, args.contexts, mining=bool(args.mining))
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
