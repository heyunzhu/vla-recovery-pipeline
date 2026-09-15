"""Pack-extensible predicate registry for recovery skill matching.

The built-in matcher remains declarative, but a skill pack may add lightweight
predicate declarations over existing qstate fields or diagnostic signal values.
Python adapters are kept as an escape hatch for cases that cannot be expressed
with simple field/operator predicates.
"""

from __future__ import annotations

import copy
import importlib.util
import re
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from .adapter_discovery import infer_pack_code_adapter_path


BUILTIN_TRIGGER_PREDICATES = frozenset(
    {
        "object_followed_lift",
        "label_matches",
        "aperture_gt",
        "aperture_lt",
        "gripper_cmd_gt",
        "holding_status_is",
        "target_ee_distance_gt",
        "target_ee_distance_lt",
        "target_future_min_xy_distance_gt",
        "target_future_min_xy_distance_lt",
        "nearest_pickable_distance_lt",
        "nearest_pickable_distance_gt",
        "nearest_pickable_is_target",
        "intent_object_is_target",
        "intent_min_xy_distance_lt",
        "wrong_object_intent_margin_gt",
        "wrong_object_intent_persist_queries_gte",
        "wrong_progress_object_total_motion_gt",
        "wrong_progress_object_goal_xy_distance_lt",
        "wrong_progress_object_is_intent",
        "wrong_progress_object_is_held",
        "wrong_progress_target_static",
        "vla_wrong_object_progress_status_is",
        "vla_pick_target_status_is",
        "vla_articulated_blocker_status_is",
        "ee_stalled",
        "diagnostic_signal_present",
        "diagnostic_signal_is",
        "diagnostic_signal_gt",
        "diagnostic_signal_gte",
        "diagnostic_signal_lt",
        "diagnostic_signal_lte",
    }
)

BUILTIN_APPLIES_PREDICATES = frozenset(
    {
        "task_language_matches",
        "target_name_matches",
        "target_name_excludes",
        "target_orientation_is",
        "goal_name_matches",
        "surface_name_matches",
        "bddl_goal_surface_matches",
    }
)

BUILTIN_APPROACH_CONTEXT_PREDICATES = frozenset(
    {
        "aperture_gt",
        "aperture_lt",
        "holding_status_is",
        "target_ee_distance_gt",
        "target_ee_distance_lt",
        "target_future_min_xy_distance_gt",
        "target_future_min_xy_distance_lt",
        "nearest_pickable_distance_lt",
        "nearest_pickable_distance_gt",
        "nearest_pickable_is_target",
        "intent_object_is_target",
        "intent_min_xy_distance_lt",
    }
)

BUILTIN_FAILURE_EVIDENCE_PREDICATES = frozenset(
    {
        "ee_stalled",
        "vla_pick_target_status_is",
        "vla_wrong_object_progress_status_is",
        "vla_articulated_blocker_status_is",
        "wrong_object_intent_margin_gt",
        "wrong_object_intent_persist_queries_gte",
        "wrong_progress_object_total_motion_gt",
        "wrong_progress_object_goal_xy_distance_lt",
        "wrong_progress_object_is_intent",
        "wrong_progress_object_is_held",
        "wrong_progress_target_static",
    }
)

PREDICATE_KINDS = ("trigger", "applies_to")
PREDICATE_SOURCES = ("state_key", "diagnostic_signal", "adapter")
PREDICATE_EVIDENCE_ROLES = ("", "approach_context", "failure_evidence")
PREDICATE_OPERATORS = (
    "is",
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "matches",
    "excludes",
    "present",
    "truthy",
)
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class PredicateRegistryError(ValueError):
    """Predicate registry is not admissible."""


def _is_abs(path: Path) -> bool:
    return path.is_absolute() or bool(path.drive)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise PredicateRegistryError("PyYAML is required to parse predicate registries") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise PredicateRegistryError(f"predicate registry must be a mapping: {path}")
    return data


