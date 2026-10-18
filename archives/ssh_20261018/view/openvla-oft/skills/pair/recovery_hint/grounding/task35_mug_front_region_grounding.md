---
id: task35_mug_front_region_grounding
name: Task35 mug front-region grounding
kind: recovery_hint
track: pair
scope: grounding
priority: 48
when_to_apply: When an already-triggered recovery is solving the yellow-and-white mug front-of-white-mug task.
when_not_to_apply: Do not use for generic mug tasks, microwave placement, inside placement, or tasks whose BDDL target region is not the porcelain mug front region.
failure_signature:
  - The BDDL goal names kitchen_table_porcelain_mug_front_region, which is not a live scene object.
  - The semantic fallback can bind the task to microwave_1_main and compile an impossible inside goal.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "yellow and white mug.*front.*white mug|front.*white mug.*yellow and white mug"
recovery_hints:
  params:
    grounding_profile: task35_mug_front_region_v1
evidence:
  tasks:
    - libero_90 task35 put the yellow and white mug to the front of the white mug
  episodes:
    - gpu1_selected_online_mining_clean_task35_20260823
---

## Intent

This policy contributes only target grounding. It keeps task35 placement on the
BDDL table-front region and rewrites the observed microwave misbinding back to
that region.

It does not create the virtual surface. The paired
`task35_mug_front_region_geometry` policy owns the planner geometry.
