"""Fresh task10 grounding adapter for the wine-rack top site."""

ADAPTER_NAME = "libero_goal_task10_fresh_grounding"
PROFILE_IDS = ("cream_cheese_wine_rack_top_v1",)


def _value(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _text(value):
    return str(value or "").strip().lower()


def _is_task10(profile, parsed):
    if profile not in PROFILE_IDS:
        return False
    language = _text(_value(parsed, "language", ""))
    return "cream cheese" in language and "rack" in language


def _is_cream_cheese(name):
    value = _text(name)
    return "cream_cheese" in value or "cream cheese" in value


def _is_wine_rack(name):
    value = _text(name)
    return "wine_rack" in value or "wine rack" in value


def normalize_grounding_profile_params(profile, params):
    if profile not in PROFILE_IDS:
        raise ValueError("unknown grounding profile: %s" % profile)
    out = dict(params or {})
    hints = dict(out.get("grounding_hints") or {})
    slot = dict(hints.get("placement_surface") or {})
    slot.setdefault("grounding_profile", profile)
    slot.setdefault("intent", "top_support")
    slot.setdefault("planner_primitive", "preferred_support_surface")
    slot.setdefault("relation", "on")
    slot.setdefault("object_class", "cream_cheese")
    slot.setdefault("surface_name", "wine_rack_1_top_region")
    slot.setdefault("surface_name_matches", ["wine_rack_1_top_region"])
    slot.setdefault("task_language_matches", ["cream cheese.*rack|rack.*cream cheese"])
    slot.setdefault("target_name_matches", ["*cream_cheese*"])
    slot.setdefault("bddl_goal_surface_matches", ["*wine_rack*top_region", "*wine_rack*main"])
    slot.setdefault("region_name_from_bddl_goal", True)
    hints["placement_surface"] = slot
    out["grounding_hints"] = hints
    return out


def resolve_goal_surface(profile, hint, scene, parsed, target=None, goal=None):
    if not _is_task10(profile, parsed):
        return None
    if target is not None and not _is_cream_cheese(target):
        return None
    if goal is not None and not _is_wine_rack(goal):
        return None
    return {
        "surface": "wine_rack_1_top_region",
        "grounding": {
            "source": "task10_wine_rack_top_site",
            "planner_primitive": "preferred_support_surface",
            "relation": "on",
        },
    }


def rewrite_placement_atom(profile, hint, atom, scene, parsed, target=None, hint_key=None):
    if not _is_task10(profile, parsed):
        return None
    predicate = _text(_value(atom, "predicate", ""))
    args = _value(atom, "args", ())
    if predicate not in {"on", "inside"} or not args or len(args) < 2:
        return None
    object_name = str(args[0])
    source_surface = str(args[1])
    if not _is_cream_cheese(object_name):
        return None
    if target is not None and str(target) != object_name and not _is_cream_cheese(target):
        return None
    if not _is_wine_rack(source_surface) and source_surface != "wine_rack_1_top_region":
        return None
    return {
        "predicate": "on",
        "object": object_name,
        "surface": "wine_rack_1_top_region",
        "grounding": {
            "source": "task10_wine_rack_top_site",
            "source_surface": source_surface,
            "hint_key": hint_key or "placement_surface",
        },
    }


def is_known_or_virtual_surface(profile, hint, surface, scene, parsed=None, hint_key=None):
    if not _is_task10(profile, parsed):
        return None
    if str(surface) != "wine_rack_1_top_region":
        return False
    objects = _value(scene, "objects", {}) or {}
    rack = objects.get("wine_rack_1_main") if isinstance(objects, dict) else None
    return rack is not None
