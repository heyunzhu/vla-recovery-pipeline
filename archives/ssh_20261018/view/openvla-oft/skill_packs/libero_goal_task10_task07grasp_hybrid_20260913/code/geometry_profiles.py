"""Fresh task10 geometry adapter for a MuJoCo wine-rack top site."""

ADAPTER_NAME = "libero_goal_task10_fresh_geometry"
PROFILE_IDS = (
    "wine_rack_top_site_descriptor_v1",
    "wine_rack_top_site_descriptor_exclude_source_v2",
    "wine_rack_top_site_descriptor_low_center_v3",
)


def _value(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _text(value):
    return str(value or "").strip().lower()


def _vector(value, length):
    if value is None:
        return None
    try:
        result = [float(value[index]) for index in range(length)]
    except (TypeError, ValueError, IndexError):
        return None
    return result


def _is_task10(profile, task):
    if profile not in PROFILE_IDS:
        return False
    language = _text(_value(task, "language", ""))
    return "cream cheese" in language and "rack" in language


def normalize_geometry_profile_params(profile, params):
    if profile not in PROFILE_IDS:
        raise ValueError("unknown geometry profile: %s" % profile)
    out = dict(params or {})
    hints = dict(out.get("geometry_hints") or {})
    slot = dict(hints.get("placement_region") or {})
    slot.setdefault("geometry_profile", profile)
    slot.setdefault("surface_name", "wine_rack_1_top_region")
    slot.setdefault("surface_name_matches", ["wine_rack_1_top_region"])
    slot.setdefault("relation", "on")
    slot.setdefault("role", "surface")
    slot.setdefault("coordinate_frame", "planner_frame")
    slot.setdefault("descriptor_shape", "rotated_box")
    hints["placement_region"] = slot
    out["geometry_hints"] = hints
    return out


def resolve_surface_descriptor(
    profile,
    surface_name,
    scene,
    task,
    table_geometry=None,
    hint=None,
    hint_key=None,
):
    if not _is_task10(profile, task) or str(surface_name) != "wine_rack_1_top_region":
        return None
    objects = _value(scene, "objects", {}) or {}
    rack = objects.get("wine_rack_1_main") if isinstance(objects, dict) else None
    if rack is None:
        return None
    geometry = _value(rack, "geometry", {}) or {}
    metadata = _value(geometry, "metadata", {}) or {}
    sites = _value(metadata, "sites", None)
    if not sites:
        sites = _value(geometry, "sites", None)
    if not sites:
        return None
    for site in sites:
        if _text(_value(site, "name", "")) != "wine_rack_1_top_region":
            continue
        center = _vector(_value(site, "pos", None), 3)
        half_extents = _vector(_value(site, "size", None), 3)
        quat = _vector(_value(site, "quat", None), 4)
        if center is None or half_extents is None:
            return None
        if quat is None:
            quat = [1.0, 0.0, 0.0, 0.0]
        descriptor_metadata = {
            "source_object": "wine_rack_1_main",
            "source_site": "wine_rack_1_top_region",
            "source_site_half_extents": half_extents,
            "coordinate_frame": "planner_frame",
            "site_size_semantics": "mujoco_half_extents",
            "geometry_profile": profile,
        }
        if profile in (
            "wine_rack_top_site_descriptor_exclude_source_v2",
            "wine_rack_top_site_descriptor_low_center_v3",
        ):
            descriptor_metadata["exclude_source_collision"] = True
            descriptor_metadata["exclude_source_collision_reason"] = "target_support_source_object"
        if profile == "wine_rack_top_site_descriptor_low_center_v3":
            support_z = float(center[2] + half_extents[2])
            place_z_offset_m = 0.045
            descriptor_metadata.update(
                {
                    "inner_bounds_coordinate_frame": "planner_frame",
                    "inner_bounds_source": "dynamic_site_half_extents",
                    "inner_bounds": {
                        "x_min": float(center[0] - half_extents[0]),
                        "x_max": float(center[0] + half_extents[0]),
                        "y_min": float(center[1] - half_extents[1]),
                        "y_max": float(center[1] + half_extents[1]),
                        "z_min": support_z,
                        "z_max": support_z + 0.005,
                        "support_z": support_z,
                    },
                    "place_z_offset_m": place_z_offset_m,
                    "planner_support_z_m": support_z + place_z_offset_m,
                }
            )
        return {
            "shape": "rotated_box",
            "kind": "virtual_wine_rack_top_site",
            "center": center,
            "half_extents": half_extents,
            "quat": quat,
            "role": "surface",
            "coordinate_frame": "planner_frame",
            "affordances": ["surface", "placement_region", "top_support"],
            "metadata": descriptor_metadata,
        }
    return None
