---
id: desk_caddy_side_region_grounding
name: Desk-caddy side BDDL table-region grounding
kind: recovery_hint
track: pair
scope: grounding
priority: 48
when_to_apply: When an already-triggered recovery is solving a mug or cup task that places the object to the left or right side of the desk caddy on a BDDL table region.
when_not_to_apply: Do not use for placing books inside named caddy compartments, or for direct placement on the caddy body.
failure_signature:
  - The BDDL goal surface is a virtual table region such as study_table_desk_caddy_right_region.
  - The semantic fallback can bind the goal to desk_caddy_1_main, which is not the intended table-side placement region.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "\\bto the (left|right)(?: compartment)? of the caddy\\b|\\b(left|right) of the caddy\\b"
    - target_name_matches: "mug|cup"
    - goal_name_matches: "desk_caddy|caddy"
    - bddl_goal_surface_matches: ".*_desk_caddy_(left|right)_region$"
recovery_hints:
  params:
    grounding_profile: desk_caddy_side_table_region_v1
evidence:
  tasks:
    - libero_90 task85 pick up the red mug and place it to the right of the caddy
    - libero_90 task86 pick up the white mug and place it to the right of the caddy
  episodes:
    - online_skill_regression_tasks81_90_trigger_expansion_20260829 task85 ep00
---

## Intent

This policy contributes only grounding for caddy-side table regions. It
preserves the BDDL `study_table_desk_caddy_left_region` or
`study_table_desk_caddy_right_region` surface and rewrites caddy-body
fallbacks back to that region.

It does not create planner geometry, choose a grasp, handle book-in-caddy
compartments, or decide when recovery should start.
