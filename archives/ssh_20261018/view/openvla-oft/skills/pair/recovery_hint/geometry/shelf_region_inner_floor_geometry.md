---
id: shelf_region_inner_floor_geometry
name: Two-layer shelf region inner-floor geometry
kind: recovery_hint
track: pair
scope: geometry
priority: 44
when_to_apply: When an already-triggered recovery must place a book into the
  top or bottom region of a wooden two-layer shelf.
when_not_to_apply: Do not use for caddy compartments, baskets, drawers,
  plates, or top-side shelf placement.
failure_signature:
  - LIBERO-90 task87/task89 BDDL goals are inside(book,
    wooden_two_layer_shelf_1_top_region).
  - LIBERO-90 task90 uses inside(book, wooden_two_layer_shelf_1_bottom_region).
  - These BDDL regions are not ordinary scene objects, so recovery needs a
    virtual inner-floor support proxy.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "shelf|cabinet shelf"
    - target_name_matches: "book"
    - bddl_goal_surface_matches:
        - "*wooden_two_layer_shelf*_top_region"
        - "*wooden_two_layer_shelf*_bottom_region"
recovery_hints:
  params:
    geometry_profile: shelf_region_inner_floor_geometry_v1
evidence:
  tasks:
    - libero_90 task87 pick up the book in the middle and place it on the cabinet shelf
    - libero_90 task89 pick up the book on the right and place it on the cabinet shelf
    - libero_90 task90 pick up the book on the right and place it under the cabinet shelf
  episodes:
    - online_skill_regression_tasks81_90_scopefix_20260829 task87/task89/task90 r0
---

## Intent

This policy contributes only planner geometry for two-layer shelf BDDL regions.
It compiles shelf `inside` goals into a virtual inner-floor support so the
existing place-on trajectory executor can be used after recovery has been
triggered.
