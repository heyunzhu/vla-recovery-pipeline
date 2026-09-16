"""Offline task-loop skill mining. No LLM in the online control loop.

Each task is scored by same-init rollouts with mining skills enabled:
success rate >= 60% (3/5) and no regression vs the skills-off baseline. Residual
failures that never fired a skill are kept as warnings/triage evidence, but the
task skip gate is success-driven. Codex may write a bounded number of times per
task regardless of the triage failure layer; after that cap the task is marked
write_budget_exhausted and mining continues.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .bundles import SkillBundle, check_mining_bundle, load_skill_bundle
from .capabilities import CORE_GRASP_PROFILES, load_capability_registry
from .coordinator import check_draft
from .packer import load_episode, pack_fail_set
from .schema import SkillSpec, load_index, parse_skill_markdown, resolve_mining_skills
from .triage import STATUS_COVERED, triage_validation_run, write_triage_artifacts
from .validate import (
    FAIL_RECALL_MIN,
    SUCCESS_EPISODE_FIRE_MAX,
    episode_id,
    evaluate_heldout_triggers,
    iter_fire_indices,
)

TASK_SUCCESS_MIN = 0.60
DEFAULT_MAX_WRITES_PER_TASK = 5
MAX_WRITES_PER_TASK = DEFAULT_MAX_WRITES_PER_TASK
STATUS_INVALID_VALIDATION = "invalid_validation"
STATUS_WRITE_BUDGET_EXHAUSTED = "write_budget_exhausted"
TASK_DIR_RE = re.compile(r"^task(\d+)$")
# Same recovery stack as the mainline cuRobo launchers. Skills-off baselines never
# enter recover(), so these flags cannot be inherited from summary.json.
DEFAULT_CUTAMP_RUNNER_PYTHON = str(
    Path(__file__).resolve().parents[4]
    / "scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh"
)
REPO_CUTAMP_RUNNER_CANDIDATES = (
    "scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh",
    "scripts/recovery/skill_pipeline/cutamp_runner_py310.sh",
)
MINING_CUTAMP_GRASP_DOF = 6
MINING_CUTAMP_TIMEOUT_SEC = 360
MINING_MAX_RECOVERY_STEPS = 200
MINING_MAX_RECOVERY_CALLS = 2
INDEX_HEADER = """# Online skills loaded by `--enable_skills`. Only `pair/` paths may appear here.
# fail_only drafts stay under skills/fail_only/ and are never loaded online.
# Admission: docs/agentic_skill_recovery_pipeline.md section 8.3.
"""


@dataclass
class SkillCoverage:
    skill_id: str
    path: str
    fail_recall: float
    success_fire_rate: float
    n_fail: int
    n_success: int
    hit_fail_ids: list[str] = field(default_factory=list)
    success_fire_ids: list[str] = field(default_factory=list)


@dataclass
class TaskDecision:
    task_id: int
    action: str
    covering_skill_ids: list[str] = field(default_factory=list)
    uncovered_dirs: list[str] = field(default_factory=list)
    covered_episode_ids: list[str] = field(default_factory=list)
    fail_recall: float = 0.0
    success_fire_rate: float = 0.0
    n_fail: int = 0
    n_success: int = 0
    reason: str = ""
    coverages: list[dict[str, Any]] = field(default_factory=list)


def parse_task_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for chunk in str(raw or "").split(","):
        item = chunk.strip()
        if not item:
            continue
        if "-" in item:
            start_s, end_s = item.split("-", 1)
            ids.extend(range(int(start_s), int(end_s) + 1))
        else:
            ids.append(int(item))
    return ids


def discover_task_ids(run_dir: str | Path) -> list[int]:
    found: list[int] = []
    for path in Path(run_dir).iterdir():
        match = TASK_DIR_RE.match(path.name)
        if match and path.is_dir():
            found.append(int(match.group(1)))
    return sorted(found)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _generated_manifest_path(generated_benchmark_dir: str | Path, generated_split: str) -> Path:
    root = Path(generated_benchmark_dir)
    manifest = (
        root / "manifests" / "all_tasks.jsonl"
        if generated_split == "all"
        else root / "manifests" / f"{generated_split}_tasks.jsonl"
    )
    if not manifest.exists():
        raise FileNotFoundError(f"generated benchmark manifest not found: {manifest}")
    return manifest


def _generated_rows(generated_benchmark_dir: str | Path, generated_split: str) -> list[dict[str, Any]]:
    return sorted(_read_jsonl(_generated_manifest_path(generated_benchmark_dir, generated_split)), key=lambda row: str(row.get("task_id") or ""))


def _generated_task_dir_name(
    task_id: int,
    *,
    generated_benchmark_dir: str | Path | None = None,
    generated_split: str = "smoke",
) -> str | None:
    if not generated_benchmark_dir:
        return None
    rows = _generated_rows(generated_benchmark_dir, generated_split)
    idx = int(task_id) - 1
    if idx < 0 or idx >= len(rows):
        raise ValueError(f"generated task selector {task_id} is outside {generated_split} manifest with {len(rows)} rows")
    task_name = str(rows[idx].get("task_id") or "").strip()
    if not task_name:
        raise ValueError(f"generated task selector {task_id} has no task_id in {generated_split} manifest")
    return task_name


def discover_task_ids_from_generated_run(
    run_dir: str | Path,
    *,
    generated_benchmark_dir: str | Path,
    generated_split: str = "smoke",
) -> list[int]:
    root = Path(run_dir)
    found: list[int] = []
    for idx, row in enumerate(_generated_rows(generated_benchmark_dir, generated_split), start=1):
        task_name = str(row.get("task_id") or "")
        if task_name and (root / task_name).is_dir():
            found.append(idx)
    return found


def task_dir(
    run_dir: str | Path,
    task_id: int,
    *,
    generated_benchmark_dir: str | Path | None = None,
    generated_split: str = "smoke",
) -> Path:
    root = Path(run_dir)
    if generated_benchmark_dir:
        return root / str(
            _generated_task_dir_name(
                task_id,
                generated_benchmark_dir=generated_benchmark_dir,
                generated_split=generated_split,
            )
        )
    return root / f"task{int(task_id):02d}"


def load_task_episodes(
    run_dir: str | Path,
    task_id: int,
    *,
    generated_benchmark_dir: str | Path | None = None,
    generated_split: str = "smoke",
) -> list[dict[str, Any]]:
    folder = task_dir(
        run_dir,
        task_id,
        generated_benchmark_dir=generated_benchmark_dir,
        generated_split=generated_split,
    )
    if not folder.is_dir():
        raise FileNotFoundError(f"missing task directory: {folder}")
    episodes = []
    for ep_dir in sorted(path for path in folder.iterdir() if path.is_dir() and path.name.startswith("ep")):
        episodes.append(load_episode(ep_dir))
    return episodes


def _is_fail(episode: Mapping[str, Any]) -> bool:
    return not bool((episode.get("meta") or episode).get("success"))


def coverage_for_skill(skill: SkillSpec, episodes: Sequence[Mapping[str, Any]]) -> SkillCoverage:
    metrics = evaluate_heldout_triggers(skill, episodes)
    hit_fail: list[str] = []
    for episode in episodes:
        if _is_fail(episode) and iter_fire_indices(skill, episode):
            hit_fail.append(episode_id(episode))
    return SkillCoverage(
        skill_id=skill.id,
        path=skill.path,
        fail_recall=metrics.fail_recall,
        success_fire_rate=metrics.success_fire_rate,
        n_fail=metrics.n_fail,
        n_success=metrics.n_success,
        hit_fail_ids=hit_fail,
        success_fire_ids=list(metrics.success_fires),
    )


def decide_task(
    task_id: int,
    episodes: Sequence[Mapping[str, Any]],
    skills: Sequence[SkillSpec],
    *,
    fail_recall_min: float = FAIL_RECALL_MIN,
    success_fire_max: float = SUCCESS_EPISODE_FIRE_MAX,
) -> TaskDecision:
    fails = [item for item in episodes if _is_fail(item)]
    successes = [item for item in episodes if not _is_fail(item)]
    coverages = [
        coverage_for_skill(skill, episodes)
        for skill in skills
        if skill.kind not in {"diagnostics", "recovery_hint"}
    ]
    hit_any: set[str] = set()
    covering_ids: list[str] = []
    for cov in coverages:
        if cov.hit_fail_ids:
            covering_ids.append(cov.skill_id)
            hit_any.update(cov.hit_fail_ids)
    uncovered = [str(item["dir"]) for item in fails if episode_id(item) not in hit_any]
    covered_ids = sorted(hit_any)
    n_fail = len(fails)
    fail_recall = 0.0 if n_fail == 0 else len(hit_any) / n_fail
    best = max(coverages, key=lambda item: (item.fail_recall, item.skill_id), default=None)
    success_fire = best.success_fire_rate if best is not None else 0.0
    decision = TaskDecision(
        task_id=int(task_id),
        action="write",
        covering_skill_ids=covering_ids,
        uncovered_dirs=uncovered,
        covered_episode_ids=covered_ids,
        fail_recall=fail_recall,
        success_fire_rate=success_fire,
        n_fail=n_fail,
        n_success=len(successes),
        coverages=[asdict(item) for item in coverages],
    )
    if n_fail == 0:
        decision.action = "skip_no_fail"
        decision.reason = "no failed episodes on this task"
        return decision
    if not skills:
        decision.action = "write"
        decision.uncovered_dirs = [str(item["dir"]) for item in fails]
        decision.reason = "library is empty"
        return decision
    too_wide = bool(successes) and success_fire > success_fire_max
    if not uncovered and not too_wide and fail_recall >= fail_recall_min:
        decision.action = "reuse"
        decision.reason = "library trigger covers every failure on this task"
        return decision
    if not uncovered and too_wide:
        decision.action = "refine"
        decision.uncovered_dirs = [str(item["dir"]) for item in fails]
        decision.reason = "library covers failures but fires too often on successes of this task"
        return decision
    decision.action = "write"
    decision.reason = "one or more failures are not covered by the current library"
    return decision


def _unique(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def append_skill_evidence(
    path: str | Path,
    *,
    tasks: Sequence[str] | None = None,
    episodes: Sequence[str] | None = None,
) -> SkillSpec:
    skill_path = Path(path)
    text = skill_path.read_text(encoding="utf-8")
    data, body = _split_front_matter(text)
    evidence = dict(data.get("evidence") or {})
    evidence["tasks"] = _unique(list(evidence.get("tasks") or []) + list(tasks or []))
    evidence["episodes"] = _unique(list(evidence.get("episodes") or []) + list(episodes or []))
    data["evidence"] = evidence
    dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    skill_path.write_text(f"---\n{dumped}---\n{body}", encoding="utf-8")
    return parse_skill_markdown(skill_path.read_text(encoding="utf-8"), path=str(skill_path))


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    from .schema import parse_front_matter

    return parse_front_matter(text)


def _task_label(episodes: Sequence[Mapping[str, Any]], task_id: int) -> str:
    if not episodes:
        return f"unknown_suite task{task_id:02d}"
    meta = dict(episodes[0].get("meta") or {})
    suite = str(meta.get("task_suite_name") or meta.get("suite") or meta.get("source_suite") or "unknown_suite")
    desc = str(meta.get("task_description") or "").strip()
    generated_task_id = str(meta.get("generated_task_id") or "").strip()
    if generated_task_id:
        source_suite = str(meta.get("source_suite") or "libero_90").strip()
        prefix = f"{source_suite} generated selector{task_id:03d} {generated_task_id}"
        return f"{prefix} {desc}" if desc else prefix
    if desc:
        return f"{suite} task{task_id:02d} {desc}"
    return f"{suite} task{task_id:02d}"


def append_coverage_evidence(
    skills: Sequence[SkillSpec],
    episodes: Sequence[Mapping[str, Any]],
    task_id: int,
) -> list[str]:
    label = _task_label(episodes, task_id)
    updated: list[str] = []
    for skill in skills:
        if not skill.path:
            continue
        hit_ids = [episode_id(item) for item in episodes if _is_fail(item) and iter_fire_indices(skill, item)]
        if not hit_ids:
            continue
        append_skill_evidence(skill.path, tasks=[label], episodes=hit_ids)
        updated.append(skill.id)
    return updated


def _rel_skill_path(skills_root: Path, path: Path) -> str:
    return path.resolve().relative_to(skills_root.resolve()).as_posix()


def _write_index(
    index_path: Path,
    online: Sequence[str],
    fail_only: Sequence[str],
    *,
    existing: Mapping[str, Any] | None = None,
) -> None:
    payload = {
        key: value
        for key, value in dict(existing or {}).items()
        if key not in {"online", "fail_only"}
    }
    payload["online"] = list(online)
    payload["fail_only"] = list(fail_only)
    index_path.write_text(INDEX_HEADER + yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _fail_only_subdir(spec: SkillSpec) -> str:
    if spec.kind in {"trigger", "repair"}:
        return "trigger"
    if spec.kind == "recovery_hint":
        return f"recovery_hint/{spec.scope or 'misc'}"
    return spec.kind


def _write_fail_only_skill(
    draft: Path,
    spec: SkillSpec,
    *,
    skills_root: Path,
    task_label: str,
    writing_ids: Sequence[str],
) -> tuple[SkillSpec, str]:
    dest = skills_root / "fail_only" / _fail_only_subdir(spec) / f"{spec.id}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    previous_tasks: list[str] = []
    previous_eps: list[str] = []
    if dest.exists():
        old = parse_skill_markdown(dest.read_text(encoding="utf-8"), path=str(dest))
        previous_tasks = list(old.evidence.get("tasks") or [])
        previous_eps = list(old.evidence.get("episodes") or [])
    shutil.copyfile(draft, dest)
    data, body = _split_front_matter(dest.read_text(encoding="utf-8"))
    data["track"] = "fail_only"
    dest.write_text(
        f"---\n{yaml.safe_dump(data, sort_keys=False, allow_unicode=True)}---\n{body}",
        encoding="utf-8",
    )
    admitted = append_skill_evidence(
        dest,
        tasks=previous_tasks + [task_label],
        episodes=previous_eps + list(writing_ids),
    )
    return admitted, _rel_skill_path(skills_root, dest)


def admit_fail_only_draft(
    draft_path: str | Path,
    *,
    skills_root: str | Path,
    episodes: Sequence[Mapping[str, Any]],
    writing_episodes: Sequence[Mapping[str, Any]] | None = None,
    fail_recall_min: float = FAIL_RECALL_MIN,
    success_fire_max: float = SUCCESS_EPISODE_FIRE_MAX,
    capability_registry: str | Path | None = None,
    local_replay_gate: bool = True,
) -> dict[str, Any]:
    skills_root = Path(skills_root)
    draft = Path(draft_path)
    spec = parse_skill_markdown(draft.read_text(encoding="utf-8"), path=str(draft))
    spec.track = "fail_only"
    writing = list(writing_episodes or [item for item in episodes if _is_fail(item)])
    if not writing:
        raise ValueError("admit_fail_only_draft requires failed writing episodes")
    metrics = evaluate_heldout_triggers(spec, writing)
    errors: list[str] = []
    # 2026-09-16: the recall ratio gate is disabled by default (fail_recall_min = 0.0).
    if local_replay_gate and fail_recall_min > 0 and metrics.fail_recall < fail_recall_min:
        errors.append(
            f"trigger recall {metrics.fail_recall:.2f} on current-task writing failures "
            f"is below {fail_recall_min:.2f}"
        )
    # Non-vacuity floor (kept): a draft that never fires on a failed writing episode is not a skill.
    if local_replay_gate and metrics.n_fail_hit <= 0:
        errors.append(
            "trigger does not fire on any current-task failed episode "
            f"(recall {metrics.fail_recall:.2f}; vacuous candidate)"
        )
    task_metrics = evaluate_heldout_triggers(spec, episodes)
    if local_replay_gate and task_metrics.n_success and task_metrics.success_fire_rate > success_fire_max:
        errors.append(
            f"trigger fires on {task_metrics.success_fire_rate:.2f} of current-task successes "
            f"(max {success_fire_max:.2f})"
        )
    writing_ids = [episode_id(item) for item in writing]
    spec.evidence["episodes"] = _unique(list(spec.evidence.get("episodes") or []) + writing_ids)
    spec.evidence["tasks"] = _unique(
        list(spec.evidence.get("tasks") or [])
        + [_task_label(episodes, int((writing[0].get("meta") or {}).get("task_id_1based") or 0))]
    )
    report = check_draft(spec, writing_episodes=writing_ids)
    errors.extend(report.errors)
    registry = load_capability_registry(capability_registry, index_path=skills_root / "_index.yaml")
    audit = registry.audit_skill(spec)
    errors.extend(f"capability: {item}" for item in audit.errors)
    if errors:
        return {
            "ok": False,
            "online_ready": False,
            "errors": errors,
            "warnings": report.warnings,
            "capability_audit": audit.to_dict(),
            "skill_id": spec.id,
            "fail_recall": metrics.fail_recall,
            "success_fire_rate": task_metrics.success_fire_rate,
        }
    task_id = int((writing[0].get("meta") or {}).get("task_id_1based") or 0)
    admitted, rel = _write_fail_only_skill(
        draft,
        spec,
        skills_root=skills_root,
        task_label=_task_label(episodes, task_id),
        writing_ids=writing_ids,
    )
    index_path = skills_root / "_index.yaml"
    data = load_index(index_path) if index_path.exists() else {"online": [], "fail_only": []}
    fail_only = _unique(list(data.get("fail_only") or []) + [rel])
    _write_index(index_path, list(data.get("online") or []), fail_only, existing=data)
    return {
        "ok": True,
        "online_ready": False,
        "errors": [],
        "warnings": report.warnings
        + [
            (
                "global offline admission already ran; local trigger replay metrics are report-only"
                if not local_replay_gate
                else "trigger-replay admission only; same-init simulation is still required before pair/online"
            )
        ],
        "capability_audit": audit.to_dict(),
        "skill_id": admitted.id,
        "path": rel,
        "fail_recall": metrics.fail_recall,
        "success_fire_rate": task_metrics.success_fire_rate,
        "evidence_episodes": list(admitted.evidence.get("episodes") or []),
    }


def admit_fail_only_bundle(
    *,
    bundle_yaml: str | Path | None = None,
    draft_dir: str | Path | None = None,
    bundle: SkillBundle | None = None,
    skills_root: str | Path,
    episodes: Sequence[Mapping[str, Any]],
    writing_episodes: Sequence[Mapping[str, Any]] | None = None,
    fail_recall_min: float = FAIL_RECALL_MIN,
    success_fire_max: float = SUCCESS_EPISODE_FIRE_MAX,
    capability_registry: str | Path | None = None,
    local_replay_gate: bool = True,
) -> dict[str, Any]:
    skills_root = Path(skills_root)
    loaded = bundle or load_skill_bundle(bundle_yaml=bundle_yaml, draft_dir=draft_dir)
    writing = list(writing_episodes or [item for item in episodes if _is_fail(item)])
    if not writing:
        raise ValueError("admit_fail_only_bundle requires failed writing episodes")
    index_path = skills_root / "_index.yaml"
    registry = load_capability_registry(capability_registry, index_path=index_path)
    check = check_mining_bundle(
        loaded,
        episodes=episodes,
        writing_episodes=writing,
        capability_registry=registry,
        index_path=index_path,
        fail_recall_min=fail_recall_min,
        success_fire_max=success_fire_max,
        local_replay_gate=local_replay_gate,
    )
    if not check.ok:
        return {
            "ok": False,
            "online_ready": False,
            "status": "bundle_rejected",
            "bundle_id": loaded.bundle_id,
            "skill_ids": loaded.skill_ids,
            "errors": check.errors,
            "warnings": check.warnings,
            "bundle_check": check.to_dict(),
        }

    writing_ids = [episode_id(item) for item in writing]
    task_id = int((writing[0].get("meta") or {}).get("task_id_1based") or 0)
    task_label = _task_label(episodes, task_id)
    rel_paths: list[str] = []
    admitted_specs: list[SkillSpec] = []
    for draft in loaded.drafts:
        draft.spec.track = "fail_only"
        admitted, rel = _write_fail_only_skill(
            draft.path,
            draft.spec,
            skills_root=skills_root,
            task_label=task_label,
            writing_ids=writing_ids,
        )
        admitted_specs.append(admitted)
        rel_paths.append(rel)

    data = load_index(index_path) if index_path.exists() else {"online": [], "fail_only": []}
    fail_only = _unique(list(data.get("fail_only") or []) + rel_paths)
    _write_index(index_path, list(data.get("online") or []), fail_only, existing=data)
    categories = {
        spec.id: ("repair" if spec.kind in {"trigger", "repair"} else spec.scope or spec.kind)
        for spec in admitted_specs
    }
    return {
        "ok": True,
        "online_ready": False,
        "status": "bundle_admitted",
        "errors": [],
        "warnings": check.warnings
        + [
            (
                "global offline admission already ran; local bundle replay metrics are report-only"
                if not local_replay_gate
                else "bundle admission only; same-init simulation is still required before pair/online"
            )
        ],
        "bundle_id": loaded.bundle_id,
        "skill_ids": [spec.id for spec in admitted_specs],
        "entrypoint_skill_ids": check.entrypoint_skill_ids,
        "hint_skill_ids": check.hint_skill_ids,
        "candidate_categories": categories,
        "paths": rel_paths,
        "bundle_check": check.to_dict(),
        "evidence_episodes": writing_ids,
    }


def pack_uncovered(
    decision: TaskDecision,
    episodes: Sequence[Mapping[str, Any]],
    out_path: str | Path,
) -> dict[str, Any]:
    fail_dirs = decision.uncovered_dirs or [str(item["dir"]) for item in episodes if _is_fail(item)]
    payload = pack_fail_set(fail_dirs, out_path, task=_task_label(episodes, decision.task_id))
    payload["mine"] = {
        "task_id": decision.task_id,
        "action": decision.action,
        "reason": decision.reason,
        "library_skill_ids": decision.covering_skill_ids,
        "instruction": (
            "The current library did not cover these failures (or was too wide on this task). "
            "First classify the failure layer. If the failure is only recovery timing, write a "
            "single fail_only repair/trigger skill. If grasp, grounding, geometry, or place is "
            "also implicated, write a skill bundle with bundle.yaml plus one markdown draft per "
            "needed category. Do not put the task number in skill ids. Do not invent trigger "
            "predicates or unregistered capabilities."
        ),
    }
    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def episode_skill_fired(episode: Mapping[str, Any]) -> bool:
    for row in episode.get("queries") or []:
        if row.get("hook_fired") or row.get("skill_id"):
            return True
    for row in episode.get("recovery") or []:
        if row.get("hook_fired") or row.get("skill_id"):
            return True
    return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _runner_failure_rows(episode: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in episode.get("recovery") or []:
        error = str(row.get("error") or "")
        if "runner_failed:" not in error:
            continue
        rows.append(
            {
                "episode_id": episode_id(episode),
                "query_idx": row.get("query_idx"),
                "kind": row.get("kind"),
                "event": row.get("event"),
                "label": row.get("label"),
                "skill_id": row.get("skill_id"),
                "error": error[:1000],
            }
        )
    return rows


def _looks_like_runner_infra_error(text: str) -> bool:
    if "runner_failed:" in text:
        return True
    lowered = text.lower()
    if "cutamp_runner_py310" in text and ("no such file or directory" in lowered or "command not found" in lowered):
        return True
    if "modulenotfounderror" in lowered and ("cutamp" in lowered or "curobo" in lowered):
        return True
    return False


def _debug_runner_failures(on_dir: str | Path | None) -> list[dict[str, Any]]:
    if on_dir in (None, ""):
        return []
    debug_dir = Path(on_dir) / "cutamp_debug"
    if not debug_dir.is_dir():
        return []
    failures: list[dict[str, Any]] = []
    for path in sorted(debug_dir.glob("*.stderr.txt")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _looks_like_runner_infra_error(text):
            continue
        failures.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "error": text[:1000],
            }
        )
    return failures


def validation_run_health(
    on_episodes: Sequence[Mapping[str, Any]],
    *,
    on_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Detect infrastructure failures that make a validation run unusable.

    A cuTAMP runner crash is not evidence that a mined skill failed. Treat it as
    a bad measurement so the mining loop can rerun the same write instead of
    consuming an attempt or asking Codex to explain fake failures.
    """
    runner_failures: list[dict[str, Any]] = []
    recovery_episode_ids: set[str] = set()
    for episode in on_episodes:
        if episode.get("recovery"):
            recovery_episode_ids.add(episode_id(episode))
        runner_failures.extend(_runner_failure_rows(episode))
    debug_failures = _debug_runner_failures(on_dir)
    if not runner_failures and not debug_failures:
        return {
            "ok": True,
            "status": "valid",
            "on_dir": str(on_dir or ""),
            "episode_count": len(on_episodes),
            "recovery_episode_count": len(recovery_episode_ids),
            "runner_failure_count": 0,
            "debug_runner_failure_count": 0,
        }
    failure_episode_ids = sorted({str(item["episode_id"]) for item in runner_failures})
    parts: list[str] = []
    if runner_failures:
        parts.append(
            f"{len(runner_failures)} recovery runner failure event(s) across "
            f"{len(failure_episode_ids)} episode(s)"
        )
    if debug_failures:
        parts.append(f"{len(debug_failures)} debug stderr infrastructure failure file(s)")
    return {
        "ok": False,
        "status": STATUS_INVALID_VALIDATION,
        "on_dir": str(on_dir or ""),
        "episode_count": len(on_episodes),
        "recovery_episode_count": len(recovery_episode_ids),
        "runner_failure_count": len(runner_failures),
        "debug_runner_failure_count": len(debug_failures),
        "runner_failure_episode_count": len(failure_episode_ids),
        "runner_failure_episode_ids": failure_episode_ids,
        "runner_failure_examples": runner_failures[:5],
        "debug_runner_failure_examples": debug_failures[:5],
        "reason": (
            "validation contains cuTAMP runner infrastructure failure signal(s): "
            + "; ".join(parts)
            + "; rerun this validation instead of treating it as a skill result"
        ),
    }


