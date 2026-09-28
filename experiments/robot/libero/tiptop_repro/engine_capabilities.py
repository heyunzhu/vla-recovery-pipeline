"""Engine-owned recovery capability identifiers.

Skill packs may declare and select capabilities, but the execution stack still
needs to know which low-level options and policy names it can actually consume.
This module is the single source of truth for those engine-consumed names.
"""

from __future__ import annotations

from typing import Any, Mapping


SUPPORTED_EXECUTOR_OPTION_KEYS = frozenset(
    {
        "grasp_close_max_above_m",
        "grasp_lift_follow_m",
        "grasp_lift_probe_m",
        "grasp_lift_probe_max_steps",
        "held_transfer_keep_z",
        "held_transfer_max_descent_m",
        "held_transfer_max_steps",
        "held_transfer_reached_m",
        "held_transfer_z_margin_m",
        "place_align_center_tolerance_m",
        "place_align_max_iters",
        "place_align_max_steps_per_iter",
        "place_align_reached_m",
        "place_align_retry_lift_m",
        "place_align_retry_lift_max_steps",
        "place_align_step_clip_m",
        "place_drop_align_xy_m",
        "place_drop_align_slices",
        "place_drop_closed_loop_align",
        "place_drop_max_steps",
        "place_drop_reached_m",
        "place_footprint_release_tolerance_m",
        "place_held_object_xy_align",
        "place_hover_clearance_m",
        "place_hover_max_steps",
        "place_hover_reached_m",
        "place_lift_max_steps",
        "place_lift_min_clearance_m",
        "place_lift_reached_m",
        "place_open_dwell_steps",
        "place_release_margin_m",
        "place_release_xy_m",
        "place_release_xy_min_m",
        "place_release_z_max_m",
        "place_retreat_m",
        "place_retreat_max_steps",
        "place_yaw_after_hover",
        "place_yaw_after_hover_max_steps",
        "place_yaw_max_cmd",
        "place_yaw_step_rad",
        "recovery_entry_escape_profile",
        "recovery_entry_lift_gripper_value",
        "recovery_entry_lift_m",
        "recovery_entry_lift_max_steps",
        "recovery_entry_lift_reached_m",
        "recovery_entry_retreat_m",
        "recovery_entry_retreat_max_steps",
        "recovery_entry_retreat_reached_m",
    }
)

SUPPORTED_PLACE_CANDIDATE_POLICIES = frozenset(
    {
        "center_and_entry_high_drop",
        "farthest_from_reference_with_corners",
        "farthest_from_object_with_corners",
        "reference_clearance_with_corners",
    }
)
PLACE_CANDIDATE_POLICY_ALIASES = {
    name: name for name in SUPPORTED_PLACE_CANDIDATE_POLICIES
}

SUPPORTED_PLACE_YAW_POLICIES = frozenset(
    {
        "thin_horizontal_along_world_x",
        "world_z_thin_x",
    }
)
PLACE_YAW_POLICY_ALIASES = {
    "thin_horizontal_along_world_x": "thin_horizontal_along_world_x",
    "world_z_thin_x": "world_z_thin_x",
    "thin_along_world_x": "thin_horizontal_along_world_x",
    "thin_along_x": "thin_horizontal_along_world_x",
}

SUPPORTED_RELEASE_MODES = frozenset({"high_drop_into_compartment"})

