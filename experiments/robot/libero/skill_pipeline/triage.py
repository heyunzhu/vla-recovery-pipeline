"""Failure triage for the offline skill mining loop.

The triage layer labels where the failure appears to live. It does not decide
that Codex is forbidden to draft: planner, grounding, geometry and executor
symptoms may still be repairable through pack-local skills, profiles or adapter
code.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .validate import episode_id

STATUS_COVERED = "covered"
STATUS_SKILL_REPAIRABLE = "skill_repairable"
STATUS_NEEDS_CAPABILITY = "needs_capability"
STATUS_NEEDS_DIAGNOSTICS = "needs_diagnostics"

SYSTEM_ERROR_PATTERNS = (
    "place_lift_too_low",
    "release_guard",
    "place_release",
    "trajectory_tracking_budget_exhausted",
    "optimized_motion_tracking_stalled",
    "optimized_joint_interpolation_too_large",
    "missing_real_cutamp_executable_plan",
    "motion planning failed",
    "no satisfying",
    "runner_missing_result_json",
    "runner_timeout",
    "executor_gap",
)
GRASP_ERROR_PATTERNS = (
    "grasp_target_not_near_precheck",
    "grasp_skip_not_near",
    "skip_place_not_holding",
)
CONSTRAINT_RE = re.compile(
    r"\[(?P<group>[^\]]+)\]\s+(?P<name>.*?)\s*<=\s*(?P<thr>[-+0-9.eE]+)\s+has\s+"
    r"(?P<ok>\d+)\s*/\s*(?P<total>\d+)\s+satisfying"
)


@dataclass
class Evidence:
    kind: str
    message: str
    episode_id: str = ""
    path: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class EpisodeDiagnosis:
    episode_id: str
    episode_dir: str
    success: bool
    skill_fired: bool
    recovery_event_count: int
    status: str
    signature: str
    reason: str
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class TriageReport:
    task_id: int
    status: str
    primary_signature: str
    reason: str
    skill_attempt_allowed: bool
    recommended_artifacts: list[str]
    recommended_next_action: str
    success_count: int
    episode_count: int
    min_successes: int
    success_rate: float
    baseline_success_count: int = 0
    regressed: bool = False
    stable_hit: bool = True
    unhit_fail_ids: list[str] = field(default_factory=list)
    episode_diagnoses: list[EpisodeDiagnosis] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _episode_success(episode: Mapping[str, Any]) -> bool:
    meta = episode.get("meta") or episode
    return bool(meta.get("success"))


def _episode_skill_fired(episode: Mapping[str, Any]) -> bool:
    for row in episode.get("queries") or []:
        if row.get("hook_fired") or row.get("skill_id"):
            return True
    for row in episode.get("recovery") or []:
        if row.get("hook_fired") or row.get("skill_id"):
            return True
    return False


def _text(row: Mapping[str, Any], *keys: str) -> str:
    return " ".join(str(row.get(key) or "") for key in keys).lower()


def _add(evidence: list[Evidence], kind: str, message: str, *, ep_id: str = "", path: str = "", **data: Any) -> None:
    evidence.append(Evidence(kind=kind, message=message, episode_id=ep_id, path=path, data=data))


def _first_rule_mismatch(rows: Sequence[Mapping[str, Any]], ep_id: str) -> Evidence | None:
    for row in rows:
        if row.get("kind") != "rule":
            continue
        target = str(row.get("target_name") or "")
        goal = str(row.get("goal_name") or "")
        bddl_target = str(row.get("bddl_target") or "")
        bddl_goal = str(row.get("bddl_goal") or "")
        sem_target = str(row.get("semantics_target") or "")
        sem_goal = str(row.get("semantics_goal") or "")
        mismatches = []
        if bddl_target and target and bddl_target != target:
            mismatches.append(f"target_name={target} bddl_target={bddl_target}")
        if bddl_goal and goal and bddl_goal != goal:
            mismatches.append(f"goal_name={goal} bddl_goal={bddl_goal}")
        if sem_target and target and sem_target != target:
            mismatches.append(f"target_name={target} semantics_target={sem_target}")
        if sem_goal and goal and sem_goal != goal:
            mismatches.append(f"goal_name={goal} semantics_goal={sem_goal}")
        goals = list(row.get("recovery_goals") or [])
        if bddl_goal and goals:
            first_atoms = list((goals[0] or {}).get("atoms") or [])
            first_goal_args = [arg for atom in first_atoms for arg in (atom.get("args") or [])]
            if first_goal_args and bddl_goal not in first_goal_args:
                mismatches.append(f"first_recovery_goal_missing_bddl_goal={bddl_goal}")
        if mismatches:
            return Evidence(
                kind="rule_binding_mismatch",
                message="rule layer selected a different target/goal than the BDDL or task semantics",
                episode_id=ep_id,
                data={
                    "mismatches": mismatches,
                    "target_name": target,
                    "goal_name": goal,
                    "bddl_target": bddl_target,
                    "bddl_goal": bddl_goal,
                    "semantics_target": sem_target,
                    "semantics_goal": sem_goal,
                },
            )
    return None


def _system_error_evidence(rows: Sequence[Mapping[str, Any]], ep_id: str) -> Evidence | None:
    for row in rows:
        hay = _text(row, "event", "label", "error", "skipped")
        for pattern in SYSTEM_ERROR_PATTERNS:
            if pattern in hay:
                return Evidence(
                    kind="system_error",
                    message=f"recovery failed in planner/executor path: {pattern}",
                    episode_id=ep_id,
                    data={
                        "pattern": pattern,
                        "kind": row.get("kind"),
                        "event": row.get("event"),
                        "label": row.get("label"),
                        "error": row.get("error"),
                    },
                )
    return None


def _grasp_error_evidence(rows: Sequence[Mapping[str, Any]], ep_id: str) -> Evidence | None:
    for row in rows:
        hay = _text(row, "event", "label", "error", "skipped")
        for pattern in GRASP_ERROR_PATTERNS:
            if pattern in hay:
                return Evidence(
                    kind="grasp_candidate",
                    message=f"grasp candidate/precheck failed: {pattern}",
                    episode_id=ep_id,
                    data={
                        "pattern": pattern,
                        "kind": row.get("kind"),
                        "event": row.get("event"),
                        "label": row.get("label"),
                        "error": row.get("error"),
                    },
                )
        if row.get("event") == "grasp_close_precheck" and row.get("success") is False:
            return Evidence(
                kind="grasp_candidate",
                message="close precheck rejected the selected grasp pose",
                episode_id=ep_id,
                data={key: row.get(key) for key in ("xy_m", "z_delta_m", "max_xy_m", "max_above_m", "error")},
            )
        if row.get("event") == "grasp_lift_probe" and (
            row.get("confirmed") is False or row.get("object_followed") is False
        ):
            return Evidence(
                kind="grasp_candidate",
                message="lift probe did not confirm that the object followed the gripper",
                episode_id=ep_id,
                data={
                    "confirmed": row.get("confirmed"),
                    "object_followed": row.get("object_followed"),
                    "object_lift_m": row.get("object_lift_m"),
                    "bilateral_contact": row.get("bilateral_contact"),
                },
            )
    return None


def diagnose_episode(episode: Mapping[str, Any]) -> EpisodeDiagnosis:
    ep_id = episode_id(episode)
    ep_dir = str(episode.get("dir") or "")
    success = _episode_success(episode)
    rows = list(episode.get("recovery") or [])
    fired = _episode_skill_fired(episode)
    evidence: list[Evidence] = []
    if success:
        return EpisodeDiagnosis(
            episode_id=ep_id,
            episode_dir=ep_dir,
            success=True,
            skill_fired=fired,
            recovery_event_count=len(rows),
            status=STATUS_COVERED,
            signature="success",
            reason="episode succeeded",
        )
    if not fired:
        _add(
            evidence,
            "trigger_missing",
            "failed episode never fired an online/mining skill",
            ep_id=ep_id,
            path=ep_dir,
        )
        return EpisodeDiagnosis(
            episode_id=ep_id,
            episode_dir=ep_dir,
            success=False,
            skill_fired=False,
            recovery_event_count=len(rows),
            status=STATUS_SKILL_REPAIRABLE,
            signature="trigger_missing_or_late",
            reason="a better trigger/recovery timing skill may cover this failure",
            evidence=evidence,
        )
    mismatch = _first_rule_mismatch(rows, ep_id)
    if mismatch is not None:
        return EpisodeDiagnosis(
            episode_id=ep_id,
            episode_dir=ep_dir,
            success=False,
            skill_fired=True,
            recovery_event_count=len(rows),
            status=STATUS_NEEDS_CAPABILITY,
            signature="rule_binding_mismatch",
            reason="the selected target/goal binding is wrong; this likely needs grounding or geometry capability",
            evidence=[mismatch],
        )
    system = _system_error_evidence(rows, ep_id)
    if system is not None:
        return EpisodeDiagnosis(
            episode_id=ep_id,
            episode_dir=ep_dir,
            success=False,
            skill_fired=True,
            recovery_event_count=len(rows),
            status=STATUS_NEEDS_CAPABILITY,
            signature=str(system.data.get("pattern") or "system_error"),
            reason="failure is in rule/planner/executor behavior; this may need pack-local capability",
            evidence=[system],
        )
    grasp = _grasp_error_evidence(rows, ep_id)
    if grasp is not None:
        return EpisodeDiagnosis(
            episode_id=ep_id,
            episode_dir=ep_dir,
            success=False,
            skill_fired=True,
            recovery_event_count=len(rows),
            status=STATUS_SKILL_REPAIRABLE,
            signature="grasp_candidate_or_timing",
            reason="a skill-scoped grasp profile or pick timing adjustment may cover this failure",
            evidence=[grasp],
        )
    if not rows:
        _add(
            evidence,
            "missing_recovery_trace",
            "skill fired but no recovery_trace rows were recorded",
            ep_id=ep_id,
            path=ep_dir,
        )
        return EpisodeDiagnosis(
            episode_id=ep_id,
            episode_dir=ep_dir,
            success=False,
            skill_fired=True,
            recovery_event_count=0,
            status=STATUS_SKILL_REPAIRABLE,
            signature="trigger_or_recovery_timing_unclear",
            reason="no recovery rows are available; keep this in the skill-writing path for now",
            evidence=evidence,
        )
    errors = [row for row in rows if row.get("error")]
    if errors:
        first = errors[0]
        _add(
            evidence,
            "unclassified_recovery_error",
            "recovery produced an error that is not yet mapped by triage",
            ep_id=ep_id,
            kind_in_trace=first.get("kind"),
            event=first.get("event"),
            label=first.get("label"),
            error=first.get("error"),
        )
    return EpisodeDiagnosis(
        episode_id=ep_id,
        episode_dir=ep_dir,
        success=False,
        skill_fired=True,
        recovery_event_count=len(rows),
        status=STATUS_NEEDS_DIAGNOSTICS,
        signature="unclassified_recovery_failure",
        reason="recovery ran but triage cannot confidently assign the root cause",
        evidence=evidence,
    )


def inspect_cutamp_debug(run_dir: str | Path, *, max_items: int = 12) -> list[Evidence]:
    root = Path(run_dir)
    debug_dirs = []
    if (root / "cutamp_debug").is_dir():
        debug_dirs.append(root / "cutamp_debug")
    debug_dirs.extend(path for path in root.glob("*/cutamp_debug") if path.is_dir())
    result_evidence: list[Evidence] = []
    zero_constraints: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for debug_dir in debug_dirs:
        for result_path in sorted(debug_dir.glob("*.result.json")):
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            failure = data.get("failure_reason")
            feasible = data.get("feasible")
            satisfying = data.get("num_satisfying")
            diag = dict(data.get("diagnostics") or {})
            executable_plan = data.get("executable_plan")
            executable_count = len(executable_plan) if isinstance(executable_plan, list) else None
            optimized_present = bool(data.get("optimized_plan")) or bool(diag.get("optimized_plan_present"))
            optimized_without_executable = bool(optimized_present and executable_count == 0)
            if feasible is False or satisfying == 0 or failure or optimized_without_executable:
                result_evidence.append(
                    Evidence(
                        kind="cutamp_result",
                        message="cuTAMP result reports infeasible or failed solve",
                        path=str(result_path),
                        data={
                            "available": data.get("available"),
                            "feasible": feasible,
                            "num_satisfying": satisfying,
                            "failure_reason": failure,
                            "optimized_plan_present": optimized_present,
                            "executable_plan_count": executable_count,
                            "plan_summary": diag.get("plan_summary"),
                            "grasp_sampler_profile": diag.get("grasp_sampler_profile"),
                        },
                    )
                )
        for stderr_path in sorted(debug_dir.glob("*.stderr.txt")):
            try:
                text = stderr_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in CONSTRAINT_RE.finditer(text):
                ok = int(match.group("ok"))
                total = int(match.group("total"))
                if ok != 0:
                    continue
                key = (match.group("group"), match.group("name").strip(), match.group("thr"), total)
                item = zero_constraints.setdefault(
                    key,
                    {
                        "group": key[0],
                        "name": key[1],
                        "threshold": key[2],
                        "ok": ok,
                        "total": total,
                        "count": 0,
                        "example_paths": [],
                    },
                )
                item["count"] += 1
                if len(item["example_paths"]) < 3:
                    item["example_paths"].append(str(stderr_path))

    constraint_evidence = [
        Evidence(
            kind="cutamp_zero_constraint",
            message="cuTAMP optimization had zero satisfying particles for a constraint",
            path=(item["example_paths"][0] if item["example_paths"] else ""),
            data=item,
        )
        for item in sorted(
            zero_constraints.values(),
            key=lambda row: (-int(row.get("count") or 0), str(row.get("group") or ""), str(row.get("name") or "")),
        )
    ]
    constraint_budget = min(6, max_items)
    evidence = constraint_evidence[:constraint_budget]
    evidence.extend(result_evidence[: max(0, max_items - len(evidence))])
    return evidence


def triage_validation_run(
    *,
    task_id: int,
    baseline_episodes: Sequence[Mapping[str, Any]],
    on_episodes: Sequence[Mapping[str, Any]],
    scored: Mapping[str, Any],
    on_dir: str | Path,
    success_min: float,
) -> TriageReport:
    episode_count = int(scored.get("n_pairs") or len(on_episodes))
    min_successes = int(math.ceil(float(success_min) * episode_count)) if episode_count else 0
    success_count = int(scored.get("on_success") or sum(int(_episode_success(item)) for item in on_episodes))
    baseline_success_count = int(
        scored.get("off_success") or sum(int(_episode_success(item)) for item in baseline_episodes)
    )
    success_rate = 0.0 if episode_count <= 0 else success_count / episode_count
    diagnoses = [diagnose_episode(item) for item in on_episodes]
    failures = [item for item in diagnoses if not item.success]
    debug_evidence = inspect_cutamp_debug(on_dir)
    stable_hit = bool(scored.get("stable_hit", True))
    unhit_fail_ids = list(scored.get("unhit_fail_ids") or [])
    regressed = bool(scored.get("regressed"))
    if episode_count > 0 and success_count >= min_successes and not regressed:
        return TriageReport(
            task_id=int(task_id),
            status=STATUS_COVERED,
            primary_signature="success_threshold_met",
            reason=f"same-init success reached {success_count}/{episode_count}",
            skill_attempt_allowed=False,
            recommended_artifacts=[],
            recommended_next_action="skip this task and continue mining the next task",
            success_count=success_count,
            episode_count=episode_count,
            min_successes=min_successes,
            success_rate=success_rate,
            baseline_success_count=baseline_success_count,
            regressed=regressed,
            stable_hit=stable_hit,
            unhit_fail_ids=unhit_fail_ids,
            episode_diagnoses=diagnoses,
            evidence=debug_evidence[:4],
        )
    needed = max(0, min_successes - success_count)
    counts = Counter(item.status for item in failures)
    skill_candidates = [item for item in failures if item.status == STATUS_SKILL_REPAIRABLE]
    capability_candidates = [item for item in failures if item.status == STATUS_NEEDS_CAPABILITY]
    if needed > 0 and len(skill_candidates) >= needed:
        sig_counts = Counter(item.signature for item in skill_candidates)
        signature = sig_counts.most_common(1)[0][0] if sig_counts else "skill_repairable"
        return TriageReport(
            task_id=int(task_id),
            status=STATUS_SKILL_REPAIRABLE,
            primary_signature=signature,
            reason=f"{len(skill_candidates)} failed episode(s) look skill-repairable; {needed} more success(es) needed",
            skill_attempt_allowed=True,
            recommended_artifacts=["repair_trigger", "recovery_hint", "diagnostic_signal"],
            recommended_next_action="pack skill-repairable validation failures and ask Codex for the next fail_only draft",
            success_count=success_count,
            episode_count=episode_count,
            min_successes=min_successes,
            success_rate=success_rate,
            baseline_success_count=baseline_success_count,
            regressed=regressed,
            stable_hit=stable_hit,
            unhit_fail_ids=unhit_fail_ids,
            episode_diagnoses=diagnoses,
            evidence=debug_evidence[:4],
        )
    if capability_candidates or any(item.kind.startswith("cutamp_") for item in debug_evidence):
        signatures = Counter(item.signature for item in capability_candidates)
        signature = signatures.most_common(1)[0][0] if signatures else "cutamp_debug_requires_capability"
        if skill_candidates and needed > len(skill_candidates):
            reason = (
                f"only {len(skill_candidates)} skill-repairable failure(s), but {needed} more success(es) are needed; "
                "remaining failures likely need additional pack-local capability"
            )
        else:
            reason = "failures point at planner/rule/executor behavior that may need pack-local capability"
        return TriageReport(
            task_id=int(task_id),
            status=STATUS_NEEDS_CAPABILITY,
            primary_signature=signature,
            reason=reason,
            skill_attempt_allowed=True,
            recommended_artifacts=[
                "grounding_profile",
                "geometry_profile",
                "place_profile",
                "grasp_profile",
                "pack_local_code_adapter",
                "diagnostic_signal",
            ],
            recommended_next_action=(
                "draft an executable pack-local skill/profile/code bundle; diagnostics-only notes are not a valid write"
            ),
            success_count=success_count,
            episode_count=episode_count,
            min_successes=min_successes,
            success_rate=success_rate,
            baseline_success_count=baseline_success_count,
            regressed=regressed,
            stable_hit=stable_hit,
            unhit_fail_ids=unhit_fail_ids,
            episode_diagnoses=diagnoses,
            evidence=debug_evidence[:8],
        )
    signature = "unclassified_recovery_failure"
    if counts:
        signature = Counter(item.signature for item in failures).most_common(1)[0][0]
    return TriageReport(
        task_id=int(task_id),
        status=STATUS_NEEDS_DIAGNOSTICS,
        primary_signature=signature,
        reason="not enough evidence to pick a failure layer confidently",
        skill_attempt_allowed=True,
        recommended_artifacts=["diagnostic_signal", "repair_trigger", "recovery_hint"],
        recommended_next_action=(
            "draft an executable diagnostic signal or conservative skill bundle, then validate; diagnostics-only notes are not a valid write"
        ),
        success_count=success_count,
        episode_count=episode_count,
        min_successes=min_successes,
        success_rate=success_rate,
        baseline_success_count=baseline_success_count,
        regressed=regressed,
        stable_hit=stable_hit,
        unhit_fail_ids=unhit_fail_ids,
        episode_diagnoses=diagnoses,
        evidence=debug_evidence[:8],
    )


def _markdown(report: TriageReport) -> str:
    lines = [
        f"# Skill mining triage: task{report.task_id:02d}",
        "",
        f"- status: {report.status}",
        f"- primary_signature: {report.primary_signature}",
        f"- success: {report.success_count}/{report.episode_count} (min {report.min_successes})",
        f"- baseline_success: {report.baseline_success_count}/{report.episode_count}",
        f"- skill_attempt_allowed: {str(report.skill_attempt_allowed).lower()}",
        f"- recommended_artifacts: {report.recommended_artifacts}",
        f"- reason: {report.reason}",
        f"- next: {report.recommended_next_action}",
        "",
        "## Episodes",
    ]
    for item in report.episode_diagnoses:
        lines.append(
            f"- {item.episode_id}: {item.status} / {item.signature}; fired={str(item.skill_fired).lower()}; "
            f"recovery_rows={item.recovery_event_count}; {item.reason}"
        )
        for ev in item.evidence[:2]:
            suffix = f" path={ev.path}" if ev.path else ""
            lines.append(f"  - evidence: {ev.kind}: {ev.message}{suffix}")
    if report.evidence:
        lines.extend(["", "## Run Evidence"])
        for ev in report.evidence:
            suffix = f" path={ev.path}" if ev.path else ""
            lines.append(f"- {ev.kind}: {ev.message}{suffix}")
    return "\n".join(lines) + "\n"


def write_triage_artifacts(report: TriageReport, out_dir: str | Path) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "triage_report.json"
    md_path = out / "triage_report.md"
    json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return {"triage_json": str(json_path), "triage_md": str(md_path)}
