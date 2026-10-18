#!/usr/bin/env python3
import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(
    "/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/"
    "logs/continual_skill_core60_pilot_20261006"
)
OUT = ROOT / "skill_overlap_c4.json"


def main():
    per_skill = defaultdict(lambda: {
        "applicable_queries": Counter(), "would_fire_queries": Counter(), "winner_queries": Counter(),
        "applicable_episodes": defaultdict(set), "would_fire_episodes": defaultdict(set), "winner_episodes": defaultdict(set),
        "winner_success_episodes": defaultdict(set),
        "task_breakdown": defaultdict(lambda: {
            "description": "", "applicable_queries": 0, "would_fire_queries": 0, "winner_queries": 0,
            "applicable_episodes": set(), "would_fire_episodes": set(), "winner_episodes": set(),
            "winner_success_episodes": set(),
            "failed_trigger_predicates": Counter(),
        }),
    })
    suites = defaultdict(lambda: {
        "queries": 0,
        "queries_multi_applicable": 0,
        "queries_multi_would_fire": 0,
        "fired_queries": 0,
        "fired_with_other_applicable": 0,
        "fired_with_other_would_fire": 0,
        "episodes_multi_would_fire": set(),
        "applicable_count_hist": Counter(),
        "would_fire_count_hist": Counter(),
        "co_applicable_pairs": Counter(),
        "co_would_fire_pairs": Counter(),
        "winner_shadow_applicable": Counter(),
        "winner_competing_fire": Counter(),
    })
    examples = []
    for job_dir in sorted((ROOT / "lanes").glob("lane*/*_C4_*")):
        m = re.match(r"\d+_C4_(.+)$", job_dir.name)
        if not m:
            continue
        suite = m.group(1)
        agg = suites[suite]
        for path in sorted((job_dir / "run").glob("task*/ep*/query_trace.jsonl")):
            episode_key = f"{path.parent.parent.name}/{path.parent.name}"
            try:
                episode_data = json.loads((path.parent / "episode.json").read_text())
                episode_success = bool(episode_data.get("success"))
                task_description = str(episode_data.get("task_description") or "")
            except (OSError, json.JSONDecodeError):
                episode_success = False
                task_description = ""
            task_key = f"{suite}/{path.parent.parent.name}"
            with path.open(errors="replace") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    diags = row.get("skill_match_diagnostics") or []
                    diag_by_skill = {d.get("skill_id"): d for d in diags if d.get("skill_id")}
                    applicable = sorted(d["skill_id"] for d in diags if d.get("applies_to", {}).get("passed"))
                    firing = sorted(d["skill_id"] for d in diags if d.get("would_fire"))
                    for skill_id in applicable:
                        per_skill[skill_id]["applicable_queries"][suite] += 1
                        per_skill[skill_id]["applicable_episodes"][suite].add(episode_key)
                        task_item = per_skill[skill_id]["task_breakdown"][task_key]
                        task_item["description"] = task_description
                        task_item["applicable_queries"] += 1
                        task_item["applicable_episodes"].add(episode_key)
                        diag = diag_by_skill.get(skill_id, {})
                        if not diag.get("would_fire"):
                            trigger_diag = diag.get("trigger", {})
                            failed = list(trigger_diag.get("failed_all") or []) + list(trigger_diag.get("failed_any") or [])
                            task_item["failed_trigger_predicates"].update(str(x) for x in failed)
                    for skill_id in firing:
                        per_skill[skill_id]["would_fire_queries"][suite] += 1
                        per_skill[skill_id]["would_fire_episodes"][suite].add(episode_key)
                        task_item = per_skill[skill_id]["task_breakdown"][task_key]
                        task_item["description"] = task_description
                        task_item["would_fire_queries"] += 1
                        task_item["would_fire_episodes"].add(episode_key)
                    agg["queries"] += 1
                    agg["applicable_count_hist"][len(applicable)] += 1
                    agg["would_fire_count_hist"][len(firing)] += 1
                    if len(applicable) > 1:
                        agg["queries_multi_applicable"] += 1
                        agg["co_applicable_pairs"].update(combinations(applicable, 2))
                    if len(firing) > 1:
                        agg["queries_multi_would_fire"] += 1
                        agg["episodes_multi_would_fire"].add(episode_key)
                        agg["co_would_fire_pairs"].update(combinations(firing, 2))
                    if row.get("hook_fired"):
                        winner = row.get("skill_id") or ""
                        per_skill[winner]["winner_queries"][suite] += 1
                        per_skill[winner]["winner_episodes"][suite].add(episode_key)
                        task_item = per_skill[winner]["task_breakdown"][task_key]
                        task_item["description"] = task_description
                        task_item["winner_queries"] += 1
                        task_item["winner_episodes"].add(episode_key)
                        if episode_success:
                            per_skill[winner]["winner_success_episodes"][suite].add(episode_key)
                            task_item["winner_success_episodes"].add(episode_key)
                        agg["fired_queries"] += 1
                        shadows = [x for x in applicable if x != winner]
                        competitors = [x for x in firing if x != winner]
                        if shadows:
                            agg["fired_with_other_applicable"] += 1
                            agg["winner_shadow_applicable"].update((winner, x) for x in shadows)
                        if competitors:
                            agg["fired_with_other_would_fire"] += 1
                            agg["winner_competing_fire"].update((winner, x) for x in competitors)
                            if len(examples) < 100:
                                examples.append({
                                    "suite": suite, "episode": episode_key,
                                    "query_idx": row.get("query_idx"), "winner": winner,
                                    "competitors": competitors, "applicable": applicable,
                                })

    output = {"run_root": str(ROOT), "condition": "C4", "suites": {}, "skills": {}, "multi_fire_examples": examples}
    for suite, agg in suites.items():
        output["suites"][suite] = {
            "queries": agg["queries"],
            "queries_multi_applicable": agg["queries_multi_applicable"],
            "queries_multi_would_fire": agg["queries_multi_would_fire"],
            "fired_queries": agg["fired_queries"],
            "fired_with_other_applicable": agg["fired_with_other_applicable"],
            "fired_with_other_would_fire": agg["fired_with_other_would_fire"],
            "episodes_multi_would_fire": sorted(agg["episodes_multi_would_fire"]),
            "applicable_count_hist": dict(agg["applicable_count_hist"]),
            "would_fire_count_hist": dict(agg["would_fire_count_hist"]),
            "co_applicable_pairs": [[list(pair), count] for pair, count in agg["co_applicable_pairs"].most_common()],
            "co_would_fire_pairs": [[list(pair), count] for pair, count in agg["co_would_fire_pairs"].most_common()],
            "winner_shadow_applicable": [[list(pair), count] for pair, count in agg["winner_shadow_applicable"].most_common()],
            "winner_competing_fire": [[list(pair), count] for pair, count in agg["winner_competing_fire"].most_common()],
        }
    for skill_id, item in sorted(per_skill.items()):
        output["skills"][skill_id] = {}
        for field in ("applicable_queries", "would_fire_queries", "winner_queries"):
            output["skills"][skill_id][field] = dict(item[field])
        for field in ("applicable_episodes", "would_fire_episodes", "winner_episodes", "winner_success_episodes"):
            output["skills"][skill_id][field] = {suite: len(keys) for suite, keys in item[field].items()}
        output["skills"][skill_id]["task_breakdown"] = {}
        for task_key, task_item in sorted(item["task_breakdown"].items()):
            output["skills"][skill_id]["task_breakdown"][task_key] = {
                "description": task_item["description"],
                "applicable_queries": task_item["applicable_queries"],
                "would_fire_queries": task_item["would_fire_queries"],
                "winner_queries": task_item["winner_queries"],
                "applicable_episodes": len(task_item["applicable_episodes"]),
                "would_fire_episodes": len(task_item["would_fire_episodes"]),
                "winner_episodes": len(task_item["winner_episodes"]),
                "winner_success_episodes": len(task_item["winner_success_episodes"]),
                "failed_trigger_predicates": task_item["failed_trigger_predicates"].most_common(),
            }
    OUT.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(json.dumps({"output": str(OUT), "suites": sorted(output["suites"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
