---
id: wine_bottle_cabinet_wrong_object_handoff
name: Wine bottle cabinet-top wrong-object handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 64
when_to_apply: In wine-bottle-to-cabinet-top tasks, hand off once the VLA repeatedly
  aims at a non-target object while the wine bottle remains static.
when_not_to_apply: Do not use for bowls, cream cheese, flat boxes, mugs, cans, books,
  caddy/basket/tray tasks, or non-cabinet-top goals. Do not use when the VLA intent
  is already the wine bottle.
failure_signature:
- LIBERO-PRO goal-swap task03 baseline and same-pack W0 are both 0/15 with no recovery
  calls.
- The parsed target and goal are correct; `wine_bottle_1_main` should be placed on
  `wooden_cabinet_1_cabinet_top`.
- W0 query traces show the wine bottle remains static and is never held, while the
  VLA path repeatedly commits to `akita_black_bowl_1_main` or another non-target object.
recovery_point: Fire after the first legal q5 window when non-target intent has persisted,
  the target is still static, and the VLA path remains away from the wine bottle.
applies_to:
  all:
  - task_language_matches: wine bottle.*cabinet|cabinet.*wine bottle
  - target_name_matches: wine_bottle|wine bottle
  - bddl_goal_surface_matches: cabinet|cabinet_top
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - intent_object_is_target: false
  - wrong_progress_target_static: true
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.035
  - intent_min_xy_distance_lt: 0.06
  - target_ee_distance_gt: 0.1
  - target_ee_distance_lt: 0.19
  - target_future_min_xy_distance_gt: 0.05
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
    source: libero_goal_swap_task03_seed51_65_w1
evidence:
  tasks:
  - 'libero_goal_swap task03: put the wine bottle on top of the cabinet'
  - libero_90 task03 put the wine bottle on top of the cabinet
  - libero_90 task05 put the bowl on top of the cabinet
  episodes:
  - task03_seed51_ep00
  - task03_seed52_ep01
  - task03_seed53_ep02
  - task03_seed54_ep03
  - task03_seed55_ep04
  - task03_seed56_ep05
  - task03_seed57_ep06
  - task03_seed58_ep07
  - task03_seed59_ep08
  - task03_seed60_ep09
  - task03_seed61_ep10
  - task03_seed62_ep11
  - task03_seed63_ep12
  - task03_seed64_ep13
  - task03_seed65_ep14
  - task3_ep0_seed51
  - task3_ep1_seed52
  - task3_ep2_seed53
  - task3_ep3_seed54
  - task3_ep4_seed55
  - task3_ep5_seed56
  - task3_ep6_seed57
  - task3_ep7_seed58
  - task3_ep8_seed59
  - task3_ep9_seed60
  - task3_ep10_seed61
  - task3_ep11_seed62
  - task3_ep12_seed63
  - task3_ep13_seed64
  - task3_ep14_seed65
  - task5_ep1_seed52
  - task5_ep2_seed53
  - task5_ep5_seed56
  - task5_ep7_seed58
  - task5_ep8_seed59
  - task5_ep9_seed60
  - task5_ep11_seed62
  - task5_ep12_seed63
  - task5_ep13_seed64
  - task5_ep14_seed65
---
This repair skill owns only the recovery handoff. Its trigger requires stable non-target
trajectory intent and a static wine-bottle target, so it is not a generic early-delegation
rule.
