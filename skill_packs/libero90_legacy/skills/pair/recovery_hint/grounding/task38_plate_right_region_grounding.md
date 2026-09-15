---
id: task38_plate_right_region_grounding
name: Task38 plate-right region grounding
kind: recovery_hint
track: pair
scope: grounding
priority: 48
when_to_apply: When an already-triggered recovery is solving the white-bowl-to-the-right-of-the-plate task.
when_not_to_apply: Do not use for placing on the plate, on a right plate, or for generic plate placement tasks.
failure_signature:
  - The BDDL goal names kitchen_table_plate_right_region, which is not a live scene object.
  - The semantic fallback can bind the task to plate_1_main and compile an on-the-plate goal instead of a right-of-plate goal.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "white bowl.*right.*plate|right.*plate.*white bowl"
recovery_hints:
  params:
    grounding_profile: task38_plate_right_region_v1
evidence:
  tasks:
    - libero_90 task38 put the white bowl to the right of the plate
  episodes:
    - gpu1_selected_online_mining_clean_task38_20260823
---

## Intent

This policy contributes only target grounding. It keeps task38 placement on the
BDDL table-right region and rewrites the observed plate-body misbinding back to
that region.

It does not create the virtual surface. The paired
`task38_plate_right_region_geometry` policy owns the planner geometry.
