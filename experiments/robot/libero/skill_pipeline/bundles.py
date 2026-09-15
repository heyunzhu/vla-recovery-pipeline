"""Skill-bundle parsing and mining-time checks.

A bundle is one Codex intervention that may contain a repair entrypoint plus
one or more grasp/grounding/geometry/place recovery hints.  This keeps mining
from treating every failure as "write exactly one repair trigger".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .capabilities import CapabilityRegistry, load_capability_registry
from .coordinator import check_draft
from .matcher import eval_applies_to
from .predicate_registry import PredicateRegistry, load_predicate_registry
from .schema import SkillSpec, parse_skill_markdown
from .validate import (
    FAIL_RECALL_MIN,
    SUCCESS_EPISODE_FIRE_MAX,
    episode_id,
    evaluate_heldout_triggers,
)

ENTRYPOINT_KINDS = frozenset({"trigger", "repair"})
RECOVERY_HINT_SCOPES = frozenset({"grasp", "grounding", "geometry", "place"})


@dataclass(frozen=True)
class BundleDraft:
    path: Path
    role: str
    category: str
    spec: SkillSpec


@dataclass(frozen=True)
class SkillBundle:
    bundle_id: str
    path: Path | None
    root: Path
    drafts: tuple[BundleDraft, ...]
    uses_existing_entrypoint: bool = False
    diagnosis: dict[str, Any] = field(default_factory=dict)

    @property
    def skill_ids(self) -> list[str]:
        return [draft.spec.id for draft in self.drafts]


@dataclass(frozen=True)
class BundleCheckReport:
    ok: bool
    bundle_id: str
    errors: list[str]
    warnings: list[str]
    entrypoint_skill_ids: list[str]
    hint_skill_ids: list[str]
    per_skill: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "bundle_id": self.bundle_id,
            "errors": self.errors,
            "warnings": self.warnings,
            "entrypoint_skill_ids": self.entrypoint_skill_ids,
            "hint_skill_ids": self.hint_skill_ids,
            "per_skill": self.per_skill,
        }


def _skill_category(spec: SkillSpec) -> str:
    if spec.kind in ENTRYPOINT_KINDS:
        return "repair"
    if spec.kind == "recovery_hint":
        return spec.scope or "recovery_hint"
    return spec.kind


def _read_manifest(bundle_yaml: Path) -> dict[str, Any]:
    data = yaml.safe_load(bundle_yaml.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"bundle manifest must be a mapping: {bundle_yaml}")
    return data


def _manifest_draft_items(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("drafts") or data.get("skills") or []
    if not isinstance(raw, list):
        raise ValueError("bundle drafts must be a list")
    items: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, str):
            items.append({"file": entry})
        elif isinstance(entry, Mapping):
            items.append(dict(entry))
        else:
            raise ValueError(f"bundle draft entry must be a string or mapping, got {type(entry).__name__}")
    return items


def _auto_draft_items(draft_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(draft_dir.rglob("*.md")):
        if path.name.lower() in {"findings.md", "readme.md"}:
            continue
        items.append({"file": path.relative_to(draft_dir).as_posix()})
    return items


def load_skill_bundle(
    *,
    bundle_yaml: str | Path | None = None,
    draft_dir: str | Path | None = None,
    predicate_registry: PredicateRegistry | None = None,
) -> SkillBundle:
    if bool(bundle_yaml) == bool(draft_dir):
        raise ValueError("provide exactly one of bundle_yaml or draft_dir")
    manifest_path: Path | None = Path(bundle_yaml) if bundle_yaml else None
    root = manifest_path.parent if manifest_path else Path(draft_dir or "")
    data: dict[str, Any] = {}
    if manifest_path:
        data = _read_manifest(manifest_path)
        draft_items = _manifest_draft_items(data)
    else:
        candidate = root / "bundle.yaml"
        if candidate.exists():
            manifest_path = candidate
            data = _read_manifest(candidate)
            draft_items = _manifest_draft_items(data)
        else:
            draft_items = _auto_draft_items(root)
    if not draft_items:
        raise ValueError(f"bundle contains no markdown drafts: {manifest_path or root}")

    drafts: list[BundleDraft] = []
    for item in draft_items:
        rel = str(item.get("file") or item.get("path") or "").strip()
        if not rel:
            raise ValueError("bundle draft entry is missing file")
        path = Path(rel)
        if not path.is_absolute():
            path = root / path
        spec = parse_skill_markdown(
            path.read_text(encoding="utf-8"),
            path=str(path),
            predicate_registry=predicate_registry,
        )
        category = str(item.get("category") or _skill_category(spec)).strip()
        role = str(item.get("role") or ("entrypoint" if spec.kind in ENTRYPOINT_KINDS else f"{category}_hint")).strip()
        drafts.append(BundleDraft(path=path, role=role, category=category, spec=spec))

    bundle_id = str(data.get("bundle_id") or data.get("id") or (manifest_path.stem if manifest_path else root.name))
    uses_existing = bool(data.get("uses_existing_entrypoint") or data.get("reuse_existing_entrypoint"))
    diagnosis = data.get("diagnosis") if isinstance(data.get("diagnosis"), Mapping) else {}
    return SkillBundle(
        bundle_id=bundle_id,
        path=manifest_path,
        root=root,
        drafts=tuple(drafts),
        uses_existing_entrypoint=uses_existing,
        diagnosis=dict(diagnosis),
    )


def _episode_states(episode: Mapping[str, Any]) -> list[dict[str, Any]]:
    meta = dict(episode.get("meta") or {})
    states: list[dict[str, Any]] = []
    for group in ("queries", "recovery"):
        for row in episode.get(group) or []:
            if isinstance(row, Mapping):
                state = {**meta, **dict(row)}
                state.setdefault("task_description", meta.get("task_description"))
                state.setdefault("bddl_goal_surfaces", meta.get("bddl_goal_surfaces"))
                state.setdefault("goal_name", meta.get("goal_name"))
                states.append(state)
    if not states:
        states.append(meta)
    return states


def _hint_episode_hits(spec: SkillSpec, episodes: Sequence[Mapping[str, Any]]) -> list[str]:
    hits: list[str] = []
    for episode in episodes:
        if any(
            eval_applies_to(
                spec.applies_to,
                state,
                predicate_registry=getattr(spec, "predicate_registry", None),
            )
            for state in _episode_states(episode)
        ):
            hits.append(episode_id(episode))
    return hits


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


def check_mining_bundle(
    bundle: SkillBundle,
    *,
    episodes: Sequence[Mapping[str, Any]],
    writing_episodes: Sequence[Mapping[str, Any]],
    capability_registry: str | Path | CapabilityRegistry | None = None,
    index_path: str | Path | None = None,
    predicate_registry: PredicateRegistry | None = None,
    fail_recall_min: float = FAIL_RECALL_MIN,
    success_fire_max: float = SUCCESS_EPISODE_FIRE_MAX,
    local_replay_gate: bool = True,
) -> BundleCheckReport:
    errors: list[str] = []
    warnings: list[str] = []
    per_skill: list[dict[str, Any]] = []
    entrypoints: list[BundleDraft] = []
    hints: list[BundleDraft] = []
    seen_ids: set[str] = set()
    writing_ids = [episode_id(item) for item in writing_episodes]
    registry = (
        capability_registry
        if isinstance(capability_registry, CapabilityRegistry)
        else load_capability_registry(capability_registry, index_path=index_path)
    )
    predicates = predicate_registry or (
        load_predicate_registry(index_path=index_path) if index_path else PredicateRegistry.builtins()
    )

    for draft in bundle.drafts:
        spec = draft.spec
        spec.predicate_registry = predicates
        spec.track = "fail_only"
        spec.evidence["episodes"] = _unique(list(spec.evidence.get("episodes") or []) + writing_ids)
        if spec.id in seen_ids:
            errors.append(f"duplicate skill id in bundle: {spec.id}")
        seen_ids.add(spec.id)
        coordinator = check_draft(spec, writing_episodes=writing_ids, predicate_registry=predicates)
        skill_row: dict[str, Any] = {
            "skill_id": spec.id,
            "kind": spec.kind,
            "scope": spec.scope,
            "role": draft.role,
            "category": draft.category,
            "path": str(draft.path),
            "coordinator": {
                "ok": coordinator.ok,
                "errors": coordinator.errors,
                "warnings": coordinator.warnings,
            },
        }
        errors.extend(f"{spec.id}: {item}" for item in coordinator.errors)
        warnings.extend(f"{spec.id}: {item}" for item in coordinator.warnings)

        audit = registry.audit_skill(spec)
        skill_row["capability_audit"] = audit.to_dict()
        errors.extend(f"{spec.id}: capability: {item}" for item in audit.errors)
        warnings.extend(f"{spec.id}: capability: {item}" for item in audit.warnings)

        if spec.kind in ENTRYPOINT_KINDS:
            entrypoints.append(draft)
            if spec.backend != "cutamp_recover":
                errors.append(f"{spec.id}: bundle entrypoint must use backend cutamp_recover")
            metrics = evaluate_heldout_triggers(spec, writing_episodes)
            task_metrics = evaluate_heldout_triggers(spec, episodes)
            skill_row["trigger_metrics"] = {
                "fail_recall": metrics.fail_recall,
                "success_fire_rate": task_metrics.success_fire_rate,
                "fail_hits": metrics.fail_hits,
                "success_fires": task_metrics.success_fires,
            }
            if local_replay_gate and metrics.fail_recall < fail_recall_min:
                errors.append(
                    f"{spec.id}: trigger recall {metrics.fail_recall:.2f} on current-task writing failures "
                    f"is below {fail_recall_min:.2f}"
                )
            if local_replay_gate and task_metrics.n_success and task_metrics.success_fire_rate > success_fire_max:
                errors.append(
                    f"{spec.id}: trigger fires on {task_metrics.success_fire_rate:.2f} of current-task successes "
                    f"(max {success_fire_max:.2f})"
                )
        elif spec.kind == "recovery_hint":
            hints.append(draft)
            if spec.scope not in RECOVERY_HINT_SCOPES:
                errors.append(
                    f"{spec.id}: recovery_hint scope must be one of {sorted(RECOVERY_HINT_SCOPES)}"
                )
            hit_ids = _hint_episode_hits(spec, writing_episodes)
            skill_row["applies_to_hits"] = hit_ids
            if local_replay_gate and not hit_ids:
                errors.append(f"{spec.id}: recovery_hint applies_to did not match any writing episode")
            if spec.scope == "grasp" and not spec.recovery_hints.get("grasp_profile"):
                errors.append(f"{spec.id}: grasp hint must set recovery_hints.grasp_profile")
            params = dict(spec.recovery_hints.get("params") or {})
            if spec.scope == "grounding" and not (
                "grounding_hints" in params or str(params.get("grounding_profile") or "").strip()
            ):
                errors.append(f"{spec.id}: grounding hint must set params.grounding_profile or params.grounding_hints")
            if spec.scope == "geometry" and not (
                "geometry_hints" in params or str(params.get("geometry_profile") or "").strip()
            ):
                errors.append(f"{spec.id}: geometry hint must set params.geometry_profile or params.geometry_hints")
            if spec.scope == "place":
                place_profile = str(params.get("place_profile") or "").strip()
                executor = params.get("executor")
                has_place_executor = isinstance(executor, Mapping) and any(
                    str(key).startswith("place_") for key in executor
                )
                if not place_profile and not has_place_executor:
                    errors.append(f"{spec.id}: place hint must set params.place_profile or params.executor place_* options")
        else:
            warnings.append(f"{spec.id}: diagnostics skills are accepted as draft artifacts but are not loaded online")
        per_skill.append(skill_row)

    if not entrypoints and not hints:
        errors.append(
            "bundle must include at least one executable repair/trigger or recovery_hint draft; "
            "diagnostics-only/blocker bundles are not valid mining candidates"
        )
    if not entrypoints and not bundle.uses_existing_entrypoint:
        errors.append("bundle must include a repair/trigger entrypoint or set uses_existing_entrypoint: true")
    if len(entrypoints) > 1:
        warnings.append(f"bundle has multiple entrypoints: {[item.spec.id for item in entrypoints]}")
    if not hints:
        warnings.append("bundle contains no recovery_hint skills; this may be another single-repair attempt")

    return BundleCheckReport(
        ok=not errors,
        bundle_id=bundle.bundle_id,
        errors=errors,
        warnings=warnings,
        entrypoint_skill_ids=[item.spec.id for item in entrypoints],
        hint_skill_ids=[item.spec.id for item in hints],
        per_skill=per_skill,
    )
