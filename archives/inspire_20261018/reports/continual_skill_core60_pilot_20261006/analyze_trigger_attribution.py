#!/usr/bin/env python3
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(
    "/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/"
    "logs/continual_skill_core60_pilot_20261006"
)
OUT = ROOT / "trigger_attribution.json"
CONDITIONS = ["BASELINE", "C0", "C1", "C2", "C3", "C4"]
SUITES = [
    "libero_goal_swap",
    "libero_spatial_task",
    "libero_goal_task",
    "libero_spatial_swap",
    "libero_object_task",
    "libero_object_swap",
]
IGNORED_ERRORS = {"", "goal_atoms_not_yet_satisfied"}


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def episode_summary(ep_dir, condition, suite):
    ep = read_json(ep_dir / "episode.json")
    task_match = re.search(r"task(\d+)", ep_dir.parent.name)
    ep_match = re.search(r"ep(\d+)", ep_dir.name)
    rules = []
    serious_errors = Counter()
    failed_kinds = Counter()
    recovery_events = 0
    trace_path = ep_dir / "recovery_trace.jsonl"
    if trace_path.exists():
        with trace_path.open(errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("kind") == "rule":
                    rules.append({
                        "query_idx": row.get("query_idx"),
                        "skill_id": row.get("skill_id"),
                        "grounding_success": bool(row.get("success")),
                        "grounding_error": row.get("error") or "",
                        "target": row.get("target_name"),
                        "goal": row.get("goal_name"),
                    })
                if row.get("skill_id"):
                    recovery_events += 1
                error = str(row.get("error") or "")
                if row.get("success") is False and error not in IGNORED_ERRORS:
                    serious_errors[error] += 1
                    failed_kinds[str(row.get("kind") or "unknown")] += 1
    first = rules[0] if rules else {}
    return {
        "condition": condition,
        "suite": suite,
        "task": int(ep.get("task_id_1based") or (int(task_match.group(1)) if task_match else -1)),
        "episode": int(ep.get("episode_idx") if ep.get("episode_idx") is not None else (int(ep_match.group(1)) if ep_match else -1)),
        "seed": ep.get("seed"),
        "success": bool(ep.get("success")),
        "recovery_calls_reported": int(ep.get("recovery_calls") or 0),
        "triggered": bool(rules),
        "num_rule_calls": len(rules),
        "first_query_idx": first.get("query_idx"),
        "first_skill": first.get("skill_id"),
        "first_grounding_success": first.get("grounding_success"),
        "first_target": first.get("target"),
        "first_goal": first.get("goal"),
        "skill_sequence": [r["skill_id"] for r in rules],
        "query_sequence": [r["query_idx"] for r in rules],
        "serious_errors": dict(serious_errors),
        "failed_kinds": dict(failed_kinds),
        "recovery_event_count": recovery_events,
    }


def aggregate(rows):
    n = len(rows)
    triggered = [r for r in rows if r["triggered"]]
    no_trigger = [r for r in rows if not r["triggered"]]
    first_queries = [r["first_query_idx"] for r in triggered if isinstance(r["first_query_idx"], (int, float))]
    winners = defaultdict(lambda: {"episodes": 0, "success": 0, "rule_calls": 0})
    errors = Counter()
    failed_kinds = Counter()
    for row in rows:
        if row["first_skill"]:
            item = winners[row["first_skill"]]
            item["episodes"] += 1
            item["success"] += int(row["success"])
            item["rule_calls"] += row["num_rule_calls"]
        errors.update(row["serious_errors"])
        failed_kinds.update(row["failed_kinds"])
    return {
        "n": n,
        "success": sum(r["success"] for r in rows),
        "triggered_episodes": len(triggered),
        "triggered_success": sum(r["success"] for r in triggered),
        "no_trigger_episodes": len(no_trigger),
        "no_trigger_success": sum(r["success"] for r in no_trigger),
        "multi_rule_episodes": sum(r["num_rule_calls"] > 1 for r in rows),
        "mean_rule_calls_when_triggered": round(sum(r["num_rule_calls"] for r in triggered) / len(triggered), 3) if triggered else None,
        "first_query_median": statistics.median(first_queries) if first_queries else None,
        "first_query_mean": round(statistics.mean(first_queries), 3) if first_queries else None,
        "first_query_min": min(first_queries) if first_queries else None,
        "first_query_max": max(first_queries) if first_queries else None,
        "winners": dict(sorted(winners.items(), key=lambda kv: (-kv[1]["episodes"], kv[0]))),
        "top_errors": errors.most_common(12),
        "failed_kinds": failed_kinds.most_common(),
    }


def transition_category(old, new):
    if old["triggered"] and not new["triggered"]:
        return "trigger_lost"
    if not old["triggered"] and new["triggered"]:
        return "trigger_added"
    if not old["triggered"] and not new["triggered"]:
        return "neither_triggered"
    if old["first_skill"] != new["first_skill"]:
        return "winner_switched"
    return "same_winner"


def main():
    rows = []
    for job_dir in sorted((ROOT / "lanes").glob("lane*/*")):
        if not job_dir.is_dir() or ".pre_resume_" in job_dir.name:
            continue
        match = re.match(r"(\d+)_([^_]+)_(.+)$", job_dir.name)
        if not match:
            continue
        _, condition, suite = match.groups()
        if condition not in CONDITIONS or suite not in SUITES:
            continue
        for ep_dir in sorted((job_dir / "run").glob("task*/ep*")):
            if (ep_dir / "episode.json").exists():
                rows.append(episode_summary(ep_dir, condition, suite))

    cells = {}
    episode_maps = {}
    for condition in CONDITIONS:
        for suite in SUITES:
            selected = [r for r in rows if r["condition"] == condition and r["suite"] == suite]
            cells[f"{condition}|{suite}"] = aggregate(selected)
            episode_maps[(condition, suite)] = {(r["task"], r["episode"]): r for r in selected}

    transitions = []
    for suite in SUITES:
        for old_condition, new_condition in zip(CONDITIONS, CONDITIONS[1:]):
            old_map = episode_maps[(old_condition, suite)]
            new_map = episode_maps[(new_condition, suite)]
            details = []
            categories = Counter()
            timing_deltas = []
            for key in sorted(old_map.keys() & new_map.keys()):
                old, new = old_map[key], new_map[key]
                if old["success"] == new["success"]:
                    continue
                direction = "gained" if new["success"] else "lost"
                category = transition_category(old, new)
                categories[f"{direction}:{category}"] += 1
                delta = None
                if isinstance(old["first_query_idx"], (int, float)) and isinstance(new["first_query_idx"], (int, float)):
                    delta = new["first_query_idx"] - old["first_query_idx"]
                    timing_deltas.append(delta)
                details.append({
                    "task": key[0], "episode": key[1], "direction": direction,
                    "category": category, "old_skill": old["first_skill"], "new_skill": new["first_skill"],
                    "old_query": old["first_query_idx"], "new_query": new["first_query_idx"], "query_delta": delta,
                    "old_rule_calls": old["num_rule_calls"], "new_rule_calls": new["num_rule_calls"],
                    "old_errors": old["serious_errors"], "new_errors": new["serious_errors"],
                })
            transitions.append({
                "suite": suite, "from": old_condition, "to": new_condition,
                "changed": len(details),
                "gained": sum(d["direction"] == "gained" for d in details),
                "lost": sum(d["direction"] == "lost" for d in details),
                "categories": dict(categories),
                "mean_query_delta_for_both_triggered": round(statistics.mean(timing_deltas), 3) if timing_deltas else None,
                "details": details,
            })

    result = {
        "run_root": str(ROOT),
        "episode_count": len(rows),
        "cells": cells,
        "transitions": transitions,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({"output": str(OUT), "episodes": len(rows), "transitions": len(transitions)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
