---
id: cream_cheese_flat_pack_short_side_grasp
name: Cream-cheese flat-pack short-side grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 63
when_to_apply: When task10 recovery is trying to regain or place cream_cheese_1_main
  after geometry/grounding have selected the wine-rack top surface.
when_not_to_apply: Do not use for non-cream-cheese targets, bowl/cup/carton objects,
  or tasks whose recovery has not selected cream_cheese_1_main.
failure_signature:
- W3 validation fired recovery in all five failed episodes but every cuTAMP solve
  remained infeasible.
- W3 generated both rack-top placement goals and fallback holding-only goals; holding-only
  goals have no place candidate and still failed with `real_cutamp_no_feasible_goal`.
- W3 diagnostics reported `libero_topdown` with 36 grasp candidates and repeated `KinematicConstraint
  pos_err` zero-satisfying particles.
- The target planner cuboid for cream cheese is a thin flat pack, approximately 0.018
  m x 0.043 m x 0.081 m.
recovery_point: After an existing repair or trigger skill has already decided to call
  recovery.
applies_to:
  all:
  - task_language_matches: cream cheese.*rack|rack.*cream cheese
  - target_name_matches: '*cream_cheese*'
recovery_hints:
  grasp_profile: cream_cheese_flat_pack_short_side_deep_v1
  target: target
  params:
    source: task10_w3_holding_no_satisfying
evidence:
  tasks:
  - 'libero_goal_task task10: Put the cream cheese on the rack'
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - mine_val_task10_w3_ep0
  - mine_val_task10_w3_ep1
  - mine_val_task10_w3_ep2
  - mine_val_task10_w3_ep3
  - mine_val_task10_w3_ep4
  - task10_ep0_seed51
  - task10_ep1_seed51
  - task10_ep2_seed51
  - task10_ep3_seed51
  - task10_ep4_seed51
---
## Intent

This policy contributes only a grasp profile. It replaces broad generic top-down grasp sampling with a small cardinal-yaw, deeper close set for the cream-cheese flat pack and a wider gripper aperture. It does not change repair timing, grounding, rack geometry, place candidates, or executor options.
