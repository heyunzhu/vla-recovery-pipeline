---
id: grasp_small_shallow_bowl_rim_diagonal_topdown
name: Small shallow bowl rim diagonal top-down grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 51
when_to_apply: When an already-triggered recovery is manipulating the small white bowl in a plate placement task.
when_not_to_apply: Do not use for the larger black bowls that are already covered by the generic bowl rim profile, mugs, cans, boxes, or non-bowl objects.
failure_signature:
  - White-bowl pick failures showed lift_probe_unconfirmed and gripper_closed_but_not_holding.
  - The white bowl is smaller and shallower than the black bowls; fixed-depth rim sampling can clamp grasp z to the object-frame bottom.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "white bowl.*plate|plate.*white bowl"
    - target_name_matches: "white_bowl|white bowl"
recovery_hints:
  grasp_profile: bowl_rim_small_shallow_diagonal_topdown_v1
  target: target
  params:
    source: task37_task38_white_bowl_pick_analysis_20260826
evidence:
  tasks:
    - libero_90 task37 put the white bowl on the plate
    - libero_90 task38 put the white bowl to the right of the plate
  episodes:
    - task37_task38_white_bowl_radial_yaw_20260826
---

## Intent

This policy contributes only the shallow white-bowl grasp sampler profile. It
keeps the diagonal rim family but uses a height-relative grasp depth so shallow
bowls are not sampled at the bottom of the AABB. Candidate yaw values are
chosen so the Panda gripper's jaw axis, rather than its local x axis, is radial
to the bowl rim.

It does not decide when to recover and does not define placement goals or
planner geometry.
