"""Static language + MuJoCo task-binding skills.

This lane is deliberately separate from recovery trigger/hint skills.  A
binding skill selects a reusable profile from task language and scene topology;
the profile then resolves concrete object/site instances after reset.  Neither
the skill nor the profile may contain BDDL goal data or snapshot coordinates.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .matcher import eval_applies_to
from .predicate_registry import PredicateRegistry, load_predicate_registry
from .schema import SkillSchemaError, SkillSpec, load_index, resolve_task_binding_skills


FAILURE_PROFILE = "language_binding_skill_profile_error"
FAILURE_CONFLICT = "language_binding_skill_conflict"
FAILURE_AMBIGUOUS = "language_binding_skill_ambiguous"
ALLOWED_RELATIONS = frozenset({"on", "inside"})
_INSTANCE_LITERAL_RE = re.compile(r"(?:^|[^a-z0-9])[_a-z]+_\d+(?:_main)?(?:$|[^a-z0-9])", re.I)
_FORBIDDEN_WORDS = ("bddl", "absolute_xyz", "target_xyz", "goal_xyz")


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SkillSchemaError("PyYAML is required to parse task-binding profiles") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, Mapping):
        raise SkillSchemaError(f"task-binding profile registry must be a mapping: {path}")
    return dict(data)


def _matches(value: str, pattern: Any) -> bool:
    if isinstance(pattern, (list, tuple, set)):
        return any(_matches(value, item) for item in pattern)
    text = str(value or "")
    raw = str(pattern or "")
    try:
        if re.search(raw, text, flags=re.I):
            return True
    except re.error:
        pass
    return fnmatchcase(text.lower(), raw.lower())


def _walk_values(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        out: list[str] = []
        for key, item in value.items():
            out.append(str(key))
            out.extend(_walk_values(item))
        return out
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            out.extend(_walk_values(item))
        return out
    return [str(value)]


def _validate_profile(name: str, profile: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"target_selector", "goal_selector", "relation", "goal_site_selector"}
    extra = sorted(set(profile) - allowed)
    if extra:
        raise SkillSchemaError(f"task_binding profile {name} has unknown keys: {extra}")
    for selector_key in ("target_selector", "goal_selector"):
        selector = profile.get(selector_key) or {}
        if not isinstance(selector, Mapping):
            raise SkillSchemaError(f"task_binding profile {name} {selector_key} must be a mapping")
        selector_extra = sorted(set(selector) - {"source", "category_matches", "name_matches", "require_unique"})
        if selector_extra:
            raise SkillSchemaError(f"task_binding profile {name} {selector_key} has unknown keys: {selector_extra}")
        source = str(selector.get("source") or "language")
        if source not in {"language", "scene"}:
            raise SkillSchemaError(f"task_binding profile {name} {selector_key}.source must be language or scene")
        if source == "scene" and not (selector.get("category_matches") or selector.get("name_matches")):
            raise SkillSchemaError(f"task_binding profile {name} scene selector requires a category/name matcher")
    site = profile.get("goal_site_selector") or {}
    if not isinstance(site, Mapping):
        raise SkillSchemaError(f"task_binding profile {name} goal_site_selector must be a mapping")
    site_extra = sorted(set(site) - {"name_matches", "required"})
    if site_extra:
        raise SkillSchemaError(f"task_binding profile {name} goal_site_selector has unknown keys: {site_extra}")
    if site and not site.get("name_matches"):
        raise SkillSchemaError(f"task_binding profile {name} goal_site_selector requires name_matches")
    raw_relation = profile.get("relation")
    relation = "on" if raw_relation is True else str(raw_relation or "")
    if relation and relation not in ALLOWED_RELATIONS:
        raise SkillSchemaError(f"task_binding profile {name} has unsupported relation: {relation}")
    dumped = " ".join(_walk_values(profile)).lower()
    if any(word in dumped for word in _FORBIDDEN_WORDS):
        raise SkillSchemaError(f"task_binding profile {name} contains forbidden BDDL/coordinate data")
    if _INSTANCE_LITERAL_RE.search(dumped):
        raise SkillSchemaError(f"task_binding profile {name} must not hard-code a concrete instance")
    normalized = copy.deepcopy(dict(profile))
    if relation:
        normalized["relation"] = relation
    return normalized


@dataclass(frozen=True)
class TaskBindingProfileRegistry:
    name: str
    path: str = ""
    enabled: bool = False
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def disabled(cls) -> "TaskBindingProfileRegistry":
        return cls(name="disabled_task_binding_profiles")

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, "path": self.path, "enabled": self.enabled, "profiles": sorted(self.profiles)}


def _registry_path(path: str | Path | None, index_path: str | Path | None) -> Path | None:
    if path:
        return Path(path)
    if not index_path:
        return None
    index = Path(index_path)
    data = load_index(index)
    raw = str(data.get("task_binding_profile_registry") or "").strip()
    if raw:
        candidate = Path(raw)
        return candidate if candidate.is_absolute() or candidate.drive else index.parent / candidate
    inferred = index.parent.parent / "profiles" / "task_binding.yaml"
    return inferred if inferred.exists() else None


def load_task_binding_profile_registry(
    path: str | Path | None = None,
    *,
    index_path: str | Path | None = None,
) -> TaskBindingProfileRegistry:
    resolved = _registry_path(path, index_path)
    if resolved is None:
        return TaskBindingProfileRegistry.disabled()
    resolved = resolved.resolve()
    if not resolved.exists():
        raise SkillSchemaError(f"task-binding profile registry does not exist: {resolved}")
    data = _load_yaml(resolved)
    raw_profiles = data.get("profiles") or {}
    if not isinstance(raw_profiles, Mapping):
        raise SkillSchemaError(f"task-binding profiles must be a mapping: {resolved}")
    profiles = {
        str(name): _validate_profile(str(name), value)
        for name, value in raw_profiles.items()
        if isinstance(value, Mapping)
    }
    if len(profiles) != len(raw_profiles):
        raise SkillSchemaError(f"every task-binding profile must be a mapping: {resolved}")
    return TaskBindingProfileRegistry(
        name=str(data.get("name") or resolved.stem),
        path=str(resolved),
        enabled=True,
        profiles=profiles,
    )


def _scene_state(language: str, scene: Any) -> dict[str, Any]:
    object_names = sorted(str(name) for name in (getattr(scene, "objects", {}) or {}))
    site_names: list[str] = []
    for obj in (getattr(scene, "objects", {}) or {}).values():
        geometry = getattr(obj, "geometry", {}) or {}
        for site in geometry.get("sites") or []:
            if isinstance(site, Mapping) and site.get("name"):
                site_names.append(str(site["name"]))
    return {
        "task_description": str(language or ""),
        "language": str(language or ""),
        "scene_object_names": object_names,
        "scene_site_names": sorted(set(site_names)),
        "scene_joint_names": sorted(str(name) for name in (getattr(scene, "joints", {}) or {})),
    }


def _categories_and_instances(scene: Any, selector: Mapping[str, Any]) -> list[str]:
    from experiments.robot.libero.tiptop_repro.language_mujoco_goals import _scene_categories

    categories = _scene_categories(scene)
    selected: list[str] = []
    for category, names in categories.items():
        if selector.get("category_matches") and not _matches(category, selector["category_matches"]):
            continue
        for name in names:
            if selector.get("name_matches") and not _matches(name, selector["name_matches"]):
                continue
            selected.append(name)
    return sorted(set(selected))


def _select_object(
    scene: Any,
    selector: Mapping[str, Any],
    parsed_selector: Mapping[str, Any] | None,
    *,
    target: bool,
    evidence: dict[str, Any],
) -> tuple[str | None, str | None]:
    from experiments.robot.libero.tiptop_repro.language_mujoco_goals import (
        _bind_target,
        _match_categories,
        _instances,
        _scene_categories,
    )

    candidates: list[str]
    source = str(selector.get("source") or "language")
    if source == "language" and parsed_selector:
        if target:
            bound, reason = _bind_target(scene, _scene_categories(scene), dict(parsed_selector), evidence)
            if bound is not None:
                candidates = [bound]
            else:
                return None, reason or FAILURE_AMBIGUOUS
        else:
            found = _match_categories(_scene_categories(scene), parsed_selector.get("tokens") or [])
            candidates = _instances(_scene_categories(scene), found)
    else:
        candidates = _categories_and_instances(scene, selector)
    if selector.get("category_matches") or selector.get("name_matches"):
        allowed = set(_categories_and_instances(scene, selector))
        candidates = [name for name in candidates if name in allowed]
    evidence["target_candidates" if target else "goal_candidates"] = list(candidates)
    if len(candidates) != 1:
        return None, FAILURE_AMBIGUOUS
    return candidates[0], None


def _select_site(scene: Any, goal: str, selector: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    obj = (getattr(scene, "objects", {}) or {}).get(goal)
    geometry = getattr(obj, "geometry", {}) or {}
    sites = sorted(
        str(site.get("name"))
        for site in geometry.get("sites") or []
        if isinstance(site, Mapping) and site.get("name") and _matches(str(site.get("name")), selector.get("name_matches"))
    )
    return (sites[0] if len(sites) == 1 else None), sites


def _failure(language: str, reason: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {
        "target": None,
        "goal": None,
        "obj_of_interest": [],
        "goal_atoms": [],
        "goal_surfaces": [],
        "init_atoms": [],
        "regions": {},
        "language": language,
        "source": "language_mujoco_skill",
        "failure_reason": reason,
        "failure_detail": detail,
        **extra,
    }


@dataclass
class TaskBindingResolver:
    skills: Sequence[SkillSpec]
    profiles: TaskBindingProfileRegistry
    predicate_registry: PredicateRegistry = field(default_factory=PredicateRegistry.builtins)

    @property
    def enabled(self) -> bool:
        return bool(self.skills)

    def summary(self) -> dict[str, Any]:
        return {"skills": [skill.id for skill in self.skills], "profiles": self.profiles.summary()}

    def _resolve_one(self, skill: SkillSpec, language: str, scene: Any) -> dict[str, Any]:
        from experiments.robot.libero.tiptop_repro.language_mujoco_goals import _parse_language

        profile = self.profiles.profiles.get(skill.task_binding_profile)
        if profile is None:
            return _failure(language, FAILURE_PROFILE, f"unknown profile {skill.task_binding_profile!r}", binding_skill=skill.id)
        parsed, parse_reason = _parse_language(language)
        if parsed is None:
            return _failure(language, parse_reason or FAILURE_PROFILE, "language could not be parsed", binding_skill=skill.id)
        evidence: dict[str, Any] = {"binding_skill": skill.id, "binding_profile": skill.task_binding_profile}
        target, reason = _select_object(
            scene,
            profile.get("target_selector") or {},
            parsed.get("target"),
            target=True,
            evidence=evidence,
        )
        if target is None:
            return _failure(language, reason or FAILURE_AMBIGUOUS, "target selector did not resolve uniquely", binding_evidence=evidence, binding_skill=skill.id)
        goal, reason = _select_object(
            scene,
            profile.get("goal_selector") or {},
            parsed.get("goal"),
            target=False,
            evidence=evidence,
        )
        if goal is None or goal == target:
            return _failure(language, reason or FAILURE_AMBIGUOUS, "goal selector did not resolve uniquely", binding_evidence=evidence, binding_skill=skill.id)
        relation = str(profile.get("relation") or parsed.get("goal", {}).get("relation") or "")
        if relation not in ALLOWED_RELATIONS:
            return _failure(language, FAILURE_PROFILE, f"unsupported relation {relation!r}", binding_evidence=evidence, binding_skill=skill.id)
        surface = goal
        site_selector = profile.get("goal_site_selector") or {}
        if site_selector:
            selected_site, candidates = _select_site(scene, goal, site_selector)
            evidence["goal_site_candidates"] = candidates
            if selected_site is None:
                return _failure(language, FAILURE_AMBIGUOUS, "goal site selector did not resolve uniquely", binding_evidence=evidence, binding_skill=skill.id)
            surface = selected_site
            evidence["goal_fixture"] = goal
            evidence["goal_site"] = surface
        atom = {"predicate": relation, "args": [target, surface]}
        return {
            "target": target,
            "goal": surface,
            "obj_of_interest": [target, goal],
            "goal_atoms": [atom],
            "goal_surfaces": [surface],
            "init_atoms": [],
            "regions": {},
            "language": language,
            "source": "language_mujoco_skill",
            "failure_reason": None,
            "parsed_language": parsed,
            "binding_evidence": evidence,
            "binding_skill": skill.id,
            "binding_profile": skill.task_binding_profile,
        }

    def resolve(self, language: str, scene: Any) -> dict[str, Any] | None:
        state = _scene_state(language, scene)
        matches = [
            skill
            for skill in self.skills
            if eval_applies_to(skill.applies_to, state, predicate_registry=self.predicate_registry)
        ]
        if not matches:
            return None
        results = [self._resolve_one(skill, str(language or ""), scene) for skill in matches]
        failures = [result for result in results if result.get("failure_reason")]
        if failures:
            detail = "; ".join(f"{result.get('binding_skill')}: {result.get('failure_detail')}" for result in failures)
            return _failure(
                str(language or ""),
                str(failures[0].get("failure_reason") or FAILURE_PROFILE),
                detail,
                binding_skill_matches=[skill.id for skill in matches],
            )
        signatures = {
            (
                str(result.get("target")),
                str(result.get("goal")),
                str((result.get("goal_atoms") or [{}])[0].get("predicate")),
            )
            for result in results
        }
        if len(signatures) != 1:
            return _failure(
                str(language or ""),
                FAILURE_CONFLICT,
                "matching task-binding skills produced different bindings",
                binding_skill_matches=[skill.id for skill in matches],
            )
        winner = dict(results[0])
        winner["binding_skill_matches"] = [skill.id for skill in matches]
        return winner


def load_task_binding_resolver(
    index_path: str | Path,
    *,
    mining: bool = False,
    predicate_registry: PredicateRegistry | None = None,
) -> TaskBindingResolver:
    predicates = predicate_registry or load_predicate_registry(index_path=index_path)
    skills = resolve_task_binding_skills(index_path, mining=mining, predicate_registry=predicates)
    profiles = load_task_binding_profile_registry(index_path=index_path)
    if skills and not profiles.enabled:
        raise SkillSchemaError("task-binding skills require task_binding_profile_registry")
    return TaskBindingResolver(skills=skills, profiles=profiles, predicate_registry=predicates)


def scene_from_context(context: Mapping[str, Any]) -> Any:
    """Rebuild the small duck-typed scene needed for offline context replay."""

    from types import SimpleNamespace

    scene_data = context.get("scene") or {}
    objects: dict[str, Any] = {}
    for raw in scene_data.get("objects") or []:
        if not isinstance(raw, Mapping) or not raw.get("name"):
            continue
        name = str(raw["name"])
        objects[name] = SimpleNamespace(
            name=name,
            pos=np.asarray(raw.get("pos") or [0.0, 0.0, 0.0], dtype=np.float64),
            quat=np.asarray(raw.get("quat") or [1.0, 0.0, 0.0, 0.0], dtype=np.float64),
            geometry={"sites": copy.deepcopy(list(raw.get("sites") or [])), "geoms": copy.deepcopy(list(raw.get("geoms") or []))},
        )
    joints = {
        str(raw["name"]): SimpleNamespace(
            name=str(raw["name"]),
            qpos=float(raw.get("qpos") or 0.0),
            qvel=float(raw.get("qvel") or 0.0),
        )
        for raw in scene_data.get("articulated_joints") or []
        if isinstance(raw, Mapping) and raw.get("name")
    }
    return SimpleNamespace(objects=objects, joints=joints)