def _load_index_yaml(index_path: Path) -> dict[str, Any]:
    if not index_path.exists():
        return {}
    try:
        import yaml
    except ImportError as exc:
        raise PredicateRegistryError("PyYAML is required to parse skill indexes with predicate registries") from exc
    data = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _resolve_relative(base: Path, value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(value)
    return path if _is_abs(path) else base / path


def _resolve_registry_path(path: str | Path | None, *, index_path: str | Path | None = None) -> Path | None:
    if path:
        return Path(path)
    if not index_path:
        return None
    index = Path(index_path)
    data = _load_index_yaml(index)
    rel = str(data.get("predicate_registry") or "").strip()
    if rel:
        return _resolve_relative(index.parent, rel)
    inferred = index.parent.parent / "profiles" / "predicates.yaml"
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
        data = _load_index_yaml(index)
        for key in ("predicate_adapter", "predicate_registry_adapter"):
            raw = str(data.get(key) or "").strip()
            if raw:
                resolved = _resolve_relative(index.parent, raw)
                if resolved is not None:
                    paths.append(resolved)
        inferred = infer_pack_code_adapter_path(
            index,
            "predicates.py",
            ids=("PREDICATE_IDS", "APPLIES_PREDICATE_IDS"),
        )
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


def _matches_text(value: Any, pattern: Any) -> bool:
    if isinstance(pattern, (list, tuple, set)):
        return any(_matches_text(value, item) for item in pattern)
    if isinstance(value, (list, tuple, set)):
        return any(_matches_text(item, pattern) for item in value)
    text = str(value or "")
    raw_pattern = str(pattern)
    try:
        if re.search(raw_pattern, text, flags=re.I):
            return True
    except re.error:
        pass
    return fnmatchcase(text.lower(), raw_pattern.lower())


def _diagnostic_values(state: Mapping[str, Any]) -> Mapping[str, Any]:
    diagnostics = state.get("diagnostic_signals")
    if not isinstance(diagnostics, Mapping):
        return {}
    values = diagnostics.get("values")
    return values if isinstance(values, Mapping) else {}


def diagnostic_signal_value(state: Mapping[str, Any], signal: str) -> Any:
    return _diagnostic_values(state).get(str(signal or ""))


def diagnostic_signal_name(expected: Any, *, fallback: str = "") -> str:
    if isinstance(expected, Mapping):
        return str(expected.get("signal") or expected.get("id") or expected.get("key") or fallback or "")
    return str(expected or fallback or "")


def diagnostic_signal_expected_value(expected: Any, *, default: Any = True) -> Any:
    if isinstance(expected, Mapping):
        return expected.get("value", expected.get("expected", default))
    return default


def compare_values(actual: Any, expected: Any, op: str) -> bool:
    op = str(op or "is").strip().lower()
    if op not in PREDICATE_OPERATORS:
        raise PredicateRegistryError(f"unsupported predicate operator: {op}")
    if op == "present":
        return actual is not None
    if op == "truthy":
        return bool(actual) is bool(expected)
    if op in {"gt", "gte", "lt", "lte"}:
        if actual is None:
            return False
        lhs = float(actual)
        rhs = float(expected)
        if op == "gt":
            return lhs > rhs
        if op == "gte":
            return lhs >= rhs
        if op == "lt":
            return lhs < rhs
        return lhs <= rhs
    if op == "matches":
        return _matches_text(actual, expected)
    if op == "excludes":
        return not _matches_text(actual, expected)
    if op == "neq":
        return actual != expected
    if isinstance(actual, bool) or isinstance(expected, bool):
        return bool(actual) is bool(expected)
    return str(actual) == str(expected)


@dataclass(frozen=True)
class PredicateSpec:
    id: str
    kind: str = "trigger"
    source: str = "state_key"
    key: str = ""
    signal: str = ""
    op: str = "is"
    evidence_role: str = ""
    description: str = ""
    expected: Any = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, default_kind: str = "trigger") -> "PredicateSpec":
        if not isinstance(data, Mapping):
            raise PredicateRegistryError("predicate spec must be a mapping")
        payload = dict(data)
        known = {
            "id",
            "name",
            "kind",
            "source",
            "key",
            "state_key",
            "signal",
            "diagnostic_signal",
            "op",
            "operator",
            "evidence_role",
            "description",
            "expected",
            "value",
        }
        extra = sorted(set(payload) - known)
        if extra:
            raise PredicateRegistryError(f"unknown predicate spec keys for {payload.get('id')}: {extra}")
        spec = cls(
            id=str(payload.get("id") or payload.get("name") or ""),
            kind=str(payload.get("kind") or default_kind or "trigger"),
            source=str(payload.get("source") or "state_key"),
            key=str(payload.get("state_key") or payload.get("key") or ""),
            signal=str(payload.get("diagnostic_signal") or payload.get("signal") or ""),
            op=str(payload.get("operator") or payload.get("op") or "is"),
            evidence_role=str(payload.get("evidence_role") or ""),
            description=str(payload.get("description") or ""),
            expected=copy.deepcopy(payload.get("expected", payload.get("value", None))),
        )
        validate_predicate_spec(spec)
        return spec

    def actual_value(self, state: Mapping[str, Any]) -> Any:
        if self.source == "diagnostic_signal":
            signal = self.signal or self.key
            return diagnostic_signal_value(state, signal)
        return state.get(self.key or self.id)

    def evaluate(self, expected: Any, state: Mapping[str, Any]) -> bool:
        actual = self.actual_value(state)
        expected_value = self.expected if self.expected is not None else expected
        if isinstance(expected, Mapping):
            expected_value = expected.get("value", expected.get("expected", expected_value))
        return compare_values(actual, expected_value, self.op)


