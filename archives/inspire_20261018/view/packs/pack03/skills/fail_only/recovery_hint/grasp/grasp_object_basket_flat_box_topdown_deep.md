---
id: grasp_object_basket_flat_box_topdown_deep
name: Object basket flat-box deep top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 60
when_to_apply: When basket recovery must pick cream cheese, butter, or chocolate
  pudding and the generic top-down sampler either has no feasible grasp or stalls
  while executing a shallow, over-wide pick.
when_not_to_apply: Do not use for cans, bottles, bowls, mugs, cartons, salad
  dressing, milk, orange juice, ketchup, tomato sauce, alphabet soup, or BBQ sauce.
failure_signature:
- Butter and chocolate pudding each produced zero satisfying particles in all 20
  recorded cuTAMP solves while using 36 generic top-down candidates at 0.085 m
  gripper width.
- Cream cheese planning was feasible in 8 of 12 solves, but all five failed
  episodes stopped on Pick with optimized_motion_tracking_stalled.
- The three target AABBs are thin rectangular packages, and the existing
  cream_cheese_flat_box_topdown_deep_v1 profile is geometry-parameterized rather
  than fixed to the default cream-cheese dimensions.
recovery_point: After a matching basket trigger enters cutamp_recover, replace the
  generic top-down target grasp set with deeper, dimension-scaled flat-box grasps.
applies_to:
  all:
  - task_language_matches: pick the (cream cheese|butter|chocolate pudding) and place it in the basket
  - target_name_matches: cream_cheese|cream cheese|butter|chocolate_pudding|chocolate pudding
  - bddl_goal_surface_matches: basket
recovery_hints:
  grasp_profile: cream_cheese_flat_box_topdown_deep_v1
  target: target
  params:
    source: object_axis_grasp_diagnosis_20260919
evidence:
  tasks:
  - 'libero_object_swap task02: Pick the cream cheese and place it in the basket'
  - 'libero_object_swap task07: Pick the butter and place it in the basket'
  - 'libero_object_swap task09: Pick the chocolate pudding and place it in the basket'
  episodes:
  - object_swap_w0_trigger_5ep/task02/ep00
  - object_swap_w0_trigger_5ep/task02/ep01
  - object_swap_w0_trigger_5ep/task02/ep02
  - object_swap_w0_trigger_5ep/task02/ep03
  - object_swap_w0_trigger_5ep/task02/ep04
  - object_swap_w0_trigger_5ep/task07/ep00
  - object_swap_w0_trigger_5ep/task07/ep01
  - object_swap_w0_trigger_5ep/task07/ep02
  - object_swap_w0_trigger_5ep/task07/ep03
  - object_swap_w0_trigger_5ep/task07/ep04
  - object_swap_w0_trigger_5ep/task09/ep00
  - object_swap_w0_trigger_5ep/task09/ep01
  - object_swap_w0_trigger_5ep/task09/ep02
  - object_swap_w0_trigger_5ep/task09/ep03
  - object_swap_w0_trigger_5ep/task09/ep04
---
This draft changes only the target grasp sampler. The reused profile derives its
depth, orientation, offsets, and gripper width from the runtime target AABB and
pose; its legacy name does not make the implementation cream-cheese-specific.
