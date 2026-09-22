---
id: object_basket_cream_cheese_early_no_approach
name: Cream-cheese basket early no-approach handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 74
when_to_apply: In a cream-cheese-to-basket task, hand off at the first query where the robot is still
  handempty with an open gripper, is not intending the target, and shows no approach toward it - the
  true target is far, static, and outside the policy's predicted approach.
when_not_to_apply: Do not fire while holding, after closure, or outside cream-cheese basket tasks.
failure_signature:
- Seeds 1-50 deterministic baseline (task t01): 25 of 50 episodes fail with recovery_calls=0 and the
  full 56-query budget; the previously shipped stall variant covered 9 of 9 such episodes but first
  fired at q25-q42, which leaves too little budget to finish a Pick+Place.
- Offline sweep on the dev corpus (seeds 51-65) picks these predicates up at q5 (task axis) with zero
  fires on success episodes.
recovery_point: Early handoff before the rollout budget is spent.
applies_to:
  all:
  - task_language_matches: pick the cream cheese and place it in the basket
  - target_name_matches: cream_cheese|cream cheese
  - bddl_goal_surface_matches: basket
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - nearest_pickable_is_target: false
  - wrong_progress_target_static: true
  - target_ee_distance_gt: 0.22
  - target_future_min_xy_distance_gt: 0.20
recovery_hints:
  params:
    source: cream_early_no_approach_offline_sweep_20260921
evidence:
  tasks:
  - 'libero_object_task task01: Pick the cream cheese and place it in the basket'
  episodes:
  - libero_screening_20260918 object axes, seeds 51-65
---
Draft for offline comparison.
