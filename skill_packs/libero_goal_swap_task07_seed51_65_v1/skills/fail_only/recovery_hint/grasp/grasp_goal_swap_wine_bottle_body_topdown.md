---
id: grasp_goal_swap_wine_bottle_body_topdown
name: Goal-swap wine bottle body top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 54
when_to_apply: When recovery is manipulating the wine bottle target in the cabinet-top
  goal-swap task and the VLA never picked the target.
when_not_to_apply: Do not use for bowls, mugs, cream cheese, flat boxes, books, cans,
  cartons, or non-wine-bottle targets.
failure_signature:
- Task03 W0 never held or moved `wine_bottle_1_main` across 15 failures.
- The target bottle starts fallen, so recovery should generate a body grasp from object
  geometry instead of inheriting the VLA's wrong-object approach.
recovery_point: After the repair skill enters `cutamp_recover`, bias cuTAMP toward
  top-down body grasps around the fallen bottle.
applies_to:
  all:
  - task_language_matches: wine bottle.*cabinet|cabinet.*wine bottle
  - target_name_matches: wine_bottle|wine bottle
  - bddl_goal_surface_matches: cabinet|cabinet_top
recovery_hints:
  grasp_profile: goal_swap_wine_bottle_body_topdown_v1
  target: target
  params:
    source: libero_goal_swap_task03_seed51_65_w1
evidence:
  tasks:
  - 'libero_goal_swap task03: put the wine bottle on top of the cabinet'
  - libero_90 task03 put the wine bottle on top of the cabinet
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
---
This hint owns only the task-local wine-bottle grasp sampler. Grounding remains the
BDDL cabinet-top goal, and placement behavior is left unchanged for W1.
