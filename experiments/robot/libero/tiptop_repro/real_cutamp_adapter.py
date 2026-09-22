from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from .affordances import is_probably_movable, is_probably_surface
from .engine_capabilities import (
    canonical_geometry_planner_primitive,
    canonical_grounding_planner_primitive,
)
from .predicates import SymbolicState
from .recovery_symbols import RecoverySymbolicAbstraction, build_recovery_symbolic_abstraction
from .real_cutamp_backend import RealCuTAMPBackend, RealCuTAMPBackendConfig, RealCuTAMPBackendResult
from .scene_graph import SceneGraph
from .scene_reader import SceneState
from .scene_graph import atom_key
from .tamp_scene import GroundedAtom, TAMPProblem, build_tamp_problem
from .task_parser import ParsedTask
from .task_semantics import TaskSemanticsResult


@dataclass(frozen=True)
class RealCuTAMPRecoveryGoal:
    name: str
    atoms: List[GroundedAtom]
    surface_names: List[str] = field(default_factory=list)
    reason: str = ""
    grounding: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "name": self.name,
            "reason": self.reason,
            "atoms": [atom.to_dict() for atom in self.atoms],
            "surface_names": list(self.surface_names),
        }
        if self.grounding:
            data["grounding"] = dict(self.grounding)
        return data


@dataclass
class RealCuTAMPRecoveryAttempt:
    goal: RealCuTAMPRecoveryGoal
    result: RealCuTAMPBackendResult
    problem: TAMPProblem

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal.to_dict(),
            "result": self.result.to_dict(),
            "tamp_problem": self.problem.to_dict(),
        }


@dataclass
class RealCuTAMPRecoveryPlan:
    feasible: bool
    selected: Optional[RealCuTAMPRecoveryAttempt] = None
    attempts: List[RealCuTAMPRecoveryAttempt] = field(default_factory=list)
    fallback_reason: str = ""
    rule_goals: List[RealCuTAMPRecoveryGoal] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feasible": bool(self.feasible),
            "selected_goal": None if self.selected is None else self.selected.goal.to_dict(),
            "selected_result": None if self.selected is None else self.selected.result.to_dict(),
            "fallback_reason": self.fallback_reason,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "rule_goals": [goal.to_dict() for goal in self.rule_goals],
        }


def _atom_dict(atom: GroundedAtom) -> Dict[str, Any]:
    return {"predicate": atom.predicate, "args": list(atom.args), "source": "real_cutamp_recovery_goal", "confidence": 1.0}


def _known_surface(name: Optional[str], scene: SceneState) -> List[str]:
    if name is None or name not in scene.objects:
        return []
    return [name]


def _semantic_atom_to_grounded(atom: Dict[str, Any]) -> Optional[GroundedAtom]:
    pred, args = atom_key(atom)
    if pred == "requires_final" and args:
        pred = args[0]
        args = args[1:]
    if pred == "in":
        pred = "inside"
    if pred == "holding" and len(args) == 2 and args[0] == "gripper":
        args = (args[1],)
    if pred in {"on", "inside"} and len(args) == 2:
        return GroundedAtom(pred, args)
    if pred == "holding" and len(args) == 1:
        return GroundedAtom(pred, args)
    if pred in {"open", "closed"} and len(args) == 1:
        return GroundedAtom(pred, args)
    if pred == "handempty":
        return GroundedAtom("handempty", ())
    return None


def _task_placement_predicate(task_semantics: TaskSemanticsResult | None) -> str:
    if task_semantics is None:
        return "on"
    progress = dict(task_semantics.task_progress or {})
    if progress.get("requires_inside"):
        return "inside"
    for atom in task_semantics.required_final_atoms or []:
        grounded = _semantic_atom_to_grounded(atom)
        if grounded is not None and grounded.predicate == "inside":
            return "inside"
    return "on"


