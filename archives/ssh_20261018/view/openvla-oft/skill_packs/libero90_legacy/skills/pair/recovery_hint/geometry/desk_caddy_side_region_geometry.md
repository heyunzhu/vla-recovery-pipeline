---
id: desk_caddy_side_region_geometry
name: Desk-caddy side BDDL table-region geometry
kind: recovery_hint
track: pair
scope: geometry
priority: 47
when_to_apply: When recovery must place a mug or cup in a BDDL table region to the left or right side of the desk caddy.
when_not_to_apply: Do not use for books placed inside named caddy compartments, direct caddy placement, or non-BDDL side regions.
failure_signature:
  - A BDDL-only caddy-side table region is not a live scene object.
  - cuTAMP needs an explicit place_on support surface and place candidates for that region.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "\\bto the (left|right)(?: compartment)? of the caddy\\b|\\b(left|right) of the caddy\\b"
    - target_name_matches: "mug|cup"
    - goal_name_matches: "desk_caddy|caddy"
    - bddl_goal_surface_matches: ".*_desk_caddy_(left|right)_region$"
recovery_hints:
  params:
    geometry_profile: desk_caddy_side_region_geometry_v1
evidence:
  tasks:
    - libero_90 task85 pick up the red mug and place it to the right of the caddy
    - libero_90 task86 pick up the white mug and place it to the right of the caddy
  episodes:
    - online_skill_regression_tasks81_90_trigger_expansion_20260829 task85 ep00
---

## Intent

This policy contributes only planner geometry for caddy-side table regions. It
exposes the BDDL `*_desk_caddy_left_region` or `*_desk_caddy_right_region` as a
thin virtual table rectangle, using the BDDL `:regions` ranges and aligning
them to the current scene when BDDL init-region evidence is available. The
surface is cropped to the portion farther from `desk_caddy_1_main`, so a
right/left-of-caddy placement does not optimize to a point too close to the
caddy body.

It does not bind caddy compartments, change mug grasping, or decide when
recovery should trigger.
