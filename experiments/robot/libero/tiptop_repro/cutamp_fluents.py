from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

from .scene_graph import Atom


@dataclass(frozen=True)
class CutampFluent:
    predicate: str
    args: Tuple[str, ...]
    source_predicate: str
    approximated: bool = False
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predicate": self.predicate,
            "args": list(self.args),
            "source_predicate": self.source_predicate,
            "approximated": self.approximated,
            "note": self.note,
        }


@dataclass
class FluentMappingResult:
    fluents: List[CutampFluent] = field(default_factory=list)
    diagnostics: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"fluents": [fluent.to_dict() for fluent in self.fluents], "diagnostics": list(self.diagnostics)}


CUTAMP_NATIVE_PREDICATES = {
    "open",
    "closed",
    "at",
    "handempty",
    "canmove",
    "justmoved",
    "holding",
    "holdingwithgrasp",
    "buttonpushed",
    "pushedwithstick",
    "canpush",
    "ismovable",
    "isbutton",
    "issurface",
    "isstick",
    "hasnotpickedup",
    "on",
}


def _atom_parts(atom: Any) -> Tuple[str, Tuple[str, ...]]:
    if hasattr(atom, "predicate") and hasattr(atom, "args"):
        return str(atom.predicate).replace("_", "").lower(), tuple(str(arg) for arg in atom.args)
    return str(atom.get("predicate", "")).replace("_", "").lower(), tuple(str(arg) for arg in atom.get("args", []))


def _add(
    result: FluentMappingResult,
    predicate: str,
    args: Tuple[str, ...] = (),
    source_predicate: str = "",
    approximated: bool = False,
    note: str = "",
) -> None:
    predicate = predicate.replace("_", "").lower()
    if predicate not in CUTAMP_NATIVE_PREDICATES:
        result.diagnostics.append(f"ignored non-cuTAMP predicate: {predicate}{args}")
        return
    result.fluents.append(CutampFluent(predicate, tuple(args), source_predicate or predicate, approximated, note))


def _map_type_fact(result: FluentMappingResult, pred: str, args: Tuple[str, ...]) -> bool:
    if pred not in {"category", "affordance"} or len(args) < 2:
        return False
    obj, typ = args[0], args[1].lower()
    if typ in {"movable", "object", "container"}:
        _add(result, "ismovable", (obj,), pred)
    if typ in {"surface", "container", "receptacle", "basket", "bowl", "plate", "table"}:
        _add(result, "issurface", (obj,), pred)
    if typ in {"button", "switch"}:
        _add(result, "isbutton", (obj,), pred)
        _add(result, "canpush", (obj,), pred)
    if typ in {"stick", "tool"}:
        _add(result, "isstick", (obj,), pred)
        _add(result, "ismovable", (obj,), pred)
    if not result.fluents:
        result.diagnostics.append(f"ignored type atom: {pred}{args}")
    return True


def map_atom_to_cutamp(atom: Any, allow_approximations: bool = True) -> FluentMappingResult:
    pred, args = _atom_parts(atom)
    result = FluentMappingResult()

    if pred == "requiresfinal" and args:
        nested = {"predicate": args[0], "args": list(args[1:])}
        nested_result = map_atom_to_cutamp(nested, allow_approximations=allow_approximations)
        result.fluents.extend(nested_result.fluents)
        result.diagnostics.extend(nested_result.diagnostics)
        return result

    if _map_type_fact(result, pred, args):
        return result

    if pred == "handempty":
        _add(result, "handempty", (), pred)
    elif pred == "holding":
        if len(args) == 1:
            _add(result, "holding", (args[0],), pred)
        elif len(args) == 2 and args[0].lower() in {"gripper", "hand", "robot"}:
            _add(result, "holding", (args[1],), pred, approximated=True, note="dropped gripper argument for cuTAMP Holding(obj)")
        else:
            result.diagnostics.append(f"bad holding arity: {pred}{args}")
    elif pred == "holdingwithgrasp" and len(args) >= 2:
        if len(args) == 3 and args[0].lower() in {"gripper", "hand", "robot"}:
            _add(result, "holdingwithgrasp", (args[1], args[2]), pred, approximated=True, note="dropped gripper argument for cuTAMP HoldingWithGrasp(obj, grasp)")
        else:
            _add(result, "holdingwithgrasp", (args[0], args[1]), pred)
    elif pred == "on" and len(args) == 2:
        _add(result, "on", args, pred)
    elif pred == "inside" and len(args) == 2:
        if allow_approximations:
            _add(result, "on", args, pred, approximated=True, note="inside approximated as cuTAMP On(obj, container_surface)")
            result.diagnostics.append(f"approximated inside{args} -> on{args}; container surface is represented by type_to_objects")
        else:
            result.diagnostics.append(f"inside has no native cuTAMP fluent: {pred}{args}")
    elif pred == "at" and len(args) == 1:
        _add(result, "at", (args[0],), pred)
    elif pred in {"canmove", "justmoved"}:
        _add(result, pred, (), pred)
    elif pred == "buttonpushed" and len(args) == 1:
        _add(result, "buttonpushed", (args[0],), pred)
    elif pred == "pushedwithstick" and len(args) == 2:
        _add(result, "pushedwithstick", args, pred)
    elif pred == "canpush" and len(args) == 1:
        _add(result, "canpush", (args[0],), pred)
    elif pred in {"ismovable", "isbutton", "issurface", "isstick", "hasnotpickedup"} and len(args) == 1:
        _add(result, pred, (args[0],), pred)
    elif pred in {"open", "closed"} and len(args) == 1:
        _add(result, pred, args, pred, note="requires experimental articulated domain; never drop this goal")
    elif pred in {"near", "geometryproxy", "target", "goal", "goalcontainer"}:
        result.diagnostics.append(f"{pred}{args} kept in semantic/geometric layer; skipped for cuTAMP native fluent set")
    else:
        result.diagnostics.append(f"ignored non-planning atom: {pred}{args}")
    return result


def map_atoms_to_cutamp(atoms: Sequence[Any], allow_approximations: bool = True) -> FluentMappingResult:
    merged = FluentMappingResult()
    seen = set()
    for atom in atoms:
        item = map_atom_to_cutamp(atom, allow_approximations=allow_approximations)
        for fluent in item.fluents:
            key = (fluent.predicate, fluent.args)
            if key not in seen:
                seen.add(key)
                merged.fluents.append(fluent)
        merged.diagnostics.extend(item.diagnostics)
    return merged
