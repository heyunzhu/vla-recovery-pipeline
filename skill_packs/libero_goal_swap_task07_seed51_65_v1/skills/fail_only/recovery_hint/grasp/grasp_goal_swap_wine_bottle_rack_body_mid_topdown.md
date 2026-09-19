---
id: grasp_goal_swap_wine_bottle_rack_body_mid_topdown
name: Goal-swap wine bottle rack mid body top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 63
when_to_apply: When a rack-goal recovery needs to pick `wine_bottle_1_main` after
  the VLA commits to another object.
when_not_to_apply: Do not use for bowls, mugs, cream cheese, flat boxes, books, cans,
  cartons, or non-wine-bottle targets. Do not use for cabinet-top goals or non-rack
  goals.
failure_signature:
- W0 never triggers recovery, but query traces show the target is still the same fallen
  wine bottle object class handled by the validated task03 W4 sampler.
- The task03 W4 mid-body top-down profile lifted the same wine-bottle asset reliably
  after lower/high samplers failed in different ways.
recovery_point: During cuTAMP recovery planning, use the existing mid-height bottle-body
  top-down candidates for the wine bottle.
applies_to:
  all:
  - task_language_matches: wine bottle.*rack|rack.*wine bottle
  - target_name_matches: wine_bottle|wine bottle
  - bddl_goal_surface_matches: wine_rack|rack
recovery_hints:
  grasp_profile: goal_swap_wine_bottle_body_mid_topdown_v3
  target: target
  params:
    source: libero_goal_swap_task10_seed51_65_w1
evidence:
  tasks:
  - 'libero_goal_swap task10: put the wine bottle on the rack'
  - 'libero_goal_swap task03: put the wine bottle on top of the cabinet'
  - libero_90 task10 put the wine bottle on the rack
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
---
This hint deliberately reuses the already registered wine-bottle mid-body grasp
profile. It changes only applicability from cabinet-top to rack-goal recovery.
