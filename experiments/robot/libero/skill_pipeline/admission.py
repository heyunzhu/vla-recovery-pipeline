"""Admission gate for candidate recovery skills.

This module is the CI-like boundary between a Codex-written draft and the
mutable skill library.  It does not run the robot simulator; it combines schema
checks, type-specific static checks, offline trigger replay, and optional
generated-benchmark smoke artifact validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .capabilities import load_capability_registry
from .coordinator import check_draft
from .generated_benchmark_gate import validate_generated_benchmark, validate_generated_smoke_run
from .grasp_static import check_grasp_skill_library, render_grasp_static_markdown
from .predicate_registry import (
    BUILTIN_APPROACH_CONTEXT_PREDICATES,
    BUILTIN_FAILURE_EVIDENCE_PREDICATES,
    PredicateRegistry,
    load_predicate_registry,
)
from .schema import SkillSchemaError, SkillSpec, iter_trigger_predicates, load_skill
from .trigger_scan import ScanConfig, load_scan_skills, scan_roots as run_offline_scan, write_scan_outputs
from .validate import FAIL_RECALL_MIN, SUCCESS_EPISODE_FIRE_MAX

DEFAULT_OFFLINE_SCAN_CORPUS_ROOT = "analysis_outputs/offline_trigger_corpus"
DEFAULT_MIN_FIRST_REPAIR_QUERY_IDX = 5

APPROACH_CONTEXT_PREDICATES = set(BUILTIN_APPROACH_CONTEXT_PREDICATES)
FAILURE_EVIDENCE_PREDICATES = set(BUILTIN_FAILURE_EVIDENCE_PREDICATES)


@dataclass(frozen=True)
class SkillAdmissionConfig:
    index_path: str | Path
    out_dir: str | Path
    scan_roots: Sequence[str | Path] = field(default_factory=tuple)
    current_scan_roots: Sequence[str | Path] = field(default_factory=tuple)
    current_task_ids: Sequence[int] = field(default_factory=tuple)
    current_task_names: Sequence[str] = field(default_factory=tuple)
    mining: bool = False
    require_offline_scan: bool = True
    allow_current_only_scan: bool = False
    include_hints: bool = True
    include_empty_query_rows: bool = False
    max_queries_per_episode: int = 0
    min_current_fail_recall: float = FAIL_RECALL_MIN
    max_success_episode_match_rate: float = SUCCESS_EPISODE_FIRE_MAX
    max_success_winner_episode_matches: int = 0
    min_first_repair_query_idx: int = DEFAULT_MIN_FIRST_REPAIR_QUERY_IDX
    generated_benchmark_dir: str | Path | None = None
    generated_split: str = "smoke"
    generated_smoke_run_dir: str | Path | None = None
    require_generated_smoke: bool = False
    generated_smoke_min_episodes_per_task: int = 1
    generated_smoke_require_video: bool = True
    min_scan_episodes_warning: int = 5
    capability_registry: str | Path | None = None
    predicate_registry: str | Path | None = None
    predicate_adapter: str | Path | None = None
    diagnostic_signal_registry: str | Path | None = None
    diagnostic_signal_statuses: str = ""
    diagnostic_provider_roots: Sequence[str | Path] = field(default_factory=tuple)


def discover_recent_trace_corpora(
    *,
    repo_root: str | Path,
    corpus_root: str | Path | None = None,
    limit: int = 8,
) -> list[Path]:
    """Return recent archived trace corpora, newest first."""

    repo = Path(repo_root)
    root = Path(corpus_root or DEFAULT_OFFLINE_SCAN_CORPUS_ROOT)
    if not root.is_absolute():
        root = repo / root
    if not root.is_dir():
        return []
    candidates = [path for path in root.iterdir() if path.is_dir() and (path / "manifest.json").exists()]
    candidates.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return candidates[: max(0, int(limit))]


def resolve_admission_scan_roots(
    explicit_roots: Sequence[str | Path] | None,
    *,
    repo_root: str | Path,
    corpus_root: str | Path | None = None,
    max_corpus_runs: int = 8,
    fallback_scan_root: str | Path | None = None,
) -> list[Path]:
    """Resolve the single global offline scan set for admission.

    The current/fallback run, explicit canaries, and recent rolling corpora are
    combined into one scan input.  This keeps admission from having separate
    "local" and "global" trigger gates while still ensuring the current task is
    present in the global replay.
    """

    roots: list[Path] = []
    if fallback_scan_root:
        roots.append(Path(fallback_scan_root))
    roots.extend(Path(path) for path in (explicit_roots or []) if str(path))
    recent = discover_recent_trace_corpora(
        repo_root=repo_root,
        corpus_root=corpus_root,
        limit=max_corpus_runs,
    )
    roots.extend(recent)

    seen: set[str] = set()
    unique: list[Path] = []
    for path in roots:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _skill_summary(spec: SkillSpec) -> dict[str, Any]:
    return {
        "id": spec.id,
        "kind": spec.kind,
        "scope": spec.scope,
        "track": spec.track,
        "hook": spec.hook or "",
        "priority": int(spec.priority),
        "path": spec.path,
    }


def _find_skill_row(scan_report: Mapping[str, Any], skill_id: str) -> dict[str, Any]:
    for row in scan_report.get("skills") or []:
        if str(row.get("skill_id") or "") == skill_id:
            return dict(row)
    return {}


def _episode_label(row: Mapping[str, Any]) -> str:
    return f"{row.get('task')}/{row.get('episode')}"


def _episode_key(row: Mapping[str, Any]) -> str:
    return _episode_label(row)


def _success_winner_episodes(scan_report: Mapping[str, Any], skill_id: str) -> list[str]:
    hits: list[str] = []
    for episode in scan_report.get("episodes") or []:
        if not bool(episode.get("success")):
            continue
        if skill_id in set(str(item) for item in episode.get("repair_winner_episode_hits") or []):
            hits.append(_episode_label(episode))
    return hits


def _canonical_prefixes(paths: Sequence[str | Path]) -> list[Path]:
    prefixes: list[Path] = []
    seen: set[str] = set()
    for raw in paths:
        if not str(raw):
            continue
        path = Path(raw).resolve()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        prefixes.append(path)
    return prefixes


def _path_under(path: str | Path, prefixes: Sequence[Path]) -> bool:
    if not prefixes:
        return False
    resolved = Path(path).resolve()
    for prefix in prefixes:
        try:
            resolved.relative_to(prefix)
            return True
        except ValueError:
            continue
    return False


def _candidate_in_episode(spec: SkillSpec, episode: Mapping[str, Any], *, winner_only: bool = False) -> bool:
    if spec.kind == "recovery_hint":
        return spec.id in set(str(item) for item in episode.get("hint_episode_hits") or [])
    key = "repair_winner_episode_hits" if winner_only else "repair_episode_hits"
    return spec.id in set(str(item) for item in episode.get(key) or [])


def _episode_scope_stats(
    *,
    spec: SkillSpec,
    episodes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    success = [item for item in episodes if bool(item.get("success"))]
    failed = [item for item in episodes if not bool(item.get("success"))]
    matches = [item for item in episodes if _candidate_in_episode(spec, item)]
    success_matches = [item for item in success if _candidate_in_episode(spec, item)]
    failed_matches = [item for item in failed if _candidate_in_episode(spec, item)]
    success_winners = [
        _episode_label(item)
        for item in success
        if _candidate_in_episode(spec, item, winner_only=True)
    ]
    return {
        "episodes": len(episodes),
        "success_episodes": len(success),
        "failed_episodes": len(failed),
        "episode_matches": len(matches),
        "success_episode_matches": len(success_matches),
        "failed_episode_matches": len(failed_matches),
        "failed_episode_recall": 0.0 if not failed else len(failed_matches) / len(failed),
        "success_match_rate": 0.0 if not success else len(success_matches) / len(success),
        "success_winner_episodes": success_winners,
        "success_winner_episode_count": len(success_winners),
    }


def _episode_under_prefixes(episode: Mapping[str, Any], prefixes: Sequence[Path]) -> bool:
    return _path_under(str(episode.get("episode_dir") or ""), prefixes) if prefixes else False


def _episode_matches_current_task(
    episode: Mapping[str, Any],
    *,
    current_task_ids: set[int],
    current_task_names: set[str],
) -> bool:
    task_name = str(episode.get("task") or "")
    if current_task_names and task_name in current_task_names:
        return True
    if current_task_ids:
        try:
            task_id = int(episode.get("task_id_1based"))
        except (TypeError, ValueError):
            task_id = -1
        if task_id in current_task_ids:
            return True
    return not current_task_ids and not current_task_names


def _trigger_failure_evidence(
    spec: SkillSpec,
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> tuple[list[str], list[str]]:
    """Return failure evidence predicates and all trigger predicate names.

    Approach predicates say where the hand is going.  Repair predicates must
    also say what has already gone wrong; otherwise the skill is an early
    delegation policy rather than a recovery trigger.
    """

    all_names: list[str] = []
    evidence: list[str] = []
    registry = predicate_registry or getattr(spec, "predicate_registry", None) or PredicateRegistry.builtins()
    for name, value in iter_trigger_predicates(spec.trigger):
        all_names.append(name)
        if registry.evidence_role(name, value) == "failure_evidence":
            evidence.append(name)
            continue
        if name == "object_followed_lift" and value is False:
            evidence.append(name)
    return sorted(set(evidence)), all_names


def _repair_trigger_static_gate(
    spec: SkillSpec,
    *,
    predicate_registry: PredicateRegistry | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    registry = predicate_registry or getattr(spec, "predicate_registry", None) or PredicateRegistry.builtins()
    evidence, names = _trigger_failure_evidence(spec, predicate_registry=registry)
    hints = dict(spec.recovery_hints or {})
    params = hints.get("params")
    if params is None:
        params = {}
    if not isinstance(params, Mapping):
        errors.append("repair/trigger recovery_hints.params must be a mapping")
        params = {}
    approach_only = bool(names) and all(registry.evidence_role(name) == "approach_context" for name in names)
    if not evidence:
        errors.append(
            "repair/trigger must include a negative failure-evidence predicate; "
            "target approach, open aperture, and empty hand are not enough"
        )
    if approach_only:
        errors.append(
            "repair/trigger appears to be target-approach-only; this is early delegation, not repair"
        )
    if "holding_status_is" in names and not evidence:
        warnings.append(
            "holding_status_is=handempty_or_unconfirmed is normal before pick and does not count as failure evidence"
        )
    if "grasp_profile" in hints:
        errors.append("repair/trigger must not own grasp_profile; use a recovery_hint grasp skill")
    if "target" in hints:
        errors.append("repair/trigger must not own target binding; use a recovery_hint grounding skill")
    if "executor" in params:
        errors.append("repair/trigger must use params.repair_profile instead of inline params.executor")
    for key in ("place_profile", "grounding_profile", "geometry_profile", "grounding_hints", "geometry_hints"):
        if key in params:
            errors.append(f"repair/trigger must not own {key}; use the matching recovery_hint skill type")
    return (
        {
            "type": "repair",
            "trigger_predicates": names,
            "failure_evidence_predicates": evidence,
            "approach_only": approach_only,
            "repair_profile": str(params.get("repair_profile") or ""),
        },
        errors,
        warnings,
    )


def _candidate_first_fire_queries(
    scan_report: Mapping[str, Any],
    skill_id: str,
) -> dict[str, dict[str, Any]]:
    first: dict[str, dict[str, Any]] = {}
    for row in scan_report.get("query_matches") or []:
        would_fire = set(str(item) for item in row.get("repair_would_fire") or [])
        if skill_id not in would_fire:
            continue
        label = f"{row.get('task')}/{row.get('episode')}"
        key = str(row.get("episode_dir") or label)
        qidx = row.get("query_idx")
        if qidx is None:
            continue
        qint = int(qidx)
        if key not in first or qint < int(first[key]["query_idx"]):
            first[key] = {
                "episode": label,
                "episode_dir": str(row.get("episode_dir") or ""),
                "query_idx": qint,
                "success": bool(row.get("success")),
            }
    return first


def _offline_scan_gate(
    *,
    spec: SkillSpec,
    scan_report: Mapping[str, Any],
    config: SkillAdmissionConfig,
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    overall = dict(scan_report.get("overall") or {})
    candidate = _find_skill_row(scan_report, spec.id)
    episode_reports = list(scan_report.get("episodes") or [])
    current_prefixes = _canonical_prefixes(config.current_scan_roots)
    current_task_ids = {int(item) for item in config.current_task_ids if int(item) > 0}
    current_task_names = {str(item) for item in config.current_task_names if str(item)}
    current_episodes = [
        episode
        for episode in episode_reports
        if (
            (_episode_under_prefixes(episode, current_prefixes) or not current_prefixes)
            and _episode_matches_current_task(
                episode,
                current_task_ids=current_task_ids,
                current_task_names=current_task_names,
            )
        )
    ]
    current_episode_dirs = {str(episode.get("episode_dir") or "") for episode in current_episodes}
    non_current_episodes = [
        episode
        for episode in episode_reports
        if str(episode.get("episode_dir") or "") not in current_episode_dirs
    ]
    current_stats = _episode_scope_stats(spec=spec, episodes=current_episodes)
    non_current_stats = _episode_scope_stats(spec=spec, episodes=non_current_episodes)
    total_episodes = int(overall.get("episodes") or 0)
    success_episodes = int(overall.get("success") or 0)
    failed_episodes = int(overall.get("failed") or 0)
    success_matches = int(candidate.get("success_episode_matches") or 0)
    failed_matches = int(candidate.get("failed_episode_matches") or 0)
    success_match_rate = 0.0 if success_episodes <= 0 else success_matches / success_episodes
    success_winners = _success_winner_episodes(scan_report, spec.id)
    non_current_success_matches = [
        _episode_label(episode)
        for episode in non_current_episodes
        if bool(episode.get("success")) and _candidate_in_episode(spec, episode)
    ]
    non_current_success_winners = [
        _episode_label(episode)
        for episode in non_current_episodes
        if bool(episode.get("success")) and _candidate_in_episode(spec, episode, winner_only=True)
    ]
    non_current_success_winner_set = set(non_current_success_winners)
    non_current_shadowed_success_matches = [
        label for label in non_current_success_matches if label not in non_current_success_winner_set
    ]
    first_fire = _candidate_first_fire_queries(scan_report, spec.id)
    min_first_q = int(config.min_first_repair_query_idx)
    current_early_fire = [
        row
        for row in first_fire.values()
        if str(row.get("episode_dir") or "") in current_episode_dirs
        and int(row.get("query_idx") or 0) < min_first_q
    ]
    non_current_early_fire = [
        row
        for row in first_fire.values()
        if str(row.get("episode_dir") or "") not in current_episode_dirs
        if int(row.get("query_idx") or 0) < min_first_q
    ]
    current_early_fire.sort(key=lambda row: (int(row.get("query_idx") or 0), str(row.get("episode") or "")))
    non_current_early_fire.sort(key=lambda row: (int(row.get("query_idx") or 0), str(row.get("episode") or "")))
    early_fire = current_early_fire + non_current_early_fire

    if total_episodes <= 0:
        errors.append("offline scan found no episodes")
    elif total_episodes < int(config.min_scan_episodes_warning):
        warnings.append(
            f"offline scan coverage is weak: only {total_episodes} episode(s)"
        )
    if current_prefixes and not current_episodes:
        errors.append(
            "offline scan was given current scan roots but found no current-task episodes"
        )
    if current_prefixes and not non_current_episodes and not bool(config.allow_current_only_scan):
        errors.append(
            "global offline scan requires non-current episodes; refusing current-task-only admission"
        )
    if not candidate:
        errors.append(f"offline scan did not include candidate skill: {spec.id}")
    elif spec.kind != "recovery_hint":
        if current_episodes and current_stats["failed_episodes"]:
            current_recall = float(current_stats["failed_episode_recall"])
            if current_recall < float(config.min_current_fail_recall):
                errors.append(
                    f"candidate repair recall on current-task failures is {current_recall:.2f}, "
                    f"below {float(config.min_current_fail_recall):.2f}"
                )
        if len(non_current_success_winners) > int(config.max_success_winner_episode_matches):
            errors.append(
                "candidate repair becomes winner on non-current success episodes: "
                f"{non_current_success_winners[:5]}"
            )
        if non_current_shadowed_success_matches:
            warnings.append(
                "candidate repair condition matches non-current success episodes but is shadowed "
                "by a higher-priority winner: "
                + ", ".join(non_current_shadowed_success_matches[:8])
            )
        if failed_episodes and failed_matches <= 0:
            warnings.append(
                "candidate repair did not match any failed episode in the global scan corpus"
            )
        if current_early_fire and min_first_q > 0:
            errors.append(
                f"candidate repair first fires before query {min_first_q} on current-task "
                f"{len(current_early_fire)} episode(s): "
                + ", ".join(
                    f"{item['episode']}@q{item['query_idx']}" for item in current_early_fire[:8]
                )
            )
        if non_current_early_fire and min_first_q > 0:
            warnings.append(
                f"candidate repair first fires before query {min_first_q} on non-current "
                f"{len(non_current_early_fire)} episode(s): "
                + ", ".join(
                    f"{item['episode']}@q{item['query_idx']}" for item in non_current_early_fire[:8]
                )
            )
    else:
        if current_episodes and not int(current_stats["episode_matches"]):
            errors.append("candidate recovery hint did not match current-task scan episodes")
        if not int(candidate.get("episode_matches") or 0):
            warnings.append("candidate recovery hint did not match any episode in the global scan corpus")

    summary = {
        "skill_id": spec.id,
        "kind": spec.kind,
        "scope": spec.scope,
        "episodes": total_episodes,
        "success_episodes": success_episodes,
        "failed_episodes": failed_episodes,
        "episode_matches": int(candidate.get("episode_matches") or 0),
        "query_matches": int(candidate.get("query_matches") or 0),
        "winner_episodes": int(candidate.get("winner_episodes") or 0),
        "success_episode_matches": success_matches,
        "failed_episode_matches": failed_matches,
        "success_match_rate": success_match_rate,
        "success_winner_episodes": success_winners,
        "first_fire_episode_count": len(first_fire),
        "min_first_repair_query_idx": min_first_q,
        "early_fire_episode_count": len(early_fire),
        "early_fire_episodes": early_fire[:20],
        "current_early_fire_episode_count": len(current_early_fire),
        "current_early_fire_episodes": current_early_fire[:20],
        "non_current_early_fire_episode_count": len(non_current_early_fire),
        "non_current_early_fire_episodes": non_current_early_fire[:20],
        "current_task_effectiveness": current_stats,
        "global_safety": {
            "episodes": total_episodes,
            "success_episodes": success_episodes,
            "failed_episodes": failed_episodes,
            "success_episode_matches": success_matches,
            "success_match_rate": success_match_rate,
            "success_winner_episodes": success_winners,
            "non_current_episodes": non_current_stats["episodes"],
            "non_current_success_episode_matches": non_current_stats["success_episode_matches"],
            "non_current_success_winner_episode_matches": len(non_current_success_winners),
            "non_current_success_winner_episodes": non_current_success_winners,
            "non_current_shadowed_success_matches": non_current_shadowed_success_matches,
            "non_current_failed_episode_matches": non_current_stats["failed_episode_matches"],
            "non_current_episode_matches": non_current_stats["episode_matches"],
        },
    }
    return summary, errors, warnings


def _run_static_gate(
    *,
    spec: SkillSpec,
    skill_file: str | Path,
    index_path: str | Path,
    out_dir: Path,
    predicate_registry: PredicateRegistry | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if spec.kind == "recovery_hint" and spec.scope == "grasp":
        grasp_report = check_grasp_skill_library(index_path, extra_skill_files=[skill_file])
        grasp_md = out_dir / "grasp_static_gate.md"
        grasp_json = out_dir / "grasp_static_gate.json"
        grasp_md.write_text(render_grasp_static_markdown(grasp_report), encoding="utf-8")
        grasp_json.write_text(json.dumps(grasp_report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        if grasp_report.error_count:
            errors.append(f"grasp static gate has {grasp_report.error_count} error(s)")
        return (
            {
                "type": "grasp",
                "errors": grasp_report.error_count,
                "warnings": grasp_report.warning_count,
                "markdown": str(grasp_md),
                "json": str(grasp_json),
            },
            errors,
            warnings,
        )
    if spec.kind in {"trigger", "repair"}:
        return _repair_trigger_static_gate(spec, predicate_registry=predicate_registry)
    warnings.append("type-specific static gate is not implemented yet; schema validation was applied")
    return {"type": spec.scope or spec.kind, "schema_only": True}, errors, warnings


def render_admission_markdown(report: Mapping[str, Any]) -> str:
    skill = dict(report.get("skill") or {})
    candidate_scan = dict(report.get("candidate_offline_scan") or {})
    lines = [
        "# Skill Admission Report",
        "",
        f"- Status: {'PASS' if report.get('ok') else 'FAIL'}",
        f"- Skill: `{skill.get('id', '')}`",
        f"- Kind: `{skill.get('kind', '')}`",
        f"- Scope: `{skill.get('scope', '')}`",
        f"- Track: `{skill.get('track', '')}`",
        f"- Index: `{report.get('index', '')}`",
        "",
        "## Errors",
        "",
    ]
    errors = list(report.get("errors") or [])
    if errors:
        lines.extend(f"- {item}" for item in errors)
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    warnings = list(report.get("warnings") or [])
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- none")
    capability_audit = dict(report.get("capability_audit") or {})
    if capability_audit:
        lines.extend(
            [
                "",
                "## Capability Audit",
                "",
                f"- Registry: `{capability_audit.get('registry_name', '')}`",
                f"- Strict: {bool(capability_audit.get('strict'))}",
                f"- Used categories: {', '.join(sorted((capability_audit.get('used') or {}).keys())) or 'none'}",
            ]
        )
        audit_errors = list(capability_audit.get("errors") or [])
        if audit_errors:
            lines.append(f"- Audit errors: {'; '.join(str(item) for item in audit_errors)}")
    if candidate_scan:
        current_stats = dict(candidate_scan.get("current_task_effectiveness") or {})
        global_stats = dict(candidate_scan.get("global_safety") or {})
        lines.extend(
            [
                "",
                "## Candidate Offline Scan",
                "",
                f"- Episodes: {candidate_scan.get('episodes', 0)}",
                f"- Success episodes: {candidate_scan.get('success_episodes', 0)}",
                f"- Failed episodes: {candidate_scan.get('failed_episodes', 0)}",
                f"- Episode matches: {candidate_scan.get('episode_matches', 0)}",
                f"- Query matches: {candidate_scan.get('query_matches', 0)}",
                f"- Winner episodes: {candidate_scan.get('winner_episodes', 0)}",
                f"- Success episode matches: {candidate_scan.get('success_episode_matches', 0)}",
                f"- Failed episode matches: {candidate_scan.get('failed_episode_matches', 0)}",
                f"- Success match rate: {float(candidate_scan.get('success_match_rate') or 0.0):.3f}",
                f"- First-fire episodes: {candidate_scan.get('first_fire_episode_count', 0)}",
                f"- Current early-fire episodes (< q{candidate_scan.get('min_first_repair_query_idx', 0)}): "
                f"{candidate_scan.get('current_early_fire_episode_count', 0)}",
                f"- Non-current early-fire episodes (< q{candidate_scan.get('min_first_repair_query_idx', 0)}): "
                f"{candidate_scan.get('non_current_early_fire_episode_count', 0)}",
            ]
        )
        if current_stats:
            lines.extend(
                [
                    "",
                    "### Current Task Effectiveness",
                    "",
                    f"- Current episodes: {current_stats.get('episodes', 0)}",
                    f"- Current failed episodes: {current_stats.get('failed_episodes', 0)}",
                    f"- Current failed matches: {current_stats.get('failed_episode_matches', 0)}",
                    f"- Current failed recall: {float(current_stats.get('failed_episode_recall') or 0.0):.3f}",
                    f"- Current success matches: {current_stats.get('success_episode_matches', 0)}",
                ]
            )
        if global_stats:
            lines.extend(
                [
                    "",
                    "### Global Safety",
                    "",
                    f"- Non-current episodes: {global_stats.get('non_current_episodes', 0)}",
                    f"- Non-current success matches: {global_stats.get('non_current_success_episode_matches', 0)}",
                    f"- Non-current success winner matches: {global_stats.get('non_current_success_winner_episode_matches', 0)}",
                    f"- Non-current shadowed success matches: {len(global_stats.get('non_current_shadowed_success_matches') or [])}",
                    f"- Non-current failed matches: {global_stats.get('non_current_failed_episode_matches', 0)}",
                    f"- Non-current episode matches: {global_stats.get('non_current_episode_matches', 0)}",
                ]
            )
        winners = list(global_stats.get("non_current_success_winner_episodes") or [])
        if winners:
            lines.append(f"- Non-current success winner episodes: {', '.join(winners[:10])}")
        shadowed = list(global_stats.get("non_current_shadowed_success_matches") or [])
        if shadowed:
            lines.append(f"- Shadowed non-current success matches: {', '.join(shadowed[:10])}")
        early = list(candidate_scan.get("current_early_fire_episodes") or [])
        if early:
            lines.append(
                "- Current early-fire examples: "
                + ", ".join(f"{item.get('episode')}@q{item.get('query_idx')}" for item in early[:10])
            )
    outputs = dict(report.get("offline_scan") or {})
    if outputs:
        lines.extend(["", "## Output Files", ""])
        for key, value in outputs.items():
            lines.append(f"- {key}: `{value}`")
    return "\n".join(lines) + "\n"


def run_skill_admission(
    skill_file: str | Path,
    *,
    config: SkillAdmissionConfig,
) -> dict[str, Any]:
    out_dir = Path(config.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    warnings: list[str] = []
    result: dict[str, Any] = {
        "schema_version": 1,
        "skill_file": str(skill_file),
        "index": str(config.index_path),
        "scan_roots": [str(path) for path in config.scan_roots],
        "current_scan_roots": [str(path) for path in config.current_scan_roots],
        "current_task_ids": [int(item) for item in config.current_task_ids],
        "current_task_names": [str(item) for item in config.current_task_names],
        "static": {},
        "offline_scan": {},
        "candidate_offline_scan": {},
        "generated_benchmark": {},
        "generated_smoke": {},
        "capability_registry": {},
        "capability_audit": {},
        "predicate_registry": {},
        "errors": errors,
        "warnings": warnings,
    }

    try:
        capability_registry = load_capability_registry(
            config.capability_registry,
            index_path=config.index_path,
        )
        result["capability_registry"] = capability_registry.summary()
    except SkillSchemaError as exc:
        capability_registry = None
        errors.append(f"capability registry: {exc}")

    try:
        predicate_registry = load_predicate_registry(
            config.predicate_registry,
            adapter_path=config.predicate_adapter,
            index_path=config.index_path,
        )
        result["predicate_registry"] = predicate_registry.summary()
    except Exception as exc:
        predicate_registry = None
        errors.append(f"predicate registry: {exc}")

    spec: SkillSpec | None = None
    try:
        spec = load_skill(skill_file, predicate_registry=predicate_registry)
        result["skill"] = _skill_summary(spec)
    except SkillSchemaError as exc:
        errors.append(f"schema: {exc}")

    if spec is not None:
        coordinator = check_draft(spec, predicate_registry=predicate_registry)
        result["coordinator"] = {
            "ok": coordinator.ok,
            "online_ready": coordinator.online_ready,
            "track": coordinator.track,
            "library": coordinator.library,
            "errors": coordinator.errors,
            "warnings": coordinator.warnings,
        }
        errors.extend(f"coordinator: {item}" for item in coordinator.errors)
        warnings.extend(f"coordinator: {item}" for item in coordinator.warnings)
        if capability_registry is not None:
            audit = capability_registry.audit_skill(spec)
            result["capability_audit"] = audit.to_dict()
            errors.extend(f"capability: {item}" for item in audit.errors)
            warnings.extend(f"capability: {item}" for item in audit.warnings)
        try:
            static, static_errors, static_warnings = _run_static_gate(
                spec=spec,
                skill_file=skill_file,
                index_path=config.index_path,
                out_dir=out_dir,
                predicate_registry=predicate_registry,
            )
            result["static"] = static
            errors.extend(static_errors)
            warnings.extend(static_warnings)
        except Exception as exc:
            errors.append(f"static gate failed: {type(exc).__name__}: {exc}")

    if spec is not None:
        scan_root_paths = [str(path) for path in config.scan_roots if str(path)]
        if scan_root_paths:
            try:
                skills = load_scan_skills(
                    config.index_path,
                    extra_skill_files=[skill_file],
                    mining=bool(config.mining),
                    predicate_registry=predicate_registry,
                )
                scan_report = run_offline_scan(
                    scan_root_paths,
                    skills,
                    ScanConfig(
                        include_hints=bool(config.include_hints),
                        include_empty_query_rows=bool(config.include_empty_query_rows),
                        max_queries_per_episode=int(config.max_queries_per_episode),
                        diagnostic_signal_registry=config.diagnostic_signal_registry,
                        diagnostic_signal_statuses=config.diagnostic_signal_statuses,
                        diagnostic_provider_roots=config.diagnostic_provider_roots,
                    ),
                    predicate_registry=predicate_registry,
                )
                result["offline_scan"] = write_scan_outputs(scan_report, out_dir / "offline_scan")
                candidate, scan_errors, scan_warnings = _offline_scan_gate(
                    spec=spec,
                    scan_report=scan_report,
                    config=config,
                )
                result["candidate_offline_scan"] = candidate
                errors.extend(scan_errors)
                warnings.extend(scan_warnings)
            except Exception as exc:
                errors.append(f"offline scan failed: {type(exc).__name__}: {exc}")
        elif config.require_offline_scan:
            errors.append("offline scan is required but no scan roots were provided")
        else:
            warnings.append("offline scan skipped because no scan roots were provided")

    if config.generated_benchmark_dir:
        benchmark_report = validate_generated_benchmark(
            config.generated_benchmark_dir,
            split=config.generated_split,
            require_freeze=True,
        )
        result["generated_benchmark"] = benchmark_report
        if not benchmark_report.get("ok"):
            errors.extend(f"generated benchmark: {item}" for item in benchmark_report.get("errors", []))
        warnings.extend(f"generated benchmark: {item}" for item in benchmark_report.get("warnings", []))

        if config.generated_smoke_run_dir:
            smoke_report = validate_generated_smoke_run(
                config.generated_smoke_run_dir,
                benchmark_dir=config.generated_benchmark_dir,
                split=config.generated_split,
                min_episodes_per_task=max(1, int(config.generated_smoke_min_episodes_per_task)),
                require_video=bool(config.generated_smoke_require_video),
            )
            result["generated_smoke"] = smoke_report
            if not smoke_report.get("ok"):
                errors.extend(f"generated smoke: {item}" for item in smoke_report.get("errors", []))
            warnings.extend(f"generated smoke: {item}" for item in smoke_report.get("warnings", []))
        elif config.require_generated_smoke:
            errors.append("--require-generated-smoke was set but no generated smoke run dir was provided")
        else:
            warnings.append("generated smoke validation skipped because no generated smoke run dir was provided")
    elif config.generated_smoke_run_dir or config.require_generated_smoke:
        errors.append("generated benchmark dir is required for generated smoke validation")

    result["ok"] = not errors
    result["errors"] = errors
    result["warnings"] = warnings
    json_path = out_dir / "skill_admission_result.json"
    md_path = out_dir / "skill_admission_report.md"
    result["result_json"] = str(json_path)
    result["result_markdown"] = str(md_path)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_admission_markdown(result), encoding="utf-8")
    return result
