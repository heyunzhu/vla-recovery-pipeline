#!/usr/bin/env python3
"""Diagnose real-cuTAMP recovery failures from a skill-pipeline run.

The runner already serializes cuTAMP problem/result JSON plus stdout/stderr.
This script joins those files back to task episodes and extracts the evidence
we need before deciding whether to edit grasp, grounding, geometry, or repair
skills.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import re
from typing import Any


CONSTRAINT_RE = re.compile(
    r"\[(?P<kind>[^\]]+)\]\s+"
    r"(?P<name>[^<]+?)\s*<=\s*"
    r"(?P<tol>[-+0-9.eE]+)\s+has\s+"
    r"(?P<satisfied>[0-9]+)/(?P<total>[0-9]+)\s+satisfying,\s+"
    r"(?P<remaining>[0-9]+)\s+remaining"
)
LOSS_RE = re.compile(
    r"Loss:\s*(?P<loss>[-+0-9.eE]+),\s*"
    r"Min:\s*(?P<min>[-+0-9.eE]+),\s*"
    r"(?P<satisfied>[0-9]+)/(?P<total>[0-9]+)\s+satisfying"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Diagnose skill-pipeline real-cuTAMP failures.")
    parser.add_argument("--run-dir", required=True, help="Skill-pipeline run directory.")
    parser.add_argument("--task-id", type=int, default=None, help="Optional LIBERO task id to join episodes.")
    parser.add_argument("--out-json", default="", help="Where to write the machine-readable report.")
    parser.add_argument("--out-md", default="", help="Where to write a markdown report.")
    parser.add_argument("--max-grasps", type=int, default=8, help="Top grasp candidates to print per episode.")
    return parser.parse_args()


def load_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def number(value: Any, digits: int = 4) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return value
        return round(float(value), digits)
    return value


def round_tree(value: Any, digits: int = 4) -> Any:
    if isinstance(value, dict):
        return {str(k): round_tree(v, digits) for k, v in value.items()}
    if isinstance(value, list):
        return [round_tree(v, digits) for v in value]
    if isinstance(value, tuple):
        return [round_tree(v, digits) for v in value]
    return number(value, digits)


def atom_key(atom: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    pred = str(atom.get("predicate", ""))
    args = tuple(str(arg) for arg in (atom.get("args") or []))
    return pred, args


def atom_signature(atoms: list[dict[str, Any]] | None) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(sorted(atom_key(atom) for atom in atoms or []))


def format_atoms(atoms: list[dict[str, Any]] | None) -> list[str]:
    out = []
    for atom in atoms or []:
        pred, args = atom_key(atom)
        out.append(f"{pred}({', '.join(args)})")
    return out


def selected_goal_from_rule(rule: dict[str, Any] | None) -> dict[str, Any]:
    if not rule:
        return {}
    goals = rule.get("recovery_goals")
    if isinstance(goals, list) and goals:
        first = goals[0]
        if isinstance(first, dict):
            return first
    return {}


def episode_records(run_dir: pathlib.Path, task_id: int | None) -> list[dict[str, Any]]:
    if task_id is None:
        return []
    task_dir = run_dir / f"task{task_id}"
    records: list[dict[str, Any]] = []
    for ep_dir in sorted(task_dir.glob("ep*")):
        rows = read_jsonl(ep_dir / "recovery_trace.jsonl")
        rule = next((row for row in rows if row.get("kind") == "rule"), None)
        plan = next((row for row in rows if row.get("kind") == "plan"), None)
        selected_goal = selected_goal_from_rule(rule)
        records.append(
            {
                "episode": ep_dir.name,
                "episode_dir": str(ep_dir),
                "query_idx": (plan or rule or {}).get("query_idx"),
                "skill_id": (plan or rule or {}).get("skill_id"),
                "plan_label": (plan or {}).get("label"),
                "plan_success": (plan or {}).get("success"),
                "plan_error": (plan or {}).get("error"),
                "rule_success": (rule or {}).get("success"),
                "language": (rule or {}).get("language"),
                "target_name": (rule or {}).get("target_name"),
                "goal_name": (rule or {}).get("goal_name"),
                "bddl_goal_atoms": (rule or {}).get("bddl_goal_atoms") or [],
                "selected_goal": selected_goal,
                "selected_goal_signature": atom_signature(selected_goal.get("atoms")),
            }
        )
    return records


def problem_records(run_dir: pathlib.Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for problem_path in sorted((run_dir / "cutamp_debug").glob("*.problem.json")):
        try:
            raw = load_json(problem_path)
        except (OSError, json.JSONDecodeError) as exc:
            records.append({"problem_path": str(problem_path), "load_error": str(exc)})
            continue
        problem = raw.get("problem", raw)
        atoms = problem.get("required_final_atoms") or problem.get("goal_atoms") or []
        result_path = problem_path.with_name(problem_path.name.replace(".problem.json", ".result.json"))
        records.append(
            {
                "problem_path": str(problem_path),
                "result_path": str(result_path),
                "stdout_path": str(problem_path.with_name(problem_path.name.replace(".problem.json", ".stdout.txt"))),
                "stderr_path": str(problem_path.with_name(problem_path.name.replace(".problem.json", ".stderr.txt"))),
                "problem": problem,
                "goal_signature": atom_signature(atoms),
            }
        )
    return records


def join_episodes_to_problems(
    episodes: list[dict[str, Any]],
    problems: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_signature: dict[tuple[tuple[str, tuple[str, ...]], ...], collections.deque[dict[str, Any]]] = collections.defaultdict(collections.deque)
    for record in problems:
        sig = record.get("goal_signature")
        if sig:
            by_signature[sig].append(record)
    joined = []
    for ep in episodes:
        sig = ep.get("selected_goal_signature")
        problem = by_signature.get(sig, collections.deque()).popleft() if sig in by_signature and by_signature[sig] else None
        item = dict(ep)
        if problem:
            item.update({k: v for k, v in problem.items() if k != "problem"})
            item["problem"] = problem["problem"]
        else:
            item["problem_match_error"] = "no cutamp problem matched selected recovery goal signature"
        joined.append(item)
    return joined


def parse_stderr(path: pathlib.Path) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    losses: list[dict[str, Any]] = []
    if not path.exists():
        return {
            "stderr_path": str(path),
            "missing": True,
            "events": [],
            "loss": {},
            "final_blockers": [],
            "zero_satisfying_constraints": [],
        }
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            constraint_match = CONSTRAINT_RE.search(line)
            if constraint_match:
                event = constraint_match.groupdict()
                event.update(
                    {
                        "line": line_no,
                        "tol": float(event["tol"]),
                        "satisfied": int(event["satisfied"]),
                        "total": int(event["total"]),
                        "remaining": int(event["remaining"]),
                        "key": f"{event['kind']}.{event['name'].strip()}",
                    }
                )
                events.append(event)
            loss_match = LOSS_RE.search(line)
            if loss_match:
                item = loss_match.groupdict()
                item.update(
                    {
                        "line": line_no,
                        "loss": float(item["loss"]),
                        "min": float(item["min"]),
                        "satisfied": int(item["satisfied"]),
                        "total": int(item["total"]),
                    }
                )
                losses.append(item)

    last_loss_line = max((item["line"] for item in losses), default=-1)
    final_blockers = [event for event in events if event["line"] > last_loss_line]
    if not final_blockers and events:
        final_blockers = events[-3:]
    zero = []
    seen = set()
    for event in events:
        key = event["key"]
        if event["satisfied"] == 0 and key not in seen:
            zero.append(key)
            seen.add(key)
    return {
        "stderr_path": str(path),
        "missing": False,
        "events": round_tree(events),
        "loss": {
            "num_updates": len(losses),
            "min_reported": number(min((item["min"] for item in losses), default=float("nan"))),
            "first_reported_min": number(losses[0]["min"]) if losses else None,
            "last_reported_min": number(losses[-1]["min"]) if losses else None,
        },
        "final_blockers": round_tree(final_blockers),
        "zero_satisfying_constraints": zero,
    }


def object_summary(obj: dict[str, Any]) -> dict[str, Any]:
    geom = obj.get("geometry") if isinstance(obj.get("geometry"), dict) else {}
    metadata = geom.get("metadata") if isinstance(geom.get("metadata"), dict) else {}
    return round_tree(
        {
            "name": obj.get("name"),
            "role": obj.get("role"),
            "pos": obj.get("pos"),
            "quat": obj.get("quat"),
            "radius": obj.get("radius"),
            "height": obj.get("height"),
            "half_extents": obj.get("half_extents"),
            "geometry_kind": geom.get("kind"),
            "geometry_source": geom.get("source"),
            "collision_geom_count": metadata.get("collision_geom_count"),
            "visual_only_geom_count": metadata.get("visual_only_geom_count"),
            "affordances": metadata.get("affordances"),
        }
    )


def collision_part_owner_prefix(name: Any) -> str:
    text = str(name or "")
    if not text:
        return ""
    match = re.match(r"(?P<prefix>.+?)_(?:g|geom_)?[0-9]+$", text)
    if match:
        return match.group("prefix")
    return text


def compact_counter(values: list[str], limit: int = 8) -> dict[str, int]:
    counts = collections.Counter(value for value in values if value)
    return dict(counts.most_common(limit))


def summarize_collision_parts(owner_name: str, parts: list[dict[str, Any]], limit: int = 12) -> dict[str, Any]:
    owner_base = str(owner_name or "").replace("_main", "")
    prefixes = [collision_part_owner_prefix(part.get("name")) for part in parts]
    body_names = [str(part.get("body_name") or "") for part in parts]
    suspicious: list[dict[str, Any]] = []
    for part, prefix, body_name in zip(parts, prefixes, body_names):
        prefix_ok = not prefix or prefix.startswith(owner_base) or owner_base.startswith(prefix)
        body_ok = not body_name or body_name == owner_name or body_name.startswith(owner_base)
        if prefix_ok and body_ok:
            continue
        suspicious.append(
            {
                "name": part.get("name"),
                "body_name": part.get("body_name"),
                "shape": part.get("shape"),
                "geom_id": part.get("geom_id"),
            }
        )
        if len(suspicious) >= limit:
            break
    return {
        "collision_part_name_prefix_counts": compact_counter(prefixes),
        "collision_part_body_name_counts": compact_counter(body_names),
        "suspicious_collision_parts": suspicious,
    }


def geometry_debug_summary(result: dict[str, Any]) -> dict[str, Any]:
    diag = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
    geom = diag.get("geometry_debug") if isinstance(diag.get("geometry_debug"), dict) else {}
    objects = []
    for obj in geom.get("objects", []) or []:
        parts = [dict(part) for part in obj.get("collision_parts", []) if isinstance(part, dict)]
        item = {
            "name": obj.get("name"),
            "role": obj.get("role"),
            "collision_representation": obj.get("collision_representation"),
            "collision_part_count": obj.get("collision_part_count"),
            "emitted_collision_parts": obj.get("emitted_collision_parts"),
            "cuboid_dims": obj.get("cuboid_dims"),
            "fallback_reason": obj.get("fallback_reason"),
        }
        if parts:
            item.update(summarize_collision_parts(str(obj.get("name") or ""), parts))
        objects.append(round_tree(item))
    collision_candidates = [
        obj
        for obj in objects
        if obj.get("collision_representation") not in {None, "excluded_target_support_surface"}
        and obj.get("role") in {"static_context", "surface"}
    ]
    return {
        "target_support_surfaces": geom.get("target_support_surfaces") or [],
        "excluded_collision_objects": geom.get("excluded_collision_objects") or [],
        "world_collision_candidate_objects": collision_candidates,
        "objects": objects,
        "collision_pair_detail": "object-level only; run cutamp ablation replay to identify likely blocker",
    }


def target_and_surfaces(problem: dict[str, Any], selected_goal: dict[str, Any]) -> tuple[str | None, list[str]]:
    target = None
    surfaces: list[str] = []
    atoms = selected_goal.get("atoms") or problem.get("goal_atoms") or []
    for atom in atoms:
        pred, args = atom_key(atom)
        if pred in {"on", "inside"} and len(args) >= 2:
            target = target or args[0]
            surfaces.append(args[1])
        elif pred == "holding" and args:
            target = target or args[-1]
    for name in selected_goal.get("surface_names") or []:
        if str(name) not in surfaces:
            surfaces.append(str(name))
    return target, surfaces


def derived_place_candidates(surface: dict[str, Any]) -> list[list[float]]:
    geom = surface.get("geometry") if isinstance(surface.get("geometry"), dict) else {}
    metadata = geom.get("metadata") if isinstance(geom.get("metadata"), dict) else {}
    inner = metadata.get("inner_bounds") if isinstance(metadata.get("inner_bounds"), dict) else {}
    if inner:
        x_min = float(inner.get("x_min", surface.get("pos", [0.0, 0.0, 0.0])[0]))
        x_max = float(inner.get("x_max", surface.get("pos", [0.0, 0.0, 0.0])[0]))
        y_min = float(inner.get("y_min", surface.get("pos", [0.0, 0.0, 0.0])[1]))
        y_max = float(inner.get("y_max", surface.get("pos", [0.0, 0.0, 0.0])[1]))
        z_offset = float(metadata.get("place_z_offset_m", 0.12))
        z = float(inner.get("support_z", inner.get("z_min", surface.get("pos", [0.0, 0.0, 0.0])[2]))) + z_offset
        return round_tree(
            [
                [0.5 * (x_min + x_max), 0.5 * (y_min + y_max), z],
                [x_min, 0.5 * (y_min + y_max), z],
                [x_max, 0.5 * (y_min + y_max), z],
                [0.5 * (x_min + x_max), y_min, z],
                [0.5 * (x_min + x_max), y_max, z],
            ]
        )
    pos = surface.get("pos") or [0.0, 0.0, 0.0]
    return round_tree([[float(pos[0]), float(pos[1]), float(pos[2]) + 0.12]])


def summarize_candidates(problem: dict[str, Any], selected_goal: dict[str, Any], max_grasps: int) -> dict[str, Any]:
    target, surface_names = target_and_surfaces(problem, selected_goal)
    grasps_by_name = problem.get("grasps") if isinstance(problem.get("grasps"), dict) else {}
    target_grasps = list(grasps_by_name.get(str(target), [])) if target else []
    top_grasps = []
    for grasp in target_grasps[:max(0, max_grasps)]:
        metadata = grasp.get("metadata") if isinstance(grasp.get("metadata"), dict) else {}
        top_grasps.append(
            round_tree(
                {
                    "pos": grasp.get("pos"),
                    "quat": grasp.get("quat"),
                    "width": grasp.get("width"),
                    "score": grasp.get("score"),
                    "source": grasp.get("source"),
                    "yaw": metadata.get("yaw"),
                    "rank": metadata.get("rank"),
                    "sampler": metadata.get("sampler"),
                }
            )
        )
    surfaces = {surface.get("name"): surface for surface in problem.get("surfaces", [])}
    place = {}
    for name in surface_names:
        surface = surfaces.get(name)
        if not surface:
            continue
        geom = surface.get("geometry") if isinstance(surface.get("geometry"), dict) else {}
        metadata = geom.get("metadata") if isinstance(geom.get("metadata"), dict) else {}
        place[name] = round_tree(
            {
                "surface": object_summary(surface),
                "inner_bounds": metadata.get("inner_bounds"),
                "place_z_offset_m": metadata.get("place_z_offset_m"),
                "exclude_source_collision": metadata.get("exclude_source_collision"),
                "derived_place_candidates": derived_place_candidates(surface),
            }
        )
    return {
        "target": target,
        "surface_names": surface_names,
        "target_grasp_count": len(target_grasps),
        "top_grasps": top_grasps,
        "place_surfaces": place,
    }


def infer_stage_diagnostics(record: dict[str, Any], problem: dict[str, Any]) -> dict[str, Any]:
    atoms = (record.get("selected_goal") or {}).get("atoms") or problem.get("goal_atoms") or []
    formatted = format_atoms(atoms)
    predicates = {atom_key(atom)[0] for atom in atoms if isinstance(atom, dict)}
    if predicates & {"on", "inside", "in"}:
        phase = "place_goal_optimization"
        basis = "selected recovery goal contains a placement atom"
    elif "holding" in predicates:
        phase = "pick_goal_optimization"
        basis = "selected recovery goal contains a holding atom"
    else:
        phase = "unknown_goal_optimization"
        basis = "selected recovery goal does not expose a pick/place predicate"
    return {"phase_guess": phase, "basis": basis, "goal_atoms": formatted}


def pos_err_constraint_summary(stderr: dict[str, Any]) -> dict[str, Any]:
    events = [
        event
        for event in stderr.get("events", []) or []
        if event.get("key") == "KinematicConstraint.pos_err"
    ]
    if not events:
        return {}
    final = [
        event
        for event in stderr.get("final_blockers", []) or []
        if event.get("key") == "KinematicConstraint.pos_err"
    ]
    event = final[-1] if final else events[-1]
    return {
        "tolerance_m": event.get("tol"),
        "satisfying_particles": event.get("satisfied"),
        "total_particles": event.get("total"),
        "line": event.get("line"),
        "note": "cuTAMP stderr reports aggregate pos_err satisfaction counts, not xyz residual vectors",
    }


def analyze_joined_record(record: dict[str, Any], max_grasps: int) -> dict[str, Any]:
    problem = record.get("problem") or {}
    result_path_raw = str(record.get("result_path") or "")
    stderr_path_raw = str(record.get("stderr_path") or "")
    result_path = pathlib.Path(result_path_raw) if result_path_raw else None
    stderr_path = pathlib.Path(stderr_path_raw) if stderr_path_raw else None
    result = load_json(result_path) if result_path is not None and result_path.is_file() else {}
    stderr = (
        parse_stderr(stderr_path)
        if stderr_path is not None
        else {
            "stderr_path": "",
            "missing": True,
            "events": [],
            "loss": {},
            "final_blockers": [],
            "zero_satisfying_constraints": [],
        }
    )
    diag = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
    out = {k: v for k, v in record.items() if k not in {"problem", "selected_goal_signature"}}
    out["selected_goal"] = {
        **(record.get("selected_goal") or {}),
        "atoms_formatted": format_atoms((record.get("selected_goal") or {}).get("atoms")),
    }
    out["cutamp_result"] = {
        "available": result.get("available"),
        "feasible": result.get("feasible"),
        "num_satisfying": result.get("num_satisfying"),
        "failure_reason": result.get("failure_reason"),
        "elapsed_sec": number(result.get("elapsed_sec")),
        "plan_type": diag.get("plan_type"),
        "optimized_plan_present": diag.get("optimized_plan_present"),
        "optimized_operator_count": diag.get("optimized_operator_count"),
        "optimized_binding_names": diag.get("optimized_binding_names"),
        "grasp_sampler_profile": diag.get("grasp_sampler_profile"),
        "grasp_counts": diag.get("grasp_counts"),
    }
    out["constraint_diagnostics"] = stderr
    out["stage_diagnostics"] = infer_stage_diagnostics(record, problem)
    out["pos_err_diagnostics"] = pos_err_constraint_summary(stderr)
    out["problem_goal_atoms"] = format_atoms(problem.get("goal_atoms") or [])
    out["problem_required_final_atoms"] = format_atoms(problem.get("required_final_atoms") or [])
    out["movables"] = [object_summary(obj) for obj in problem.get("movables", [])]
    out["surfaces"] = [object_summary(obj) for obj in problem.get("surfaces", [])]
    out["statics"] = [object_summary(obj) for obj in problem.get("statics", [])]
    out["candidate_diagnostics"] = summarize_candidates(problem, record.get("selected_goal") or {}, max_grasps)
    out["geometry_debug"] = geometry_debug_summary(result)
    return out


def summarize_report(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    constraint_freq = collections.Counter()
    final_freq = collections.Counter()
    skill_freq = collections.Counter()
    feasible = 0
    for ep in episodes:
        if ep.get("cutamp_result", {}).get("feasible"):
            feasible += 1
        if ep.get("skill_id"):
            skill_freq[str(ep["skill_id"])] += 1
        diag = ep.get("constraint_diagnostics", {})
        for key in diag.get("zero_satisfying_constraints", []) or []:
            constraint_freq[key] += 1
        for event in diag.get("final_blockers", []) or []:
            final_freq[event.get("key", "")] += 1
    return {
        "num_episodes": len(episodes),
        "num_feasible": feasible,
        "num_infeasible": len(episodes) - feasible,
        "skills": dict(skill_freq),
        "zero_satisfying_constraint_frequency": dict(constraint_freq),
        "final_blocker_frequency": dict(final_freq),
    }


def md_list(items: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in items) if items else "none"


def write_markdown(path: pathlib.Path, report: dict[str, Any]) -> None:
    lines: list[str] = []
    summary = report["summary"]
    lines.append("# cuTAMP Recovery Diagnosis")
    lines.append("")
    lines.append(f"- run_dir: `{report['run_dir']}`")
    if report.get("task_id") is not None:
        lines.append(f"- task_id: `{report['task_id']}`")
    lines.append(f"- episodes: {summary['num_episodes']}")
    lines.append(f"- feasible: {summary['num_feasible']}")
    lines.append(f"- infeasible: {summary['num_infeasible']}")
    lines.append(f"- skills: `{summary['skills']}`")
    lines.append(f"- zero-satisfying constraints: `{summary['zero_satisfying_constraint_frequency']}`")
    lines.append(f"- final blockers: `{summary['final_blocker_frequency']}`")
    lines.append("")

    for ep in report["episodes"]:
        lines.append(f"## {ep.get('episode', pathlib.Path(str(ep.get('problem_path', 'unknown'))).stem)}")
        result = ep.get("cutamp_result", {})
        constraints = ep.get("constraint_diagnostics", {})
        cand = ep.get("candidate_diagnostics", {})
        geom = ep.get("geometry_debug", {})
        lines.append(
            "- trigger: "
            f"query_idx={ep.get('query_idx')} skill=`{ep.get('skill_id')}` "
            f"label=`{ep.get('plan_label')}`"
        )
        lines.append(
            "- result: "
            f"feasible={result.get('feasible')} num_satisfying={result.get('num_satisfying')} "
            f"reason=`{result.get('failure_reason')}` elapsed_sec={result.get('elapsed_sec')}"
        )
        final = [event.get("key", "") for event in constraints.get("final_blockers", [])]
        zero = constraints.get("zero_satisfying_constraints", [])
        lines.append(f"- final blockers: {md_list([item for item in final if item])}")
        lines.append(f"- zero-satisfying constraints: {md_list(zero)}")
        lines.append(f"- loss: `{constraints.get('loss')}`")
        lines.append(f"- phase guess: `{(ep.get('stage_diagnostics') or {}).get('phase_guess')}`")
        lines.append(f"- pos_err detail: `{ep.get('pos_err_diagnostics') or {}}`")
        lines.append(f"- goal: {md_list(ep.get('problem_required_final_atoms') or ep.get('problem_goal_atoms') or [])}")
        lines.append(f"- target: `{cand.get('target')}` surfaces: {md_list(cand.get('surface_names') or [])}")
        lines.append(
            "- support exclusions: "
            f"target_support={md_list(geom.get('target_support_surfaces') or [])} "
            f"excluded=`{geom.get('excluded_collision_objects') or []}`"
        )
        lines.append(f"- world collision candidates: `{geom.get('world_collision_candidate_objects') or []}`")
        lines.append(f"- collision pair detail: `{geom.get('collision_pair_detail')}`")
        for movable in ep.get("movables", []):
            lines.append(f"- movable: `{movable}`")
        for name, place in (cand.get("place_surfaces") or {}).items():
            lines.append(f"- place surface `{name}`: `{place}`")
        lines.append(f"- top grasps: `{cand.get('top_grasps') or []}`")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
    episodes = episode_records(run_dir, args.task_id)
    problems = problem_records(run_dir)
    joined = join_episodes_to_problems(episodes, problems) if episodes else problems
    analyzed = [analyze_joined_record(record, args.max_grasps) for record in joined]
    report = {
        "run_dir": str(run_dir),
        "task_id": args.task_id,
        "summary": summarize_report(analyzed),
        "episodes": analyzed,
    }

    out_json = pathlib.Path(args.out_json) if args.out_json else run_dir / "cutamp_recovery_diagnosis.json"
    out_md = pathlib.Path(args.out_md) if args.out_md else run_dir / "cutamp_recovery_diagnosis.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(out_md, report)
    print(f"wrote_json={out_json}")
    print(f"wrote_markdown={out_md}")
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
