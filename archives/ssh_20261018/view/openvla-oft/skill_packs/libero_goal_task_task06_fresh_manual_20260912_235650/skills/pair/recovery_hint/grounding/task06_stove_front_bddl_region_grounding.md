---
id: task06_stove_front_bddl_region_grounding
name: Task06 stove-front BDDL region grounding
kind: recovery_hint
track: pair
scope: grounding
priority: 60
when_to_apply: When task06 recovery is already triggered for pushing cream cheese to the front of the stove and the BDDL goal surface is main_table_stove_front_region.
when_not_to_apply: Do not use for placing onto the stove body, for other stove tasks without this BDDL region, or when the target is not cream cheese.
failure_signature:
  - BDDL goal atom is on(cream_cheese_1_main, main_table_stove_front_region).
  - Recovery rule layer observed parser goal flat_stove_1_main and compiled required_final_atoms to on(cream_cheese_1_main, flat_stove_1_main).
  - Forced recovery at query 20 failed 0/3 with no satisfying particles while aiming at the stove body instead of the table region.
recovery_point: After a repair or forced-recovery entrypoint has decided to call cuTAMP.
applies_to:
  all:
    - task_language_matches: ".*cream cheese.*front of the stove.*"
    - target_name_matches: "*cream_cheese*"
    - bddl_goal_surface_matches: "*main_table_stove_front_region"
recovery_hints:
  params:
    grounding_profile: task06_stove_front_bddl_region_grounding_v1
evidence:
  tasks:
    - libero_goal_task task06 Push the cream cheese to the front of the stove
  episodes:
    - baseline_task06_seed51_65_cleanpack/task06/ep00
    - force_q20_task06_seed51_3_empty_pack/task06/ep00
---

## Grounding Diagnosis

The task is a table-region goal, not a stove-body placement. The BDDL goal surface is
`main_table_stove_front_region`, but the recovery rule layer observed during forced
query-20 recovery produced `on(cream_cheese_1_main, flat_stove_1_main)`. This hint
preserves the BDDL region and allows the paired geometry profile to register that
region as a virtual fixed table rectangle.