def score_validation_run(
    baseline: Sequence[Mapping[str, Any]],
    on_episodes: Sequence[Mapping[str, Any]],
    *,
    success_min: float = TASK_SUCCESS_MIN,
) -> dict[str, Any]:
    """Same-init success gate for mining. Absolute 60% plus no baseline regression."""
    on_map = {}
    for item in on_episodes:
        meta = item.get("meta") or item
        on_map[int(meta.get("episode_idx"))] = item
    paired_off = 0
    paired_on = 0
    n_pairs = 0
    unhit_fail_ids: list[str] = []
    for off in baseline:
        meta = off.get("meta") or off
        on = on_map.get(int(meta.get("episode_idx")))
        if on is None:
            continue
        n_pairs += 1
        off_ok = bool((off.get("meta") or off).get("success"))
        on_ok = bool((on.get("meta") or on).get("success"))
        paired_off += int(off_ok)
        paired_on += int(on_ok)
        if not on_ok and not episode_skill_fired(on):
            unhit_fail_ids.append(episode_id(on))
    sr = 0.0 if n_pairs == 0 else paired_on / n_pairs
    off_sr = 0.0 if n_pairs == 0 else paired_off / n_pairs
    stable_hit = not unhit_fail_ids
    regressed = paired_on < paired_off
    passed = n_pairs > 0 and sr >= success_min and not regressed
    reasons: list[str] = []
    warnings: list[str] = []
    if n_pairs <= 0:
        reasons.append("no paired same-init episodes")
    if sr < success_min:
        reasons.append(f"success rate {sr:.2f} < {success_min:.2f}")
    if regressed:
        reasons.append(f"regressed vs baseline ({paired_on}/{n_pairs} < {paired_off}/{n_pairs})")
    if unhit_fail_ids:
        warnings.append("remaining failures never fired a skill: " + ", ".join(unhit_fail_ids))
    return {
        "passed": passed,
        "n_pairs": n_pairs,
        "on_success": paired_on,
        "off_success": paired_off,
        "success_rate": sr,
        "baseline_success_rate": off_sr,
        "regressed": regressed,
        "stable_hit": stable_hit,
        "unhit_fail_ids": unhit_fail_ids,
        "reason": "; ".join(reasons),
        "warnings": warnings,
    }


