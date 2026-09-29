"""Skill-pack local articulation-profile expansion.

Articulation skills select a named, evidence-backed handle grasp and execution
policy.  The profile owns task-independent MuJoCo binding data and controller
parameters; the skill owns only the declarative context in which that profile
should be selected.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from experiments.robot.libero.tiptop_repro.articulation import transform

from .schema import SkillSchemaError, load_index


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SkillSchemaError("PyYAML is required to parse articulation profile registries") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SkillSchemaError(f"articulation profile registry must be a mapping: {path}")
    return data


def _is_abs(path: Path) -> bool:
    return path.is_absolute() or bool(path.drive)


def _resolve_registry_path(
    path: str | Path | None = None,
    *,
    index_path: str | Path | None = None,
) -> Path | None:
    if path:
        return Path(path)
    if not index_path:
        return None
    index = Path(index_path)
    data = load_index(index)
    rel = str(data.get("articulation_profile_registry") or "").strip()
    if rel:
        candidate = Path(rel)
        return candidate if _is_abs(candidate) else index.parent / candidate
    inferred = index.parent.parent / "profiles" / "articulation.yaml"
    return inferred if inferred.exists() else None


def _deep_merge(defaults: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(defaults))
    for key, value in dict(overrides).items():
        if isinstance(merged.get(key), Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _validate_articulation_options(profile_name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SkillSchemaError(f"articulation_profile {profile_name} articulation must be a mapping")
    options = copy.deepcopy(dict(value))
    if not options.get("enabled"):
        raise SkillSchemaError(f"articulation_profile {profile_name} must set articulation.enabled=true")
    bindings = options.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise SkillSchemaError(f"articulation_profile {profile_name} requires non-empty bindings")
    for binding_index, binding in enumerate(bindings):
        if not isinstance(binding, Mapping):
            raise SkillSchemaError(
                f"articulation_profile {profile_name} binding {binding_index} must be a mapping"
            )
        for key in ("part_id", "joint_name", "open_range", "closed_range", "target_source"):
            if binding.get(key) in (None, "", []):
                raise SkillSchemaError(
                    f"articulation_profile {profile_name} binding {binding_index} missing {key}"
                )
        grasps = binding.get("grasps")
        grasp_profiles = binding.get("grasp_profiles")
        if not isinstance(grasps, list) or not grasps:
            raise SkillSchemaError(
                f"articulation_profile {profile_name} binding {binding_index} requires grasps"
            )
        if not isinstance(grasp_profiles, list) or len(grasp_profiles) != len(grasps):
            raise SkillSchemaError(
                f"articulation_profile {profile_name} binding {binding_index} grasp/profile count mismatch"
            )
        try:
            for grasp in grasps:
                transform(grasp)
        except Exception as exc:
            raise SkillSchemaError(
                f"articulation_profile {profile_name} binding {binding_index} has invalid grasp: {exc}"
            ) from exc
        for grasp_profile in grasp_profiles:
            if not isinstance(grasp_profile, Mapping) or not str(grasp_profile.get("id") or "").strip():
                raise SkillSchemaError(
                    f"articulation_profile {profile_name} binding {binding_index} has unnamed grasp profile"
                )
    return options


@dataclass(frozen=True)
class ArticulationProfileRegistry:
    name: str
    path: str = ""
    enabled: bool = False
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def disabled(cls) -> "ArticulationProfileRegistry":
        return cls(name="disabled_articulation_profiles", enabled=False)

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "enabled": self.enabled,
            "profiles": sorted(self.profiles),
        }

    def expand_recovery_hints(self, recovery_hints: Mapping[str, Any] | None) -> dict[str, Any]:
        hints = copy.deepcopy(dict(recovery_hints or {}))
        params = hints.get("params")
        if params is None:
            return hints
        if not isinstance(params, Mapping):
            raise SkillSchemaError(
                "recovery_hints.params must be a mapping before articulation profile expansion"
            )
        params = copy.deepcopy(dict(params))
        profile_name = str(params.get("articulation_profile") or "").strip()
        if not profile_name:
            hints["params"] = params
            return hints
        if not self.enabled:
            return hints
        profile = self.profiles.get(profile_name)
        if profile is None:
            raise SkillSchemaError(f"unknown articulation_profile: {profile_name}")
        explicit = params.get("articulation") or {}
        if not isinstance(explicit, Mapping):
            raise SkillSchemaError("recovery_hints.params.articulation must be a mapping")
        params["articulation"] = _deep_merge(profile["articulation"], explicit)
        params["articulation_profile"] = profile_name
        hints["params"] = params
        return hints


def load_articulation_profile_registry(
    path: str | Path | None = None,
    *,
    index_path: str | Path | None = None,
) -> ArticulationProfileRegistry:
    registry_path = _resolve_registry_path(path, index_path=index_path)
    if registry_path is None:
        return ArticulationProfileRegistry.disabled()
    registry_path = registry_path.resolve()
    if not registry_path.exists():
        raise SkillSchemaError(f"articulation profile registry does not exist: {registry_path}")
    data = _load_yaml(registry_path)
    raw_profiles = data.get("profiles") or {}
    if not isinstance(raw_profiles, Mapping):
        raise SkillSchemaError(
            f"articulation profile registry profiles must be a mapping: {registry_path}"
        )
    profiles: dict[str, dict[str, Any]] = {}
    for name, value in raw_profiles.items():
        profile_name = str(name).strip()
        if not profile_name or not isinstance(value, Mapping):
            raise SkillSchemaError(f"invalid articulation profile entry: {name!r}")
        profiles[profile_name] = {
            "articulation": _validate_articulation_options(
                profile_name,
                value.get("articulation"),
            )
        }
    return ArticulationProfileRegistry(
        name=str(data.get("name") or registry_path.stem),
        path=str(registry_path),
        enabled=True,
        profiles=profiles,
    )
