"""Skill-pack local repair-profile expansion.

Repair profiles keep recovery-entry executor parameter bundles out of repair
skill Markdown files. Runtime expands a named profile into the legacy
``recovery_hints.params.executor`` mapping before the executor sees it.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .schema import SkillSchemaError, load_index


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - covered by schema tests elsewhere.
        raise SkillSchemaError("PyYAML is required to parse repair profile registries") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SkillSchemaError(f"repair profile registry must be a mapping: {path}")
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
    rel = str(data.get("repair_profile_registry") or "").strip()
    if rel:
        candidate = Path(rel)
        return candidate if _is_abs(candidate) else index.parent / candidate
    inferred = index.parent.parent / "profiles" / "repair.yaml"
    return inferred if inferred.exists() else None


def _deep_merge(defaults: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(defaults))
    for key, value in dict(overrides).items():
        if isinstance(merged.get(key), Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


@dataclass(frozen=True)
class RepairProfileRegistry:
    name: str
    path: str = ""
    enabled: bool = False
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def disabled(cls) -> "RepairProfileRegistry":
        return cls(name="disabled_repair_profiles", enabled=False)

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
            raise SkillSchemaError("recovery_hints.params must be a mapping before repair profile expansion")
        params = copy.deepcopy(dict(params))
        raw_profile = str(params.get("repair_profile") or "").strip()
        if not raw_profile:
            hints["params"] = params
            return hints
        if not self.enabled:
            return hints
        profile = self.profiles.get(raw_profile)
        if profile is None:
            raise SkillSchemaError(f"unknown repair_profile: {raw_profile}")
        executor = profile.get("executor")
        if not isinstance(executor, Mapping):
            raise SkillSchemaError(f"repair_profile {raw_profile} must define an executor mapping")
        explicit_executor = params.get("executor")
        if explicit_executor is None:
            explicit_executor = {}
        if not isinstance(explicit_executor, Mapping):
            raise SkillSchemaError("recovery_hints.params.executor must be a mapping")
        params["executor"] = _deep_merge(executor, explicit_executor)
        hints["params"] = params
        return hints


def load_repair_profile_registry(
    path: str | Path | None = None,
    *,
    index_path: str | Path | None = None,
) -> RepairProfileRegistry:
    registry_path = _resolve_registry_path(path, index_path=index_path)
    if registry_path is None:
        return RepairProfileRegistry.disabled()
    registry_path = registry_path.resolve()
    if not registry_path.exists():
        raise SkillSchemaError(f"repair profile registry does not exist: {registry_path}")
    data = _load_yaml(registry_path)
    raw_profiles = data.get("profiles") or {}
    if not isinstance(raw_profiles, Mapping):
        raise SkillSchemaError(f"repair profile registry profiles must be a mapping: {registry_path}")
    profiles: dict[str, dict[str, Any]] = {}
    for name, value in raw_profiles.items():
        profile_name = str(name).strip()
        if not profile_name:
            raise SkillSchemaError(f"repair profile registry has an empty profile name: {registry_path}")
        if not isinstance(value, Mapping):
            raise SkillSchemaError(f"repair profile {profile_name} must be a mapping")
        profiles[profile_name] = copy.deepcopy(dict(value))
    return RepairProfileRegistry(
        name=str(data.get("name") or registry_path.stem),
        path=str(registry_path),
        enabled=True,
        profiles=profiles,
    )
