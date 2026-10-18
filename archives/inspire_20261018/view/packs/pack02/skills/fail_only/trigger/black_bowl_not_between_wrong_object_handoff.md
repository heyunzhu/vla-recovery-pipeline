---
id: black_bowl_not_between_wrong_object_handoff
name: Black bowl not-between wrong-object handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 70
when_to_apply: In the spatial black-bowl task where the target is the bowl not between
  the plate and ramekin, hand off when the VLA has persistently aimed at the other
  black bowl while the target bowl is still unheld and the gripper is open.
when_not_to_apply: Do not use for generic bowl-on-plate tasks, white bowls, cabinet/rack/stove
  goals, or when the VLA is already holding the target bowl. Do not fire from target
  approach alone; require a persistent wrong-object intent signal.
failure_signature:
- W0 on libero_spatial_task task1 was 0/15 with 14 failures never firing a recovery
  skill.
- Query traces bind the BDDL target to akita_black_bowl_2_main, but most failures
  show intent_object_name=akita_black_bowl_1_main from query 5-8 while the gripper
  remains open.
- Offline replay of this predicate over W0 hits 14/15 failed episodes with first fire
  at query 5-8, satisfying the minimum query window without relying on seed or absolute
  coordinates.
- A 5-episode forced q7 probe using the existing hollow_bowl_rim_topdown grasp achieved
  3/5, including successful full Place plans onto plate_1_main.
recovery_point: Fire after wrong-object intent has persisted for at least two queries
  and before the wrong bowl is closed on, so cuTAMP can plan a full pick-place for
  akita_black_bowl_2_main.
applies_to:
  all:
  - task_language_matches: black bowl.*not between.*plate|not between.*plate.*ramekin|not
      between.*ramekin.*plate
  - target_name_matches: akita_black_bowl_2|black_bowl|bowl
  - goal_name_matches: plate
  - bddl_goal_surface_matches: plate
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - wrong_object_intent_persist_queries_gte: 2
  - wrong_object_intent_margin_gt: 0.03
  - target_ee_distance_lt: 0.35
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
    source: libero_spatial_task01_cross_suite_w1_wrong_object_probe
    notes: Reuses the registered hollow_bowl_rim_topdown grasp hint already active
      for black-bowl-on-plate recoveries.
evidence:
  tasks:
  - 'libero_spatial_task task1: Pick the akita black bowl not between the plate and
    the ramekin and place it on the plate'
  - libero_90 task01 Pick the akita black bowl not between the plate and the ramekin
    and place it on the plate
  - libero_90 task03 Pick the akita black bowl next to the plate and place it on the
    plate
  episodes:
  - task1_ep0_seed51
  - task1_ep1_seed52
  - task1_ep2_seed53
  - task1_ep3_seed54
  - task1_ep4_seed55
  - task1_ep6_seed57
  - task1_ep7_seed58
  - task1_ep8_seed59
  - task1_ep9_seed60
  - task1_ep10_seed61
  - task1_ep11_seed62
  - task1_ep12_seed63
  - task1_ep13_seed64
  - task1_ep14_seed65
  - probe_force_q7_seed52_success
  - probe_force_q7_seed54_success
  - probe_force_q7_seed55_success
  - task1_ep5_seed56
  - task3_ep0_seed51
  - task3_ep1_seed52
  - task3_ep3_seed54
  - task3_ep4_seed55
  - task3_ep5_seed56
  - task3_ep6_seed57
  - task3_ep7_seed58
  - task3_ep8_seed59
  - task3_ep9_seed60
  - task3_ep10_seed61
  - task3_ep11_seed62
  - task3_ep13_seed64
  - task3_ep14_seed65
---
This trigger is intentionally narrower than the existing generic bowl-on-plate handoff. It uses the runner's wrong-object intent diagnostics as the negative signal and leaves grasp selection to the existing hollow bowl profile.
