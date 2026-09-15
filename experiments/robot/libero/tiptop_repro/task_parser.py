from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Sequence


STOPWORDS = {
    "the",
    "a",
    "an",
    "to",
    "in",
    "on",
    "into",
    "onto",
    "and",
    "of",
    "at",
    "put",
    "place",
    "pick",
    "move",
    "open",
    "close",
    "turn",
    "push",
    "it",
}

# Spatial adjectives must not bind furniture link names (cabinet_middle).
TARGET_SKIP_WORDS = {"front", "back", "middle", "left", "right", "top", "bottom"}

CATEGORY_TOKENS = (
    "bowl",
    "mug",
    "cup",
    "pot",
    "can",
    "bottle",
    "book",
    "plate",
    "cream",
    "cheese",
    "butter",
    "ketchup",
    "milk",
    "juice",
    "soup",
)

# Drawer/shelf links that share the furniture token, e.g. white_cabinet_1_cabinet_top.
_FURNITURE_COMPARTMENT_MARKERS = (
    "cabinet_top",
    "cabinet_middle",
    "cabinet_bottom",
    "cabinet_base",
    "drawer",
    "door",
    "handle",
)


def language_requests_inside(language: str) -> bool:
    words = set(language.lower().replace("_", " ").split())
    return bool({"in", "into", "inside"} & words)


def language_requests_on_top(language: str) -> bool:
    low = language.lower().replace("_", " ")
    if language_requests_inside(low):
        return False
    return "on top of" in low or "onto the top of" in low


def _furniture_body_score(name: str) -> int:
    low = name.lower()
    if any(marker in low for marker in _FURNITURE_COMPARTMENT_MARKERS):
        return 40
    if "main" in low:
        return 0
    return 10


def prefer_cabinet_body_name(object_names: Iterable[str], avoid: Optional[str] = None) -> Optional[str]:
    cabinet_names = [name for name in object_names if name != avoid and "cabinet" in name.lower()]
    if not cabinet_names:
        return None
    return sorted(cabinet_names, key=_furniture_body_score)[0]


def _category_restrict(words: Sequence[str], object_names: Sequence[str]) -> Optional[list[str]]:
    word_set = set(words)
    for token in CATEGORY_TOKENS:
        if token not in word_set:
            continue
        filtered = [name for name in object_names if token in name.lower()]
        if filtered:
            return filtered
    return None


@dataclass(frozen=True)
class ParsedTask:
    language: str
    target_hint: Optional[str]
    goal_hint: Optional[str]
    operation: str
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def _match_object(
    words: Iterable[str],
    object_names: Iterable[str],
    prefer_furniture_body: bool = False,
    skip_words: Optional[Iterable[str]] = None,
    restrict_to: Optional[Iterable[str]] = None,
) -> Optional[str]:
    names = list(restrict_to) if restrict_to is not None else list(object_names)
    object_lows = [(name, name.lower()) for name in names]
    skip = {str(word).lower() for word in (skip_words or [])}
    hits: list[str] = []
    for word in words:
        if word in STOPWORDS or word in skip:
            continue
        for name, low in object_lows:
            if word in low:
                if prefer_furniture_body:
                    hits.append(name)
                else:
                    return name
    if not hits:
        return None
    return sorted(dict.fromkeys(hits), key=_furniture_body_score)[0]


def parse_task(
    language: str,
    object_names: Iterable[str],
    *,
    bddl_text: Optional[str] = None,
    bddl_path: Optional[str] = None,
    env: Any = None,
) -> ParsedTask:
    names = list(object_names)
    low = language.lower().replace("_", " ")
    words = [w.strip(".,;:!?()[]") for w in low.split()]
    operation = "place" if any(w in words for w in ("put", "place", "move")) else "manipulate"
    if any(w in words for w in ("pick", "grasp", "grab")):
        operation = "pick"

    target_restrict = _category_restrict(words, names)
    target_hint = _match_object(
        words,
        names,
        skip_words=TARGET_SKIP_WORDS,
        restrict_to=target_restrict,
    )
    goal_hint = None
    on_top = language_requests_on_top(low)
    for prep in ("into", "inside", "in", "to", "onto", "on"):
        if prep not in words:
            continue
        rest = words[words.index(prep) + 1 :]
        if prep in {"on", "onto"} and len(rest) >= 2 and rest[0] == "top" and rest[1] == "of":
            rest = rest[2:]
            on_top = True
        prefer_body = on_top and any("cabinet" in token for token in rest)
        goal_hint = _match_object(rest, names, prefer_furniture_body=prefer_body)
        if goal_hint is not None:
            break
    if goal_hint is None:
        for special in ("microwave", "drawer", "cabinet", "basket", "box", "stove", "plate", "table"):
            if special in words:
                prefer_body = on_top and special == "cabinet"
                goal_hint = _match_object([special], names, prefer_furniture_body=prefer_body)
                if goal_hint is not None:
                    break
    if goal_hint == target_hint:
        goal_hint = None

    diagnostics: Dict[str, Any] = {
        "parser_target_hint": target_hint,
        "parser_goal_hint": goal_hint,
        "target_source": "parser",
        "goal_source": "parser",
        "category_restrict": list(target_restrict or []),
    }
    if bddl_text or bddl_path or env is not None:
        from .bddl_goals import load_bddl_hints

        hints = load_bddl_hints(names, bddl_text=bddl_text, bddl_path=bddl_path, env=env)
        diagnostics["bddl_path"] = hints.get("source")
        diagnostics["bddl_goal_atoms"] = hints.get("goal_atoms") or []
        diagnostics["bddl_goal_surfaces"] = hints.get("goal_surfaces") or []
        diagnostics["bddl_init_atoms"] = hints.get("init_atoms") or []
        diagnostics["bddl_regions"] = hints.get("regions") or {}
        diagnostics["bddl_obj_of_interest"] = hints.get("obj_of_interest") or []
        if hints.get("target"):
            target_hint = str(hints["target"])
            diagnostics["target_source"] = "bddl"
            diagnostics["bddl_target"] = target_hint
        if hints.get("goal") and hints.get("goal") != target_hint:
            goal_hint = str(hints["goal"])
            diagnostics["goal_source"] = "bddl"
            diagnostics["bddl_goal"] = goal_hint

    return ParsedTask(
        language=language,
        target_hint=target_hint,
        goal_hint=goal_hint,
        operation=operation,
        diagnostics=diagnostics,
    )
