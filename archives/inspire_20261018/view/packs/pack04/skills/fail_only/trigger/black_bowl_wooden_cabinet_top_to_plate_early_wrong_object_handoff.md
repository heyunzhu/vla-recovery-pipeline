---
id: black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff
name: Black bowl wooden-cabinet top to plate early wrong-object handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 78
when_to_apply: In the spatial task that asks for the akita black bowl on the top of
  the wooden cabinet to be placed on the plate, hand off early once the VLA persistently
  aims at the other akita black bowl while the true BDDL target remains static on
  the cabinet top.
when_not_to_apply: Do not use for the non-wooden cabinet wording from task4/task8,
  not-between or next-to-plate variants, cabinet-top placement goals, generic bowl-on-plate
  tasks without wooden-cabinet wording, white bowls, cream-cheese tasks, rack/stove/cabinet-goal
  tasks, or after the robot is already holding any object. Do not fire from a true-target
  approach; require persistent wrong-object intent and a static true target.
failure_signature:
- Skills-off baseline for libero_spatial_task task5 seed51-65 was 0/15.
- W0 with the current cross-suite pack reached only 5/15 even though the task4 cabinet-top
  trigger matched the task language.
- W0 failed episodes task5_ep0_seed51, task5_ep6_seed57, task5_ep10_seed61, and task5_ep12_seed63
  never fired a skill. Their q6-q8 traces show intent_object_is_target=false, nearest_pickable_is_target=false,
  wrong_progress_target_static=true, and persistent wrong-object intent while the
  robot is still handempty.
- The task4 trigger remains too conservative for the task5 wooden-cabinet layout because
  target_future_min_xy_distance_m is often 0.10-0.15m in the safe window, below the
  existing 0.18m threshold.
- W0 successes seed52, seed55, seed59, and seed65 demonstrate that the existing hollow_bowl_rim_topdown
  grasp and plate placement path can solve this task once recovery starts in time.
recovery_point: Fire around q6-q8 in the early wrong-object intent window, before
  the VLA spends the rollout moving the distractor bowl or exhausts the target approach
  window.
applies_to:
  all:
  - task_language_matches: black bowl.*(?:on|top).*wooden cabinet.*plate|black bowl.*wooden
      cabinet.*plate|on the top of the wooden cabinet.*place.*plate
  - target_name_matches: akita_black_bowl_2|black_bowl|bowl
  - goal_name_matches: plate
  - bddl_goal_surface_matches: plate
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - nearest_pickable_is_target: false
  - wrong_progress_target_static: true
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.08
  - intent_min_xy_distance_lt: 0.06
  - target_future_min_xy_distance_gt: 0.1
  - target_ee_distance_gt: 0.12
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
    source: libero_spatial_task05_cross_suite_w0_trace_replay
    notes: This is a task5-specific early handoff that reuses the existing hollow_bowl_rim_topdown
      grasp and current plate placement path. It only narrows language to wooden cabinet
      and relaxes the task4 distance gates that missed the task5 safe window.
evidence:
  tasks:
  - '{''libero_spatial_task task5'': ''Pick the akita black bowl on the top of the
    wooden cabinet and place it on the plate''}'
  - libero_90 task05 Pick the akita black bowl on the top of the wooden cabinet and
    place it on the plate
  episodes:
  - task5_ep0_seed51_w0_no_fire_static_replay_first_match_q6
  - task5_ep6_seed57_w0_no_fire_static_replay_first_match_q6
  - task5_ep10_seed61_w0_no_fire_static_replay_first_match_q7
  - task5_ep12_seed63_w0_no_fire_static_replay_first_match_q6
  - task5_ep1_seed52_w0_success_existing_recovery
  - task5_ep4_seed55_w0_success_existing_recovery
  - task5_ep8_seed59_w0_success_existing_recovery
  - task5_ep14_seed65_w0_success_existing_recovery
  - task5_ep0_seed51
  - task5_ep6_seed57
  - task5_ep10_seed61
  - task5_ep12_seed63
  - task5_ep1_seed52
  - task5_ep2_seed53
  - task5_ep3_seed54
  - task5_ep4_seed55
  - task5_ep5_seed56
  - task5_ep7_seed58
  - task5_ep8_seed59
  - task5_ep9_seed60
  - task5_ep11_seed62
  - task5_ep13_seed64
  - task5_ep14_seed65
---
This trigger is deliberately separate from the task4/task8 cabinet wording. It requires the literal wooden-cabinet language so it does not match the already protected task4 success run.
