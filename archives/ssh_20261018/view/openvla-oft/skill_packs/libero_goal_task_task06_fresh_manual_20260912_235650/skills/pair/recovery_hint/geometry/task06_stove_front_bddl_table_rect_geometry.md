---
id: task06_stove_front_bddl_table_rect_geometry
name: Task06 stove-front BDDL table rectangle geometry
kind: recovery_hint
track: pair
scope: geometry
priority: 58
when_to_apply: When task06 recovery targets the BDDL stove-front table region and the planner needs a virtual fixed table rectangle for it.
when_not_to_apply: Do not use for true stove-surface placement or non-table regions.
failure_signature:
  - BDDL exposes main_table_stove_front_region with table-region bounds.
  - The region is not a MuJoCo scene object, so cuTAMP needs a virtual fixed table rectangle surface.
  - Forced recovery without this geometry produced target_support_surfaces as an empty list.
recovery_point: Alongside the task06 stove-front grounding hint, before building the cuTAMP problem.
applies_to:
  all:
    - task_language_matches: ".*cream cheese.*front of the stove.*"
    - target_name_matches: "*cream_cheese*"
    - bddl_goal_surface_matches: "*main_table_stove_front_region"
recovery_hints:
  params:
    geometry_profile: task06_stove_front_bddl_table_rect_geometry_v1
evidence:
  tasks:
    - libero_goal_task task06 Push the cream cheese to the front of the stove
  episodes:
    - baseline_task06_seed51_65_cleanpack/task06/ep00
    - force_q20_task06_seed51_3_empty_pack/task06/ep00
---

## Geometry Diagnosis

`main_table_stove_front_region` comes from the task BDDL rather than from a scene
object. The geometry profile asks the shared fixed-table-rect primitive to read
the BDDL region bounds, align them to the live scene table, and expose the region
as a virtual placement surface for `place_on` planning.