def canonical_validation_exp_name(task_id: int, writes: int) -> str:
    return f"mine_val_task{int(task_id):02d}_w{int(writes)}"


def write_validation_record(
    out_dir: str | Path,
    *,
    task_id: int,
    writes: int,
    on_dir: str | Path,
    status: str,
    payload: Mapping[str, Any],
) -> str:
    out = Path(out_dir)
    exp_name = canonical_validation_exp_name(task_id, writes)
    validation_root = out / "validation"
    record = {
        "schema_version": 1,
        "kind": "mining_validation_canonical_record",
        "updated_at": _now_iso(),
        "task_id": int(task_id),
        "writes": int(writes),
        "canonical_exp_name": exp_name,
        "canonical_on_dir": str(validation_root / exp_name),
        "selected_on_dir": str(Path(on_dir)),
        "status": str(status),
        "valid": str(status) != STATUS_INVALID_VALIDATION,
        "payload": dict(payload),
    }
    path = validation_root / f"{exp_name}.canonical.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(path)


def mining_cutamp_argv(
    *,
    val_log_dir: str | Path,
    exp_name: str,
    runner_python: str | None = None,
    repo_root: str | Path | None = None,
) -> list[str]:
    """Flags that actually execute recovery. Independent of the skills-off baseline."""
    python_bin = resolve_cutamp_runner_python(runner_python=runner_python, repo_root=repo_root)
    debug_dir = str(Path(val_log_dir) / exp_name / "cutamp_debug")
    return [
        "--use_real_cutamp_backend",
        "--real_cutamp_require_feasible",
        "--real_cutamp_grasp_dof",
        str(MINING_CUTAMP_GRASP_DOF),
        "--real_cutamp_curobo_plan",
        "--real_cutamp_serialize_trajectories",
        "--prefer_real_cutamp_executable_plan",
        "--require_real_cutamp_executable_plan",
        "--max_recovery_calls",
        str(MINING_MAX_RECOVERY_CALLS),
        "--real_cutamp_runner_python",
        python_bin,
        "--real_cutamp_runner_timeout_sec",
        str(MINING_CUTAMP_TIMEOUT_SEC),
        "--real_cutamp_debug_dir",
        debug_dir,
        "--max_recovery_steps",
        str(MINING_MAX_RECOVERY_STEPS),
    ]


