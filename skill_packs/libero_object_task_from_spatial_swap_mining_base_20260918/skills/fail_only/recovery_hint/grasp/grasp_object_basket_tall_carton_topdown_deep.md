---
id: grasp_object_basket_tall_carton_topdown_deep
name: Milk and orange-juice basket dimension-scaled deep grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 61
when_to_apply: When basket recovery must pick the milk or orange-juice carton
  and the generic top-down grasp closes through the object without retaining it.
when_not_to_apply: Do not use for cans, bowls, flat boxes, cream cheese, butter,
  chocolate pudding, sauces, or salad dressing.
failure_signature:
- Failed milk and orange-juice recoveries are planner-feasible but the first
  lift probe has object_followed=false, bilateral_contact=false, and lift below
  0.003 m; successful probes retain about 0.021-0.023 m lift.
- Their runtime AABB is about 0.0525 x 0.0531 x 0.1312 m, while the generic
  top-down candidate width is about 0.0821 m.
recovery_point: After a matching trigger enters recovery, use dimension-scaled
  deeper top-down grasps on the target carton.
applies_to:
  all:
  - task_language_matches: pick the (milk|orange juice) and place it in the basket
  - target_name_matches: milk|orange_juice|orange juice
  - bddl_goal_surface_matches: basket
recovery_hints:
  grasp_profile: cream_cheese_flat_box_topdown_deep_v1
  target: target
  params:
    source: object_task_tall_carton_grasp_gap_20260920
evidence:
  tasks:
  - 'libero_object_task task05: Pick the milk and place it in the basket'
  - 'libero_object_task task07: Pick the orange juice and place it in the basket'
  episodes:
  - object_task_w0_triggers_graspcand_5ep/task05/ep03
  - object_task_w0_triggers_graspcand_5ep/task05/ep04
  - object_task_w0_triggers_graspcand_5ep/task07/ep00
  - object_task_w0_triggers_graspcand_5ep/task07/ep04
---
This draft reuses the already registered geometry-parameterized profile. It does
not change trigger timing or basket placement.
