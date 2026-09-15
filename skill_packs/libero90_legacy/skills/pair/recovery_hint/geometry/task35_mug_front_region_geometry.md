---
id: task35_mug_front_region_geometry
name: Task35 mug front-region geometry
kind: recovery_hint
track: pair
scope: geometry
priority: 47
when_to_apply: When task35 recovery must place the yellow-and-white mug in the BDDL front-of-white-mug table region.
when_not_to_apply: Do not use as a generic BDDL region parser, for microwave placement, or for regions other than kitchen_table_porcelain_mug_front_region.
failure_signature:
  - kitchen_table_porcelain_mug_front_region is a BDDL-only region, not a scene object.
  - cuTAMP needs an explicit place_on support surface and place candidates for that region.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "yellow and white mug.*front.*white mug|front.*white mug.*yellow and white mug"
recovery_hints:
  params:
    geometry_profile: task35_mug_front_region_geometry_v1
evidence:
  tasks:
    - libero_90 task35 put the yellow and white mug to the front of the white mug
  episodes:
    - gpu1_selected_online_mining_clean_task35_20260823
---

## Intent

This policy contributes only planner geometry. It exposes task35's BDDL-only
front region as a fixed, thin table support surface with place candidates.

It does not bind the task target and does not implement generic BDDL region
parsing.
