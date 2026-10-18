---
id: task38_plate_right_region_geometry
name: Task38 plate-right region geometry
kind: recovery_hint
track: pair
scope: geometry
priority: 47
when_to_apply: When task38 recovery must place the white bowl in the BDDL right-of-plate table region.
when_not_to_apply: Do not use as a generic BDDL region parser, for placing on the plate, or for regions other than kitchen_table_plate_right_region.
failure_signature:
  - kitchen_table_plate_right_region is a BDDL-only region, not a scene object.
  - cuTAMP needs an explicit place_on support surface and place candidates for that region.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "white bowl.*right.*plate|right.*plate.*white bowl"
recovery_hints:
  params:
    geometry_profile: task38_plate_right_region_geometry_v1
evidence:
  tasks:
    - libero_90 task38 put the white bowl to the right of the plate
  episodes:
    - gpu1_selected_online_mining_clean_task38_20260823
---

## Intent

This policy contributes only planner geometry. It exposes task38's BDDL-only
right-of-plate region as a fixed, thin table support surface with place
candidates.

Candidate points stay inside the BDDL region bounds. For task38 they are
ordered to try the point farthest from `plate_1_main` first, because recent
planning failures were dominated by plate-side collision at the official
region boundary rather than by a wrong success region.

It does not bind the task target and does not implement generic BDDL region
parsing.