def validate_predicate_spec(spec: PredicateSpec) -> None:
    if not _ID_RE.match(spec.id):
        raise PredicateRegistryError(f"invalid predicate id: {spec.id!r}")
    if spec.kind not in PREDICATE_KINDS:
        raise PredicateRegistryError(f"{spec.id}: kind must be one of {PREDICATE_KINDS}")
    if spec.id in BUILTIN_TRIGGER_PREDICATES or spec.id in BUILTIN_APPLIES_PREDICATES:
        raise PredicateRegistryError(f"{spec.id}: pack predicate must not shadow a built-in predicate")
    if spec.source not in PREDICATE_SOURCES:
        raise PredicateRegistryError(f"{spec.id}: source must be one of {PREDICATE_SOURCES}")
    if spec.source == "state_key" and not spec.key:
        raise PredicateRegistryError(f"{spec.id}: state_key predicate requires key")
    if spec.source == "diagnostic_signal" and not (spec.signal or spec.key):
        raise PredicateRegistryError(f"{spec.id}: diagnostic_signal predicate requires signal")
    if spec.source == "adapter":
        raise PredicateRegistryError(f"{spec.id}: adapter predicates must be declared by predicate_adapter, not YAML")
    if spec.op not in PREDICATE_OPERATORS:
        raise PredicateRegistryError(f"{spec.id}: unsupported operator {spec.op!r}")
    if spec.evidence_role not in PREDICATE_EVIDENCE_ROLES:
        raise PredicateRegistryError(f"{spec.id}: evidence_role must be one of {PREDICATE_EVIDENCE_ROLES}")


@dataclass(frozen=True)
class PredicateAdapter:
    name: str
    path: str
    predicate_ids: frozenset[str]
    applies_predicate_ids: frozenset[str]
    failure_evidence_predicate_ids: frozenset[str] = frozenset()
    approach_context_predicate_ids: frozenset[str] = frozenset()
    module: ModuleType | None = None

    def evaluate_predicate(self, name: str, expected: Any, state: Mapping[str, Any]) -> bool:
        if self.module is None or name not in self.predicate_ids:
            raise KeyError(name)
        fn = getattr(self.module, "evaluate_predicate", None)
        if not callable(fn):
            raise PredicateRegistryError(f"predicate adapter missing evaluate_predicate: {self.path}")
        return bool(fn(name, expected, copy.deepcopy(dict(state))))

    def evaluate_applies_predicate(self, name: str, expected: Any, state: Mapping[str, Any]) -> bool:
        if self.module is None or name not in self.applies_predicate_ids:
            raise KeyError(name)
        fn = getattr(self.module, "evaluate_applies_predicate", None)
        if not callable(fn):
            raise PredicateRegistryError(f"predicate adapter missing evaluate_applies_predicate: {self.path}")
        return bool(fn(name, expected, copy.deepcopy(dict(state))))

    def actual_value_for_predicate(self, name: str, state: Mapping[str, Any]) -> Any:
        if self.module is None or name not in self.predicate_ids:
            raise KeyError(name)
        fn = getattr(self.module, "actual_value_for_predicate", None)
        if callable(fn):
            return fn(name, copy.deepcopy(dict(state)))
        return None

    def actual_value_for_applies_predicate(self, name: str, state: Mapping[str, Any]) -> Any:
        if self.module is None or name not in self.applies_predicate_ids:
            raise KeyError(name)
        fn = getattr(self.module, "actual_value_for_applies_predicate", None)
        if callable(fn):
            return fn(name, copy.deepcopy(dict(state)))
        return None


_ADAPTER_CACHE: dict[str, PredicateAdapter] = {}


