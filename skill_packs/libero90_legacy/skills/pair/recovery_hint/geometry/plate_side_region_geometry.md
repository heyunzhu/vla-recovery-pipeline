---
id: plate_side_region_geometry
name: Plate-side BDDL table-region geometry
kind: recovery_hint
track: pair
scope: geometry
priority: 47
when_to_apply: When recovery must place an object in a BDDL table region to the left or right of the plate.
when_not_to_apply: Do not use for direct plate placement, selected left/right plate objects, or BDDL goals that are not plate-side table regions.
failure_signature:
  - A BDDL-only plate-side table region is not a live scene object.
  - cuTAMP needs an explicit place_on support surface and place candidates for that region.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "\\bto the (left|right) of the plate\\b|\\b(left|right) of the plate\\b"
    - target_name_matches: "chocolate_pudding|cream_cheese|butter|box"
    - bddl_goal_surface_matches: ".*_table_plate_(left|right)_region$"
recovery_hints:
  params:
    geometry_profile: plate_side_region_geometry_v1
evidence:
  tasks:
    - libero_90 task70 put the chocolate pudding to the left of the plate
    - libero_90 task71 put the chocolate pudding to the right of the plate
  episodes:
    - online_skill_selected_tasks_9cef474_20260826_r3 task70/task71 failures
---

## Intent

This policy contributes only planner geometry. It exposes the BDDL plate-side
table region as a thin virtual table rectangle, using the BDDL `:regions`
ranges and aligning them to the current scene when BDDL init-region evidence is
available.

It does not decide when recovery should trigger and does not modify grasping.
