"""Dependency-free actor context shared by offline and automated mining."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


GUIDELINE_FILES = (
    "docs/skill_authoring_evidence_and_probes.md",
    "docs/repair_skill_authoring_guidelines.md",
    "docs/grasp_skill_authoring_guidelines.md",
    "docs/grounding_skill_authoring_guidelines.md",
    "docs/geometry_skill_authoring_guidelines.md",
    "docs/place_skill_authoring_guidelines.md",
    "docs/repair_skill_static_test_standard.md",
    "docs/grasp_skill_static_test_standard.md",
    "docs/grounding_skill_static_test_standard.md",
    "docs/geometry_skill_static_test_standard.md",
    "docs/place_skill_static_test_standard.md",
    "docs/skill_pipeline_mining_loop.md",
    "docs/offline_skill_trigger_scan.md",
    "docs/skill_pack_isolation_2026-09-09.md",
    "docs/diagnostic_signal_pipeline.md",
    "docs/skill_capability_registry.md",
)


def guideline_index(repo: Path) -> str:
    lines = [
        "Read the authoring guide for EVERY skill type you change before drafting.",
        "These are full files, not excerpts. In findings.md cite the guides and",
        "the source/trace/frame files you actually inspected. File presence is not proof of reading.",
    ]
    for rel in GUIDELINE_FILES:
        path = repo / rel
        if not path.is_file():
            raise FileNotFoundError(f"Required actor guideline missing: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"- {rel}: `{path.as_posix()}` (sha256={digest})")
    return "\n".join(lines)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def trace_rows(path: Path) -> list[dict]:
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue  # A live writer may have left an incomplete final line.
            if isinstance(value, dict):
                rows.append(value)
    return rows


def compact(value: Any, limit: int = 2000) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + " [open source file for full record]"


def episode_evidence(path: Path) -> dict:
    episode = read_json(path / "episode.json")
    recovery = trace_rows(path / "recovery_trace.jsonl")
    queries = trace_rows(path / "query_trace.jsonl")
    interesting = []
    for i, row in enumerate(recovery):
        if (row.get("error") or row.get("selected_skill") or row.get("winner")
                or row.get("kind") == "rule" or row.get("event") == "place_release_check"):
            interesting.append(i)
    chosen = sorted(set(interesting[:3] + interesting[-3:]))
    selected = [recovery[i] for i in chosen]
    qids = {row.get("query_idx") for row in selected if isinstance(row.get("query_idx"), int)}
    if not qids and queries:
        failures = [q for q in queries if q.get("vla_pick_target_status") in {
            "non_target_intent_with_motion", "closed_non_target", "empty_close_near_target"}]
        for row in queries[:1] + failures[:1] + queries[-1:]:
            if isinstance(row.get("query_idx"), int):
                qids.add(row["query_idx"])
    near = [q for q in queries if isinstance(q.get("query_idx"), int)
            and any(abs(q["query_idx"] - v) <= 1 for v in qids)]
    frames = sorted(path.glob("frames/*"))
    near_frames = [str(f) for f in frames if any(f"q{q:04d}" in f.name for q in qids)]
    debug = path / "cutamp_debug"
    shared_debug = path.parent.parent / "cutamp_debug"
    debug_is_shared = not debug.is_dir() and shared_debug.is_dir()
    if debug_is_shared:
        debug = shared_debug
    stderrs = sorted(debug.glob("*.stderr.txt"))
    constraints = []
    for f in stderrs:
        matching = [s for s in f.read_text(errors="replace").splitlines()
                    if any(t in s for t in ("satisfying", "No satisfying", "Motion planning failed", "No such file", "Traceback"))]
        if matching:
            constraints.append({"path": str(f), "lines": matching[-10:]})
    return {
        "episode_dir": str(path), "episode": episode,
        "trace_paths": [str(path / name) for name in ("query_trace.jsonl", "recovery_trace.jsonl")],
        "recovery_records": [compact(r, 2500) for r in selected],
        "nearby_queries": [compact(r, 1200) for r in near[:6]],
        "frames": near_frames[:8] or [str(f) for f in frames[:2]],
        "debug_dir": str(debug),
        "debug_scope": "validation_shared_unassigned_to_episode" if debug_is_shared else "episode",
        "problem_paths": [str(f) for f in sorted(debug.glob("*.problem.json"))[:3]],
        "result_paths": [str(f) for f in sorted(debug.glob("*.result.json"))[:3]],
        "constraint_records": constraints[:2] + constraints[2:][-1:],
    }


def history(entry: dict) -> list[dict]:
    result = []
    previous: dict[str, bool] = {}
    for attempt in entry.get("attempts") or []:
        triage = attempt.get("triage") or {}
        outcomes = {str(e.get("episode_id")): bool(e.get("success"))
                    for e in triage.get("episode_diagnoses") or []}
        result.append({
            "write": attempt.get("writes"), "validation_dir": attempt.get("on_dir"),
            "successes": triage.get("success_count"), "episodes": triage.get("episode_count"),
            "signature": triage.get("primary_signature"),
            "improved": [k for k, v in outcomes.items() if v and k in previous and not previous[k]],
            "regressed": [k for k, v in outcomes.items() if not v and previous.get(k)],
            "failures": [{"episode_id": e.get("episode_id"), "signature": e.get("signature"),
                          "path": e.get("episode_dir")} for e in triage.get("episode_diagnoses") or []
                         if not e.get("success")],
        })
        previous = outcomes
    return result


def collect_context(run_root: Path, evidence_path: Path, task_id: int) -> dict:
    lane = read_json(run_root / "mine/lane_command.json")
    args = lane.get("args") or {}
    suite = args.get("task_suite_name")
    if not suite:
        raise ValueError("lane_command.json has no task_suite_name; refusing to guess suite")
    state = read_json(run_root / "mine/mine_state.json")
    if int(state.get("awaiting_task") or 0) != task_id:
        raise ValueError("Task changed while assembling intervention context")
    entry = (state.get("tasks") or {}).get(str(task_id)) or {}
    evidence = read_json(evidence_path)
    episodes = [Path(r["episode_dir"]) for r in evidence.get("failures") or [] if r.get("episode_dir")]
    # Include successes as controls when this round has them, not only the fail_set.
    controls = []
    if episodes:
        for p in sorted(episodes[0].parent.glob("ep*/episode.json")):
            if read_json(p).get("success"):
                controls.append(p.parent)
    selected = list(dict.fromkeys(episodes[:2] + episodes[-1:] + controls[:1]))
    details = [episode_evidence(p) for p in selected]
    for detail in details:
        meta = detail["episode"]
        recorded_suite = meta.get("source_suite") or meta.get("task_suite_name")
        if recorded_suite and recorded_suite != suite:
            raise ValueError(f"Evidence suite {recorded_suite} disagrees with lane {suite}")
        if meta.get("task_id_1based") and int(meta["task_id_1based"]) != task_id:
            raise ValueError("Evidence task id disagrees with active task")
    descriptions = sorted({str(d["episode"].get("task_description") or d["episode"].get("task_language") or "")
                           for d in details} - {""})
    pack = str(args.get("skill_pack") or "")
    repo = str(args.get("repo_root") or lane.get("repo_root") or lane.get("cwd") or "")
    pack_path = Path(pack) if Path(pack).is_absolute() else Path(repo) / "skill_packs" / pack
    files = {}
    if pack_path.is_dir():
        for p in sorted(pack_path.rglob("*")):
            if p.is_file() and p.suffix in {".md", ".yaml", ".py"}:
                files[str(p.relative_to(pack_path))] = hashlib.sha256(p.read_bytes()).hexdigest()
    result = {
        "identity": {"run_root": str(run_root), "suite": suite, "task_id": task_id,
                     "task_descriptions": descriptions, "skill_pack": str(pack_path), "repo": repo,
                     "writes_used": int(entry.get("writes") or 0), "seed_start": args.get("episode_seed_start"),
                     "num_trials": args.get("num_trials"), "evidence_path": str(evidence_path),
                     "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest()},
        "pack_files_sha256": files,
        "current_candidate": {k: entry.get(k) for k in ("candidate_skill_ids", "candidate_bundle_id", "candidate_skill_paths")},
        "rounds": history(entry), "representative_episodes": details,
        "invalid_validations": entry.get("invalid_validations") or [],
        "all_failure_episode_dirs": [str(p) for p in episodes],
    }
    if details:
        first = selected[0]
        q = trace_rows(first / "query_trace.jsonl")
        if q:
            # Preserve the raw goal/recovery fields; no guessed surface or language rewrite here.
            result["initial_query_record"] = {k: q[0][k] for k in (
                "query_idx", "target_name", "target_xyz", "goal_name", "goal_xyz", "bddl_path",
                "bddl_goal_atoms", "bddl_goal_surfaces", "bddl_regions", "recovery_hints") if k in q[0]}
    manifest = Path(repo) / "deployment_manifest.json"
    if manifest.exists():
        result["identity"]["deployment_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--task", required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(collect_context(args.run_root, args.evidence, args.task), ensure_ascii=False))
