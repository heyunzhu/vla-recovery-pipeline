---
id: object_basket_tomato_persistent_wrong_intent
name: Tomato sauce basket persistent wrong-intent handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 75
when_to_apply: In tomato-sauce-to-basket tasks, hand off when non-target intent has
  persisted for four queries, the gripper is open and empty, and the target's
  predicted approach remains more than 0.12 m away.
when_not_to_apply: Do not use outside tomato-sauce basket tasks, after an object is
  held, for transient wrong intent, or once the target approach is already within
  0.12 m.
failure_signature:
- A persistent wrong-object signal alone fires before q5 in part of the tomato
  corpus; requiring target_future_min_xy_distance_m above 0.12 removes those early
  rows while preserving 48 of 60 failed episodes.
- The object-axis corpus contains no successful tomato-sauce episodes, so this
  draft is additionally constrained by language, target, basket goal, and distance.
recovery_point: Enter recovery after q4 while the policy still predicts an approach
  away from the true tomato-sauce target.
applies_to:
  all:
  - task_language_matches: pick the tomato sauce and place it in the basket
  - target_name_matches: tomato_sauce|tomato sauce
  - bddl_goal_surface_matches: basket
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.0
  - target_future_min_xy_distance_gt: 0.12
recovery_hints:
  params:
    source: object_axes_offline_trigger_tomato_20260919
evidence:
  tasks:
  - libero_object_task and libero_object_swap tomato-sauce basket-placement tasks
  episodes:
  - libero_screening_20260918 object axes, baseline and W0, seeds 51-65
---
This draft only decides when to hand off. It does not select a grasp or place profile.
