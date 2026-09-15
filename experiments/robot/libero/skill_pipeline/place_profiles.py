"""Skill-pack local place-profile expansion.

Place profiles keep task-specific executor parameter bundles out of skill
Markdown files. Runtime expands a named profile into generic place-policy
hooks, then bridges those hooks into the legacy
``recovery_hints.params.executor`` mapping before the executor sees it.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from experiments.robot.libero.tiptop_repro.engine_capabilities import SUPPORTED_EXECUTOR_OPTION_KEYS

from .adapter_discovery import infer_pack_code_adapter_path
from .schema import SkillSchemaError, load_index


PLACE_POLICY_HOOKS = ("hover", "align", "release")

_HOOK_FUNCTIONS = {
    "hover": ("resolve_hover_policy", "resolve_place_hover_policy"),
    "align": ("resolve_align_policy", "resolve_place_align_policy"),
    "release": ("resolve_release_policy", "resolve_place_release_policy"),
}

_HOOK_META_KEYS = frozenset({"mode", "type", "description", "enabled", "executor", "notes"})

_HOVER_EXECUTOR_KEYS = frozenset(
    {
        "held_transfer_keep_z",
        "held_transfer_z_margin_m",
        "held_transfer_max_descent_m",
        "held_transfer_max_steps",
        "held_transfer_reached_m",
        "place_hover_clearance_m",
        "place_hover_max_steps",
        "place_hover_reached_m",
        "place_lift_min_clearance_m",
        "place_lift_max_steps",
        "place_lift_reached_m",
    }
)

_ALIGN_EXECUTOR_KEYS = frozenset(
    {
        "place_held_object_xy_align",
        "place_align_reached_m",
        "place_align_center_tolerance_m",
        "place_footprint_release_tolerance_m",
        "place_align_step_clip_m",
        "place_align_max_iters",
        "place_align_max_steps_per_iter",
        "place_align_retry_lift_m",
        "place_align_retry_lift_max_steps",
    }
)

_RELEASE_EXECUTOR_KEYS = frozenset(
    {
        "place_drop_closed_loop_align",
        "place_drop_align_slices",
        "place_drop_max_steps",
        "place_drop_reached_m",
        "place_drop_align_xy_m",
        "place_release_xy_m",
        "place_release_xy_min_m",
        "place_release_margin_m",
        "place_release_z_max_m",
        "place_open_dwell_steps",
        "place_retreat_m",
        "place_retreat_max_steps",
    }
)

_HOOK_EXECUTOR_KEYS = {
    "hover": _HOVER_EXECUTOR_KEYS,
    "align": _ALIGN_EXECUTOR_KEYS,
    "release": _RELEASE_EXECUTOR_KEYS,
}

_HOOK_MODE_DEFAULTS = {
    ("hover", "held_transfer_keep_z"): {"held_transfer_keep_z": True},
    ("align", "held_object_xy_align"): {"place_held_object_xy_align": True},
    ("release", "closed_loop_drop"): {"place_drop_closed_loop_align": True},
}
_HOOK_MODE_DEFAULT_NAMES = frozenset(mode for _, mode in _HOOK_MODE_DEFAULTS)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - covered by schema tests elsewhere.
        raise SkillSchemaError("PyYAML is required to parse place profile registries") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SkillSchemaError(f"place profile registry must be a mapping: {path}")
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
    rel = str(data.get("place_profile_registry") or "").strip()
    if rel:
        candidate = Path(rel)
        return candidate if _is_abs(candidate) else index.parent / candidate
    inferred = index.parent.parent / "profiles" / "place.yaml"
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
        raw = str(data.get("place_policy_adapter") or data.get("place_profile_adapter") or "").strip()
        if raw:
            candidate = Path(raw)
            paths.append(candidate if _is_abs(candidate) else index.parent / candidate)
        inferred = infer_pack_code_adapter_path(index, "place_policies.py")
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


def _mapping_or_empty(value: Any, *, label: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise SkillSchemaError(f"{label} must be a mapping")
    return copy.deepcopy(dict(value))


def _normalize_hook_policy(profile: str, hook: str, raw: Any) -> dict[str, Any]:
    if raw in (None, "", False):
        return {}
    if raw is True:
        raw = {"enabled": True}
    if not isinstance(raw, Mapping):
        raise SkillSchemaError(f"place_profile {profile} {hook} hook must be a mapping")
    policy = copy.deepcopy(dict(raw))
    if policy.get("enabled") is False:
        return {}
    mode = str(policy.get("mode") or policy.get("type") or "").strip().lower()
    allowed = _HOOK_EXECUTOR_KEYS[hook]
    unknown = sorted(str(key) for key in policy if str(key) not in _HOOK_META_KEYS and str(key) not in allowed)
    if unknown:
        raise SkillSchemaError(
            f"place_profile {profile} {hook} hook has unsupported key(s): {unknown}"
        )
    executor = policy.get("executor")
    if executor not in (None, ""):
        if not isinstance(executor, Mapping):
            raise SkillSchemaError(f"place_profile {profile} {hook}.executor must be a mapping")
        bad = sorted(str(key) for key in executor if str(key).strip() not in allowed)
        if bad:
            raise SkillSchemaError(
                f"place_profile {profile} {hook}.executor has unsupported key(s): {bad}"
            )
    return policy


def _executor_from_hook_policy(profile: str, hook: str, policy: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_hook_policy(profile, hook, policy)
    if not normalized:
        return {}
    mode = str(normalized.get("mode") or normalized.get("type") or "").strip().lower()
    executor = copy.deepcopy(_HOOK_MODE_DEFAULTS.get((hook, mode), {}))
    for key in _HOOK_EXECUTOR_KEYS[hook]:
        if key in normalized:
            executor[key] = copy.deepcopy(normalized[key])
    nested = normalized.get("executor")
    if isinstance(nested, Mapping):
        executor = _deep_merge(executor, nested)
    if mode and mode != "executor_options" and mode not in _HOOK_MODE_DEFAULT_NAMES and not executor:
        raise SkillSchemaError(
            f"place_profile {profile} {hook} hook mode {mode} produced no executor options"
        )
    bad = sorted(str(key) for key in executor if str(key).strip() not in SUPPORTED_EXECUTOR_OPTION_KEYS)
    if bad:
        raise SkillSchemaError(
            f"place_profile {profile} {hook} hook expands to unsupported executor key(s): {bad}"
        )
    return executor


def _executor_from_place_hooks(profile: str, hooks: Mapping[str, Any]) -> dict[str, Any]:
    executor: dict[str, Any] = {}
    for hook in PLACE_POLICY_HOOKS:
        raw = hooks.get(hook)
        if raw in (None, "", False):
            continue
        executor = _deep_merge(executor, _executor_from_hook_policy(profile, hook, raw))
    return executor


@dataclass(frozen=True)
class PlacePolicyAdapter:
    name: str
    path: str
    profile_ids: frozenset[str]
    module: ModuleType

    def resolve_hooks(
        self,
        profile: str,
        profile_data: Mapping[str, Any],
        params: Mapping[str, Any],
    ) -> dict[str, dict[str, Any]]:
        hooks: dict[str, dict[str, Any]] = {}
        for hook in PLACE_POLICY_HOOKS:
            raw: Any = None
            for fn_name in _HOOK_FUNCTIONS[hook]:
                fn = getattr(self.module, fn_name, None)
                if callable(fn):
                    raw = fn(profile, copy.deepcopy(dict(profile_data)), copy.deepcopy(dict(params)))
                    break
            if raw in (None, "", False):
                continue
            hooks[hook] = _normalize_hook_policy(profile, hook, raw)
        return hooks


@dataclass(frozen=True)
class PlaceProfileRegistry:
    name: str
    path: str = ""
    enabled: bool = False
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    adapters: tuple[PlacePolicyAdapter, ...] = ()

    @classmethod
    def disabled(cls) -> "PlaceProfileRegistry":
        return cls(name="disabled_place_profiles", enabled=False)

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

    def adapter_for(self, profile: str) -> PlacePolicyAdapter | None:
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
            raise SkillSchemaError("recovery_hints.params must be a mapping before place profile expansion")
        params = copy.deepcopy(dict(params))
        raw_profile = str(params.get("place_profile") or "").strip()
        if not raw_profile:
            hints["params"] = params
            return hints
        if not self.enabled:
            return hints
        profile = self.profiles.get(raw_profile)
        if profile is None:
            raise SkillSchemaError(f"unknown place_profile: {raw_profile}")
        profile_params = _mapping_or_empty(profile.get("params"), label=f"place_profile {raw_profile} params")
        explicit_executor = _mapping_or_empty(params.get("executor"), label="recovery_hints.params.executor")
        params = _deep_merge(profile_params, params)

        legacy_executor = _mapping_or_empty(profile.get("executor"), label=f"place_profile {raw_profile} executor")
        raw_hooks = _mapping_or_empty(profile.get("hooks"), label=f"place_profile {raw_profile} hooks")
        adapter = self.adapter_for(raw_profile)
        adapter_hooks = adapter.resolve_hooks(raw_profile, profile, params) if adapter is not None else {}
        hooks = _deep_merge(raw_hooks, adapter_hooks)
        hook_executor = _executor_from_place_hooks(raw_profile, hooks)

        existing_policy = _mapping_or_empty(params.get("place_policy"), label="recovery_hints.params.place_policy")
        place_policy: dict[str, Any] = {
            "profile": raw_profile,
            "hooks": copy.deepcopy(hooks),
        }
        if adapter is not None:
            place_policy["adapter"] = adapter.name
            place_policy["adapter_path"] = adapter.path
        params["place_policy"] = _deep_merge(place_policy, existing_policy)
        params["executor"] = _deep_merge(_deep_merge(legacy_executor, hook_executor), explicit_executor)
        hints["params"] = params
        return hints


_ADAPTER_CACHE: dict[str, PlacePolicyAdapter] = {}


def load_place_policy_adapter(path: str | Path) -> PlacePolicyAdapter:
    resolved = Path(path).resolve()
    cache_key = str(resolved)
    cached = _ADAPTER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if not resolved.exists():
        raise SkillSchemaError(f"place policy adapter does not exist: {resolved}")
    module_name = f"_libero_place_policy_adapter_{abs(hash(cache_key))}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise SkillSchemaError(f"cannot load place policy adapter: {resolved}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    profile_ids = frozenset(str(item).strip() for item in getattr(module, "PROFILE_IDS", ()) if str(item).strip())
    if not profile_ids:
        raise SkillSchemaError(f"place policy adapter must expose non-empty PROFILE_IDS: {resolved}")
    if not any(callable(getattr(module, name, None)) for names in _HOOK_FUNCTIONS.values() for name in names):
        raise SkillSchemaError(
            f"place policy adapter must expose at least one hover/align/release resolver: {resolved}"
        )
    adapter = PlacePolicyAdapter(
        name=str(getattr(module, "ADAPTER_NAME", resolved.stem)),
        path=str(resolved),
        profile_ids=profile_ids,
        module=module,
    )
    _ADAPTER_CACHE[cache_key] = adapter
    return adapter


def load_place_profile_registry(
    path: str | Path | None = None,
    *,
    adapter_path: str | Path | None = None,
    index_path: str | Path | None = None,
) -> PlaceProfileRegistry:
    registry_path = _resolve_registry_path(path, index_path=index_path)
    if registry_path is None:
        adapter_paths = _adapter_paths(adapter_path, index_path=index_path)
        if not adapter_paths:
            return PlaceProfileRegistry.disabled()
        # A pack may ship place-policy code without a profile catalog yet.  Keep
        # the adapter loaded so a profile reference fails loudly instead of being
        # silently skipped by the disabled registry.
        return PlaceProfileRegistry(
            name="place_profile_adapter_registry",
            enabled=True,
            adapters=tuple(load_place_policy_adapter(item) for item in adapter_paths),
        )
    registry_path = registry_path.resolve()
    if not registry_path.exists():
        raise SkillSchemaError(f"place profile registry does not exist: {registry_path}")
    data = _load_yaml(registry_path)
    raw_profiles = data.get("profiles") or {}
    if not isinstance(raw_profiles, Mapping):
        raise SkillSchemaError(f"place profile registry profiles must be a mapping: {registry_path}")
    profiles: dict[str, dict[str, Any]] = {}
    for name, value in raw_profiles.items():
        profile_name = str(name).strip()
        if not profile_name:
            raise SkillSchemaError(f"place profile registry has an empty profile name: {registry_path}")
        if not isinstance(value, Mapping):
            raise SkillSchemaError(f"place profile {profile_name} must be a mapping")
        profiles[profile_name] = copy.deepcopy(dict(value))
    adapters = tuple(load_place_policy_adapter(path) for path in _adapter_paths(adapter_path, index_path=index_path))
    return PlaceProfileRegistry(
        name=str(data.get("name") or registry_path.stem),
        path=str(registry_path),
        enabled=True,
        profiles=profiles,
        adapters=adapters,
    )
