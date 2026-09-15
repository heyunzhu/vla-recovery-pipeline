"""Offline replay of skill trigger and recovery-hint matching over rollout traces."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .diagnostics.registry import load_registry as load_diagnostic_registry
from .diagnostics.runtime import DiagnosticSignalRuntime, parse_active_statuses
from .matcher import match_recovery_hints
from .predicate_registry import PredicateRegistry
from .runtime import SkillRuntime
from .schema import SkillSpec, load_skill, resolve_mining_skills, resolve_online_skills


@dataclass(frozen=True)
class ScanConfig:
    include_hints: bool = True
    include_empty_query_rows: bool = False
    max_queries_per_episode: int = 0
    diagnostic_signal_registry: str | Path | None = None
    diagnostic_signal_statuses: str = ""
    diagnostic_provider_roots: Sequence[str | Path] = field(default_factory=tuple)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                item = {"_decode_error": line[:300]}
            if isinstance(item, dict):
                rows.append(item)
    return rows


def iter_episode_dirs(root: str | Path) -> Iterable[Path]:
    base = Path(root)
    for episode_json in sorted(base.rglob("episode.json")):
        ep_dir = episode_json.parent
        task_name = ep_dir.parent.name
        is_task_dir = task_name.startswith("task") or task_name.startswith("libero_")
        if not ep_dir.name.startswith("ep") or not is_task_dir:
            continue
        if any(part.endswith("_annotated_recovery_marked") for part in ep_dir.parts):
            continue
        yield ep_dir


def load_scan_skills(
    index_path: str | Path,
    *,
    extra_skill_files: Sequence[str | Path] = (),
    mining: bool = False,
    predicate_registry: PredicateRegistry | None = None,
) -> list[SkillSpec]:
    skills = (
        resolve_mining_skills(index_path, predicate_registry=predicate_registry)
        if mining
        else resolve_online_skills(index_path, predicate_registry=predicate_registry)
    )
    by_id = {skill.id: skill for skill in skills}
    for path in extra_skill_files:
        spec = load_skill(path, predicate_registry=predicate_registry)
        if spec.kind == "diagnostics":
            continue
        by_id[spec.id] = spec
    return sorted(by_id.values(), key=lambda item: (-int(item.priority), item.id))


def _task_num(task_name: str) -> int:
    if task_name.startswith("task"):
        try:
            return int(task_name.replace("task", ""))
        except ValueError:
            pass
    return -1


def _episode_meta(ep_dir: Path) -> dict[str, Any]:
    meta = read_json(ep_dir / "episode.json")
    task = ep_dir.parent.name
    meta.setdefault("task_id_1based", _task_num(task))
    meta.setdefault("episode", ep_dir.name)
    meta.setdefault("success", False)
    return meta


def _query_state(row: Mapping[str, Any], meta: Mapping[str, Any], query_idx: int) -> dict[str, Any]:
    state = dict(row)
    state.setdefault("query_idx", query_idx)
    state.setdefault("label", "")
    if "aperture" not in state and state.get("gripper_aperture") is not None:
        state["aperture"] = state.get("gripper_aperture")
    description = (
        row.get("task_description")
        or row.get("language")
        or meta.get("task_description")
        or meta.get("language")
        or ""
    )
    state["task_description"] = str(description)
    return state


def _diagnostic_runtime_from_config(cfg: ScanConfig) -> DiagnosticSignalRuntime | None:
    statuses = str(cfg.diagnostic_signal_statuses or "").strip()
    if not statuses or cfg.diagnostic_signal_registry in (None, ""):
        return None
    registry = load_diagnostic_registry(
        cfg.diagnostic_signal_registry,
        provider_roots=tuple(Path(root) for root in cfg.diagnostic_provider_roots),
    )
    return DiagnosticSignalRuntime.from_registry(registry, active_statuses=parse_active_statuses(statuses))


def _hint_summary(match: Any) -> dict[str, str]:
    skill = match.skill
    hints = dict(skill.recovery_hints or {})
    params = hints.get("params") if isinstance(hints.get("params"), Mapping) else {}
    return {
        "skill_id": skill.id,
        "scope": str(skill.scope or ""),
        "priority": str(int(skill.priority)),
        "grasp_profile": str(hints.get("grasp_profile") or ""),
        "hint_keys": ",".join(sorted(str(key) for key in params.keys())) if isinstance(params, Mapping) else "",
    }


def scan_episode(
    ep_dir: str | Path,
    skills: Sequence[SkillSpec],
    config: ScanConfig | None = None,
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> dict[str, Any]:
    cfg = config or ScanConfig()
    path = Path(ep_dir)
    meta = _episode_meta(path)
    queries = read_jsonl(path / "query_trace.jsonl")
    if cfg.max_queries_per_episode and cfg.max_queries_per_episode > 0:
        queries = queries[: cfg.max_queries_per_episode]
    runtime = SkillRuntime(list(skills), predicate_registry=predicate_registry)
    diagnostic_runtime = _diagnostic_runtime_from_config(cfg)
    query_rows: list[dict[str, Any]] = []
    repair_skill_ids: set[str] = {skill.id for skill in skills if skill.kind != "recovery_hint"}
    hint_skill_ids: set[str] = {skill.id for skill in skills if skill.kind == "recovery_hint"}
    first_repair_query: int | None = None
    first_repair_skill = ""
    first_hint_by_scope: dict[str, dict[str, Any]] = {}
    repair_episode_hits: set[str] = set()
    repair_winner_episode_hits: set[str] = set()
    hint_episode_hits: set[str] = set()

    for query_pos, row in enumerate(queries):
        qidx = int(row.get("query_idx", query_pos) if row.get("query_idx") is not None else query_pos)
        row_with_signals = dict(row)
        state = _query_state(row_with_signals, meta, qidx)
        if diagnostic_runtime is not None:
            diagnostic_signals = diagnostic_runtime.compute("after_pi0_query", state)
            row_with_signals["diagnostic_signals"] = diagnostic_signals
            state["diagnostic_signals"] = diagnostic_signals
        decision = runtime.after_pi0_query(state)
        diagnostics = list(runtime.last_hook_diagnostics or [])
        would_fire = [str(item["skill_id"]) for item in diagnostics if item.get("would_fire")]
        winner = ""
        if decision and decision.get("enter_recovery"):
            winner = str(decision.get("skill_id") or "")
        hint_matches = (
            match_recovery_hints(runtime.skills, runtime.last_state, predicate_registry=predicate_registry)
            if cfg.include_hints
            else []
        )
        hints = [_hint_summary(match) for match in hint_matches]
        hint_ids = [item["skill_id"] for item in hints]

        for skill_id in would_fire:
            if skill_id in repair_skill_ids:
                repair_episode_hits.add(skill_id)
        if winner:
            repair_winner_episode_hits.add(winner)
            if first_repair_query is None:
                first_repair_query = qidx
                first_repair_skill = winner
        for skill_id in hint_ids:
            if skill_id in hint_skill_ids:
                hint_episode_hits.add(skill_id)
        for item in hints:
            scope = item["scope"] or "unknown"
            first_hint_by_scope.setdefault(scope, {"query_idx": qidx, "skill_id": item["skill_id"]})

        if cfg.include_empty_query_rows or would_fire or winner or hint_ids:
            query_rows.append(
                {
                    "task": path.parent.name,
                    "episode": path.name,
                    "episode_dir": str(path),
                    "success": bool(meta.get("success")),
                    "query_idx": qidx,
                    "mode": row.get("mode", ""),
                    "repair_would_fire": would_fire,
                    "repair_winner": winner,
                    "hint_matches": hints,
                    "target_name": row.get("target_name", ""),
                    "goal_name": row.get("goal_name", ""),
                    "task_description": state.get("task_description", ""),
                    "diagnostic_signals": state.get("diagnostic_signals", {}),
                }
            )

    return {
        "episode_dir": str(path),
        "task": path.parent.name,
        "episode": path.name,
        "task_id_1based": meta.get("task_id_1based"),
        "episode_idx": meta.get("episode_idx"),
        "seed": meta.get("seed"),
        "success": bool(meta.get("success")),
        "query_count": len(queries),
        "first_repair_query_idx": first_repair_query,
        "first_repair_skill": first_repair_skill,
        "repair_episode_hits": sorted(repair_episode_hits),
        "repair_winner_episode_hits": sorted(repair_winner_episode_hits),
        "hint_episode_hits": sorted(hint_episode_hits),
        "first_hint_by_scope": first_hint_by_scope,
        "query_matches": query_rows,
    }


def scan_roots(
    roots: Sequence[str | Path],
    skills: Sequence[SkillSpec],
    config: ScanConfig | None = None,
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> dict[str, Any]:
    cfg = config or ScanConfig()
    episode_reports: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root in roots:
        for ep_dir in iter_episode_dirs(root):
            resolved = ep_dir.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            episode_reports.append(scan_episode(ep_dir, skills, cfg, predicate_registry=predicate_registry))

    repair_ids = [skill.id for skill in skills if skill.kind != "recovery_hint"]
    hint_ids = [skill.id for skill in skills if skill.kind == "recovery_hint"]
    repair_hit_counts: Counter[str] = Counter()
    repair_winner_counts: Counter[str] = Counter()
    hint_hit_counts: Counter[str] = Counter()
    repair_query_counts: Counter[str] = Counter()
    repair_winner_query_counts: Counter[str] = Counter()
    hint_query_counts: Counter[str] = Counter()
    success_ep_hits: Counter[str] = Counter()
    fail_ep_hits: Counter[str] = Counter()
    query_rows: list[dict[str, Any]] = []

    for episode in episode_reports:
        success = bool(episode["success"])
        for skill_id in episode["repair_episode_hits"]:
            repair_hit_counts[skill_id] += 1
            (success_ep_hits if success else fail_ep_hits)[skill_id] += 1
        for skill_id in episode["repair_winner_episode_hits"]:
            repair_winner_counts[skill_id] += 1
        for skill_id in episode["hint_episode_hits"]:
            hint_hit_counts[skill_id] += 1
            (success_ep_hits if success else fail_ep_hits)[skill_id] += 1
        for row in episode["query_matches"]:
            query_rows.append(row)
            for skill_id in row["repair_would_fire"]:
                repair_query_counts[skill_id] += 1
            if row["repair_winner"]:
                repair_winner_query_counts[str(row["repair_winner"])] += 1
            for item in row["hint_matches"]:
                hint_query_counts[item["skill_id"]] += 1

    skill_rows: list[dict[str, Any]] = []
    for skill in sorted(skills, key=lambda item: (item.kind == "recovery_hint", item.scope, -item.priority, item.id)):
        is_hint = skill.kind == "recovery_hint"
        skill_rows.append(
            {
                "skill_id": skill.id,
                "kind": skill.kind,
                "scope": skill.scope,
                "hook": skill.hook or "",
                "priority": int(skill.priority),
                "episode_matches": int((hint_hit_counts if is_hint else repair_hit_counts).get(skill.id, 0)),
                "query_matches": int((hint_query_counts if is_hint else repair_query_counts).get(skill.id, 0)),
                "winner_episodes": int(repair_winner_counts.get(skill.id, 0)) if not is_hint else 0,
                "winner_queries": int(repair_winner_query_counts.get(skill.id, 0)) if not is_hint else 0,
                "success_episode_matches": int(success_ep_hits.get(skill.id, 0)),
                "failed_episode_matches": int(fail_ep_hits.get(skill.id, 0)),
            }
        )

    tasks: dict[str, dict[str, Any]] = defaultdict(lambda: {"episodes": 0, "success": 0, "repair_hits": 0, "hint_hits": 0})
    for episode in episode_reports:
        task = str(episode["task"])
        tasks[task]["episodes"] += 1
        tasks[task]["success"] += int(bool(episode["success"]))
        tasks[task]["repair_hits"] += int(bool(episode["repair_episode_hits"]))
        tasks[task]["hint_hits"] += int(bool(episode["hint_episode_hits"]))
    task_rows = [
        {
            "task": task,
            "episodes": row["episodes"],
            "success": row["success"],
            "success_rate": row["success"] / row["episodes"] if row["episodes"] else 0.0,
            "repair_hit_episodes": row["repair_hits"],
            "hint_hit_episodes": row["hint_hits"],
        }
        for task, row in sorted(tasks.items(), key=lambda item: _task_num(item[0]))
    ]

    return {
        "schema_version": 1,
        "roots": [str(Path(root)) for root in roots],
        "episodes": episode_reports,
        "tasks": task_rows,
        "skills": skill_rows,
        "query_matches": query_rows,
        "overall": {
            "episodes": len(episode_reports),
            "success": sum(1 for item in episode_reports if item["success"]),
            "failed": sum(1 for item in episode_reports if not item["success"]),
            "repair_skills": len(repair_ids),
            "hint_skills": len(hint_ids),
            "query_match_rows": len(query_rows),
        },
    }


def _json_cell(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def write_scan_outputs(report: Mapping[str, Any], out_dir: str | Path) -> dict[str, str]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "offline_skill_scan.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    episode_csv = target / "episode_skill_scan.csv"
    with episode_csv.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "task",
            "episode",
            "success",
            "query_count",
            "first_repair_query_idx",
            "first_repair_skill",
            "repair_winner_episode_hits",
            "repair_episode_hits",
            "hint_episode_hits",
            "first_hint_by_scope",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for episode in report.get("episodes") or []:
            writer.writerow({key: _json_cell(episode.get(key)) for key in fieldnames})

    skill_csv = target / "skill_scan_summary.csv"
    with skill_csv.open("w", newline="", encoding="utf-8") as handle:
        rows = list(report.get("skills") or [])
        fieldnames = list(rows[0].keys()) if rows else ["skill_id"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    query_csv = target / "query_skill_matches.csv"
    with query_csv.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "task",
            "episode",
            "episode_dir",
            "success",
            "query_idx",
            "mode",
            "repair_would_fire",
            "repair_winner",
            "hint_matches",
            "target_name",
            "goal_name",
            "task_description",
            "diagnostic_signals",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.get("query_matches") or []:
            writer.writerow({key: _json_cell(row.get(key)) for key in fieldnames})

    md_path = target / "offline_skill_scan.md"
    md_path.write_text(render_scan_markdown(report), encoding="utf-8")
    return {
        "json": str(json_path),
        "episode_csv": str(episode_csv),
        "skill_csv": str(skill_csv),
        "query_csv": str(query_csv),
        "markdown": str(md_path),
    }


def render_scan_markdown(report: Mapping[str, Any]) -> str:
    overall = report.get("overall") or {}
    lines = [
        "# Offline Skill Trigger Scan",
        "",
        f"- Episodes: {overall.get('episodes', 0)}",
        f"- Success: {overall.get('success', 0)}",
        f"- Failed: {overall.get('failed', 0)}",
        f"- Repair skills: {overall.get('repair_skills', 0)}",
        f"- Recovery hint skills: {overall.get('hint_skills', 0)}",
        f"- Query match rows: {overall.get('query_match_rows', 0)}",
        "",
        "## Skill Summary",
        "",
        "| skill | kind | scope | ep matches | query matches | winner eps | success eps | failed eps |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report.get("skills") or []:
        if not row.get("episode_matches") and not row.get("query_matches"):
            continue
        lines.append(
            f"| `{row.get('skill_id')}` | {row.get('kind')} | {row.get('scope') or '-'} | "
            f"{row.get('episode_matches', 0)} | {row.get('query_matches', 0)} | "
            f"{row.get('winner_episodes', 0)} | {row.get('success_episode_matches', 0)} | "
            f"{row.get('failed_episode_matches', 0)} |"
        )
    lines.extend(
        [
            "",
            "## Episode First Hits",
            "",
            "| task | ep | success | first repair q | repair winner | repair hits | hint hits |",
            "| --- | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for episode in report.get("episodes") or []:
        repair_hits = ",".join(episode.get("repair_episode_hits") or []) or "-"
        hint_hits = ",".join(episode.get("hint_episode_hits") or []) or "-"
        first_q = episode.get("first_repair_query_idx")
        lines.append(
            f"| {episode.get('task')} | {episode.get('episode')} | {int(bool(episode.get('success')))} | "
            f"{'-' if first_q is None else first_q} | `{episode.get('first_repair_skill') or '-'}` | "
            f"{repair_hits} | {hint_hits} |"
        )
    return "\n".join(lines) + "\n"