def _hint_params(recovery_hints: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(recovery_hints, Mapping):
        return {}
    params = recovery_hints.get("params")
    return dict(params) if isinstance(params, Mapping) else {}


def _hint_group(recovery_hints: Mapping[str, Any] | None, key: str) -> Dict[str, Any]:
    params = _hint_params(recovery_hints)
    hints = params.get(key)
    return dict(hints) if isinstance(hints, Mapping) else {}


_GROUNDING_RUNTIME_ADAPTER_CACHE: Dict[str, Any] = {}


def _load_grounding_runtime_adapter(path: str) -> Any:
    resolved = Path(path).resolve()
    cache_key = str(resolved)
    cached = _GROUNDING_RUNTIME_ADAPTER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if not resolved.exists():
        raise FileNotFoundError(f"grounding profile runtime adapter does not exist: {resolved}")
    module_name = f"_tiptop_grounding_runtime_adapter_{abs(hash(cache_key))}"
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load grounding profile runtime adapter: {resolved}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    _GROUNDING_RUNTIME_ADAPTER_CACHE[cache_key] = module
    return module


def _call_grounding_runtime_adapter(hint: Mapping[str, Any], function_name: str, **kwargs: Any) -> Any:
    path = str(hint.get("grounding_profile_adapter_path") or "").strip()
    profile = str(hint.get("grounding_profile") or "").strip()
    if not path or not profile:
        return None
    module = _load_grounding_runtime_adapter(path)
    fn = getattr(module, function_name, None)
    if not callable(fn):
        return None
    return fn(profile, hint=dict(hint), **kwargs)


def _grounding_hint_mappings(recovery_hints: Mapping[str, Any] | None) -> Dict[str, Dict[str, Any]]:
    hints = _hint_group(recovery_hints, "grounding_hints")
    return {
        str(key): dict(value)
        for key, value in hints.items()
        if isinstance(value, Mapping)
    }


def _adapter_goal_surface_result(
    scene: SceneState,
    parsed: ParsedTask,
    target: Optional[str],
    goal: Optional[str],
    hint: Mapping[str, Any],
) -> Optional[Tuple[Optional[str], Dict[str, Any]]]:
    result = _call_grounding_runtime_adapter(
        hint,
        "resolve_goal_surface",
        scene=scene,
        parsed=parsed,
        target=target,
        goal=goal,
    )
    if not isinstance(result, Mapping):
        return None
    surface = result.get("surface", result.get("to", goal))
    grounding = result.get("grounding", {})
    return (None if surface is None else str(surface), dict(grounding) if isinstance(grounding, Mapping) else {})


def _adapter_fixed_table_region_rewrite(
    atom: GroundedAtom,
    parsed: ParsedTask,
    target: Optional[str],
    hint: Mapping[str, Any],
    region_name: str,
) -> Optional[Tuple[GroundedAtom, Dict[str, Any]]]:
    result = _call_grounding_runtime_adapter(
        hint,
        "rewrite_fixed_table_region_atom",
        atom=atom,
        parsed=parsed,
        target=target,
        region_name=region_name,
    )
    if not isinstance(result, Mapping):
        return None
    predicate = str(result.get("predicate") or "on")
    obj = str(result.get("object") or "")
    surface = str(result.get("surface") or result.get("to") or "")
    if not obj or not surface:
        return None
    grounding = result.get("grounding", {})
    return GroundedAtom(predicate, (obj, surface)), dict(grounding) if isinstance(grounding, Mapping) else {}


def _adapter_placement_atom_rewrite(
    atom: GroundedAtom,
    scene: SceneState,
    parsed: ParsedTask,
    target: Optional[str],
    recovery_hints: Mapping[str, Any] | None,
) -> Optional[Tuple[GroundedAtom, Dict[str, Any]]]:
    for hint_key, hint in _grounding_hint_mappings(recovery_hints).items():
        result = _call_grounding_runtime_adapter(
            hint,
            "rewrite_placement_atom",
            atom=atom,
            scene=scene,
            parsed=parsed,
            target=target,
            hint_key=hint_key,
        )
        if not isinstance(result, Mapping):
            continue
        predicate = str(result.get("predicate") or atom.predicate)
        obj = str(result.get("object") or result.get("target") or atom.args[0])
        surface = str(result.get("surface") or result.get("to") or result.get("goal_surface") or "")
        if not obj or not surface:
            continue
        grounding = dict(result.get("grounding") or {}) if isinstance(result.get("grounding"), Mapping) else {}
        grounding.setdefault("source", "skill_grounding_adapter")
        grounding.setdefault("hint_key", hint_key)
        grounding.setdefault("grounding_profile", str(hint.get("grounding_profile") or ""))
        return GroundedAtom(predicate, (obj, surface)), grounding
    return None


def _adapter_container_region_source(
    region_name: str,
    scene: SceneState,
    hint: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    result = _call_grounding_runtime_adapter(
        hint,
        "resolve_container_region_source",
        region_name=region_name,
        scene=scene,
    )
    return dict(result) if isinstance(result, Mapping) and result.get("source") else None


def _adapter_movable_support_allowed(
    surface: str,
    atom: GroundedAtom,
    scene: SceneState,
    parsed: ParsedTask | None,
    target: Optional[str],
    hint: Mapping[str, Any],
) -> Optional[bool]:
    result = _call_grounding_runtime_adapter(
        hint,
        "allow_movable_support_surface",
        surface=surface,
        atom=atom,
        scene=scene,
        parsed=parsed,
        target=target,
    )
    if result is None:
        return None
    return bool(result)


def _adapter_virtual_surface_declared(
    surface: str,
    scene: SceneState,
    parsed: ParsedTask | None,
    recovery_hints: Mapping[str, Any] | None,
) -> bool:
    for hint_key, hint in _grounding_hint_mappings(recovery_hints).items():
        result = _call_grounding_runtime_adapter(
            hint,
            "is_known_or_virtual_surface",
            surface=surface,
            scene=scene,
            parsed=parsed,
            hint_key=hint_key,
        )
        if result is not None:
            return bool(result)
    return False


def _grounding_planner_primitive(hint: Mapping[str, Any]) -> str:
    return canonical_grounding_planner_primitive(hint)


def _movable_support_surface_hint(recovery_hints: Mapping[str, Any] | None) -> Dict[str, Any]:
    # Planner-world support registration is geometry, not target binding. Keep
    # the grounding_hints fallback so older skill packs remain readable.
    geometry_hints = _hint_group(recovery_hints, "geometry_hints")
    grounding_hints = _hint_group(recovery_hints, "grounding_hints")
    geometry_support = geometry_hints.get("movable_support_surface")
    grounding_support = grounding_hints.get("support_object")
    if isinstance(geometry_support, Mapping):
        out = dict(grounding_support) if isinstance(grounding_support, Mapping) else {}
        out.update(dict(geometry_support))
        return out
    movable_support = grounding_hints.get("movable_support_surface")
    if isinstance(movable_support, Mapping):
        out = dict(grounding_support) if isinstance(grounding_support, Mapping) else {}
        out.update(dict(movable_support))
        return out
    if isinstance(grounding_support, Mapping):
        return dict(grounding_support)
    placement_surface = grounding_hints.get("placement_surface")
    if isinstance(placement_surface, Mapping):
        if _grounding_planner_primitive(placement_surface) == "movable_support_surface":
            return dict(placement_surface)
    return {}


def _allow_movable_support_surface(
    surface: str,
    atom: GroundedAtom,
    scene: SceneState,
    parsed: ParsedTask | None,
    target: Optional[str],
    recovery_hints: Mapping[str, Any] | None,
) -> bool:
    if surface == target or surface not in scene.objects or atom.predicate.lower() != "on":
        return False
    hint = _movable_support_surface_hint(recovery_hints)
    if not hint:
        return False
    if _grounding_planner_primitive(hint) != "movable_support_surface":
        return False
    adapter_allowed = _adapter_movable_support_allowed(surface, atom, scene, parsed, target, hint)
    if adapter_allowed is not None:
        return adapter_allowed
    if bool(hint.get("require_movable", True)) and not is_probably_movable(surface):
        return False
    patterns = hint.get("support_name_matches") or hint.get("name_matches")
    if patterns and not _matches_any(surface, patterns):
        return False
    object_class = str(hint.get("object_class") or hint.get("support_object_class") or "").lower()
    language = str(parsed.language if parsed is not None else "").lower()
    if object_class and object_class not in surface.lower() and object_class not in language:
        return False
    return True


def _surface_names_for_goal(
    atoms: List[GroundedAtom],
    scene: SceneState,
    *,
    parsed: ParsedTask | None = None,
    target: Optional[str] = None,
    recovery_hints: Mapping[str, Any] | None = None,
) -> List[str]:
    names: List[str] = []
    for atom in atoms:
        if atom.predicate in {"on", "inside"} and len(atom.args) == 2:
            surface = atom.args[1]
            if surface == "table":
                names.append(surface)
            elif surface in scene.objects and (
                is_probably_surface(surface)
                or _allow_movable_support_surface(surface, atom, scene, parsed, target, recovery_hints)
            ):
                names.append(surface)
            elif _is_fixed_table_region_surface(surface, parsed, recovery_hints):
                names.append(surface)
            elif _placement_region_source_name(surface, recovery_hints) in scene.objects:
                names.append(surface)
            elif _adapter_virtual_surface_declared(surface, scene, parsed, recovery_hints):
                names.append(surface)
    out: List[str] = []
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _movable_support_grounding_for_goal(
    atoms: List[GroundedAtom],
    scene: SceneState,
    parsed: ParsedTask,
    target: Optional[str],
    recovery_hints: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    hint = _movable_support_surface_hint(recovery_hints)
    if not hint:
        return {}
    supports: List[str] = []
    for atom in atoms:
        if atom.predicate.lower() not in {"on", "inside"} or len(atom.args) != 2:
            continue
        surface = atom.args[1]
        if is_probably_surface(surface):
            continue
        if _allow_movable_support_surface(surface, atom, scene, parsed, target, recovery_hints):
            supports.append(surface)
    supports = list(dict.fromkeys(supports))
    if not supports:
        return {}
    return {
        "source": "skill_grounding_hint",
        "intent": str(hint.get("intent") or "movable_support"),
        "object_class": str(hint.get("object_class") or hint.get("support_object_class") or ""),
        "movable_support_surface_names": supports,
    }


def _placement_surface_hint(recovery_hints: Mapping[str, Any] | None) -> Dict[str, Any]:
    hints = _hint_group(recovery_hints, "grounding_hints")
    surface = hints.get("placement_surface")
    return dict(surface) if isinstance(surface, Mapping) else {}


def _placement_region_hint(recovery_hints: Mapping[str, Any] | None) -> Dict[str, Any]:
    hints = _hint_group(recovery_hints, "geometry_hints")
    region = hints.get("placement_region")
    return dict(region) if isinstance(region, Mapping) else {}


def _geometry_planner_primitive(hint: Mapping[str, Any]) -> str:
    return canonical_geometry_planner_primitive(hint)


def _fixed_table_region_grounding_hint(recovery_hints: Mapping[str, Any] | None) -> Dict[str, Any]:
    hint = _placement_surface_hint(recovery_hints)
    if _grounding_planner_primitive(hint) != "table_region_surface":
        return {}
    return hint


def _fixed_table_region_geometry_hint(recovery_hints: Mapping[str, Any] | None) -> Dict[str, Any]:
    hint = _placement_region_hint(recovery_hints)
    if _geometry_planner_primitive(hint) != "fixed_table_rect":
        return {}
    return hint


def _fixed_table_region_name(recovery_hints: Mapping[str, Any] | None) -> Optional[str]:
    for hint in (
        _fixed_table_region_grounding_hint(recovery_hints),
        _fixed_table_region_geometry_hint(recovery_hints),
    ):
        name = str(hint.get("region_name") or "").strip()
        if name:
            return name
    return None


def _strict_fixed_table_region_goal(recovery_hints: Mapping[str, Any] | None) -> bool:
    for hint in (
        _fixed_table_region_grounding_hint(recovery_hints),
        _fixed_table_region_geometry_hint(recovery_hints),
    ):
        if not hint:
            continue
        if "strict_placement_surface" in hint:
            return bool(hint.get("strict_placement_surface"))
        if hint.get("region_name") or hint.get("region_name_from_bddl_goal"):
            return True
    return False


def _regex_matches_any(text: str, patterns: Any) -> bool:
    if isinstance(patterns, str):
        patterns = [patterns]
    if not isinstance(patterns, list):
        return False
    value = str(text or "")
    for pattern in patterns:
        try:
            if re.search(str(pattern), value, flags=re.I):
                return True
        except re.error:
            continue
    return False


def _matches_any(name: str, patterns: Any) -> bool:
    if isinstance(patterns, str):
        patterns = [patterns]
    if not isinstance(patterns, list):
        return False
    low = name.lower()
    return any(fnmatchcase(low, str(pattern).lower()) for pattern in patterns)


def _matches_name_or_regex(name: str, patterns: Any) -> bool:
    return _matches_any(name, patterns) or _regex_matches_any(name, patterns)


def _bddl_goal_surface_names(parsed: ParsedTask | None) -> List[str]:
    if parsed is None:
        return []
    diagnostics = dict(parsed.diagnostics or {})
    surfaces: List[str] = []
    raw_surfaces = diagnostics.get("bddl_goal_surfaces") or []
    if isinstance(raw_surfaces, str):
        raw_surfaces = [raw_surfaces]
    if isinstance(raw_surfaces, list):
        surfaces.extend(str(surface) for surface in raw_surfaces if str(surface or ""))
    for atom in diagnostics.get("bddl_goal_atoms") or []:
        if not isinstance(atom, Mapping):
            continue
        pred = str(atom.get("predicate") or "").lower()
        args = list(atom.get("args") or [])
        if pred in {"on", "inside"} and len(args) >= 2:
            surfaces.append(str(args[1]))
    out: List[str] = []
    seen = set()
    for surface in surfaces:
        if surface in seen:
            continue
        seen.add(surface)
        out.append(surface)
    return out


def _dynamic_bddl_table_region_name(
    parsed: ParsedTask | None,
    recovery_hints: Mapping[str, Any] | None,
    *,
    surface: Optional[str] = None,
) -> Optional[str]:
    candidates: List[str] = []
    if surface:
        candidates.append(str(surface))
    candidates.extend(_bddl_goal_surface_names(parsed))
    for hint in (
        _fixed_table_region_grounding_hint(recovery_hints),
        _fixed_table_region_geometry_hint(recovery_hints),
    ):
        if not hint:
            continue
        if not (hint.get("region_name_from_bddl_goal") or hint.get("bounds_from_bddl_region")):
            continue
        patterns = (
            hint.get("bddl_goal_surface_matches")
            or hint.get("region_name_matches")
            or hint.get("source_region_matches")
        )
        for candidate in candidates:
            if not candidate:
                continue
            if patterns and not _matches_name_or_regex(candidate, patterns):
                continue
            return candidate
    return None


def _is_fixed_table_region_surface(
    surface: str,
    parsed: ParsedTask | None,
    recovery_hints: Mapping[str, Any] | None,
) -> bool:
    fixed_region = _fixed_table_region_name(recovery_hints)
    if fixed_region and surface == fixed_region:
        return True
    return _dynamic_bddl_table_region_name(parsed, recovery_hints, surface=surface) == surface


_COMPARTMENT_TOKENS = ("front", "back", "left", "right", "middle", "center")


def _compartment_from_region_name(region_name: str, hint: Mapping[str, Any] | None = None) -> str:
    if isinstance(hint, Mapping):
        raw = str(hint.get("compartment") or "").strip().lower()
        if raw:
            return raw
    low = str(region_name or "").lower()
    for token in _COMPARTMENT_TOKENS:
        if f"_{token}_" in low or low.endswith(f"_{token}"):
            return token
    return ""


def resolve_skill_goal_surface(
    scene: SceneState,
    parsed: ParsedTask,
    target: Optional[str],
    goal: Optional[str],
    recovery_hints: Mapping[str, Any] | None = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Resolve a coarse task goal to a skill-preferred placement surface."""
    if goal is None or goal not in scene.objects:
        return goal, {}
    hint = _placement_surface_hint(recovery_hints)
    if not hint:
        return goal, {}
    adapter_resolved = _adapter_goal_surface_result(scene, parsed, target, goal, hint)
    if adapter_resolved is not None:
        return adapter_resolved
    intent = str(hint.get("intent") or "").lower()
    primitive = _grounding_planner_primitive(hint)
    object_class = str(hint.get("object_class") or "").lower()
    relation = str(hint.get("relation") or "").lower()
    language = str(parsed.language or "").lower()
    goal_low = goal.lower()
    if primitive not in {
        "preferred_support_surface",
        "preferred_container_surface",
        "container_region_surface",
    }:
        return goal, {}
    if object_class and object_class not in goal_low and object_class not in language:
        return goal, {}
    if primitive == "preferred_support_surface" and intent == "top_support":
        if "top" not in language and "_top" not in goal_low and "top_side" not in goal_low:
            return goal, {}
    elif primitive == "preferred_support_surface" and intent == "shelf_support":
        if "shelf" not in language and "shelf" not in goal_low:
            return goal, {}
    else:
        if relation and relation != "inside":
            return goal, {}
        if "drawer" not in language and "inside" not in language and "in " not in language:
            return goal, {}
        drawer_level = str(hint.get("drawer_level") or "").lower()
        if drawer_level and drawer_level not in language and f"_{drawer_level}" not in goal_low:
            return goal, {}

    names = sorted(scene.objects)
    avoid = {
        name
        for name in names
        if name != target and hint.get("avoid") and _matches_any(name, hint.get("avoid"))
    }
    for group in ("prefer", "fallback"):
        patterns = hint.get(group)
        if isinstance(patterns, str):
            patterns = [patterns]
        if not isinstance(patterns, list):
            continue
        for pattern in patterns:
            matches = [
                name
                for name in names
                if name != target
                and name not in avoid
                and _matches_any(name, [pattern])
                and (not object_class or object_class in name.lower())
            ]
            if not matches:
                continue
            resolved = matches[0]
            if resolved == goal:
                return goal, {}
            return resolved, {
                "source": "skill_grounding_hint",
                "intent": intent,
                "object_class": object_class,
                "relation": relation,
                "from": goal,
                "to": resolved,
                "pattern": str(pattern),
            }
    return goal, {}


def _placement_region_proxy_name(container: str, hint: Mapping[str, Any], *, compartment: str = "") -> str:
    suffix = str(hint.get("proxy_suffix") or "inner_floor").strip("_") or "inner_floor"
    if compartment and not suffix.startswith(f"{compartment}_"):
        suffix = f"{compartment}_{suffix}"
    return f"{container}_{suffix}"


def _container_region_source_result(
    region_name: str,
    scene: SceneState,
    recovery_hints: Mapping[str, Any] | None = None,
) -> Optional[Dict[str, Any]]:
    hint = _placement_surface_hint(recovery_hints)
    if hint:
        adapter_source = _adapter_container_region_source(region_name, scene, hint)
        if adapter_source is not None:
            return dict(adapter_source)
    if region_name in scene.objects:
        return {"source": region_name}
    for suffix in ("_contain_region", "_container_region", "_inside_region", "_top_region", "_bottom_region"):
        if not region_name.endswith(suffix):
            continue
        base = region_name[: -len(suffix)]
        candidates = [f"{base}_main", base]
        for level_suffix in ("_top", "_bottom"):
            if base.endswith(level_suffix):
                shelf_base = base[: -len(level_suffix)]
                candidates.extend([f"{shelf_base}_main", shelf_base])
        for candidate in candidates:
            if candidate in scene.objects:
                return {"source": candidate}
        for compartment in _COMPARTMENT_TOKENS:
            marker = f"_{compartment}"
            if not base.endswith(marker):
                continue
            container = base[: -len(marker)]
            for candidate in (f"{container}_main", container):
                if candidate in scene.objects:
                    return {"source": candidate}
    return None


def _container_region_source_name(
    region_name: str,
    scene: SceneState,
    recovery_hints: Mapping[str, Any] | None = None,
) -> Optional[str]:
    result = _container_region_source_result(region_name, scene, recovery_hints)
    if not result:
        return None
    source = str(result.get("source") or "")
    return source or None


def _placement_region_source_name(region_name: str, recovery_hints: Mapping[str, Any] | None) -> Optional[str]:
    hint = _placement_region_hint(recovery_hints)
    if not hint:
        return None
    suffix = str(hint.get("proxy_suffix") or "inner_floor").strip("_") or "inner_floor"
    marker = f"_{suffix}"
    if not region_name.endswith(marker):
        return None
    source = region_name[: -len(marker)]
    compartment = _compartment_from_region_name(region_name, hint)
    if compartment and source.endswith(f"_{compartment}"):
        source = source[: -(len(compartment) + 1)]
    return source


def _placement_region_applies(
    container: str,
    atom: GroundedAtom,
    parsed: ParsedTask,
    recovery_hints: Mapping[str, Any] | None,
) -> bool:
    hint = _placement_region_hint(recovery_hints)
    if not hint or atom.predicate.lower() != "inside":
        return False
    if _geometry_planner_primitive(hint) != "inner_floor":
        return False
    relation = str(hint.get("relation") or "inside").lower()
    if relation != "inside":
        return False
    language = str(parsed.language or "").lower()
    object_class = str(hint.get("object_class") or "").lower()
    if object_class and object_class not in container.lower() and object_class not in language:
        return False
    drawer_level = str(hint.get("drawer_level") or "").lower()
    if drawer_level and drawer_level not in language and f"_{drawer_level}" not in container.lower():
        return False
    patterns = hint.get("container_name_matches") or hint.get("name_matches")
    if patterns and not _matches_any(container, patterns):
        return False
    region_patterns = hint.get("region_name_matches") or hint.get("source_region_matches")
    if region_patterns and not _matches_any(atom.args[1], region_patterns):
        return False
    compartment = str(hint.get("compartment") or "").strip().lower()
    if compartment and compartment not in str(atom.args[1]).lower():
        return False
    return True


def _is_known_or_virtual_surface(
    surface: str,
    scene: SceneState,
    recovery_hints: Mapping[str, Any] | None,
    parsed: ParsedTask | None = None,
) -> bool:
    if surface == "table" or surface in scene.objects:
        return True
    if _is_fixed_table_region_surface(surface, parsed, recovery_hints):
        return True
    if _adapter_virtual_surface_declared(surface, scene, parsed, recovery_hints):
        return True
    source = _placement_region_source_name(surface, recovery_hints)
    return bool(source and source in scene.objects)


def _rewrite_fixed_table_region_atom(
    atom: GroundedAtom,
    parsed: ParsedTask,
    target: Optional[str],
    recovery_hints: Mapping[str, Any] | None,
) -> Tuple[GroundedAtom, Dict[str, Any]] | None:
    hint = _fixed_table_region_grounding_hint(recovery_hints)
    region_name = _fixed_table_region_name(recovery_hints) or _dynamic_bddl_table_region_name(
        parsed,
        recovery_hints,
        surface=atom.args[1] if len(atom.args) >= 2 else None,
    )
    if not hint or not region_name:
        return None
    adapter_rewrite = _adapter_fixed_table_region_rewrite(atom, parsed, target, hint, region_name)
    if adapter_rewrite is not None:
        return adapter_rewrite
    obj, surface = atom.args
    language_patterns = hint.get("task_language_matches")
    if language_patterns and not _regex_matches_any(parsed.language, language_patterns):
        return None
    target_patterns = hint.get("target_name_matches") or hint.get("object_name_matches")
    if target_patterns and not (
        _matches_any(obj, target_patterns) or _matches_any(str(target or ""), target_patterns)
    ):
        return None
    if target is not None and obj != target:
        target_patterns = target_patterns or hint.get("allow_non_target_object_name_matches")
        if not target_patterns or not _matches_any(obj, target_patterns):
            return None
    rewrite_patterns = hint.get("rewrite_misgrounded_goals") or hint.get("source_surface_matches")
    surface_is_region = surface == region_name
    if not surface_is_region and rewrite_patterns and not _matches_any(surface, rewrite_patterns):
        return None
    if not surface_is_region and not rewrite_patterns:
        return None
    rewritten = GroundedAtom("on", (obj, region_name))
    return rewritten, {
        "source": "skill_grounding_hint",
        "intent": str(hint.get("intent") or "fixed_table_region"),
        "relation": str(hint.get("relation") or "on"),
        "from": surface,
        "to": region_name,
        "semantic_predicate": atom.predicate,
        "compiled_predicate": "on",
    }


def _rewrite_placement_atom_with_skill_hints(
    atom: GroundedAtom,
    scene: SceneState,
    parsed: ParsedTask,
    target: Optional[str],
    recovery_hints: Mapping[str, Any] | None,
) -> Tuple[GroundedAtom, Dict[str, Any]]:
    if atom.predicate.lower() not in {"on", "inside"} or len(atom.args) != 2:
        return atom, {}
    adapter_rewrite = _adapter_placement_atom_rewrite(atom, scene, parsed, target, recovery_hints)
    if adapter_rewrite is not None:
        return adapter_rewrite
    obj, surface = atom.args
    resolved, grounding = resolve_skill_goal_surface(scene, parsed, target, surface, recovery_hints)
    resolved_surface = resolved if resolved is not None else surface
    rewritten = GroundedAtom(atom.predicate, (obj, resolved_surface))
    fixed_region = _rewrite_fixed_table_region_atom(rewritten, parsed, target, recovery_hints)
    if fixed_region is not None:
        return fixed_region
    source_result = _container_region_source_result(resolved_surface, scene, recovery_hints)
    source_surface = str(source_result.get("source") or "") if source_result else ""
    source_surface = source_surface or resolved_surface
    hint = _placement_region_hint(recovery_hints)
    compartment = _compartment_from_region_name(resolved_surface, hint)
    if _placement_region_applies(source_surface, rewritten, parsed, recovery_hints):
        proxy = _placement_region_proxy_name(source_surface, hint, compartment=compartment)
        rewritten = GroundedAtom("on", (obj, proxy))
        region_grounding = {
            "source": "skill_geometry_hint",
            "intent": str(hint.get("intent") or "drawer_inner_floor"),
            "relation": "inside",
            "from": source_surface,
            "to": proxy,
            "semantic_predicate": atom.predicate,
            "compiled_predicate": "on",
        }
        if compartment:
            region_grounding["compartment"] = compartment
        if source_surface != resolved_surface:
            alias = {
                "from": resolved_surface,
                "to": source_surface,
            }
            if source_result:
                for key, value in source_result.items():
                    if key in {"source", "from"}:
                        continue
                    alias[key] = value
            region_grounding["container_region_alias"] = alias
        if grounding:
            region_grounding["surface_grounding"] = dict(grounding)
        return rewritten, region_grounding
    return rewritten, grounding


def _merge_atoms(*atom_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for atoms in atom_lists:
        for atom in atoms:
            pred, args = atom_key(atom)
            key = (pred, args)
            if key in seen:
                continue
            seen.add(key)
            merged.append(atom)
    return merged


def _has_recovery_atom(recovery: RecoverySymbolicAbstraction, predicate: str, *args: str) -> bool:
    for atom in recovery.atoms:
        pred, atom_args = atom_key(atom)
        if pred != predicate:
            continue
        if args and atom_args != tuple(args):
            continue
        return True
    return False


def _normalize_cutamp_atom_key(predicate: str, args: Tuple[str, ...]) -> Tuple[str, Tuple[str, ...]]:
    pred = str(predicate).replace("_", "").lower()
    norm_args = tuple(str(arg) for arg in args)
    if pred == "handempty":
        return "handempty", ()
    if pred == "holding":
        if len(norm_args) == 2 and norm_args[0].lower() in {"gripper", "hand", "robot"}:
            return "holding", (norm_args[1],)
        return "holding", norm_args
    return pred, norm_args


def _satisfied_init_keys(atoms: List[Dict[str, Any]], min_confidence: float = 0.60) -> Set[Tuple[str, Tuple[str, ...]]]:
    keys: Set[Tuple[str, Tuple[str, ...]]] = set()
    for atom in atoms:
        confidence = float(atom.get("confidence", 1.0)) if isinstance(atom, dict) else 1.0
        if confidence < min_confidence:
            continue
        pred, args = atom_key(atom)
        keys.add(_normalize_cutamp_atom_key(pred, args))
    return keys


def _goal_already_satisfied(goal_atoms: List[GroundedAtom], init_keys: Set[Tuple[str, Tuple[str, ...]]]) -> bool:
    if not goal_atoms:
        return False
    return all(_normalize_cutamp_atom_key(atom.predicate, atom.args) in init_keys for atom in goal_atoms)


def build_recovery_goal_candidates(
    scene: SceneState,
    parsed: ParsedTask,
    sym: SymbolicState,
    task_semantics: TaskSemanticsResult | None = None,
    recovery: RecoverySymbolicAbstraction | None = None,
    graph: SceneGraph | None = None,
    mode: str = "default",
    recovery_hints: Mapping[str, Any] | None = None,
) -> List[RealCuTAMPRecoveryGoal]:
    """Build cuTAMP-native recovery goals.

    TiPToP lets the VLM output goal predicates, then cuTAMP enumerates the plan
    skeletons internally. For recovery we keep the same contract: this function
    only emits On/Inside/Holding/HandEmpty goals that the current cuTAMP domain
    can ground. Order is task-progress placement first, then holding as a
    fallback, then low-disturbance park/clear. Holding is kept so drawer and
    tray tasks can still regrasp when Place has no feasible particles.

    Goals whose fluents are already present in the simulator-truth initial
    state are not emitted. Sending them to cuTAMP produces an empty skeleton
    that is currently misreported as particle initialization failure.
    """
    if recovery is None:
        graph_for_recovery = graph or SceneGraph(
            task_language=parsed.language,
            ee_pos=scene.ee_pos[:3].astype(float).tolist(),
            gripper_open=scene.gripper_open,
            world_atoms=[],
            target=sym.target.name if sym.target is not None else parsed.target_hint,
            goal=sym.goal.name if sym.goal is not None else parsed.goal_hint,
        )
        recovery = build_recovery_symbolic_abstraction(scene, sym, graph_for_recovery)
    target = task_semantics.target_object if task_semantics is not None else None
    goal = task_semantics.goal_object if task_semantics is not None else None
    target = target or recovery.target or (sym.target.name if sym.target is not None else parsed.target_hint)
    goal = goal or recovery.goal or (sym.goal.name if sym.goal is not None else parsed.goal_hint)

    init_atoms: List[Dict[str, Any]] = []
    if graph is not None:
        init_atoms.extend(graph.world_atoms)
    init_atoms.extend(recovery.atoms)
    init_keys = _satisfied_init_keys(init_atoms)

    candidates: List[RealCuTAMPRecoveryGoal] = []
    seen = set()

    def add(
        name: str,
        atoms: List[GroundedAtom],
        surface_names: List[str],
        reason: str,
        grounding: Dict[str, Any] | None = None,
    ) -> None:
        key = tuple((atom.predicate, atom.args) for atom in atoms)
        if not atoms or key in seen:
            return
        if _goal_already_satisfied(atoms, init_keys):
            return
        seen.add(key)
        candidates.append(
            RealCuTAMPRecoveryGoal(
                name=name,
                atoms=atoms,
                surface_names=surface_names,
                reason=reason,
                grounding=dict(grounding or {}),
            )
        )

    def goal_surface_names(atoms: List[GroundedAtom]) -> List[str]:
        return _surface_names_for_goal(atoms, scene, parsed=parsed, target=target, recovery_hints=recovery_hints)

    def goal_grounding(atoms: List[GroundedAtom], base: Dict[str, Any] | None = None) -> Dict[str, Any]:
        grounding = _movable_support_grounding_for_goal(atoms, scene, parsed, target, recovery_hints)
        if base:
            grounding.update(base)
        return grounding

    if mode == "pick_only":
        if target is not None and target in scene.objects:
            add(
                "pick_only_target_holding",
                [GroundedAtom("holding", (target,))],
                [],
                "experiment override: recover by picking the target only, do not finish place",
        )
        return candidates

    # Articulated tasks must not degrade to picking the cabinet or an empty
    # HandEmpty goal. Preserve unresolved bindings so the backend reports them.
    articulated_goals = []
    raw_goals = list((parsed.diagnostics or {}).get("bddl_goal_atoms") or [])
    if task_semantics is not None:
        raw_goals.extend(task_semantics.required_final_atoms)
    for raw in raw_goals:
        atom = _semantic_atom_to_grounded(raw)
        if atom is not None and atom.predicate in {"open", "closed"} and atom not in articulated_goals:
            articulated_goals.append(atom)
    if not articulated_goals and parsed.operation in {"open", "close"} and target:
        articulated_goals = [GroundedAtom("open" if parsed.operation == "open" else "closed", (target,))]
    if articulated_goals:
        # Do not use the legacy name-based open-state heuristic to prune goals.
        return [RealCuTAMPRecoveryGoal(
            name=f"articulation_{a.predicate}_{a.args[0]}",
            atoms=[a, GroundedAtom("handempty", ())], surface_names=[],
            reason="native articulated recovery subgoal; remaining task goals are not claimed solved",
        ) for a in articulated_goals]

    strict_fixed_table_region = _strict_fixed_table_region_goal(recovery_hints)
    placement_pred = _task_placement_predicate(task_semantics)
    bddl_placement: List[GroundedAtom] = []
    semantic_placement: List[GroundedAtom] = []
    semantic_holding: List[Tuple[int, GroundedAtom]] = []
    for raw_atom in (parsed.diagnostics or {}).get("bddl_goal_atoms") or []:
        grounded = _semantic_atom_to_grounded(raw_atom)
        if grounded is not None and grounded.predicate in {"on", "inside"}:
            bddl_placement.append(grounded)
    if task_semantics is not None:
        for idx, raw_atom in enumerate(task_semantics.required_final_atoms):
            grounded = _semantic_atom_to_grounded(raw_atom)
            if grounded is None:
                continue
            if grounded.predicate in {"on", "inside"}:
                semantic_placement.append(grounded)
            elif grounded.predicate == "holding":
                semantic_holding.append((idx, grounded))

    for idx, grounded in enumerate(bddl_placement):
        grounded, grounding = _rewrite_placement_atom_with_skill_hints(grounded, scene, parsed, target, recovery_hints)
        obj, surface = grounded.args
        if obj not in scene.objects or not _is_known_or_virtual_surface(surface, scene, recovery_hints, parsed):
            continue
        atoms = [grounded, GroundedAtom("handempty", ())]
        add(
            f"bddl_required_{idx}_{grounded.predicate}_{obj}_to_{surface}",
            atoms,
            goal_surface_names(atoms),
            "BDDL placement atom converted to a cuTAMP-native recovery goal",
            grounding=goal_grounding(atoms, grounding),
        )

    for idx, grounded in enumerate(semantic_placement):
        grounded, grounding = _rewrite_placement_atom_with_skill_hints(grounded, scene, parsed, target, recovery_hints)
        obj, surface = grounded.args
        if obj not in scene.objects or not _is_known_or_virtual_surface(surface, scene, recovery_hints, parsed):
            continue
        atoms = [grounded, GroundedAtom("handempty", ())]
        add(
            f"llm_required_{idx}_{grounded.predicate}_{obj}_to_{surface}",
            atoms,
            goal_surface_names(atoms),
            "single required_final placement atom converted to a cuTAMP-native goal",
            grounding=goal_grounding(atoms, grounding),
        )
    if len(semantic_placement) > 1:
        rewritten_atoms = [
            _rewrite_placement_atom_with_skill_hints(atom, scene, parsed, target, recovery_hints)[0]
            for atom in semantic_placement
        ]
        atoms = [*rewritten_atoms, GroundedAtom("handempty", ())]
        add(
            "llm_required_all_placement_atoms",
            atoms,
            goal_surface_names(atoms),
            "all placement required_final atoms converted to one cuTAMP goal",
            grounding=goal_grounding(atoms),
        )

    if target is not None and target in scene.objects and goal is not None and goal in scene.objects:
        raw_atom = GroundedAtom(placement_pred, (target, goal))
        rewritten_atom, grounding = _rewrite_placement_atom_with_skill_hints(
            raw_atom, scene, parsed, target, recovery_hints
        )
        goal_for_plan = rewritten_atom.args[1]
        if _has_recovery_atom(recovery, "target_not_at_goal", target, goal) or _has_recovery_atom(
            recovery, "target_not_at_goal", target, goal_for_plan
        ):
            atoms = [rewritten_atom, GroundedAtom("handempty", ())]
            add(
                "recovery_finish_target_to_goal",
                atoms,
                goal_surface_names(atoms),
                "target is not at the task goal; ask cuTAMP to optimize a pick/place recovery",
                grounding=goal_grounding(atoms, grounding),
            )

    if target is not None and target in scene.objects and goal is not None and goal in scene.objects:
        raw_atom = GroundedAtom(placement_pred, (target, goal))
        rewritten_atom, grounding = _rewrite_placement_atom_with_skill_hints(
            raw_atom, scene, parsed, target, recovery_hints
        )
        atoms = [rewritten_atom, GroundedAtom("handempty", ())]
        add(
            "task_goal_on_surface",
            atoms,
            goal_surface_names(atoms),
            "attempt task-progress recovery with cuTAMP-native On/Inside goal",
            grounding=goal_grounding(atoms, grounding),
        )

    for idx, grounded in semantic_holding:
        obj = grounded.args[0]
        if obj not in scene.objects:
            continue
        add(
            f"llm_required_{idx}_holding_{obj}",
            [grounded],
            [],
            "single required_final holding atom converted to a cuTAMP-native goal",
        )

    if target is not None and target in scene.objects:
        if _has_recovery_atom(recovery, "stuck_like") or _has_recovery_atom(recovery, "near_gripper", target):
            add(
                "recovery_regain_target_holding",
                [GroundedAtom("holding", (target,))],
                [],
                "recovery atoms indicate nearby/stuck contact; fallback to a grasp skeleton after Place",
            )
        add(
            "regain_target_holding",
            [GroundedAtom("holding", (target,))],
            [],
            "recover object control by asking cuTAMP to grasp the target",
        )
        if not strict_fixed_table_region:
            add(
                "recovery_park_target_on_table",
                [GroundedAtom("on", (target, "table")), GroundedAtom("handempty", ())],
                ["table"],
                "safe low-disturbance recovery state: put the target on the table before handing back to VLA",
            )

    for obstacle in recovery.movable_obstacles[:2]:
        if obstacle in scene.objects and obstacle != target:
            add(
                f"recovery_clear_{obstacle}_to_table",
                [GroundedAtom("on", (obstacle, "table")), GroundedAtom("handempty", ())],
                ["table"],
                "movable obstacle is near the target; let cuTAMP search a clear-and-place skeleton for that object",
            )

    if target is not None and target in scene.objects and not strict_fixed_table_region:
        add(
            "park_target_on_table",
            [GroundedAtom("on", (target, "table")), GroundedAtom("handempty", ())],
            ["table"],
            "park target on the table as a low-disturbance state for VLA handoff",
        )

    if not candidates:
        add(
            "handempty_reset",
            [GroundedAtom("handempty", ())],
            ["table"],
            "fallback to a gripper-empty state when no target can be grounded",
        )
    return candidates


class RealCuTAMPRecoveryPlanner:
    """Try cuTAMP-native recovery goals before falling back to TiPToP-lite."""

    def __init__(
        self,
        cfg: RealCuTAMPBackendConfig | None = None,
        backend: RealCuTAMPBackend | None = None,
        llm_goal_generator: Any | None = None,
    ) -> None:
        self.backend = backend or RealCuTAMPBackend(cfg or RealCuTAMPBackendConfig())
        self.llm_goal_generator = llm_goal_generator
        self.goal_mode = "default"

    def plan(
        self,
        scene: SceneState,
        parsed: ParsedTask,
        sym: SymbolicState,
        graph: SceneGraph,
        task_semantics: TaskSemanticsResult | None = None,
        recovery_hints: Mapping[str, Any] | None = None,
    ) -> RealCuTAMPRecoveryPlan:
        attempts: List[RealCuTAMPRecoveryAttempt] = []
        hints = dict(recovery_hints or {})
        if self.backend.cfg.articulation_options:
            hints["articulation"] = dict(self.backend.cfg.articulation_options)
        recovery = build_recovery_symbolic_abstraction(scene, sym, graph)
        llm_diag: Dict[str, Any] = {}
        llm_goals: List[RealCuTAMPRecoveryGoal] = []
        if self.goal_mode != "pick_only" and self.llm_goal_generator is not None:
            llm_goals, diag = self.llm_goal_generator.propose(scene, parsed, sym, graph, task_semantics, recovery)
            llm_diag = diag.to_dict()
        rule_goals = build_recovery_goal_candidates(
            scene,
            parsed,
            sym,
            task_semantics,
            recovery=recovery,
            graph=graph,
            mode=self.goal_mode,
            recovery_hints=hints,
        )
        goals: List[RealCuTAMPRecoveryGoal] = []
        seen_goal_keys = set()
        for source, source_goals in (("llm", llm_goals), ("rule", rule_goals)):
            if source == "llm" and any(g.name.startswith("articulation_") for g in rule_goals):
                continue  # Do not replace explicit joint goals with a pick/place fallback.
            for goal in source_goals:
                key = tuple((atom.predicate, atom.args) for atom in goal.atoms)
                if key in seen_goal_keys:
                    continue
                seen_goal_keys.add(key)
                if source == "llm":
                    goal = RealCuTAMPRecoveryGoal(
                        name=goal.name,
                        atoms=goal.atoms,
                        surface_names=goal.surface_names,
                        reason=f"llm_guided:{goal.reason}",
                        grounding=goal.grounding,
                    )
                goals.append(goal)
        for goal in goals:
            required_atoms = [_atom_dict(atom) for atom in goal.atoms]
            problem = build_tamp_problem(
                scene,
                parsed,
                sym,
                goal_atoms_override=goal.atoms,
                surface_names=goal.surface_names,
                init_atoms=_merge_atoms(graph.world_atoms, recovery.atoms),
                required_final_atoms=_merge_atoms(required_atoms),
                recovery_hints=hints,
            )
            result = self.backend.solve(problem, recovery_hints=hints)
            if llm_diag:
                result.diagnostics["llm_recovery_goal_generator"] = llm_diag
            attempt = RealCuTAMPRecoveryAttempt(goal=goal, result=result, problem=problem)
            attempts.append(attempt)
            if result.available and result.feasible:
                return RealCuTAMPRecoveryPlan(feasible=True, selected=attempt, attempts=attempts, rule_goals=rule_goals)
        reason = "real_cutamp_no_feasible_goal" if attempts else "real_cutamp_no_recovery_goals"
        return RealCuTAMPRecoveryPlan(
            feasible=False, selected=None, attempts=attempts, fallback_reason=reason, rule_goals=rule_goals
        )
