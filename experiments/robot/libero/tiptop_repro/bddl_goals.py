"""Read LIBERO BDDL task hints and map object names onto the live scene."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


_GOAL_PREDICATES = {"on", "in", "inside", "holding", "open", "closed", "handempty"}
_FLOAT_RE = re.compile(r"^-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def bddl_source_from_env(env: Any) -> Optional[str]:
    seen: set[int] = set()
    current = env
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        for attr in ("bddl_file_name", "bddl_file"):
            value = getattr(current, attr, None)
            if value:
                return str(value)
        current = getattr(current, "env", None) or getattr(current, "unwrapped", None)
    return None


def _matching_paren(text: str, open_idx: int) -> int:
    depth = 0
    for idx in range(open_idx, len(text)):
        char = text[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _section_body(text: str, heading: str) -> Optional[str]:
    needle = f"(:{heading}"
    start = text.lower().find(needle.lower())
    if start < 0:
        return None
    end = _matching_paren(text, start)
    if end < 0:
        return None
    inner = text[start + len(needle) : end].strip()
    return inner


def _tokenize(body: str) -> List[str]:
    tokens: List[str] = []
    buf: List[str] = []
    for char in body:
        if char in "()":
            if buf:
                tokens.append("".join(buf))
                buf = []
            tokens.append(char)
        elif char.isspace():
            if buf:
                tokens.append("".join(buf))
                buf = []
        else:
            buf.append(char)
    if buf:
        tokens.append("".join(buf))
    return tokens


def _parse_sexpr(tokens: Sequence[str], idx: int = 0) -> tuple[Any, int]:
    if idx >= len(tokens):
        return None, idx
    token = tokens[idx]
    if token != "(":
        return token, idx + 1
    out: List[Any] = []
    idx += 1
    while idx < len(tokens) and tokens[idx] != ")":
        child, idx = _parse_sexpr(tokens, idx)
        if child is not None:
            out.append(child)
    if idx < len(tokens) and tokens[idx] == ")":
        idx += 1
    return out, idx


def _top_level_forms(body: str) -> List[List[Any]]:
    tokens = _tokenize(body or "")
    forms: List[List[Any]] = []
    idx = 0
    while idx < len(tokens):
        if tokens[idx] != "(":
            idx += 1
            continue
        form, idx = _parse_sexpr(tokens, idx)
        if isinstance(form, list) and form:
            forms.append(form)
    return forms


def _flatten_floats(node: Any) -> List[float]:
    out: List[float] = []
    if isinstance(node, list):
        for item in node:
            out.extend(_flatten_floats(item))
        return out
    raw = str(node)
    if not _FLOAT_RE.match(raw):
        return out
    try:
        out.append(float(raw))
    except ValueError:
        pass
    return out


def _parse_goal_atoms(body: str) -> List[Dict[str, Any]]:
    tokens = _tokenize(body)
    atoms: List[Dict[str, Any]] = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token != "(":
            idx += 1
            continue
        if idx + 1 >= len(tokens):
            break
        pred = tokens[idx + 1]
        normalized_pred = pred.lower()
        if normalized_pred == "and":
            idx += 2
            continue
        if normalized_pred not in _GOAL_PREDICATES:
            idx += 1
            continue
        if normalized_pred == "in":
            normalized_pred = "inside"
        args: List[str] = []
        cursor = idx + 2
        while cursor < len(tokens) and tokens[cursor] != ")":
            if tokens[cursor] != "(":
                args.append(tokens[cursor])
            cursor += 1
        atoms.append({"predicate": normalized_pred, "args": args})
        idx = cursor + 1
    return atoms


def _parse_regions(body: str) -> Dict[str, Dict[str, Any]]:
    regions: Dict[str, Dict[str, Any]] = {}
    for form in _top_level_forms(body or ""):
        name = str(form[0]) if form else ""
        if not name:
            continue
        target = ""
        ranges: List[float] = []
        for child in form[1:]:
            if not isinstance(child, list) or not child:
                continue
            key = str(child[0]).lower()
            if key == ":target" and len(child) >= 2:
                target = str(child[1])
            elif key == ":ranges":
                ranges = _flatten_floats(child[1:])
        qualified = f"{target}_{name}" if target and not name.startswith(f"{target}_") else name
        entry = {
            "name": name,
            "target": target,
            "qualified_name": qualified,
            "ranges": ranges,
        }
        regions[name] = entry
        regions[qualified] = entry
    return regions


def _placement_goal_surfaces(atoms: Sequence[Dict[str, Any]]) -> List[str]:
    surfaces: List[str] = []
    seen = set()
    for atom in atoms:
        pred = str(atom.get("predicate") or "").lower()
        args = list(atom.get("args") or [])
        if pred not in {"on", "inside"} or len(args) < 2:
            continue
        surface = str(args[1])
        if surface in seen:
            continue
        seen.add(surface)
        surfaces.append(surface)
    return surfaces


def parse_bddl_task_goals(text: str) -> Dict[str, Any]:
    language_body = _section_body(text, "language")
    interest_body = _section_body(text, "obj_of_interest")
    goal_body = _section_body(text, "goal")
    init_body = _section_body(text, "init")
    regions_body = _section_body(text, "regions")
    interest = [tok for tok in _tokenize(interest_body or "") if tok not in {"(", ")"}]
    goal_atoms = _parse_goal_atoms(goal_body or "")
    return {
        "language": " ".join((language_body or "").split()),
        "obj_of_interest": interest,
        "goal_atoms": goal_atoms,
        "goal_surfaces": _placement_goal_surfaces(goal_atoms),
        "init_atoms": _parse_goal_atoms(init_body or ""),
        "regions": _parse_regions(regions_body or ""),
    }


def map_bddl_name_to_scene(bddl_name: str, object_names: Iterable[str]) -> Optional[str]:
    names = list(object_names)
    if not bddl_name:
        return None
    if bddl_name in names:
        return bddl_name
    if bddl_name.endswith("_top_side"):
        prefix = bddl_name[: -len("_top_side")]
        for candidate in (
            f"{prefix}_cabinet_top",
            f"{prefix}_top",
            f"{prefix}_main",
        ):
            if candidate in names:
                return candidate
    main = f"{bddl_name}_main"
    if main in names:
        return main
    hits = [name for name in names if name == bddl_name or name.startswith(f"{bddl_name}_")]
    if len(hits) == 1:
        return hits[0]
    mains = [name for name in hits if name.endswith("_main")]
    if len(mains) == 1:
        return mains[0]
    return None


def _mapped_atoms(atoms: Sequence[Dict[str, Any]], object_names: Sequence[str]) -> List[Dict[str, Any]]:
    mapped: List[Dict[str, Any]] = []
    for atom in atoms:
        args = [map_bddl_name_to_scene(str(arg), object_names) or str(arg) for arg in atom.get("args") or []]
        mapped.append({"predicate": atom.get("predicate"), "args": args})
    return mapped


def resolve_bddl_target_and_goal(
    parsed: Dict[str, Any],
    object_names: Iterable[str],
) -> Dict[str, Any]:
    names = list(object_names)
    target = None
    goal = None
    for atom in parsed.get("goal_atoms") or []:
        pred = str(atom.get("predicate") or "").lower()
        args = list(atom.get("args") or [])
        if pred in {"on", "inside"} and len(args) >= 2:
            target = map_bddl_name_to_scene(args[0], names)
            goal = map_bddl_name_to_scene(args[1], names)
            if goal is None and str(args[1]).lower() == "table":
                goal = "table"
            break
        if pred == "holding" and args:
            target = map_bddl_name_to_scene(args[-1], names)
            if target is not None:
                break
    if target is None:
        for raw in parsed.get("obj_of_interest") or []:
            mapped = map_bddl_name_to_scene(str(raw), names)
            if mapped is not None:
                target = mapped
                break
    if goal is None:
        interest = list(parsed.get("obj_of_interest") or [])
        if len(interest) >= 2:
            goal = map_bddl_name_to_scene(str(interest[1]), names)
    goal_atoms = _mapped_atoms(parsed.get("goal_atoms") or [], names)
    init_atoms = _mapped_atoms(parsed.get("init_atoms") or [], names)
    return {
        "target": target,
        "goal": goal,
        "obj_of_interest": list(parsed.get("obj_of_interest") or []),
        "goal_atoms": goal_atoms,
        "goal_surfaces": _placement_goal_surfaces(goal_atoms),
        "init_atoms": init_atoms,
        "regions": dict(parsed.get("regions") or {}),
        "language": parsed.get("language") or "",
    }


def load_bddl_hints(
    object_names: Iterable[str],
    *,
    bddl_text: Optional[str] = None,
    bddl_path: Optional[str] = None,
    env: Any = None,
) -> Dict[str, Any]:
    path = bddl_path or (bddl_source_from_env(env) if env is not None else None)
    text = bddl_text
    if text is None and path:
        file_path = Path(path)
        if file_path.is_file():
            text = file_path.read_text(encoding="utf-8")
    if not text:
        return {
            "target": None,
            "goal": None,
            "source": path,
            "goal_atoms": [],
            "goal_surfaces": [],
            "init_atoms": [],
            "regions": {},
            "obj_of_interest": [],
        }
    resolved = resolve_bddl_target_and_goal(parse_bddl_task_goals(text), object_names)
    resolved["source"] = path
    return resolved