def resolve_cutamp_runner_python(
    *,
    runner_python: str | None = None,
    repo_root: str | Path | None = None,
) -> str:
    if runner_python:
        return str(runner_python)
    env_value = os.environ.get("CUTAMP_RUNNER_PYTHON")
    if env_value:
        return str(env_value)
    roots: list[Path] = []
    if repo_root:
        roots.append(Path(repo_root))
    roots.append(Path(__file__).resolve().parents[4])
    for root in roots:
        for rel in REPO_CUTAMP_RUNNER_CANDIDATES:
            candidate = root / rel
            if candidate.exists():
                return str(candidate)
    return DEFAULT_CUTAMP_RUNNER_PYTHON


def mining_validation_command(
    *,
    baseline_run_dir: str | Path,
    skills_root: str | Path,
    val_log_dir: str | Path,
    task_id: int,
    writes: int,
    seed: int = 90,
    cutamp_runner_python: str | None = None,
    generated_benchmark_dir: str | Path | None = None,
    generated_split: str = "smoke",
    capability_registry: str | Path | None = None,
    early_stop_first_n_failures: int = 5,
) -> dict[str, Any]:
    baseline_run_dir = Path(baseline_run_dir)
    val_log_dir = Path(val_log_dir)
    summary: dict[str, Any] = {}
    summary_path = baseline_run_dir / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    params = dict(summary.get("params") or {})
    pretrained = str(summary.get("pretrained_path") or params.get("pretrained_path") or "")
    repo_root = str(params.get("openvla_repo_root") or "")
    exp_name = f"mine_val_task{int(task_id):02d}_w{int(writes)}"
    # Validations inherit the cell's language-source protocol from the baseline it scores against.
    language_source_argv = [
        item
        for key, default in (
            ("task_language_source", "filename"),
            ("engine_language_source", "policy"),
        )
        for item in (f"--{key}", str(params.get(key) or default))
    ]
    argv = [
        "python",
        "scripts/recovery/skill_pipeline/run_skill_eval.py",
        "--enable_mining_skills",
        "--skill_index",
        str(Path(skills_root) / "_index.yaml"),
        "--log_dir",
        str(val_log_dir),
        "--exp_name",
        exp_name,
        "--config_name",
        str(params.get("config_name") or "pi0_libero"),
        "--pretrained_path",
        pretrained,
        "--task_suite_name",
        str(params.get("task_suite_name") or "libero_90"),
        "--task_ids",
        str(int(task_id)),
        "--num_trials_per_task",
        "5",
        "--early_stop_first_n_failures",
        str(max(0, int(early_stop_first_n_failures or 0))),
        "--seed",
        str(params.get("seed") or seed),
        "--action_chunk",
        str(params.get("action_chunk") or 5),
        "--save_video",
        "--fps",
        str(params.get("fps") or 30),
        *language_source_argv,
        *mining_cutamp_argv(
            val_log_dir=val_log_dir,
            exp_name=exp_name,
            runner_python=cutamp_runner_python,
            repo_root=repo_root,
        ),
    ]
    if capability_registry:
        argv.extend(["--capability_registry", str(capability_registry)])
    if generated_benchmark_dir:
        argv.extend(
            [
                "--generated_benchmark_dir",
                str(generated_benchmark_dir),
                "--generated_split",
                generated_split,
                "--generated_task_ids",
                str(int(task_id)),
            ]
        )
    return {
        "exp_name": exp_name,
        "log_dir": str(val_log_dir),
        "on_dir": str(val_log_dir / exp_name),
        "argv": argv,
        "command": " ".join(argv),
    }


def load_mine_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return {"completed": [], "awaiting_task": None, "awaiting_kind": None, "tasks": {}}
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data.setdefault("awaiting_kind", None)
    data.setdefault("completed", [])
    data.setdefault("tasks", {})
    return data


def clear_consumed_wait_file(state_path: str | Path, state: Mapping[str, Any]) -> bool:
    """Remove a ``WAIT_CODEX.json`` the state machine has already moved past.

    The mining lane writes the wait file when it needs a draft and never removes
    it, so a finished run keeps looking like it is still waiting. That misleads
    every file-based status check, including the intervention watcher. Whenever
    the state stops asking for a draft, the wait file has been consumed.
    """
    if str(state.get("awaiting_kind") or "") == "draft":
        return False
    wait_path = Path(state_path).parent / "WAIT_CODEX.json"
    try:
        wait_path.unlink()
    except OSError:
        return False
    return True