GEOMETRY_PRIMITIVE_ALIASES = {
    "fixed_table_rect": "fixed_table_rect",
    "table_rect": "fixed_table_rect",
    "table_region_rect": "fixed_table_rect",
    "inner_floor": "inner_floor",
    "container_inner_floor": "inner_floor",
    "virtual_inner_floor": "inner_floor",
    "movable_support_surface": "movable_support_surface",
    "movable_support": "movable_support_surface",
}
GEOMETRY_INTENT_PRIMITIVE_ALIASES = {
    "fixed_table_rect": "fixed_table_rect",
    "fixed_table_region": "fixed_table_rect",
    "table_region": "fixed_table_rect",
    "bddl_table_rect": "fixed_table_rect",
    "bddl_table_region": "fixed_table_rect",
    "drawer_inner_floor": "inner_floor",
    "container_inner_floor": "inner_floor",
    "compartment_inner_floor": "inner_floor",
    "shelf_region_inner_floor": "inner_floor",
    "movable_support": "movable_support_surface",
    "stack_support": "movable_support_surface",
}
SUPPORTED_GEOMETRY_PLANNER_PRIMITIVES = frozenset(
    {"fixed_table_rect", "inner_floor", "movable_support_surface"}
)
SUPPORTED_GEOMETRY_DESCRIPTOR_SHAPES = frozenset({"box", "rotated_box", "cylinder", "sphere"})
GEOMETRY_DESCRIPTOR_SHAPE_ALIASES = {
    "box": "box",
    "cuboid": "box",
    "rect": "box",
    "rectangular_prism": "box",
    "rotated_box": "rotated_box",
    "oriented_box": "rotated_box",
    "obb": "rotated_box",
    "cylinder": "cylinder",
    "cyl": "cylinder",
    "sphere": "sphere",
    "ball": "sphere",
}

GROUNDING_PRIMITIVE_ALIASES = {
    "table_region_surface": "table_region_surface",
    "fixed_table_region": "table_region_surface",
    "table_region": "table_region_surface",
    "bddl_table_region": "table_region_surface",
    "container_region_surface": "container_region_surface",
    "container_region": "container_region_surface",
    "container_compartment": "container_region_surface",
    "container_inside": "container_region_surface",
    "preferred_support_surface": "preferred_support_surface",
    "support_surface": "preferred_support_surface",
    "top_support": "preferred_support_surface",
    "shelf_support": "preferred_support_surface",
    "preferred_container_surface": "preferred_container_surface",
    "container_surface": "preferred_container_surface",
    "drawer_container": "preferred_container_surface",
    "movable_support_surface": "movable_support_surface",
    "movable_support": "movable_support_surface",
    "stack_support": "movable_support_surface",
}
GROUNDING_INTENT_PRIMITIVE_ALIASES = {
    "fixed_table_region": "table_region_surface",
    "fixed_table_rect": "table_region_surface",
    "table_region": "table_region_surface",
    "bddl_table_region": "table_region_surface",
    "container_inside": "container_region_surface",
    "container_compartment": "container_region_surface",
    "top_support": "preferred_support_surface",
    "shelf_support": "preferred_support_surface",
    "drawer_container": "preferred_container_surface",
    "movable_support": "movable_support_surface",
    "stack_support": "movable_support_surface",
}
SUPPORTED_GROUNDING_PLANNER_PRIMITIVES = frozenset(
    {
        "table_region_surface",
        "container_region_surface",
        "preferred_support_surface",
        "preferred_container_surface",
        "movable_support_surface",
    }
)


def canonical_place_candidate_policy(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return PLACE_CANDIDATE_POLICY_ALIASES.get(raw, "")


def canonical_place_yaw_policy(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return PLACE_YAW_POLICY_ALIASES.get(raw, "")


def canonical_release_mode(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return raw if raw in SUPPORTED_RELEASE_MODES else ""


def canonical_geometry_planner_primitive(hint: Mapping[str, Any]) -> str:
    raw = str(hint.get("planner_primitive") or hint.get("primitive") or "").strip().lower()
    if raw:
        return GEOMETRY_PRIMITIVE_ALIASES.get(raw, "")
    intent = str(hint.get("intent") or "").strip().lower()
    return GEOMETRY_INTENT_PRIMITIVE_ALIASES.get(intent, "")


def canonical_geometry_descriptor_shape(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return GEOMETRY_DESCRIPTOR_SHAPE_ALIASES.get(raw, "")


def canonical_grounding_planner_primitive(hint: Mapping[str, Any]) -> str:
    raw = str(hint.get("planner_primitive") or hint.get("primitive") or "").strip().lower()
    if raw:
        return GROUNDING_PRIMITIVE_ALIASES.get(raw, "")
    intent = str(hint.get("intent") or "").strip().lower()
    return GROUNDING_INTENT_PRIMITIVE_ALIASES.get(intent, "")
