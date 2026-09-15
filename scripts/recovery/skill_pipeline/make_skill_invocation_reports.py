#!/usr/bin/env python3
"""Build skill catalog and episode-level invocation reports for a skill run."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = yaml.safe_load(parts[1]) or {}
    return meta, parts[2].strip()


def compact(obj: Any) -> str:
    if obj in (None, "", [], {}):
        return ""
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def hint_summary(hints: Any) -> str:
    if not isinstance(hints, dict):
        return ""
    parts: list[str] = []
    grasp_profile = hints.get("grasp_profile")
    if grasp_profile:
        parts.append(f"grasp_profile={grasp_profile}")
    target = hints.get("target")
    if target:
        parts.append(f"target={target}")
    params = hints.get("params") or {}
    grounding = params.get("grounding_hints") or {}
    if isinstance(grounding, dict) and grounding:
        values = []
        for key, value in grounding.items():
            if isinstance(value, dict):
                values.append(f"{key}:{value.get('intent') or value.get('relation') or 'hint'}")
            else:
                values.append(str(key))
        parts.append("grounding=" + ",".join(values))
    geometry = params.get("geometry_hints") or {}
    if isinstance(geometry, dict) and geometry:
        values = []
        for key, value in geometry.items():
            if isinstance(value, dict):
                values.append(f"{key}:{value.get('intent') or value.get('relation') or 'hint'}")
            else:
                values.append(str(key))
        parts.append("geometry=" + ",".join(values))
    executor = params.get("executor") or {}
    if isinstance(executor, dict) and executor:
        values = ",".join(f"{key}={value}" for key, value in sorted(executor.items()))
        parts.append("executor=" + values)
    return " | ".join(parts)


def hint_sources(hints: Any) -> list[str]:
    if not isinstance(hints, dict):
        return []
    sources = (hints.get("params") or {}).get("hint_sources") or []
    out: list[str] = []
    if isinstance(sources, list):
        for item in sources:
            if isinstance(item, dict) and item.get("skill_id"):
                out.append(str(item["skill_id"]))
    return out


def task_key(path: Path) -> tuple[int, int]:
    return (int(path.parts[-3].replace("task", "")), int(path.parts[-2].replace("ep", "")))


def build_skill_catalog(repo: Path, report_dir: Path) -> list[dict[str, Any]]:
    index_path = repo / "skills" / "_index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    online_paths = [Path(p) for p in index.get("online", [])]
    online_ids: list[str] = []
    rows: list[dict[str, Any]] = []
    for rel in online_paths:
        path = repo / "skills" / rel
        meta, _ = read_frontmatter(path)
        skill_id = str(meta.get("id") or rel.stem)
        online_ids.append(skill_id)
        rows.append(
            {
                "status": "online",
                "id": skill_id,
                "path": str(rel).replace("\\", "/"),
                "kind": meta.get("kind", ""),
                "scope": meta.get("scope", ""),
                "hook": meta.get("hook", ""),
                "priority": meta.get("priority", ""),
                "trigger_or_applies_to": compact(meta.get("trigger") or meta.get("applies_to")),
                "recovery_hints": hint_summary(meta.get("recovery_hints") or {}),
                "when_to_apply": meta.get("when_to_apply", ""),
                "when_not_to_apply": meta.get("when_not_to_apply", ""),
            }
        )

    repair_dir = repo / "skills" / "pair" / "repair"
    for path in sorted(repair_dir.glob("*.md")):
        meta, _ = read_frontmatter(path)
        skill_id = str(meta.get("id") or path.stem)
        if skill_id in online_ids:
            continue
        rows.append(
            {
                "status": "disabled",
                "id": skill_id,
                "path": str(path.relative_to(repo / "skills")).replace("\\", "/"),
                "kind": meta.get("kind", ""),
                "scope": meta.get("scope", ""),
                "hook": meta.get("hook", ""),
                "priority": meta.get("priority", ""),
                "trigger_or_applies_to": compact(meta.get("trigger") or meta.get("applies_to")),
                "recovery_hints": hint_summary(meta.get("recovery_hints") or {}),
                "when_to_apply": meta.get("when_to_apply", ""),
                "when_not_to_apply": meta.get("when_not_to_apply", ""),
            }
        )

    with (report_dir / "skill_catalog.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    with (report_dir / "skill_catalog.md").open("w", encoding="utf-8") as f:
        f.write("# Skill Catalog\n\n")
        f.write("Generated from the current remote skills index. Disabled repair skills are files on disk but absent from `online:`.\n\n")
        f.write("| status | id | kind | scope/hook | priority | purpose | hints |\n")
        f.write("|---|---|---|---|---:|---|---|\n")
        for row in rows:
            scope_hook = row["scope"] or row["hook"]
            purpose = str(row["when_to_apply"] or "").replace("|", "\\|")
            hints = str(row["recovery_hints"] or "").replace("|", "\\|")
            f.write(
                f"| {row['status']} | `{row['id']}` | {row['kind']} | {scope_hook} | "
                f"{row['priority']} | {purpose} | {hints} |\n"
            )
    return rows


def build_episode_reports(base: Path, lanes: list[str], report_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lane in lanes:
        lane_dir = base / lane
        for episode_path in sorted(lane_dir.glob("task*/ep*/episode.json"), key=task_key):
            task = episode_path.parts[-3]
            episode = episode_path.parts[-2]
            episode_data = read_json(episode_path)
            recovery_rows = list(iter_jsonl(episode_path.with_name("recovery_trace.jsonl")) or [])
            query_rows = list(iter_jsonl(episode_path.with_name("query_trace.jsonl")) or [])
            queries_by_idx: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for query_row in query_rows:
                query_idx = query_row.get("query_idx")
                if query_idx is not None:
                    queries_by_idx[int(query_idx)].append(query_row)

            primary_skills: list[str] = []
            recovery_queries: list[int] = []
            for recovery_row in recovery_rows:
                skill_id = (
                    recovery_row.get("skill_id")
                    or recovery_row.get("primary_skill_id")
                    or recovery_row.get("selected_skill_id")
                )
                if skill_id and skill_id not in primary_skills:
                    primary_skills.append(str(skill_id))
                if recovery_row.get("query_idx") is not None:
                    recovery_queries.append(int(recovery_row["query_idx"]))
            first_query = min(recovery_queries) if recovery_queries else ""

            hint_ids: list[str] = []
            hint_summaries: list[str] = []
            candidate_queries: list[dict[str, Any]] = []
            if first_query != "":
                candidate_queries.extend(queries_by_idx.get(int(first_query), []))
            candidate_queries.extend(
                query_row
                for query_row in query_rows
                if query_row.get("skill_id") in primary_skills and query_row.get("recovery_hints")
            )
            for query_row in candidate_queries:
                hints = query_row.get("recovery_hints")
                for skill_id in hint_sources(hints):
                    if skill_id not in hint_ids:
                        hint_ids.append(skill_id)
                summary = hint_summary(hints)
                if summary and summary not in hint_summaries:
                    hint_summaries.append(summary)

            description = episode_data.get("task_description") or episode_data.get("language") or ""
            if not description and query_rows:
                description = query_rows[0].get("task_description") or query_rows[0].get("language") or ""

            rows.append(
                {
                    "task": task,
                    "episode": episode,
                    "success": bool(episode_data.get("success")),
                    "recovery_called": bool(primary_skills),
                    "first_recovery_query_idx": first_query,
                    "primary_repair_skills": ";".join(primary_skills),
                    "recovery_hint_skills": ";".join(hint_ids),
                    "hint_summary": " || ".join(hint_summaries),
                    "task_description": description,
                    "lane": lane,
                }
            )

    with (report_dir / "episode_skill_invocations.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    with (report_dir / "episode_skill_invocations.md").open("w", encoding="utf-8") as f:
        f.write("# Episode Skill Invocations\n\n")
        f.write("| task | ep | success | recovery q | repair skill | hint skills | hint summary |\n")
        f.write("|---|---:|---:|---:|---|---|---|\n")
        for row in rows:
            summary = (row["hint_summary"] or "-").replace("|", "\\|")
            f.write(
                f"| {row['task']} | {row['episode']} | {int(row['success'])} | "
                f"{row['first_recovery_query_idx'] if row['first_recovery_query_idx'] != '' else '-'} | "
                f"{row['primary_repair_skills'] or '-'} | {row['recovery_hint_skills'] or '-'} | {summary} |\n"
            )
    return rows


def build_task_summary(rows: list[dict[str, Any]], report_dir: Path) -> list[dict[str, Any]]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_task[row["task"]].append(row)

    summary_rows: list[dict[str, Any]] = []
    for task in sorted(by_task, key=lambda item: int(item.replace("task", ""))):
        task_rows = by_task[task]
        successes = sum(1 for row in task_rows if row["success"])
        recoveries = sum(1 for row in task_rows if row["recovery_called"])
        primary_counts: Counter[str] = Counter()
        hint_counts: Counter[str] = Counter()
        for row in task_rows:
            for skill_id in filter(None, row["primary_repair_skills"].split(";")):
                primary_counts[skill_id] += 1
            for skill_id in filter(None, row["recovery_hint_skills"].split(";")):
                hint_counts[skill_id] += 1
        summary_rows.append(
            {
                "task": task,
                "success": f"{successes}/{len(task_rows)}",
                "success_rate": f"{successes / len(task_rows):.3f}",
                "recovery_episodes": f"{recoveries}/{len(task_rows)}",
                "primary_repair_skills_by_episode": ";".join(
                    f"{key}:{value}" for key, value in primary_counts.most_common()
                )
                or "-",
                "recovery_hint_skills_by_episode": ";".join(
                    f"{key}:{value}" for key, value in hint_counts.most_common()
                )
                or "-",
            }
        )

    with (report_dir / "task_skill_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    with (report_dir / "task_skill_summary.md").open("w", encoding="utf-8") as f:
        f.write("# Task Skill Summary\n\n")
        f.write("| task | success | recovery eps | repair skills | hint skills |\n")
        f.write("|---|---:|---:|---|---|\n")
        for row in summary_rows:
            f.write(
                f"| {row['task']} | {row['success']} | {row['recovery_episodes']} | "
                f"{row['primary_repair_skills_by_episode']} | {row['recovery_hint_skills_by_episode']} |\n"
            )
    return summary_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--lanes", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    repo = Path(args.repo)
    base = Path(args.base)
    report_dir = Path(args.out)
    report_dir.mkdir(parents=True, exist_ok=True)

    build_skill_catalog(repo, report_dir)
    episode_rows = build_episode_reports(base, args.lanes, report_dir)
    build_task_summary(episode_rows, report_dir)

    print(f"wrote reports to {report_dir}")
    for path in sorted(report_dir.iterdir()):
        print(f"{path.name}\\t{path.stat().st_size}")


if __name__ == "__main__":
    main()
