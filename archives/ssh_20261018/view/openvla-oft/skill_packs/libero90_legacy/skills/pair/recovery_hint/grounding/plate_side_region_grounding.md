---
id: plate_side_region_grounding
name: Plate-side BDDL table-region grounding
kind: recovery_hint
track: pair
scope: grounding
priority: 48
when_to_apply: When an already-triggered recovery is solving a task that places a movable object to the left or right of the plate on a BDDL table region.
when_not_to_apply: Do not use for placing directly on a plate, on a selected left/right plate object, or for plate-relative tasks whose BDDL goal is not a table plate-side region.
failure_signature:
  - The BDDL goal surface is a virtual table region such as living_room_table_plate_left_region or living_room_table_plate_right_region.
  - The semantic fallback can bind the goal to plate_1_main and compile an on-the-plate goal instead of a beside-the-plate goal.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "\\bto the (left|right) of the plate\\b|\\b(left|right) of the plate\\b"
    - target_name_matches: "chocolate_pudding|cream_cheese|butter|box"
    - bddl_goal_surface_matches: ".*_table_plate_(left|right)_region$"
recovery_hints:
  params:
    grounding_profile: plate_side_table_region_v1
evidence:
  tasks:
    - libero_90 task70 put the chocolate pudding to the left of the plate
    - libero_90 task71 put the chocolate pudding to the right of the plate
  episodes:
    - online_skill_selected_tasks_9cef474_20260826_r3 task70/task71 failures
---

## Intent

This policy contributes only grounding. It preserves the BDDL table-side region
as the placement surface and rewrites observed plate-body fallbacks back to that
region.

It does not create the virtual surface. The paired
`plate_side_region_geometry` policy owns planner geometry and place candidates.
