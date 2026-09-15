"""Skill-pack local geometry-profile expansion.

Geometry profiles keep benchmark-specific virtual surface parameters out of
skill Markdown files. Runtime expands a named profile into the legacy
``recovery_hints.params.geometry_hints`` and optional executor mappings before
the planner/executor see them.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from .adapter_discovery import infer_pack_code_adapter_path
from .schema import SkillSchemaError, load_index


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - covered by schema tests elsewhere.
        raise SkillSchemaError("PyYAML is required to parse geometry profile registries") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SkillSchemaError(f"geometry profile registry must be a mapping: {path}")
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
    rel = str(data.get("geometry_profile_registry") or "").strip()
    if rel:
        candidate = Path(rel)
        return candidate if _is_abs(candidate) else index.parent / candidate
    inferred = index.parent.parent / "profiles" / "geometry.yaml"
    return inferred if inferred.exists() else None


def _adapter_paths(
    adapter_path: str | Path | None,
    *,
    index_path: str | Path | None = None,
) -> list[Path]:
    paths: list[Path] = []
    if adapter_path not in (None, ""):
        paths.append(Path(adapter_path))
    if index_path not in (None, ""):
        index = Path(index_path)
        data = load_index(index)
        raw = str(data.get("geometry_profile_adapter") or "").strip()
        if raw:
            candidate = Path(raw)
            paths.append(candidate if _is_abs(candidate) else index.parent / candidate)
        inferred = infer_pack_code_adapter_path(index, "geometry_profiles.py")
        if inferred is not None:
            paths.append(inferred)
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _deep_merge(defaults: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(defaults))
    for key, value in dict(overrides).items():
        if isinstance(merged.get(key), Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


@dataclass(frozen=True)
class GeometryProfileAdapter:
    name: str
    path: str
    profile_ids: frozenset[str]
    module: ModuleType

    def normalize_params(self, profile: str, params: Mapping[str, Any]) -> dict[str, Any]:
        fn = getattr(self.module, "normalize_geometry_profile_params")
        out = dict(fn(profile, copy.deepcopy(dict(params))))
        hints = out.get("geometry_hints")
        if isinstance(hints, Mapping):
            hints = copy.deepcopy(dict(hints))
            out["geometry_hints"] = hints
            for key in ("placement_region", "movable_support_surface"):
                slot = hints.get(key)
                if not isinstance(slot, Mapping):
                    continue
                slot = copy.deepcopy(dict(slot))
                slot.setdefault("geometry_profile_adapter_path", self.path)
                hints[key] = slot
        return out


@dataclass(frozen=True)
class GeometryProfileRegistry:
    name: str
    path: str = ""
    enabled: bool = False
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    adapters: tuple[GeometryProfileAdapter, ...] = ()

    @classmethod
    def disabled(cls) -> "GeometryProfileRegistry":
        return cls(name="disabled_geometry_profiles", enabled=False)

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "enabled": self.enabled,
            "profiles": sorted(self.profiles),
            "adapters": [
                {"name": adapter.name, "path": adapter.path, "profiles": sorted(adapter.profile_ids)}
                for adapter in self.adapters
            ],
        }

    def adapter_for(self, profile: str) -> GeometryProfileAdapter | None:
        for adapter in self.adapters:
            if profile in adapter.profile_ids:
                return adapter
        return None

    def expand_recovery_hints(self, recovery_hints: Mapping[str, Any] | None) -> dict[str, Any]:
        hints = copy.deepcopy(dict(recovery_hints or {}))
        params = hints.get("params")
        if params is None:
            return hints
        if not isinstance(params, Mapping):
            raise SkillSchemaError("recovery_hints.params must be a mapping before geometry profile expansion")
        params = copy.deepcopy(dict(params))
        raw_profile = str(params.get("geometry_profile") or "").strip()
        if not raw_profile:
            hints["params"] = params
            return hints
        if not self.enabled:
            return hints
        profile = self.profiles.get(raw_profile)
        if profile is None:
            raise SkillSchemaError(f"unknown geometry_profile: {raw_profile}")
        profile_params = profile.get("params")
        if profile_params is None:
            profile_params = {}
        if not isinstance(profile_params, Mapping):
            raise SkillSchemaError(f"geometry_profile {raw_profile} params must be a mapping")
        params = _deep_merge(profile_params, params)
        adapter = self.adapter_for(raw_profile)
        if adapter is not None:
            params = adapter.normalize_params(raw_profile, params)
        hints["params"] = params
        return hints


_ADAPTER_CACHE: dict[str, GeometryProfileAdapter] = {}


def load_geometry_profile_adapter(path: str | Path) -> GeometryProfileAdapter:
    resolved = Path(path).resolve()
    cache_key = str(resolved)
    cached = _ADAPTER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if not resolved.exists():
        raise SkillSchemaError(f"geometry profile adapter does not exist: {resolved}")
    module_name = f"_libero_geometry_profile_adapter_{abs(hash(cache_key))}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise SkillSchemaError(f"cannot load geometry profile adapter: {resolved}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    profile_ids = frozenset(str(item).strip() for item in getattr(module, "PROFILE_IDS", ()) if str(item).strip())
    if not profile_ids:
        raise SkillSchemaError(f"geometry profile adapter must expose non-empty PROFILE_IDS: {resolved}")
    if not callable(getattr(module, "normalize_geometry_profile_params", None)):
        raise SkillSchemaError(f"geometry profile adapter missing callable normalize_geometry_profile_params: {resolved}")
    adapter = GeometryProfileAdapter(
        name=str(getattr(module, "ADAPTER_NAME", resolved.stem)),
        path=str(resolved),
        profile_ids=profile_ids,
        module=module,
    )
    _ADAPTER_CACHE[cache_key] = adapter
    return adapter


def load_geometry_profile_registry(
    path: str | Path | None = None,
    *,
    adapter_path: str | Path | None = None,
    index_path: str | Path | None = None,
) -> GeometryProfileRegistry:
    registry_path = _resolve_registry_path(path, index_path=index_path)
    if registry_path is None:
        adapter_paths = _adapter_paths(adapter_path, index_path=index_path)
        if not adapter_paths:
            return GeometryProfileRegistry.disabled()
        # A pack may ship geometry code without a profile catalog yet.  Keep the
        # adapter loaded so a profile reference fails loudly instead of being
        # silently skipped by the disabled registry.
        return GeometryProfileRegistry(
            name="geometry_profile_adapter_registry",
            enabled=True,
            adapters=tuple(load_geometry_profile_adapter(item) for item in adapter_paths),
        )
    registry_path = registry_path.resolve()
    if not registry_path.exists():
        raise SkillSchemaError(f"geometry profile registry does not exist: {registry_path}")
    data = _load_yaml(registry_path)
    raw_profiles = data.get("profiles") or {}
    if not isinstance(raw_profiles, Mapping):
        raise SkillSchemaError(f"geometry profile registry profiles must be a mapping: {registry_path}")
    profiles: dict[str, dict[str, Any]] = {}
    for name, value in raw_profiles.items():
        profile_name = str(name).strip()
        if not profile_name:
            raise SkillSchemaError(f"geometry profile registry has an empty profile name: {registry_path}")
        if not isinstance(value, Mapping):
            raise SkillSchemaError(f"geometry profile {profile_name} must be a mapping")
        profiles[profile_name] = copy.deepcopy(dict(value))
    adapters = tuple(load_geometry_profile_adapter(path) for path in _adapter_paths(adapter_path, index_path=index_path))
    return GeometryProfileRegistry(
        name=str(data.get("name") or registry_path.stem),
        path=str(registry_path),
        enabled=True,
        profiles=profiles,
        adapters=adapters,
    )
