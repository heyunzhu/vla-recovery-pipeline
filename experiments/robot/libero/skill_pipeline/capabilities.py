"""Capability registry for skill-owned recovery hints.

The registry is intentionally lightweight: skills remain declarative, while an
index can say which low-level runner/planner/executor capabilities those
skills are allowed to exercise.  This keeps new skill libraries from silently
depending on old LIBERO-90 helper code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from experiments.robot.libero.tiptop_repro.engine_capabilities import (
    SUPPORTED_EXECUTOR_OPTION_KEYS,
    SUPPORTED_GEOMETRY_DESCRIPTOR_SHAPES,
    SUPPORTED_PLACE_CANDIDATE_POLICIES,
    SUPPORTED_PLACE_YAW_POLICIES,
    SUPPORTED_RELEASE_MODES,
    canonical_geometry_descriptor_shape,
    canonical_geometry_planner_primitive,
    canonical_grounding_planner_primitive,
)
from experiments.robot.libero.tiptop_repro.grasp_profiles import DEFAULT_GRASP_SAMPLER_PROFILE

from .predicate_registry import (
    BUILTIN_APPLIES_PREDICATES,
    BUILTIN_TRIGGER_PREDICATES,
    diagnostic_signal_name,
)
from .schema import SkillSchemaError, SkillSpec, load_index

CAPABILITY_CATEGORIES = (
    "grasp_profiles",
    "place_profiles",
    "repair_profiles",
    "grounding_profiles",
    "geometry_profiles",
    "geometry_hint_keys",
    "geometry_hint_intents",
    "grounding_hint_keys",
    "grounding_hint_intents",
    "executor_options",
    "place_candidate_policies",
    "place_yaw_policies",
    "release_modes",
    "trigger_predicates",
    "applies_to_predicates",
    "diagnostic_signals",
    "geometry_descriptor_shapes",
)

CORE_GRASP_PROFILES = frozenset({"", "default", DEFAULT_GRASP_SAMPLER_PROFILE, "native", "cutamp_native"})


def _validate_engine_supported_declarations(
    capabilities: Mapping[str, frozenset[str]],
    registry_path: Path,
) -> None:
    errors: list[str] = []
    checks = (
        ("executor_options", SUPPORTED_EXECUTOR_OPTION_KEYS),
        ("place_candidate_policies", SUPPORTED_PLACE_CANDIDATE_POLICIES),
        ("place_yaw_policies", SUPPORTED_PLACE_YAW_POLICIES),
        ("release_modes", SUPPORTED_RELEASE_MODES),
        ("geometry_descriptor_shapes", SUPPORTED_GEOMETRY_DESCRIPTOR_SHAPES),
    )
    for category, supported in checks:
        unknown = sorted(value for value in capabilities.get(category, frozenset()) if value not in supported)
        if unknown:
            errors.append(f"{category} not consumed by engine: {unknown}")

    for value in sorted(capabilities.get("geometry_hint_intents", frozenset())):
        if not canonical_geometry_planner_primitive({"intent": value}):
            errors.append(f"geometry_hint_intents not consumed by engine: {value}")

    for value in sorted(capabilities.get("grounding_hint_intents", frozenset())):
        if not canonical_grounding_planner_primitive({"intent": value}):
            errors.append(f"grounding_hint_intents not consumed by engine: {value}")

    if errors:
        raise SkillSchemaError(
            f"capability registry declares unsupported engine capabilities: {registry_path}: "
            + "; ".join(errors)
        )


def _predicate_items(block: Mapping[str, Any] | None) -> list[tuple[str, Any]]:
    if not isinstance(block, Mapping):
        return []
    out: list[tuple[str, Any]] = []
    for group in ("all", "any"):
        values = block.get(group)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, Mapping):
                continue
            out.extend((str(name), expected) for name, expected in item.items())
    return out


def _geometry_descriptor_shape(hint: Mapping[str, Any]) -> str:
    descriptor = hint.get("surface_descriptor")
    raw = ""
    if isinstance(descriptor, Mapping):
        raw = str(
            descriptor.get("shape")
            or descriptor.get("geometry_shape")
            or descriptor.get("descriptor_shape")
            or ""
        )
    raw = raw or str(
        hint.get("surface_descriptor_shape")
        or hint.get("geometry_descriptor_shape")
        or hint.get("descriptor_shape")
        or hint.get("shape")
        or ""
    )
    return canonical_geometry_descriptor_shape(raw)


@dataclass(frozen=True)
class CapabilityAudit:
    registry_name: str
    registry_path: str
    strict: bool
    used: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "registry_name": self.registry_name,
            "registry_path": self.registry_path,
            "strict": self.strict,
            "used": self.used,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class CapabilityRegistry:
    name: str
    path: str = ""
    strict: bool = False
    enabled: bool = False
    capabilities: dict[str, frozenset[str]] = field(default_factory=dict)

    @classmethod
    def allow_all(cls) -> "CapabilityRegistry":
        return cls(
            name="implicit_legacy_allow_all",
            strict=False,
            enabled=False,
            capabilities={key: frozenset() for key in CAPABILITY_CATEGORIES},
        )

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "strict": self.strict,
            "enabled": self.enabled,
            "capabilities": {key: sorted(values) for key, values in self.capabilities.items()},
        }

    def _allowed(self, category: str, value: str) -> bool:
        if not self.enabled or not self.strict:
            return True
        allowed = self.capabilities.get(category, frozenset())
        return value in allowed

    def _record(
        self,
        *,
        used: dict[str, set[str]],
        errors: list[str],
        category: str,
        value: Any,
        label: str | None = None,
    ) -> None:
        text = str(value or "").strip()
        if not text:
            return
        used.setdefault(category, set()).add(text)
        if not self._allowed(category, text):
            errors.append(f"unregistered {category}: {label or text}")

    def audit_recovery_hints(self, recovery_hints: Mapping[str, Any] | None) -> CapabilityAudit:
        used: dict[str, set[str]] = {key: set() for key in CAPABILITY_CATEGORIES}
        errors: list[str] = []
        warnings: list[str] = []
        hints = dict(recovery_hints or {})

        self._record(
            used=used,
            errors=errors,
            category="grasp_profiles",
            value=hints.get("grasp_profile"),
        )

        params = hints.get("params")
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            warnings.append("recovery_hints.params is not a mapping; schema validation should reject this first")
            params = {}

        self._record(
            used=used,
            errors=errors,
            category="place_profiles",
            value=params.get("place_profile"),
        )
        self._record(
            used=used,
            errors=errors,
            category="repair_profiles",
            value=params.get("repair_profile"),
        )
        self._record(
            used=used,
            errors=errors,
            category="grounding_profiles",
            value=params.get("grounding_profile"),
        )
        self._record(
            used=used,
            errors=errors,
            category="geometry_profiles",
            value=params.get("geometry_profile"),
        )

        grounding_hints = params.get("grounding_hints")
        if isinstance(grounding_hints, Mapping):
            for key, value in grounding_hints.items():
                self._record(
                    used=used,
                    errors=errors,
                    category="grounding_hint_keys",
                    value=key,
                )
                if isinstance(value, Mapping):
                    self._record(
                        used=used,
                        errors=errors,
                        category="grounding_hint_intents",
                        value=value.get("intent"),
                        label=f"{key}.intent={value.get('intent')}",
                    )

        geometry_hints = params.get("geometry_hints")
        if isinstance(geometry_hints, Mapping):
            for key, value in geometry_hints.items():
                self._record(
                    used=used,
                    errors=errors,
                    category="geometry_hint_keys",
                    value=key,
                )
                if not isinstance(value, Mapping):
                    continue
                self._record(
                    used=used,
                    errors=errors,
                    category="geometry_hint_intents",
                    value=value.get("intent"),
                    label=f"{key}.intent={value.get('intent')}",
                )
                self._record(
                    used=used,
                    errors=errors,
                    category="place_candidate_policies",
                    value=value.get("place_candidate_policy"),
                    label=f"{key}.place_candidate_policy={value.get('place_candidate_policy')}",
                )
                self._record(
                    used=used,
                    errors=errors,
                    category="place_yaw_policies",
                    value=value.get("place_yaw_policy"),
                    label=f"{key}.place_yaw_policy={value.get('place_yaw_policy')}",
                )
                self._record(
                    used=used,
                    errors=errors,
                    category="release_modes",
                    value=value.get("release_mode"),
                    label=f"{key}.release_mode={value.get('release_mode')}",
                )
                self._record(
                    used=used,
                    errors=errors,
                    category="geometry_descriptor_shapes",
                    value=_geometry_descriptor_shape(value),
                    label=f"{key}.surface_descriptor.shape",
                )

        executor = params.get("executor")
        if isinstance(executor, Mapping):
            for key, value in executor.items():
                self._record(
                    used=used,
                    errors=errors,
                    category="executor_options",
                    value=key,
                )
                if key == "place_yaw_after_hover":
                    self._record(
                        used=used,
                        errors=errors,
                        category="place_yaw_policies",
                        value=value,
                        label=f"executor.place_yaw_after_hover={value}",
                    )

        used_lists = {key: sorted(values) for key, values in used.items() if values}
        return CapabilityAudit(
            registry_name=self.name,
            registry_path=self.path,
            strict=self.strict,
            used=used_lists,
            errors=errors,
            warnings=warnings,
        )

    def audit_skill(self, spec: SkillSpec) -> CapabilityAudit:
        hint_audit = self.audit_recovery_hints(spec.recovery_hints)
        used: dict[str, set[str]] = {key: set(hint_audit.used.get(key, [])) for key in CAPABILITY_CATEGORIES}
        errors = list(hint_audit.errors)
        warnings = list(hint_audit.warnings)

        for name, expected in _predicate_items(spec.trigger):
            if name not in BUILTIN_TRIGGER_PREDICATES:
                self._record(
                    used=used,
                    errors=errors,
                    category="trigger_predicates",
                    value=name,
                )
            if name.startswith("diagnostic_signal_"):
                self._record(
                    used=used,
                    errors=errors,
                    category="diagnostic_signals",
                    value=diagnostic_signal_name(expected),
                    label=f"trigger.{name}",
                )

        for name, expected in _predicate_items(spec.applies_to):
            if name not in BUILTIN_APPLIES_PREDICATES:
                self._record(
                    used=used,
                    errors=errors,
                    category="applies_to_predicates",
                    value=name,
                )
            if name.startswith("diagnostic_signal_"):
                self._record(
                    used=used,
                    errors=errors,
                    category="diagnostic_signals",
                    value=diagnostic_signal_name(expected),
                    label=f"applies_to.{name}",
                )

        used_lists = {key: sorted(values) for key, values in used.items() if values}
        return CapabilityAudit(
            registry_name=self.name,
            registry_path=self.path,
            strict=self.strict,
            used=used_lists,
            errors=errors,
            warnings=warnings,
        )


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise SkillSchemaError("PyYAML is required to parse capability registries") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SkillSchemaError(f"capability registry must be a mapping: {path}")
    return data


def _resolve_registry_path(path: str | Path | None, *, index_path: str | Path | None = None) -> Path | None:
    if path:
        return Path(path)
    if not index_path:
        return None
    index_data = load_index(index_path)
    rel = str(index_data.get("capability_registry") or "").strip()
    if not rel:
        return None
    candidate = Path(rel)
    if not candidate.is_absolute():
        candidate = Path(index_path).parent / candidate
    return candidate


def load_capability_registry(
    path: str | Path | None = None,
    *,
    index_path: str | Path | None = None,
) -> CapabilityRegistry:
    registry_path = _resolve_registry_path(path, index_path=index_path)
    if registry_path is None:
        return CapabilityRegistry.allow_all()
    registry_path = registry_path.resolve()
    if not registry_path.exists():
        raise SkillSchemaError(f"capability registry does not exist: {registry_path}")
    data = _load_yaml(registry_path)
    raw_mode = str(data.get("mode") or "strict").strip().lower()
    strict = raw_mode not in {"allow_all", "permissive", "off", "disabled"}
    raw_caps = data.get("capabilities") or {}
    if not isinstance(raw_caps, Mapping):
        raise SkillSchemaError(f"capability registry capabilities must be a mapping: {registry_path}")
    capabilities: dict[str, frozenset[str]] = {}
    for category in CAPABILITY_CATEGORIES:
        raw_values = raw_caps.get(category) or []
        if isinstance(raw_values, str):
            values = [raw_values]
        elif isinstance(raw_values, list):
            values = raw_values
        else:
            raise SkillSchemaError(f"capability registry {category} must be a list: {registry_path}")
        text_values = {str(item).strip() for item in values if str(item).strip()}
        if category == "grasp_profiles":
            text_values.update(CORE_GRASP_PROFILES)
        if category == "geometry_descriptor_shapes":
            text_values = {
                canonical_geometry_descriptor_shape(item) or item
                for item in text_values
            }
        capabilities[category] = frozenset(sorted(text_values))
    _validate_engine_supported_declarations(capabilities, registry_path)
    return CapabilityRegistry(
        name=str(data.get("name") or registry_path.stem),
        path=str(registry_path),
        strict=strict,
        enabled=True,
        capabilities=capabilities,
    )


def add_capability_audit_to_hints(
    recovery_hints: Mapping[str, Any] | None,
    audit: CapabilityAudit,
) -> dict[str, Any]:
    hints = dict(recovery_hints or {})
    params = dict(hints.get("params") or {})
    params["capability_audit"] = audit.to_dict()
    hints["params"] = params
    return hints
