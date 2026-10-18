---
id: object_basket_cream_cheese_far_target_ee_stall
name: Cream-cheese basket far-target end-effector stall handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 75
when_to_apply: In a cream-cheese-to-basket task, hand off when the robot remains
  handempty with an open gripper, the true target is still far and static, and
  the end effector has moved no more than 3 cm across six consecutive queries.
when_not_to_apply: Do not fire while holding an object, after gripper closure,
  while the target is being approached, before six observations exist, or
  outside cream-cheese basket tasks.
failure_signature:
- The uncovered object-task episodes run all 56 queries without recovery,
  wrong-object progress, or target approach.
- Their wrong-object identity is not stable enough for the intent-persistence
  family, but the end effector later enters a true low-motion plateau while the
  target remains far and unmoved.
recovery_point: Use a lower-priority fallback after the early q5 intent windows
  have had an opportunity to fire, but before the 56-query rollout is exhausted.
applies_to:
  all:
  - task_language_matches: pick the cream cheese and place it in the basket
  - target_name_matches: cream_cheese|cream cheese
  - bddl_goal_surface_matches: basket
trigger:
  all:
  - ee_stalled:
      window: 6
      max_disp_m: 0.03
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - target_ee_distance_gt: 0.18
  - target_future_min_xy_distance_gt: 0.12
  - wrong_progress_target_static: true
recovery_hints:
  params:
    source: object_cream_stall_trigger_round_20260920 config_D_window6_maxdisp_3cm (1cm variant rejected as too late)
evidence:
  tasks:
  - 'libero_object_task task01: Pick the cream cheese and place it in the basket'
  - 'libero_object_swap task02: Pick the cream cheese and place it in the basket'
  episodes:
  - libero_screening_20260918 object axes, baseline and W0, seeds 51-65
  - object_dev_repro_20260920 cream-cheese success/failure controls, seeds 51-55
---
This candidate does not use wrong-object identity or lower any persistence
threshold. It is deliberately lower priority than both existing cream-cheese
triggers, so those earlier, more specific rules retain precedence.
