---
id: wine_bottle_rack_wrong_object_handoff
name: Wine bottle rack wrong-object handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 65
when_to_apply: In wine-bottle-to-rack tasks, hand off once the VLA repeatedly aims
  at a non-target object while the wine bottle remains static.
when_not_to_apply: Do not use for bowls, cream cheese, flat boxes, mugs, cans, books,
  caddy/basket/tray tasks, cabinet-top goals, or any task where the goal surface is
  not the wine rack. Do not use when the VLA intent is already the wine bottle.
failure_signature:
- LIBERO-PRO goal-swap task10 baseline and same-pack W0 are both 0/15 with no recovery
  calls.
- The parsed target and goal are correct; `wine_bottle_1_main` should be placed on
  `wine_rack_1_top_region`.
- W0 query traces show the wine bottle remains static and is never held, while the
  VLA path repeatedly commits to `akita_black_bowl_1_main`.
recovery_point: Fire after the first legal q5 window when non-target intent has persisted,
  the target is still static, and the VLA path remains away from the wine bottle.
applies_to:
  all:
  - task_language_matches: wine bottle.*rack|rack.*wine bottle
  - target_name_matches: wine_bottle|wine bottle
  - bddl_goal_surface_matches: wine_rack|rack
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - intent_object_is_target: false
  - wrong_progress_target_static: true
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.035
  - intent_min_xy_distance_lt: 0.06
  - target_ee_distance_gt: 0.12
  - target_ee_distance_lt: 0.24
  - target_future_min_xy_distance_gt: 0.05
recovery_hints:
  params:
    repair_profile: wine_bottle_high_grasp_close_guard_v1
    source: libero_goal_swap_task10_seed51_65_w1
evidence:
  tasks:
  - 'libero_goal_swap task10: put the wine bottle on the rack'
  - libero_90 task10 put the wine bottle on the rack
  - libero_90 task05 put the bowl on top of the cabinet
  episodes:
  - task10_ep0_seed51
  - task10_ep1_seed52
  - task10_ep2_seed53
  - task10_ep3_seed54
  - task10_ep4_seed55
  - task10_ep5_seed56
  - task10_ep6_seed57
  - task10_ep7_seed58
  - task10_ep8_seed59
  - task10_ep9_seed60
  - task10_ep10_seed61
  - task10_ep11_seed62
  - task10_ep12_seed63
  - task10_ep13_seed64
  - task10_ep14_seed65
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
This trigger owns only the recovery handoff. It is rack-scoped and requires
persistent non-target trajectory intent with a static wine-bottle target, so it
does not become a generic early-delegation rule.
