---
id: cream_cheese_task10_flat_box_level_topdown
name: Task10 cream-cheese flat-box level top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 95
when_to_apply: Diagnostic task10 rack-placement runs when recovery manipulates
  cream_cheese_1_main and the task07 flat-box profile reaches a skewed or unreliable
  grasp.
when_not_to_apply: Do not use outside this temporary task10 diagnostic experiment.
failure_signature:
- Bowl/plate-off task10 diagnostics make cuTAMP planning feasible, but several
  seeds still fail at `gripper_closed_but_not_holding`.
- Successful-looking attempts show that a level, visually flat gripper posture is
  more promising than tilted or yaw-diverse grasps.
recovery_point: After task10 rack grounding/geometry hints have selected cream
  cheese as the target and before cuTAMP samples 6-DOF grasps.
applies_to:
  all:
  - task_language_matches: cream cheese.*rack|rack.*cream cheese
  - target_name_matches: '*cream_cheese*'
recovery_hints:
  grasp_profile: cream_cheese_flat_box_level_topdown_v1
  target: target
  params:
    source: task10_level_topdown_grasp_experiment
evidence:
  tasks:
  - 'libero_goal_task task10: Put the cream cheese on the rack'
  - 'diagnostic seeds 61-65: bowl/plate collision objects ignored in cuTAMP world'
---
This experiment keeps the original task07 cream-cheese profile available, but
raises this task10-specific hint above it so forced recovery uses the level
top-down profile.
