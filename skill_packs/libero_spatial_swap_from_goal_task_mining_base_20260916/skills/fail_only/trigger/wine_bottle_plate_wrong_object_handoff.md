---
id: wine_bottle_plate_wrong_object_handoff
name: Wine bottle plate wrong-object handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 71
when_to_apply: In wine-bottle-on-plate tasks, hand off to recovery while the VLA
  still has an open empty hand but keeps fixating on the bowl or another
  non-target object close enough to pick it.
when_not_to_apply: Do not use outside wine-bottle-to-plate tasks. Do not use once
  the hand already holds an object, because the failure has already become a
  wrong-object carry.
failure_signature:
- Skills-off and W0 validation for LIBERO-Pro goal-task task09 are both 0/15 in
  the 2026-09-16 round (seeds 51-65).
- Baseline query traces show sustained wrong-object intent on
  akita_black_bowl_1_main while wine_bottle_1_main stays static, with admission-safe
  q5+ windows in 12/15 episodes under this trigger's predicates.
- Forced q5 recovery on the same task reaches a feasible cuTAMP pick plan
  (14 satisfying particles, libero_topdown sampler) but exhausts the optimized
  motion budget when entering directly from the policy's bowl-approach pose;
  the registered entry-lift repair profile provides the missing entry action.
recovery_point: Fire after wrong-object intent persists for four queries, the open gripper is
  within 0.22 m of the wrongly fixated pickable, and the intent object XY is
  within 0.035 m, before the VLA
  closes on akita_black_bowl_1_main.
applies_to:
  all:
  - task_language_matches: put.*wine bottle.*on.*plate|wine bottle.*on.*plate
  - target_name_matches: wine_bottle|wine bottle
  - goal_name_matches: plate
  - bddl_goal_surface_matches: plate
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - nearest_pickable_is_target: false
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.03
  - nearest_pickable_distance_lt: 0.22
  - intent_min_xy_distance_lt: 0.035
  - target_ee_distance_lt: 0.25
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
    source: libero_goal_task09_20260916_w1
evidence:
  tasks:
  - 'libero_goal_task task09: Put the wine bottle on the plate'
  episodes:
  - baseline_task09_seed51_65_skills_off ep00-ep14 (2026-09-16 run)
  - w0_task09_seed51_65_existing_pack ep00-ep14 (2026-09-16 run)
  - probe_force_q5_seed51_55_existing_pack ep00-ep04 (2026-09-15 reference run)
---
This trigger only decides when to enter recovery for the wine-bottle-to-plate
task family. The matching grasp hint keeps the feasible top-down bottle pick
with the tall-bottle close guard; grounding already resolves
on(wine_bottle_1_main, plate_1_main) correctly and needs no rewrite.