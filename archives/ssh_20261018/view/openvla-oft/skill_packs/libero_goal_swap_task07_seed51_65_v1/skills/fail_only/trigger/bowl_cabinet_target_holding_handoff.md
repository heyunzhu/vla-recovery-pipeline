---
id: bowl_cabinet_target_holding_handoff
name: Bowl cabinet target holding handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 63
when_to_apply: In put-the-bowl-on-top-of-the-cabinet tasks, hand off after the VLA
  has committed to and is holding or tightly tracking the parsed black bowl target,
  before it drifts around the cabinet without releasing on the top surface.
when_not_to_apply: Do not use for bowl-on-plate tasks, cream-cheese-in-bowl tasks,
  wine-bottle tasks, flat boxes, mugs, books, baskets, trays, or non-cabinet-top goals.
failure_signature:
- LIBERO-PRO goal-swap task05 baseline and same-pack W0 are both 0/15 with no recovery
  calls.
- Query traces show `akita_black_bowl_1_main` as the parsed target and `wooden_cabinet_1_cabinet_top`
  as the BDDL goal surface.
- Failed episodes often reach `holding_status=holding` with the target near the gripper,
  but the bowl is not placed on the cabinet top by the end of the rollout.
recovery_point: Fire after the VLA has picked or tightly approached the target bowl,
  so cuTAMP can take over the cabinet-top placement using the current target pose.
applies_to:
  all:
  - task_language_matches: bowl.*cabinet|cabinet.*bowl
  - target_name_matches: bowl
  - target_name_excludes: white_bowl
  - bddl_goal_surface_matches: cabinet|cabinet_top|wooden_cabinet.*cabinet_top
trigger:
  all:
  - target_ee_distance_lt: 0.19
  - target_future_min_xy_distance_lt: 0.19
  any:
  - holding_status_is: holding
  - aperture_lt: 0.03
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
    source: libero_goal_swap_task05_seed51_65_w1
    executor:
      place_lift_max_steps: 80
      place_lift_reached_m: 0.015
      place_hover_clearance_m: 0.08
      place_hover_max_steps: 80
      place_hover_reached_m: 0.018
evidence:
  tasks:
  - 'libero_goal_swap task05: put the bowl on top of the cabinet'
  - libero_90 task05 put the bowl on top of the cabinet
  episodes:
  - task5_ep0_seed51
  - task5_ep1_seed52
  - task5_ep2_seed53
  - task5_ep3_seed54
  - task5_ep4_seed55
  - task5_ep5_seed56
  - task5_ep6_seed57
  - task5_ep7_seed58
  - task5_ep8_seed59
  - task5_ep9_seed60
  - task5_ep10_seed61
  - task5_ep11_seed62
  - task5_ep12_seed63
  - task5_ep13_seed64
  - task5_ep14_seed65
---
This is a narrow repair entrypoint for the black bowl cabinet-top task. It avoids early fire by requiring the target bowl to be close to the gripper and either already held or contacted after gripper closure; it does not try to solve unrelated bowl goals.