def save_mine_state(path: str | Path, state: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    clear_consumed_wait_file(path, state)


def engine_capability_ids() -> frozenset[str]:
    """Grasp ids the engine implements itself, so no pack had to provide them."""
    ids = set(CORE_GRASP_PROFILES)
    try:
        from experiments.robot.libero.tiptop_repro.grasp_profiles import (
            CORE_TOPDOWN_GRASP_SAMPLER_PROFILES,
        )

        ids.update(str(item) for item in CORE_TOPDOWN_GRASP_SAMPLER_PROFILES)
    except Exception:  # pragma: no cover - engine import may be unavailable offline
        pass
    return frozenset(ids)


def classify_capability_source(
    used: Mapping[str, Sequence[str]] | None,
    added: Mapping[str, Sequence[str]] | None,
) -> str:
    """How one round obtained the capabilities its draft used.

    - ``new_code``: this round added a capability id in pack code.
    - ``borrowed``: it reused a capability a pack already provided.
    - ``default``: it only named engine-provided profiles.
    - ``skill_only``: it named no capability at all (pure timing/trigger skill).
    - ``unknown``: the audit could not be recomputed, e.g. for older state files.
    """
    added_ids = sorted({str(item) for values in (added or {}).values() for item in values})
    if added_ids:
        return "new_code"
    if used is None:
        return "unknown"
    flat = sorted({str(item) for values in used.values() for item in values})
    if not flat:
        return "skill_only"
    if all(item in engine_capability_ids() for item in flat):
        return "default"
    return "borrowed"


def admitted_capability_used(
    skills_root: str | Path,
    rel_paths: Sequence[str],
    *,
    capability_registry: str | Path | None = None,
) -> dict[str, list[str]] | None:
    """Category -> ids used by the admitted drafts, or None when uncomputable."""
    root = Path(skills_root)
    try:
        registry = load_capability_registry(capability_registry, index_path=root / "_index.yaml")
    except Exception:
        return None
    used: dict[str, set[str]] = {}
    parsed = 0
    for rel in rel_paths:
        path = root / str(rel)
        if not path.exists():
            continue
        try:
            spec = parse_skill_markdown(path.read_text(encoding="utf-8"), path=str(path))
            audit = registry.audit_skill(spec)
        except Exception:
            return None
        parsed += 1
        for category, values in (audit.used or {}).items():
            used.setdefault(str(category), set()).update(str(item) for item in values)
    if parsed == 0:
        return None
    return {key: sorted(values) for key, values in sorted(used.items()) if values}


def _mine_summary_payload(state: Mapping[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    tasks = dict(state.get("tasks") or {})
    for raw_tid, entry_obj in sorted(tasks.items(), key=lambda item: int(item[0])):
        entry = dict(entry_obj or {})
        triage = dict(entry.get("last_triage") or {})
        accounting = dict(entry.get("last_capability_accounting") or {})
        rows.append(
            {
                "task_id": int(raw_tid),
                "status": entry.get("status") or "pending",
                "writes": int(entry.get("writes") or 0),
                "best": entry.get("best"),
                "candidate_bundle_id": entry.get("candidate_bundle_id"),
                "candidate_skill_ids": list(entry.get("candidate_skill_ids") or []),
                "candidate_categories": dict(entry.get("candidate_categories") or {}),
                "triage_status": triage.get("status"),
                "primary_signature": triage.get("primary_signature"),
                "reason": triage.get("reason"),
                "skill_attempt_allowed": triage.get("skill_attempt_allowed"),
                "recommended_artifacts": list(triage.get("recommended_artifacts") or []),
                "triage_json": dict(entry.get("last_triage_paths") or {}).get("triage_json"),
                "triage_md": dict(entry.get("last_triage_paths") or {}).get("triage_md"),
                "capability_source": accounting.get("capability_source"),
                "used_capabilities": dict(accounting.get("used_capabilities") or {}),
                "added_capability_ids": list(accounting.get("added_capability_ids") or []),
                "changed_files": list(accounting.get("changed_files") or []),
                "code_admission_ok": accounting.get("code_admission_ok"),
            }
        )
    sources: dict[str, int] = {}
    for row in rows:
        if int(row.get("writes") or 0) <= 0:
            continue
        key = str(row.get("capability_source") or "unknown")
        sources[key] = sources.get(key, 0) + 1
    return {
        "completed": list(state.get("completed") or []),
        "awaiting_task": state.get("awaiting_task"),
        "awaiting_kind": state.get("awaiting_kind"),
        "capability_sources": sources,
        "tasks": rows,
    }


def write_mine_summary(out_dir: str | Path, state: Mapping[str, Any]) -> dict[str, str]:
    out = Path(out_dir)
    payload = _mine_summary_payload(state)
    json_path = out / "mine_summary.json"
    md_path = out / "mine_summary.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Skill mining summary", ""]
    lines.append(f"- completed: {payload['completed']}")
    lines.append(f"- awaiting: task={payload['awaiting_task']} kind={payload['awaiting_kind']}")
    lines.append(f"- capability sources: {payload.get('capability_sources') or {}}")
    lines.extend(["", "## Tasks"])
    for row in payload["tasks"]:
        lines.append(
            f"- task{int(row['task_id']):02d}: status={row['status']} writes={row['writes']} "
            f"triage={row.get('triage_status')} signature={row.get('primary_signature')} "
            f"capability={row.get('capability_source')}"
        )
        if row.get("added_capability_ids"):
            lines.append(f"  - added capabilities: {row['added_capability_ids']}")
        if row.get("changed_files"):
            lines.append(f"  - changed files: {row['changed_files']}")
        if row.get("reason"):
            lines.append(f"  - reason: {row['reason']}")
        if row.get("triage_md"):
            lines.append(f"  - report: {row['triage_md']}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"summary_json": str(json_path), "summary_md": str(md_path)}


def _task_entry(state: dict[str, Any], task_id: int) -> dict[str, Any]:
    entry = state.setdefault("tasks", {}).setdefault(str(int(task_id)), {})
    entry.setdefault("writes", 0)
    entry.setdefault("attempts", [])
    entry.setdefault("status", "pending")
    return entry


def _pack_for_task(
    *,
    run_dir: str | Path,
    skills: Sequence[SkillSpec],
    out_dir: Path,
    task_id: int,
    fail_recall_min: float,
    success_fire_max: float,
    include_dirs: Sequence[str] | None = None,
    generated_benchmark_dir: str | Path | None = None,
    generated_split: str = "smoke",
) -> tuple[TaskDecision, Path]:
    episodes = load_task_episodes(
        run_dir,
        task_id,
        generated_benchmark_dir=generated_benchmark_dir,
        generated_split=generated_split,
    )
    decision = decide_task(
        task_id,
        episodes,
        skills,
        fail_recall_min=fail_recall_min,
        success_fire_max=success_fire_max,
    )
    if include_dirs is not None:
        decision.uncovered_dirs = _unique([str(item) for item in include_dirs])
        decision.action = "write"
        decision.reason = "triage selected these validation failures as skill-repairable"
    elif not decision.uncovered_dirs:
        decision.uncovered_dirs = [str(item["dir"]) for item in episodes if _is_fail(item)]
        decision.action = "write"
    task_out = out_dir / f"task{int(task_id):02d}"
    task_out.mkdir(parents=True, exist_ok=True)
    pack_path = task_out / "fail_set.json"
    pack_uncovered(decision, episodes, pack_path)
    return decision, pack_path


def _need_draft_payload(
    *,
    state: dict[str, Any],
    state_path: Path,
    task_id: int,
    decision: TaskDecision,
    pack_path: Path,
    writes: int,
    max_writes_per_task: int = DEFAULT_MAX_WRITES_PER_TASK,
) -> dict[str, Any]:
    completed = {int(item) for item in state.get("completed") or []}
    completed.discard(int(task_id))
    state["completed"] = sorted(completed)
    state["awaiting_task"] = int(task_id)
    state["awaiting_kind"] = "draft"
    save_mine_state(state_path, state)
    return {
        "status": "need_draft",
        "awaiting_task": int(task_id),
        "action": decision.action,
        "reason": decision.reason,
        "writes_used": writes,
        "writes_max": int(max_writes_per_task),
        "evidence_json": str(pack_path),
        "uncovered_dirs": decision.uncovered_dirs,
        "covering_skill_ids": decision.covering_skill_ids,
        "state_path": str(state_path),
    }


def _need_validation_payload(
    *,
    state: dict[str, Any],
    state_path: Path,
    baseline_run_dir: str | Path,
    skills_root: Path,
    out_dir: Path,
    task_id: int,
    writes: int,
    max_writes_per_task: int = DEFAULT_MAX_WRITES_PER_TASK,
    generated_benchmark_dir: str | Path | None = None,
    generated_split: str = "smoke",
    capability_registry: str | Path | None = None,
) -> dict[str, Any]:
    spec = mining_validation_command(
        baseline_run_dir=baseline_run_dir,
        skills_root=skills_root,
        val_log_dir=out_dir / "validation",
        task_id=task_id,
        writes=writes,
        generated_benchmark_dir=generated_benchmark_dir,
        generated_split=generated_split,
        capability_registry=capability_registry,
    )
    entry = _task_entry(state, task_id)
    entry["status"] = "awaiting_validation"
    entry["validation"] = spec
    completed = {int(item) for item in state.get("completed") or []}
    completed.discard(int(task_id))
    state["completed"] = sorted(completed)
    state["awaiting_task"] = int(task_id)
    state["awaiting_kind"] = "validation"
    save_mine_state(state_path, state)
    return {
        "status": "need_validation",
        "awaiting_task": int(task_id),
        "writes_used": writes,
        "writes_max": int(max_writes_per_task),
        "validation": spec,
        "message": (
            "Run the same-init eval with --enable_mining_skills, then "
            "run_skill_mine.py score --on_dir <validation.on_dir>"
        ),
        "state_path": str(state_path),
    }


def step_mine(
    *,
    run_dir: str | Path,
    skills_root: str | Path,
    out_dir: str | Path,
    task_ids: Sequence[int],
    fail_recall_min: float = FAIL_RECALL_MIN,
    success_fire_max: float = SUCCESS_EPISODE_FIRE_MAX,
    max_writes_per_task: int = DEFAULT_MAX_WRITES_PER_TASK,
    generated_benchmark_dir: str | Path | None = None,
    generated_split: str = "smoke",
    capability_registry: str | Path | None = None,
) -> dict[str, Any]:
    """Advance until a draft or a 5-rollout validation is required."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    state_path = out / "mine_state.json"
    state = load_mine_state(state_path)
    completed = {int(item) for item in state.get("completed") or []}
    awaiting = state.get("awaiting_task")
    kind = state.get("awaiting_kind")
    if awaiting is not None and kind == "draft":
        return {
            "status": "awaiting_draft",
            "awaiting_task": int(awaiting),
            "message": f"ingest a draft for task {awaiting} before stepping further",
            "state_path": str(state_path),
        }
    if awaiting is not None and kind == "validation":
        entry = _task_entry(state, int(awaiting))
        return {
            "status": "awaiting_validation",
            "awaiting_task": int(awaiting),
            "validation": entry.get("validation"),
            "message": f"score the same-init run for task {awaiting} before stepping further",
            "state_path": str(state_path),
        }
    skills_root = Path(skills_root)
    index_path = skills_root / "_index.yaml"
    for task_id in task_ids:
        if int(task_id) in completed:
            continue
        skills = resolve_mining_skills(index_path) if index_path.exists() else []
        entry = _task_entry(state, task_id)
        episodes = load_task_episodes(
            run_dir,
            task_id,
            generated_benchmark_dir=generated_benchmark_dir,
            generated_split=generated_split,
        )
        fails = [item for item in episodes if _is_fail(item)]
        baseline_success_rate = (
            0.0 if not episodes else (len(episodes) - len(fails)) / len(episodes)
        )
        if not skills and episodes and baseline_success_rate >= TASK_SUCCESS_MIN:
            entry["status"] = "skip_baseline_pass"
            entry["baseline_success_rate"] = baseline_success_rate
            entry["reason"] = (
                f"skills-off baseline already passed ({len(episodes) - len(fails)}/{len(episodes)} "
                f">= {TASK_SUCCESS_MIN:.0%})"
            )
            completed.add(int(task_id))
            state["completed"] = sorted(completed)
            save_mine_state(state_path, state)
            continue
        if not fails and not skills:
            entry["status"] = "skip_no_fail"
            completed.add(int(task_id))
            state["completed"] = sorted(completed)
            save_mine_state(state_path, state)
            continue
        if not skills:
            decision, pack_path = _pack_for_task(
                run_dir=run_dir,
                skills=skills,
                out_dir=out,
                task_id=task_id,
                fail_recall_min=fail_recall_min,
                success_fire_max=success_fire_max,
                generated_benchmark_dir=generated_benchmark_dir,
                generated_split=generated_split,
            )
            entry["last_decision"] = asdict(decision)
            entry["pack_run_dir"] = str(Path(run_dir))
            return _need_draft_payload(
                state=state,
                state_path=state_path,
                task_id=task_id,
                decision=decision,
                pack_path=pack_path,
                writes=int(entry.get("writes") or 0),
                max_writes_per_task=max_writes_per_task,
            )
        return _need_validation_payload(
            state=state,
            state_path=state_path,
            baseline_run_dir=run_dir,
            skills_root=skills_root,
            out_dir=out,
            task_id=task_id,
            writes=int(entry.get("writes") or 0),
            max_writes_per_task=max_writes_per_task,
            generated_benchmark_dir=generated_benchmark_dir,
            generated_split=generated_split,
            capability_registry=capability_registry,
        )
    state["completed"] = sorted(completed)
    summary_paths = write_mine_summary(out, state)
    save_mine_state(state_path, state)
    return {"status": "done", "completed": sorted(completed), **summary_paths, "state_path": str(state_path)}


def ingest_mine_draft(
    *,
    draft_md: str | Path | None = None,
    bundle_yaml: str | Path | None = None,
    draft_dir: str | Path | None = None,
    run_dir: str | Path,
    skills_root: str | Path,
    out_dir: str | Path,
    task_id: int | None = None,
    code_admission_gate: bool = False,
    code_manifest: str | Path | None = None,
    code_base_ref: str = "HEAD",
    code_base_file_texts: Mapping[str, str] | None = None,
    code_admission_out_dir: str | Path | None = None,
    admission_gate: bool = False,
    admission_scan_roots: Sequence[str | Path] | None = None,
    admission_corpus_root: str | Path | None = None,
    admission_max_corpus_runs: int = 8,
    admission_out_dir: str | Path | None = None,
    admission_require_offline_scan: bool = True,
    admission_include_hints: bool = True,
    max_writes_per_task: int = DEFAULT_MAX_WRITES_PER_TASK,
    generated_benchmark_dir: str | Path | None = None,
    generated_split: str = "smoke",
    generated_smoke_run_dir: str | Path | None = None,
    require_generated_smoke: bool = False,
    generated_smoke_min_episodes_per_task: int = 1,
    generated_smoke_require_video: bool = True,
    capability_registry: str | Path | None = None,
    predicate_registry: str | Path | None = None,
    predicate_adapter: str | Path | None = None,
    diagnostic_signal_registry: str | Path | None = None,
    diagnostic_signal_statuses: str = "",
    diagnostic_provider_roots: Sequence[str | Path] = (),
) -> dict[str, Any]:
    draft_modes = [bool(draft_md), bool(bundle_yaml), bool(draft_dir)]
    if sum(draft_modes) != 1:
        raise ValueError("provide exactly one of draft_md, bundle_yaml, or draft_dir")
    out = Path(out_dir)
    state_path = out / "mine_state.json"
    state = load_mine_state(state_path)
    awaiting = state.get("awaiting_task")
    kind = state.get("awaiting_kind")
    tid = int(task_id if task_id is not None else awaiting or 0)
    if not tid:
        raise ValueError("task_id is required when mine_state has no awaiting_task")
    if awaiting is not None and int(awaiting) != tid:
        raise ValueError(f"mine is awaiting task {awaiting}, not {tid}")
    if kind not in (None, "draft"):
        raise ValueError(f"mine is awaiting {kind}, not a draft")
    entry = _task_entry(state, tid)
    writes = int(entry.get("writes") or 0)
    max_writes = int(max_writes_per_task)
    if writes >= max_writes:
        raise ValueError(f"task {tid} already used {max_writes} Codex writes")
    pack_run_dir = Path(entry.get("pack_run_dir") or run_dir)
    episodes = load_task_episodes(
        pack_run_dir,
        tid,
        generated_benchmark_dir=generated_benchmark_dir,
        generated_split=generated_split,
    )
    uncovered = list(entry.get("uncovered_dirs") or entry.get("last_decision", {}).get("uncovered_dirs") or [])
    writing = [item for item in episodes if str(item["dir"]) in set(uncovered)] or [
        item for item in episodes if _is_fail(item)
    ]
    bundle = None
    if bundle_yaml or draft_dir:
        bundle = load_skill_bundle(bundle_yaml=bundle_yaml, draft_dir=draft_dir)
    skills_root_path = Path(skills_root).resolve()
    inferred_pack_root = skills_root_path.parent if (skills_root_path.parent / "pack.yaml").exists() else None
    if code_admission_gate or code_manifest:
        from .code_admission import CodeAdmissionConfig, run_code_admission

        repo_root = Path(__file__).resolve().parents[4]
        code_gate_out = (
            Path(code_admission_out_dir)
            if code_admission_out_dir
            else out / f"task{tid:02d}" / f"code_admission_w{writes + 1}"
        )
        skill_files = [draft.path for draft in bundle.drafts] if bundle is not None else [Path(draft_md or "")]
        code_admission = run_code_admission(
            CodeAdmissionConfig(
                repo_root=repo_root,
                out_dir=code_gate_out,
                manifest_path=code_manifest,
                skill_files=skill_files,
                index_path=Path(skills_root) / "_index.yaml",
                capability_registry=capability_registry,
                predicate_registry=predicate_registry,
                predicate_adapter=predicate_adapter,
                pack_root=inferred_pack_root,
                base_ref=code_base_ref,
                base_file_texts=code_base_file_texts or {},
                changed_files=list(code_base_file_texts) if code_base_file_texts is not None else None,
            )
        )
        entry["last_code_admission"] = {
            "ok": bool(code_admission.get("ok")),
            "result_json": code_admission.get("result_json"),
            "result_markdown": code_admission.get("result_markdown"),
            "errors": list(code_admission.get("errors") or []),
            "warnings": list(code_admission.get("warnings") or []),
            "change_types": [str(item) for item in (code_admission.get("change_types") or [])],
            "changed_files": [str(item) for item in (code_admission.get("changed_files") or [])],
            "added_capabilities": {
                str(category): [str(item) for item in values]
                for category, values in (code_admission.get("code_added_capabilities") or {}).items()
            },
        }
        if not code_admission.get("ok"):
            entry["status"] = "awaiting_draft"
            state["awaiting_task"] = tid
            state["awaiting_kind"] = "draft"
            save_mine_state(state_path, state)
            return {
                "ok": False,
                "status": "code_admission_failed",
                "task_id": tid,
                "writes_used": writes,
                "writes_max": max_writes,
                "code_admission": code_admission,
                "errors": list(code_admission.get("errors") or []),
                "warnings": list(code_admission.get("warnings") or []),
                "message": "candidate code failed admission; draft was not added to fail_only or _index.yaml",
                "state_path": str(state_path),
            }
    if admission_gate:
        from .admission import SkillAdmissionConfig, resolve_admission_scan_roots, run_skill_admission

        code_repo_root = Path(__file__).resolve().parents[4]
        try:
            skills_root_path.relative_to(code_repo_root)
            repo_root = code_repo_root
        except ValueError:
            repo_root = skills_root_path.parent
        scan_roots = resolve_admission_scan_roots(
            admission_scan_roots,
            repo_root=repo_root,
            corpus_root=admission_corpus_root,
            max_corpus_runs=int(admission_max_corpus_runs),
            fallback_scan_root=pack_run_dir,
        )
        gate_out = Path(admission_out_dir) if admission_out_dir else out / f"task{tid:02d}" / f"admission_w{writes + 1}"
        current_task_name = task_dir(
            pack_run_dir,
            tid,
            generated_benchmark_dir=generated_benchmark_dir,
            generated_split=generated_split,
        ).name
        admissions: list[dict[str, Any]]
        if bundle is not None:
            admissions = []
            for draft in bundle.drafts:
                skill_gate_out = gate_out / draft.spec.id
                admissions.append(
                    run_skill_admission(
                        draft.path,
                        config=SkillAdmissionConfig(
                            index_path=Path(skills_root) / "_index.yaml",
                            out_dir=skill_gate_out,
                            scan_roots=tuple(scan_roots),
                            current_scan_roots=(pack_run_dir,),
                            current_task_ids=(tid,),
                            current_task_names=(current_task_name,),
                            mining=True,
                            require_offline_scan=bool(admission_require_offline_scan),
                            include_hints=bool(admission_include_hints),
                            generated_benchmark_dir=generated_benchmark_dir,
                            generated_split=generated_split,
                            generated_smoke_run_dir=generated_smoke_run_dir,
                            require_generated_smoke=bool(require_generated_smoke),
                            generated_smoke_min_episodes_per_task=int(generated_smoke_min_episodes_per_task),
                            generated_smoke_require_video=bool(generated_smoke_require_video),
                            capability_registry=capability_registry,
                            predicate_registry=predicate_registry,
                            predicate_adapter=predicate_adapter,
                            diagnostic_signal_registry=diagnostic_signal_registry,
                            diagnostic_signal_statuses=diagnostic_signal_statuses,
                            diagnostic_provider_roots=diagnostic_provider_roots,
                        ),
                    )
                )
            admission = {
                "ok": all(bool(item.get("ok")) for item in admissions),
                "bundle_id": bundle.bundle_id,
                "skill_admissions": admissions,
                "errors": [
                    f"{item.get('skill', {}).get('id', 'unknown')}: {error}"
                    for item in admissions
                    for error in list(item.get("errors") or [])
                ],
                "warnings": [
                    f"{item.get('skill', {}).get('id', 'unknown')}: {warning}"
                    for item in admissions
                    for warning in list(item.get("warnings") or [])
                ],
                "result_json": "",
                "result_markdown": "",
            }
            gate_out.mkdir(parents=True, exist_ok=True)
            admission["result_json"] = str(gate_out / "bundle_admission_result.json")
            (gate_out / "bundle_admission_result.json").write_text(
                json.dumps(admission, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            admission = run_skill_admission(
                draft_md,
                config=SkillAdmissionConfig(
                    index_path=Path(skills_root) / "_index.yaml",
                    out_dir=gate_out,
                    scan_roots=tuple(scan_roots),
                    current_scan_roots=(pack_run_dir,),
                    current_task_ids=(tid,),
                    current_task_names=(current_task_name,),
                    mining=True,
                    require_offline_scan=bool(admission_require_offline_scan),
                    include_hints=bool(admission_include_hints),
                    generated_benchmark_dir=generated_benchmark_dir,
                    generated_split=generated_split,
                    generated_smoke_run_dir=generated_smoke_run_dir,
                    require_generated_smoke=bool(require_generated_smoke),
                    generated_smoke_min_episodes_per_task=int(generated_smoke_min_episodes_per_task),
                    generated_smoke_require_video=bool(generated_smoke_require_video),
                    capability_registry=capability_registry,
                    predicate_registry=predicate_registry,
                    predicate_adapter=predicate_adapter,
                    diagnostic_signal_registry=diagnostic_signal_registry,
                    diagnostic_signal_statuses=diagnostic_signal_statuses,
                    diagnostic_provider_roots=diagnostic_provider_roots,
                ),
            )
        entry["last_admission"] = {
            "ok": bool(admission.get("ok")),
            "result_json": admission.get("result_json"),
            "result_markdown": admission.get("result_markdown"),
            "errors": list(admission.get("errors") or []),
            "warnings": list(admission.get("warnings") or []),
        }
        if not admission.get("ok"):
            entry["status"] = "awaiting_draft"
            state["awaiting_task"] = tid
            state["awaiting_kind"] = "draft"
            save_mine_state(state_path, state)
            return {
                "ok": False,
                "status": "admission_failed",
                "task_id": tid,
                "writes_used": writes,
                "writes_max": max_writes,
                "admission": admission,
                "errors": list(admission.get("errors") or []),
                "warnings": list(admission.get("warnings") or []),
                "message": "candidate skill failed admission; it was not added to fail_only or _index.yaml",
                "state_path": str(state_path),
            }
    if bundle is not None:
        result = admit_fail_only_bundle(
            bundle=bundle,
            skills_root=skills_root,
            episodes=episodes,
            writing_episodes=writing,
            capability_registry=capability_registry,
            local_replay_gate=not admission_gate,
        )
    else:
        result = admit_fail_only_draft(
            draft_md,
            skills_root=skills_root,
            episodes=episodes,
            writing_episodes=writing,
            capability_registry=capability_registry,
            local_replay_gate=not admission_gate,
        )
    result["task_id"] = tid
    if not result["ok"]:
        return result
    skill_ids = list(result.get("skill_ids") or ([result["skill_id"]] if result.get("skill_id") else []))
    entrypoint_ids = list(result.get("entrypoint_skill_ids") or [])
    entry["writes"] = writes + 1
    entry["candidate_skill_id"] = result.get("skill_id") or (entrypoint_ids[0] if entrypoint_ids else (skill_ids[0] if skill_ids else None))
    entry["candidate_bundle_id"] = result.get("bundle_id")
    entry["candidate_skill_ids"] = skill_ids
    entry["candidate_skill_paths"] = list(result.get("paths") or ([result["path"]] if result.get("path") else []))
    entry["candidate_categories"] = dict(result.get("candidate_categories") or {})
    used_capabilities = admitted_capability_used(
        skills_root,
        list(entry.get("candidate_skill_paths") or []),
        capability_registry=capability_registry,
    )
    code_gate = dict(entry.get("last_code_admission") or {})
    added_capabilities = {
        str(category): [str(item) for item in values]
        for category, values in (code_gate.get("added_capabilities") or {}).items()
    }
    entry["last_capability_accounting"] = {
        "used_capabilities": dict(used_capabilities or {}),
        "used_capabilities_known": used_capabilities is not None,
        "added_capabilities": added_capabilities,
        "added_capability_ids": sorted({item for values in added_capabilities.values() for item in values}),
        "changed_files": [str(item) for item in (code_gate.get("changed_files") or [])],
        "change_types": [str(item) for item in (code_gate.get("change_types") or [])],
        "code_admission_ok": code_gate.get("ok"),
        "capability_source": classify_capability_source(used_capabilities, added_capabilities),
    }
    if admission_gate:
        result["admission"] = entry.get("last_admission")
    if code_admission_gate or code_manifest:
        result["code_admission"] = entry.get("last_code_admission")
    entry["ingested"] = result
    entry["status"] = "awaiting_validation"
    payload = _need_validation_payload(
        state=state,
        state_path=state_path,
        baseline_run_dir=run_dir,
        skills_root=Path(skills_root),
        out_dir=out,
        task_id=tid,
        writes=entry["writes"],
        max_writes_per_task=max_writes,
        generated_benchmark_dir=generated_benchmark_dir,
        generated_split=generated_split,
        capability_registry=capability_registry,
    )
    result.update(payload)
    result["ok"] = True
    result["status"] = "need_validation"
    result["writes_used"] = entry["writes"]
    result["writes_max"] = max_writes
    return result


def score_mine(
    *,
    run_dir: str | Path,
    skills_root: str | Path,
    out_dir: str | Path,
    on_dir: str | Path,
    task_id: int | None = None,
    success_min: float = TASK_SUCCESS_MIN,
    max_writes_per_task: int = DEFAULT_MAX_WRITES_PER_TASK,
    generated_benchmark_dir: str | Path | None = None,
    generated_split: str = "smoke",
) -> dict[str, Any]:
    out = Path(out_dir)
    state_path = out / "mine_state.json"
    state = load_mine_state(state_path)
    awaiting = state.get("awaiting_task")
    kind = state.get("awaiting_kind")
    tid = int(task_id if task_id is not None else awaiting or 0)
    if not tid:
        raise ValueError("task_id is required when mine_state has no awaiting_task")
    if kind == "draft":
        raise ValueError("ingest a draft before scoring")
    baseline = load_task_episodes(
        run_dir,
        tid,
        generated_benchmark_dir=generated_benchmark_dir,
        generated_split=generated_split,
    )
    on_root = Path(on_dir)
    on_episodes = load_task_episodes(
        on_root,
        tid,
        generated_benchmark_dir=generated_benchmark_dir,
        generated_split=generated_split,
    )
    entry = _task_entry(state, tid)
    writes = int(entry.get("writes") or 0)
    health = validation_run_health(on_episodes, on_dir=on_root)
    if not health.get("ok"):
        entry.setdefault("invalid_validations", []).append(
            {
                "writes": writes,
                "on_dir": str(on_root),
                "health": health,
                "created_at": _now_iso(),
            }
        )
        entry["last_invalid_validation"] = health
        entry["status"] = "awaiting_validation"
        state["awaiting_task"] = tid
        state["awaiting_kind"] = "validation"
        record_path = write_validation_record(
            out,
            task_id=tid,
            writes=writes,
            on_dir=on_root,
            status=STATUS_INVALID_VALIDATION,
            payload=health,
        )
        summary_paths = write_mine_summary(out, state)
        save_mine_state(state_path, state)
        return {
            "ok": False,
            "status": STATUS_INVALID_VALIDATION,
            "task_id": tid,
            "sr_passed": False,
            "writes_used": writes,
            "validation_record": record_path,
            **health,
            **summary_paths,
            "state_path": str(state_path),
        }
    scored = score_validation_run(baseline, on_episodes, success_min=success_min)
    record_path = write_validation_record(
        out,
        task_id=tid,
        writes=writes,
        on_dir=on_root,
        status="scored",
        payload={**scored, "health": health},
    )
    triage = triage_validation_run(
        task_id=tid,
        baseline_episodes=baseline,
        on_episodes=on_episodes,
        scored=scored,
        on_dir=on_root,
        success_min=success_min,
    )
    triage_paths = write_triage_artifacts(triage, out / f"task{tid:02d}" / f"triage_w{writes}")
    attempt = {
        "writes": writes,
        "on_dir": str(on_root),
        "triage": triage.to_dict(),
        "triage_paths": triage_paths,
        "validation_record": record_path,
        **scored,
    }
    entry.setdefault("attempts", []).append(attempt)
    best = entry.get("best")
    if best is None or float(scored["success_rate"]) >= float(best.get("success_rate") or -1):
        entry["best"] = {
            "success_rate": scored["success_rate"],
            "on_success": scored["on_success"],
            "skill_id": entry.get("candidate_skill_id"),
            "skill_ids": list(entry.get("candidate_skill_ids") or []),
            "bundle_id": entry.get("candidate_bundle_id"),
            "on_dir": str(on_root),
        }
    entry["last_triage"] = triage.to_dict()
    entry["last_triage_paths"] = triage_paths
    skills = resolve_mining_skills(Path(skills_root) / "_index.yaml") if (Path(skills_root) / "_index.yaml").exists() else []
    max_writes = int(max_writes_per_task)
    if scored["passed"] or triage.status == STATUS_COVERED:
        entry["status"] = "passed"
        entry["sr_passed"] = True
        append_coverage_evidence(skills, baseline, tid)
        completed = {int(item) for item in state.get("completed") or []}
        completed.add(tid)
        state["completed"] = sorted(completed)
        state["awaiting_task"] = None
        state["awaiting_kind"] = None
        summary_paths = write_mine_summary(out, state)
        save_mine_state(state_path, state)
        return {
            "ok": True,
            "status": "passed",
            "task_id": tid,
            "sr_passed": True,
            **scored,
            "triage": triage.to_dict(),
            "validation_record": record_path,
            **triage_paths,
            **summary_paths,
            "state_path": str(state_path),
        }
    if writes < max_writes:
        skill_dirs = [
            item.episode_dir
            for item in triage.episode_diagnoses
            if item.status == "skill_repairable" and item.episode_dir
        ]
        failed_dirs = [item.episode_dir for item in triage.episode_diagnoses if not item.success and item.episode_dir]
        include_dirs = skill_dirs if skill_dirs else failed_dirs or None
        decision, pack_path = _pack_for_task(
            run_dir=on_root,
            skills=skills,
            out_dir=out,
            task_id=tid,
            fail_recall_min=FAIL_RECALL_MIN,
            success_fire_max=SUCCESS_EPISODE_FIRE_MAX,
            include_dirs=include_dirs,
            generated_benchmark_dir=generated_benchmark_dir,
            generated_split=generated_split,
        )
        if include_dirs and include_dirs != skill_dirs:
            decision.reason = (
                f"triage marked this round {triage.status}/{triage.primary_signature}; "
                "packing all failed validation episodes for Codex intervention"
            )
        entry["last_decision"] = asdict(decision)
        entry["pack_run_dir"] = str(on_root)
        entry["status"] = "awaiting_draft"
        payload = _need_draft_payload(
            state=state,
            state_path=state_path,
            task_id=tid,
            decision=decision,
            pack_path=pack_path,
            writes=writes,
            max_writes_per_task=max_writes,
        )
        payload.update(scored)
        payload["ok"] = False
        payload["status"] = "need_draft"
        payload["task_id"] = tid
        payload["triage"] = triage.to_dict()
        payload["validation_record"] = record_path
        payload.update(triage_paths)
        payload["message"] = (
            f"validation failed ({scored['reason'] or triage.reason}). Codex write "
            f"{writes + 1}/{max_writes}."
        )
        return payload
    entry["status"] = STATUS_WRITE_BUDGET_EXHAUSTED
    entry["sr_passed"] = False
    completed = {int(item) for item in state.get("completed") or []}
    completed.add(tid)
    state["completed"] = sorted(completed)
    state["awaiting_task"] = None
    state["awaiting_kind"] = None
    summary_paths = write_mine_summary(out, state)
    save_mine_state(state_path, state)
    return {
        "ok": True,
        "status": STATUS_WRITE_BUDGET_EXHAUSTED,
        "task_id": tid,
        "sr_passed": False,
        "writes_used": writes,
        "writes_max": max_writes,
        **scored,
        "triage": triage.to_dict(),
        "validation_record": record_path,
        **triage_paths,
        **summary_paths,
        "best": entry.get("best"),
        "message": (
            f"used {max_writes} Codex writes; marking task write_budget_exhausted "
            f"(best sr={float((entry.get('best') or {}).get('success_rate') or 0):.2f})"
        ),
        "state_path": str(state_path),
    }
