"""Resolve a task's target/goal from the task language plus a MuJoCo scene snapshot.

This is the ``language_mujoco`` half of the BDDL goal-isolation boundary
(``docs/bddl_goal_context_migration_implementation_plan.md``, sections 3-6). It
returns the same dict shape as
``experiments.robot.libero.tiptop_repro.bddl_goals.load_bddl_hints`` so that
``parse_task()`` and every downstream consumer stay unchanged.

Contract
--------
* Input: the task language (the exact sentence handed to the policy) and an
  initial ``SceneState`` from ``scene_reader.read_scene()``.
* Output: ``target`` / ``goal`` / ``obj_of_interest`` / ``goal_atoms`` /
  ``goal_surfaces`` / ``init_atoms`` / ``regions`` / ``language`` / ``source``,
  with ``source == "language_mujoco"``.
* This module never reads BDDL and never falls back to it. Every failure is
  explicit via ``failure_reason`` and leaves the goal fields empty, so the
  caller can disable goal-dependent recovery for that episode instead of acting
  on a guessed goal.
* Binding must happen once per episode, right after reset: relations such as
  ``on the cookies box`` stop holding as soon as the policy moves an object.

Scope of this first slice
-------------------------
Supported: object goals (``on`` / ``inside``) whose target is described by a
category plus a scene relation (``on`` / ``in`` / ``next to`` / ``between`` /
``not between`` / ``from table center``).

Deliberately refused, with an explicit reason instead of a guess:

* goal *regions* (``to the front of the stove``, ``to the left of the plate``,
  ``under the cabinet shelf``) and goal references to a fixture that exposes
  named region sites (``cook_region``, ``top_region``, ``top_side``, ...);
* frame-dependent direction words (``on the left plate``, ``the black bowl in
  the middle``) unless the described category has exactly one instance;
* non-placement actions (``open the top drawer``, ``turn on the stove``).

Both need the frame/region conventions that are being audited separately.

Tolerances (``CONTACT_TOL_M``, ``NEAR_MARGIN_M``) absorb MuJoCo resting
penetration and the AABB approximation of mesh geometry. They are not task or
region geometry constants, and every use is recorded in ``binding_evidence``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

SOURCE = "language_mujoco"

FAILURE_PARSE = "language_goal_parse_failed"
FAILURE_ACTION = "language_goal_action_unsupported"
FAILURE_REGION = "language_goal_region_unsupported"
FAILURE_DIRECTION = "language_goal_direction_unsupported"
FAILURE_AMBIGUOUS = "language_goal_binding_ambiguous"
FAILURE_TARGET_NOT_FOUND = "language_goal_target_not_found"
FAILURE_GOAL_NOT_FOUND = "language_goal_goal_not_found"

CONTACT_TOL_M = 0.02
NEAR_MARGIN_M = 0.06
DEFAULT_HALF_EXTENT_M = 0.03
BETWEEN_T_RANGE = (0.15, 0.85)

_MAIN_SUFFIX = "_main"
_INSTANCE_RE = re.compile(r"^(?P<stem>.+?)_(?P<idx>\d+)$")

_CLAUSE_SPLITTERS = (
    " and then place it ",
    " and then put it ",
    " and place it ",
    " and put it ",
    " then place it ",
    " then put it ",
    " and place ",
    " and put ",
)
_LEADING_VERBS = (
    "pick up",
    "pick",
    "grab",
    "take",
    "get",
    "put",
    "place",
    "move",
    "stack",
    "push",
    "slide",
)
_STOPWORDS = frozenset({"the", "a", "an", "of", "it", "and", "then", "that", "is", "at", "with"})
_DIRECTION_WORDS = frozenset({"left", "right", "middle", "front", "back", "behind", "center", "centre"})
_NON_PLACEMENT_ACTIONS = ("open", "close", "turn on", "turn off")
_PREPOSITIONS = ("onto", "into", "inside", "on", "in")
_PREP_TO_PREDICATE = {"on": "on", "onto": "on", "in": "inside", "into": "inside", "inside": "inside"}
_REGION_SITE_SUFFIXES = (
    "_cook_region",
    "_top_region",
    "_bottom_region",
    "_heating_region",
    "_contain_region",
    "_top_side",
)
# Goal clauses containing these always denote a region or a fixture sub-surface
# rather than a plain object (see the module docstring).
_GOAL_REGION_KEYWORDS = (
    "under",
    "in front of",
    "front of",
    "left of",
    "right of",
    "back of",
    "behind",
    "top of",
    "layer",
    "drawer",
    "shelf",
)
_SUPPORT_QUALIFIERS = frozenset({"top", "layer", "bottom", "side", "shelf"})
_TO_GUARDS = frozenset({"next", "up", "close", "due", "belongs"})
_DIRECTION_PHRASE_RE = re.compile(
    r"\b(?:in|on|at|to)?\s*(?:the\s+)?(?:left|right|middle|front|back|behind|center|centre)\b"
)

# Irregular language -> scene-category spellings. Everything else is matched by
# normalized name: exact, then alias, then longest unique substring.
_CATEGORY_ALIASES: Dict[str, str] = {
    "cookie_box": "cookies",
    "cookies_box": "cookies",
    "cream_cheese_box": "cream_cheese",
    "yellow_and_white_mug": "white_yellow_mug",
    "white_and_yellow_mug": "white_yellow_mug",
    "white_mug": "porcelain_mug",
    "red_mug": "red_coffee_mug",
    "book": "black_book",
    "cabinet": "wooden_cabinet",
    "drawer": "wooden_cabinet",
    "stove": "flat_stove",
    "caddy": "desk_caddy",
    "ketchup_bottle": "ketchup",
}


def _not_found(role: str) -> str:
    """Failure-reason family for a reference role ('target', 'target_ref', ...)."""
    return FAILURE_TARGET_NOT_FOUND if str(role).startswith("target") else FAILURE_GOAL_NOT_FOUND


def resolve_language_mujoco_hints(language: str, scene: Any) -> Dict[str, Any]:
    """Return BDDL-shaped goal hints derived from ``language`` and ``scene``.

    ``scene`` must expose ``.objects`` (name -> object with ``.pos`` and optional
    ``.geometry``, see ``scene_reader.read_scene``).
    """
    text = str(language or "")
    result = _empty_result(text)
    evidence: Dict[str, Any] = {}

    def fail(reason: str, detail: str) -> Dict[str, Any]:
        # Keep whatever the binder already measured: a refused goal must still
        # be diagnosable from the trace.
        if evidence:
            result["binding_evidence"] = evidence
        return _fail(result, reason, detail)

    if not text.strip():
        return fail(FAILURE_PARSE, "empty language")
    if scene is None or not getattr(scene, "objects", None):
        return fail(FAILURE_PARSE, "scene has no objects")

    categories = _scene_categories(scene)
    if not categories:
        return fail(FAILURE_PARSE, "no categorisable scene objects")

    parsed, reason = _parse_language(text)
    result["parsed_language"] = parsed or {}
    if parsed is None:
        return fail(reason or FAILURE_PARSE, "language could not be parsed")

    target, why = _bind_target(scene, categories, parsed["target"], evidence)
    if target is None:
        return fail(why or FAILURE_TARGET_NOT_FOUND, "target binding failed")

    goal_spec = parsed["goal"]
    if goal_spec.get("region"):
        return fail(FAILURE_REGION, str(goal_spec.get("region_detail") or "goal region"))
    goal, why = _bind_goal(scene, categories, goal_spec, evidence)
    if goal is None:
        return fail(why or FAILURE_GOAL_NOT_FOUND, "goal binding failed")
    if goal == target:
        return fail(FAILURE_GOAL_NOT_FOUND, "goal resolved to the target object")

    predicate = _PREP_TO_PREDICATE[str(goal_spec["relation"])]
    goal_atoms = [{"predicate": predicate, "args": [target, goal]}]

    result.update(
        {
            "target": target,
            "goal": goal,
            "obj_of_interest": [target, goal],
            "goal_atoms": goal_atoms,
            "goal_surfaces": _placement_goal_surfaces(goal_atoms),
            "init_atoms": [],
            "regions": {},
            "binding_evidence": evidence,
        }
    )
    return result


# ---------------------------------------------------------------------------
# language parsing
# ---------------------------------------------------------------------------


def _parse_language(language: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    low = " " + _normalize_text(language) + " "
    for action in _NON_PLACEMENT_ACTIONS:
        if low.strip().startswith(action):
            return None, FAILURE_ACTION

    target_text, goal_text = _split_clauses(low)
    if target_text is None or not goal_text.strip():
        return None, FAILURE_PARSE

    target = _parse_target_clause(target_text)
    goal = _parse_goal_clause(goal_text)
    if target is None or goal is None:
        return None, FAILURE_PARSE
    return {"action": "pick_place", "target": target, "goal": goal}, None


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", str(text).lower())).strip()


def _split_clauses(low: str) -> Tuple[Optional[str], str]:
    for splitter in _CLAUSE_SPLITTERS:
        index = low.find(splitter)
        if index >= 0:
            return low[:index], low[index + len(splitter) :]
    tokens = low.split()
    for index, token in enumerate(tokens):
        if token in _PREPOSITIONS and index > 0:
            return " ".join(tokens[:index]), " ".join(tokens[index:])
    # "put the chocolate pudding to the left of the plate": no on/in preposition
    # before the goal, so split on the last free-standing " to ".
    for index in range(len(tokens) - 1, 0, -1):
        if tokens[index] != "to" or tokens[index - 1] in _TO_GUARDS:
            continue
        return " ".join(tokens[:index]), " ".join(tokens[index:])
    return None, ""


def _parse_target_clause(clause: str) -> Optional[Dict[str, Any]]:
    # Selector first, stopword removal afterwards: phrases such as
    # "between the plate and the ramekin" and "on top of the cabinet" need their
    # stopwords to stay splittable.
    tokens = _strip_leading_verbs([t for t in clause.split() if t])
    if not tokens:
        return None
    spec = _parse_selector(tokens)
    spec["tokens"] = _clean(spec.get("phrase") or [])
    spec["direction"] = [t for t in spec["tokens"] if t in _DIRECTION_WORDS]
    spec["tokens"] = [t for t in spec["tokens"] if t not in _DIRECTION_WORDS]
    for key in ("ref", "ref_a", "ref_b"):
        if key in spec:
            spec[key] = [t for t in _clean(spec[key]) if t not in _DIRECTION_WORDS]
    if not spec["tokens"]:
        return None
    return spec


def _parse_goal_clause(clause: str) -> Optional[Dict[str, Any]]:
    tokens = _strip_leading_verbs([t for t in clause.split() if t])
    if not tokens:
        return None

    joined = " ".join(tokens)
    # Goal *regions*: "to the front of the stove", "under the cabinet shelf",
    # "in the top layer of the wooden cabinet", "on top of the cabinet". These
    # need the region conventions audited separately, so refuse explicitly.
    for keyword in _GOAL_REGION_KEYWORDS:
        if keyword in joined:
            return {"relation": "on", "tokens": [], "direction": [], "region": True,
                    "region_detail": f"goal clause contains {keyword!r}"}

    relation = None
    rest: List[str] = tokens
    for index, token in enumerate(tokens):
        if token in _PREPOSITIONS:
            relation = _PREP_TO_PREDICATE[token]
            rest = tokens[index + 1 :]
            break
    if relation is None:
        return {"relation": "on", "tokens": [], "direction": [], "region": True,
                "region_detail": "no placement preposition in goal clause"}

    rest = list(rest)
    if rest[:2] == ["top", "of"]:
        rest = rest[2:]

    direction = [t for t in rest if t in _DIRECTION_WORDS]
    if direction:
        position = next(i for i, t in enumerate(rest) if t in _DIRECTION_WORDS)
        after = rest[position + 1 :]
        if after and after[0] == "of":
            return {"relation": relation, "tokens": [], "direction": direction, "region": True,
                    "region_detail": f"direction {direction[0]!r} followed by 'of'"}

    body = [
        t
        for t in _clean(_DIRECTION_PHRASE_RE.sub(" ", " ".join(rest)).split())
        if t not in _SUPPORT_QUALIFIERS
    ]
    if not body:
        return None
    return {"relation": relation, "tokens": body, "direction": direction, "region": False}


def _clean(tokens: Sequence[str]) -> List[str]:
    return [str(t) for t in tokens if t and str(t) not in _STOPWORDS]


def _strip_leading_verbs(tokens: Sequence[str]) -> List[str]:
    out = list(tokens)
    while out:
        joined = " ".join(out)
        matched = None
        for verb in _LEADING_VERBS:
            if joined.startswith(verb + " "):
                matched = verb
                break
        if matched is None:
            break
        out = out[len(matched.split()) :]
        if out and out[0] in {"up", "down"}:
            out = out[1:]
    return out


def _parse_selector(tokens: Sequence[str]) -> Dict[str, Any]:
    """Split a target phrase into its own words plus any spatial filter."""
    joined = " ".join(tokens)
    padded = f" {joined} "

    if " not between " in padded:
        head, tail = joined.split(" not between ", 1)
        parts = tail.split(" and ")
        if len(parts) >= 2:
            return {"kind": "between", "negated": True, "phrase": head.split(),
                    "ref_a": parts[0].split(), "ref_b": " and ".join(parts[1:]).split()}

    if " between " in padded:
        head, tail = joined.split(" between ", 1)
        parts = tail.split(" and ")
        if len(parts) >= 2:
            return {"kind": "between", "negated": False, "phrase": head.split(),
                    "ref_a": parts[0].split(), "ref_b": " and ".join(parts[1:]).split()}

    for marker in (" next to ", " near "):
        if marker in padded:
            head, tail = joined.split(marker, 1)
            return {"kind": "next_to", "phrase": head.split(), "ref": tail.split()}

    if "center" in tokens or "centre" in tokens:
        return {"kind": "table_center", "phrase": [t for t in tokens if t not in {"center", "centre", "from", "table"}]}

    if " top of " in padded:
        head, tail = joined.split(" top of ", 1)
        return {"kind": "on", "phrase": head.split(), "ref": tail.split()}

    for prep in _PREPOSITIONS:
        marker = f" {prep} "
        if marker in padded:
            head, tail = joined.split(marker, 1)
            return {"kind": _PREP_TO_PREDICATE[prep], "phrase": head.split(), "ref": tail.split()}

    return {"kind": "bare", "phrase": list(tokens)}


# ---------------------------------------------------------------------------
# scene binding
# ---------------------------------------------------------------------------


def _bind_target(
    scene: Any,
    categories: Dict[str, List[str]],
    spec: Dict[str, Any],
    evidence: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    kind = str(spec.get("kind") or "bare")
    direction = list(spec.get("direction") or [])

    if kind == "bare":
        return _unique_instance(categories, spec["tokens"], evidence, "target", direction)
    if kind == "next_to":
        return _bind_binary(scene, categories, spec, evidence, "target", _is_next_to, "next_to")
    if kind == "on":
        return _bind_binary(scene, categories, spec, evidence, "target", _is_on, "on")
    if kind == "inside":
        return _bind_binary(scene, categories, spec, evidence, "target", _is_inside, "inside")
    if kind == "between":
        return _bind_between(scene, categories, spec, evidence, "target")
    if kind == "table_center":
        return _bind_table_center(scene, categories, spec, evidence, "target")
    return None, FAILURE_PARSE


def _bind_goal(
    scene: Any,
    categories: Dict[str, List[str]],
    spec: Dict[str, Any],
    evidence: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    name, why = _unique_instance(categories, spec.get("tokens") or [], evidence, "goal", spec.get("direction") or [])
    if name is None:
        return None, why
    region_sites = _fixture_region_sites(scene, name)
    evidence["goal_region_sites"] = region_sites
    if region_sites:
        return None, FAILURE_REGION
    return name, None


def _unique_instance(
    categories: Dict[str, List[str]],
    tokens: Sequence[str],
    evidence: Dict[str, Any],
    role: str,
    direction: Sequence[str],
) -> Tuple[Optional[str], Optional[str]]:
    found = _match_categories(categories, tokens)
    instances = _instances(categories, found)
    evidence[f"{role}_categories"] = found
    evidence[f"{role}_instances"] = instances
    if len(instances) == 1:
        if direction:
            evidence[f"{role}_direction_ignored"] = list(direction)
        return instances[0], None
    if instances:
        return None, (FAILURE_DIRECTION if direction else FAILURE_AMBIGUOUS)
    return None, _not_found(role)


def _bind_binary(
    scene: Any,
    categories: Dict[str, List[str]],
    spec: Dict[str, Any],
    evidence: Dict[str, Any],
    role: str,
    predicate: Any,
    label: str,
) -> Tuple[Optional[str], Optional[str]]:
    reference, why = _unique_instance(categories, spec.get("ref") or [], evidence, f"{role}_ref", [])
    if reference is None:
        return None, why
    ref_object = _object(scene, reference)

    hits: List[str] = []
    scores: Dict[str, Any] = {}
    for name in _instances(categories, _match_categories(categories, spec["tokens"])):
        obj = _object(scene, name)
        if obj is None or ref_object is None:
            continue
        ok, detail = predicate(obj, ref_object)
        scores[name] = detail
        if ok:
            hits.append(name)
    evidence[f"{role}_{label}"] = {"reference": reference, "scores": scores}
    if len(hits) == 1:
        return hits[0], None
    if not hits:
        return None, _not_found(role)
    evidence[f"{role}_{label}_hits"] = hits
    return None, FAILURE_AMBIGUOUS


def _bind_between(
    scene: Any,
    categories: Dict[str, List[str]],
    spec: Dict[str, Any],
    evidence: Dict[str, Any],
    role: str,
) -> Tuple[Optional[str], Optional[str]]:
    ref_a, why_a = _unique_instance(categories, spec.get("ref_a") or [], evidence, f"{role}_ref_a", [])
    if ref_a is None:
        return None, why_a
    ref_b, why_b = _unique_instance(categories, spec.get("ref_b") or [], evidence, f"{role}_ref_b", [])
    if ref_b is None:
        return None, why_b
    obj_a, obj_b = _object(scene, ref_a), _object(scene, ref_b)
    if obj_a is None or obj_b is None:
        return None, FAILURE_PARSE

    negated = bool(spec.get("negated"))
    hits: List[str] = []
    scores: Dict[str, Any] = {}
    for name in _instances(categories, _match_categories(categories, spec["tokens"])):
        obj = _object(scene, name)
        if obj is None:
            continue
        inside, detail = _between_metrics(obj, obj_a, obj_b)
        scores[name] = detail
        if inside != negated:
            hits.append(name)
    evidence[f"{role}_between"] = {"ref_a": ref_a, "ref_b": ref_b, "negated": negated, "scores": scores}
    if len(hits) == 1:
        return hits[0], None
    if not hits:
        return None, _not_found(role)
    evidence[f"{role}_between_hits"] = hits
    return None, FAILURE_AMBIGUOUS


def _bind_table_center(
    scene: Any,
    categories: Dict[str, List[str]],
    spec: Dict[str, Any],
    evidence: Dict[str, Any],
    role: str,
) -> Tuple[Optional[str], Optional[str]]:
    tables = [c for c in categories if "table" in c]
    if len(tables) != 1:
        return None, FAILURE_PARSE
    table = _object(scene, categories[tables[0]][0])
    if table is None:
        return None, FAILURE_PARSE

    ranked: List[Tuple[float, str]] = []
    for name in _instances(categories, _match_categories(categories, spec["tokens"])):
        obj = _object(scene, name)
        if obj is None:
            continue
        ranked.append((float(np.linalg.norm(obj.pos[:2] - table.pos[:2])), name))
    ranked.sort()
    evidence[f"{role}_table_center"] = {"table": table.name, "ranked": ranked}
    if not ranked:
        return None, _not_found(role)
    if len(ranked) > 1 and ranked[1][0] - ranked[0][0] <= CONTACT_TOL_M:
        return None, FAILURE_AMBIGUOUS
    return ranked[0][1], None


# ---------------------------------------------------------------------------
# scene helpers
# ---------------------------------------------------------------------------


def _scene_categories(scene: Any) -> Dict[str, List[str]]:
    out: Dict[str, List[Tuple[int, str]]] = {}
    for name in getattr(scene, "objects", {}) or {}:
        category, index = _split_instance(str(name))
        out.setdefault(category, []).append((index if index is not None else 0, str(name)))
    return {c: [n for _, n in sorted(v)] for c, v in sorted(out.items())}


def _split_instance(name: str) -> Tuple[str, Optional[int]]:
    base = name[: -len(_MAIN_SUFFIX)] if name.endswith(_MAIN_SUFFIX) else name
    match = _INSTANCE_RE.match(base)
    if match:
        return match.group("stem"), int(match.group("idx"))
    return base, None


def _object(scene: Any, name: str) -> Any:
    return (getattr(scene, "objects", {}) or {}).get(name)


def _fixture_region_sites(scene: Any, name: str) -> List[str]:
    obj = _object(scene, name)
    geometry = getattr(obj, "geometry", None) or {}
    sites = [entry.get("name") for entry in geometry.get("sites") or [] if isinstance(entry, dict)]
    return sorted(
        str(site)
        for site in sites
        if site and str(site).endswith(_REGION_SITE_SUFFIXES) and not str(site).endswith("_init_region")
    )


def _match_categories(categories: Dict[str, List[str]], tokens: Sequence[str]) -> List[str]:
    """Map a language phrase onto scene categories (longest phrase first)."""
    tokens = _clean(tokens)
    for start in range(len(tokens)):
        snake = "_".join(tokens[start:])
        if not snake:
            continue
        alias = _CATEGORY_ALIASES.get(snake)
        if alias and alias in categories:
            return [alias]
        if snake in categories:
            return [snake]
        hits = [c for c in categories if snake in c or c in snake]
        if hits:
            longest = max(len(c) for c in hits)
            return [c for c in hits if len(c) == longest]
    return []


def _instances(categories: Dict[str, List[str]], found: Sequence[str]) -> List[str]:
    out: List[str] = []
    for category in found:
        out.extend(categories.get(category, []))
    return out


def _half_extents(obj: Any) -> np.ndarray:
    sizes: List[Sequence[float]] = []
    geometry = getattr(obj, "geometry", None) or {}
    if isinstance(geometry, dict):
        for group in ("geoms", "sites"):
            for entry in geometry.get(group) or []:
                size = entry.get("size") if isinstance(entry, dict) else None
                if size is not None and len(size) >= 3:
                    sizes.append(size)
    if not sizes:
        return np.full(3, DEFAULT_HALF_EXTENT_M, dtype=np.float64)
    return np.max(np.abs(np.asarray(sizes, dtype=np.float64)), axis=0)[:3]


def _is_on(a: Any, b: Any) -> Tuple[bool, Dict[str, float]]:
    ha, hb = _half_extents(a), _half_extents(b)
    dx = float(abs(a.pos[0] - b.pos[0]))
    dy = float(abs(a.pos[1] - b.pos[1]))
    gap = float((a.pos[2] - ha[2]) - (b.pos[2] + hb[2]))
    xy_ok = bool(dx <= ha[0] + hb[0] + CONTACT_TOL_M and dy <= ha[1] + hb[1] + CONTACT_TOL_M)
    return xy_ok and -CONTACT_TOL_M <= gap <= CONTACT_TOL_M, {
        "dx": dx, "dy": dy, "contact_gap_m": gap, "xy_overlap": float(xy_ok)
    }


def _is_next_to(a: Any, b: Any) -> Tuple[bool, Dict[str, float]]:
    ha, hb = _half_extents(a), _half_extents(b)
    dx = max(float(abs(a.pos[0] - b.pos[0])) - (ha[0] + hb[0]), 0.0)
    dy = max(float(abs(a.pos[1] - b.pos[1])) - (ha[1] + hb[1]), 0.0)
    surface_gap = float((dx * dx + dy * dy) ** 0.5)
    dz = float(abs(a.pos[2] - b.pos[2]))
    stacked = bool(_is_on(a, b)[0] or _is_on(b, a)[0])
    ok = (not stacked) and surface_gap <= NEAR_MARGIN_M and dz <= ha[2] + hb[2] + CONTACT_TOL_M
    return ok, {"surface_gap_m": surface_gap, "dz": dz, "stacked": float(stacked)}


def _is_inside(a: Any, b: Any) -> Tuple[bool, Dict[str, float]]:
    ha, hb = _half_extents(a), _half_extents(b)
    dx = float(abs(a.pos[0] - b.pos[0]))
    dy = float(abs(a.pos[1] - b.pos[1]))
    dz = float(a.pos[2] - b.pos[2])
    ok = bool(
        dx <= hb[0] + CONTACT_TOL_M
        and dy <= hb[1] + CONTACT_TOL_M
        and abs(dz) <= hb[2] + CONTACT_TOL_M
    )
    return ok, {"dx": dx, "dy": dy, "dz": dz,
                "container_half_extents": [float(v) for v in hb], "target_half_extents": [float(v) for v in ha]}


def _between_metrics(a: Any, b: Any, c: Any) -> Tuple[bool, Dict[str, float]]:
    start = np.asarray(b.pos[:2], dtype=np.float64)
    end = np.asarray(c.pos[:2], dtype=np.float64)
    point = np.asarray(a.pos[:2], dtype=np.float64)
    segment = end - start
    length_sq = float(segment @ segment)
    if length_sq <= 1e-9:
        return False, {"t": 0.0, "perpendicular_m": float("inf")}
    t = float((point - start) @ segment / length_sq)
    projection = start + np.clip(t, 0.0, 1.0) * segment
    perpendicular = float(np.linalg.norm(point - projection))
    lo, hi = BETWEEN_T_RANGE
    return bool(lo <= t <= hi and perpendicular <= NEAR_MARGIN_M), {"t": t, "perpendicular_m": perpendicular}


def _placement_goal_surfaces(atoms: Sequence[Dict[str, Any]]) -> List[str]:
    surfaces: List[str] = []
    seen = set()
    for atom in atoms:
        predicate = str(atom.get("predicate") or "").lower()
        args = list(atom.get("args") or [])
        if predicate not in {"on", "inside"} or len(args) < 2:
            continue
        surface = str(args[1])
        if surface in seen:
            continue
        seen.add(surface)
        surfaces.append(surface)
    return surfaces


def _empty_result(language: str) -> Dict[str, Any]:
    return {
        "target": None,
        "goal": None,
        "obj_of_interest": [],
        "goal_atoms": [],
        "goal_surfaces": [],
        "init_atoms": [],
        "regions": {},
        "language": language,
        "source": SOURCE,
        "failure_reason": None,
    }


def _fail(result: Dict[str, Any], reason: str, detail: str) -> Dict[str, Any]:
    result["failure_reason"] = reason
    result["failure_detail"] = detail
    result["target"] = None
    result["goal"] = None
    result["obj_of_interest"] = []
    result["goal_atoms"] = []
    result["goal_surfaces"] = []
    return result