def load_predicate_adapter(path: str | Path) -> PredicateAdapter:
    resolved = Path(path).resolve()
    cache_key = str(resolved)
    cached = _ADAPTER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if not resolved.exists():
        raise PredicateRegistryError(f"predicate adapter does not exist: {resolved}")
    module_name = f"_libero_predicate_adapter_{abs(hash(cache_key))}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise PredicateRegistryError(f"cannot load predicate adapter: {resolved}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    trigger_ids = frozenset(str(item).strip() for item in getattr(module, "PREDICATE_IDS", ()) if str(item).strip())
    applies_ids = frozenset(
        str(item).strip() for item in getattr(module, "APPLIES_PREDICATE_IDS", ()) if str(item).strip()
    )
    if not trigger_ids and not applies_ids:
        raise PredicateRegistryError(f"predicate adapter must expose PREDICATE_IDS or APPLIES_PREDICATE_IDS: {resolved}")
    shadows = (trigger_ids | applies_ids) & (BUILTIN_TRIGGER_PREDICATES | BUILTIN_APPLIES_PREDICATES)
    if shadows:
        raise PredicateRegistryError(f"predicate adapter must not shadow built-ins: {sorted(shadows)}")
    adapter = PredicateAdapter(
        name=str(getattr(module, "ADAPTER_NAME", resolved.stem)),
        path=str(resolved),
        predicate_ids=trigger_ids,
        applies_predicate_ids=applies_ids,
        failure_evidence_predicate_ids=frozenset(
            str(item).strip()
            for item in getattr(module, "FAILURE_EVIDENCE_PREDICATE_IDS", ())
            if str(item).strip()
        ),
        approach_context_predicate_ids=frozenset(
            str(item).strip()
            for item in getattr(module, "APPROACH_CONTEXT_PREDICATE_IDS", ())
            if str(item).strip()
        ),
        module=module,
    )
    _ADAPTER_CACHE[cache_key] = adapter
    return adapter


def _specs_from_section(raw: Any, *, kind: str) -> list[PredicateSpec]:
    if not raw:
        return []
    items: list[Mapping[str, Any]] = []
    if isinstance(raw, Mapping):
        for name, value in raw.items():
            payload = dict(value) if isinstance(value, Mapping) else {"key": str(value)}
            payload.setdefault("id", str(name))
            items.append(payload)
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, Mapping):
                raise PredicateRegistryError(f"{kind} predicates must be mappings")
            items.append(item)
    else:
        raise PredicateRegistryError(f"{kind} predicates must be a mapping or list")
    return [PredicateSpec.from_mapping(item, default_kind=kind) for item in items]


