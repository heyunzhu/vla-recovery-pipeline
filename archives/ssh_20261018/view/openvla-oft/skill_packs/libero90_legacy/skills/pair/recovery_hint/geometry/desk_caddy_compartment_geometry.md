---
id: desk_caddy_compartment_geometry
name: Desk-caddy compartment geometry
kind: recovery_hint
track: pair
scope: geometry
priority: 47
when_to_apply: When an already-triggered recovery must place a book into a named front, back, left, or right compartment of the desk caddy.
when_not_to_apply: Do not use for non-caddy containers, drawers, cabinets, or table regions.
failure_signature:
  - A desk-caddy compartment exists only as a BDDL contain region and needs a virtual inner-floor place_on proxy.
  - desk_caddy_1_main can otherwise be treated as a non-surface object, causing inside placement to fall back to an unknown cuTAMP surface.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "(front|back|left|right) compartment.*caddy|caddy.*(front|back|left|right) compartment"
    - target_name_matches: "book|black_book"
    - goal_name_matches: "desk_caddy|caddy"
    - bddl_goal_surface_matches:
        - "*desk_caddy*_*_contain_region"
recovery_hints:
  params:
    geometry_profile: desk_caddy_compartment_inner_floor_v1
evidence:
  tasks:
    - libero_90 task74 pick up the book and place it in the front compartment of the caddy
    - libero_90 task75 pick up the book and place it in the left compartment of the caddy
  episodes:
    - online_skill_regression_tasks31_32_37_38_70_71_74_75_20260826 task74/task75
    - book_caddy_budget_ab_20260830 validated a longer hover-yaw budget together with the place alignment/drop budget for task74/75/76/78/79/80/81/82/83/84.
---

## Intent

This policy contributes planner geometry for named desk-caddy compartments.
It creates a virtual `*_front_inner_floor`, `*_left_inner_floor`,
`*_right_inner_floor`, or `*_back_inner_floor` support surface inside the
caddy and allows the source caddy collision to be excluded for this
placement goal. It also excludes the table collision obstacle while that
virtual inner floor is the `on(...)` target, matching ordinary
`on(object, table)` pick-and-place. Book top-down grasp selection lives in
the separate book grasp skill. Placement yaw is pinned so the book's thin
horizontal edge lines up with world x, which is the orientation that fits
the named front/left compartments. After the executor has hovered over the
compartment opening, it rotates only about world z toward that thin-x yaw
in small steps, with up to 48 yaw steps in the formal budget version, then
high-drops. It does not replay Place joint q2 or track the planned
end-effector quaternion. Other tasks keep the table as a collision body.

It does not bind non-caddy containers and does not implement a generic
`place_in` executor.
