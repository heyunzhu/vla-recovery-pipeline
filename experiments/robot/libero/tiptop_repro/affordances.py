from __future__ import annotations

from typing import List

MOVABLE_TOKENS = (
    "mug",
    "bowl",
    "plate",
    "book",
    "box",
    "can",
    "bottle",
    "basket",
    "chocolate",
    "cup",
    "object",
    "cream",
    "cheese",
    "pudding",
    "butter",
    "ketchup",
    "milk",
    "juice",
    "soup",
    "sauce",
    "tomato",
    "alphabet",
    "orange",
)
CONTAINER_TOKENS = ("microwave", "drawer", "cabinet", "basket", "box", "container")
SURFACE_TOKENS = ("table", "stove", "counter", "tray", "plate", "surface")
# Furniture links named like ``*_cabinet_top`` are used by LIBERO BDDL
# for "on top of the cabinet" support surfaces, not for inside placement.
TOP_SUPPORT_SURFACE_TOKENS = ("cabinet top", "cabinet top side", "top side")
VIRTUAL_SUPPORT_SURFACE_TOKENS = ("inner floor", "placement region", "support proxy")
# Shallow open receptacles stay "surface" symbolically (on/place_on), but
# geometry uses an inner opening. Do not add these to CONTAINER_TOKENS.
# "plate" is the dinner-plate surface (plate_1_main), not stove burner plates.
SHALLOW_RECEPTACLE_TOKENS = ("tray", "plate")
SHALLOW_RECEPTACLE_EXCLUDE_TOKENS = ("burner", "stove", "oven")
# Open vessels that should keep wall geometry instead of a filled AABB cuboid.
# Collision / in_xy use the wall mesh. 6-DOF sampling still reads Cuboid.dims, so
# the backend samples the AABB rim rather than the cavity center.
HOLLOW_VESSEL_TOKENS = ("bowl", "mug", "cup")
ARTICULATED_TOKENS = ("door", "drawer", "microwave", "cabinet")
FIXTURE_TOKENS = (
    "robot",
    "mount",
    "base",
    "root",
    "fixture",
    "region",
    "workspace",
    "floor",
    "wall",
)


def normalize_name(name: str) -> str:
    return name.lower().replace("_", " ").replace("-", " ")


def is_top_support_surface(name: str) -> bool:
    low = normalize_name(name)
    return any(tok in low for tok in TOP_SUPPORT_SURFACE_TOKENS)


def is_virtual_support_surface(name: str) -> bool:
    low = normalize_name(name)
    return any(tok in low for tok in VIRTUAL_SUPPORT_SURFACE_TOKENS)


def object_affordances(name: str) -> List[str]:
    low = normalize_name(name)
    is_door_link = "microdoorroot" in low or "doorroot" in low
    is_top_support = is_top_support_surface(name)
    is_virtual_support = is_virtual_support_surface(name)
    affordances: List[str] = []
    if (any(tok in low for tok in FIXTURE_TOKENS) and not is_virtual_support) or is_door_link:
        affordances.append("fixture")
    if any(tok in low for tok in CONTAINER_TOKENS) and not is_door_link and not is_top_support and not is_virtual_support:
        affordances.append("container")
    if (any(tok in low for tok in SURFACE_TOKENS) or is_top_support or is_virtual_support) and not is_door_link:
        affordances.append("surface")
    if is_virtual_support and not is_door_link:
        affordances.append("placement_region")
    if is_top_support and not is_door_link:
        affordances.append("top_support")
    if (any(tok in low for tok in ARTICULATED_TOKENS) and not is_top_support and not is_virtual_support) or is_door_link:
        affordances.append("articulated")
        affordances.append("openable")
        affordances.append("closeable")
    if any(tok in low for tok in MOVABLE_TOKENS) and "fixture" not in affordances:
        affordances.append("movable")
    if is_door_link:
        affordances.append("door_link")
    return sorted(set(affordances))


def is_probably_movable(name: str) -> bool:
    aff = object_affordances(name)
    return "movable" in aff and "fixture" not in aff and "door_link" not in aff


def is_probably_surface(name: str) -> bool:
    aff = object_affordances(name)
    if "door_link" in aff or "fixture" in aff:
        return False
    return "surface" in aff or "container" in aff


def is_shallow_receptacle(name: str) -> bool:
    low = normalize_name(name)
    if any(tok in low for tok in SHALLOW_RECEPTACLE_EXCLUDE_TOKENS):
        return False
    return any(tok in low for tok in SHALLOW_RECEPTACLE_TOKENS)


def is_hollow_vessel(name: str) -> bool:
    low = normalize_name(name)
    return any(tok in low for tok in HOLLOW_VESSEL_TOKENS)


def is_probably_articulated(name: str) -> bool:
    aff = object_affordances(name)
    return "articulated" in aff or "door_link" in aff


def object_category(name: str) -> str:
    aff = object_affordances(name)
    if "door_link" in aff:
        return "door_link"
    if "container" in aff:
        return "container"
    if "surface" in aff:
        return "surface"
    if "movable" in aff:
        return "movable"
    if "fixture" in aff:
        return "fixture"
    return "object"