@dataclass(frozen=True)
class PredicateRegistry:
    name: str
    path: str = ""
    enabled: bool = False
    predicates: dict[str, PredicateSpec] = field(default_factory=dict)
    applies_predicates: dict[str, PredicateSpec] = field(default_factory=dict)
    adapters: tuple[PredicateAdapter, ...] = ()

    @classmethod
    def builtins(cls) -> "PredicateRegistry":
        return cls(name="builtin_predicates", enabled=False)

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "enabled": self.enabled,
            "predicates": sorted(self.predicates),
            "applies_predicates": sorted(self.applies_predicates),
            "adapters": [
                {
                    "name": adapter.name,
                    "path": adapter.path,
                    "predicates": sorted(adapter.predicate_ids),
                    "applies_predicates": sorted(adapter.applies_predicate_ids),
                }
                for adapter in self.adapters
            ],
        }

    @property
    def trigger_predicate_ids(self) -> frozenset[str]:
        ids = set(BUILTIN_TRIGGER_PREDICATES)
        ids.update(self.predicates)
        for adapter in self.adapters:
            ids.update(adapter.predicate_ids)
        return frozenset(ids)

    @property
    def applies_predicate_ids(self) -> frozenset[str]:
        ids = set(BUILTIN_APPLIES_PREDICATES)
        ids.update(self.applies_predicates)
        for adapter in self.adapters:
            ids.update(adapter.applies_predicate_ids)
        return frozenset(ids)

    def is_trigger_predicate_allowed(self, name: str) -> bool:
        return str(name) in self.trigger_predicate_ids

    def is_applies_predicate_allowed(self, name: str) -> bool:
        return str(name) in self.applies_predicate_ids

    def evaluate_predicate(self, name: str, expected: Any, state: Mapping[str, Any]) -> bool:
        key = str(name)
        spec = self.predicates.get(key)
        if spec is not None:
            return spec.evaluate(expected, state)
        for adapter in self.adapters:
            if key in adapter.predicate_ids:
                return adapter.evaluate_predicate(key, expected, state)
        raise KeyError(f"unknown predicate: {name}")

    def evaluate_applies_predicate(self, name: str, expected: Any, state: Mapping[str, Any]) -> bool:
        key = str(name)
        spec = self.applies_predicates.get(key)
        if spec is not None:
            return spec.evaluate(expected, state)
        for adapter in self.adapters:
            if key in adapter.applies_predicate_ids:
                return adapter.evaluate_applies_predicate(key, expected, state)
        raise KeyError(f"unknown applies_to predicate: {name}")

    def actual_value_for_predicate(self, name: str, state: Mapping[str, Any]) -> Any:
        key = str(name)
        spec = self.predicates.get(key)
        if spec is not None:
            return spec.actual_value(state)
        for adapter in self.adapters:
            if key in adapter.predicate_ids:
                return adapter.actual_value_for_predicate(key, state)
        return None

    def actual_value_for_applies_predicate(self, name: str, state: Mapping[str, Any]) -> Any:
        key = str(name)
        spec = self.applies_predicates.get(key)
        if spec is not None:
            return spec.actual_value(state)
        for adapter in self.adapters:
            if key in adapter.applies_predicate_ids:
                return adapter.actual_value_for_applies_predicate(key, state)
        return None

    def evidence_role(self, name: str, expected: Any = None) -> str:
        key = str(name)
        if key in BUILTIN_FAILURE_EVIDENCE_PREDICATES:
            return "failure_evidence"
        if key in BUILTIN_APPROACH_CONTEXT_PREDICATES:
            return "approach_context"
        if key.startswith("diagnostic_signal_") and isinstance(expected, Mapping):
            role = str(expected.get("evidence_role") or "").strip()
            return role if role in PREDICATE_EVIDENCE_ROLES else ""
        spec = self.predicates.get(key) or self.applies_predicates.get(key)
        if spec is not None:
            return spec.evidence_role
        for adapter in self.adapters:
            if key in adapter.failure_evidence_predicate_ids:
                return "failure_evidence"
            if key in adapter.approach_context_predicate_ids:
                return "approach_context"
        return ""


def load_predicate_registry(
    path: str | Path | None = None,
    *,
    adapter_path: str | Path | None = None,
    index_path: str | Path | None = None,
) -> PredicateRegistry:
    registry_path = _resolve_registry_path(path, index_path=index_path)
    adapters = tuple(load_predicate_adapter(path) for path in _adapter_paths(adapter_path, index_path=index_path))
    if registry_path is None:
        if not adapters:
            return PredicateRegistry.builtins()
        return PredicateRegistry(name="predicate_adapter_registry", enabled=True, adapters=adapters)
    registry_path = registry_path.resolve()
    if not registry_path.exists():
        raise PredicateRegistryError(f"predicate registry does not exist: {registry_path}")
    data = _load_yaml(registry_path)
    raw_predicates = data.get("predicates") or {}
    trigger_raw = {}
    applies_raw = {}
    if isinstance(raw_predicates, Mapping):
        trigger_raw = raw_predicates.get("trigger") or raw_predicates.get("triggers") or {}
        applies_raw = raw_predicates.get("applies_to") or raw_predicates.get("applies") or {}
        bare = {
            key: value
            for key, value in raw_predicates.items()
            if key not in {"trigger", "triggers", "applies_to", "applies"}
        }
        if bare:
            trigger_raw = {**bare, **dict(trigger_raw)} if isinstance(trigger_raw, Mapping) else bare
    elif isinstance(raw_predicates, list):
        trigger_raw = raw_predicates
    else:
        raise PredicateRegistryError(f"predicate registry predicates must be a mapping or list: {registry_path}")
    trigger_specs = _specs_from_section(trigger_raw, kind="trigger")
    applies_specs = _specs_from_section(applies_raw, kind="applies_to")
    predicates = {spec.id: spec for spec in trigger_specs}
    applies_predicates = {spec.id: spec for spec in applies_specs}
    if len(predicates) != len(trigger_specs):
        raise PredicateRegistryError(f"duplicate trigger predicate ids: {registry_path}")
    if len(applies_predicates) != len(applies_specs):
        raise PredicateRegistryError(f"duplicate applies_to predicate ids: {registry_path}")
    return PredicateRegistry(
        name=str(data.get("name") or registry_path.stem),
        path=str(registry_path),
        enabled=True,
        predicates=predicates,
        applies_predicates=applies_predicates,
        adapters=adapters,
    )
