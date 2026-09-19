---
id: object_basket_salad_dressing_precontact_wrong_intent
name: Salad-dressing basket precontact wrong-intent handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 76
when_to_apply: In salad-dressing basket-placement tasks, hand off when persistent
  wrong-object intent enters a bounded 0.10-0.16 m precontact approach window
  while the true target remains more than 0.18 m from the end effector.
when_not_to_apply: Do not use outside salad-dressing basket tasks, after an object
  is held, inside 0.10 m, or once the pick-target status is no longer open.
failure_signature:
- In the 600-episode object-axis corpus this window matches all 60 failed
  salad-dressing episodes, first at q5-q9, with no q<5 match.
- At every first match the inferred wrong object has moved at most 0.002 m and
  the nearest pickable remains at least 0.1269 m away.
- The standard wrong_object_intent_margin_m is null throughout this target family;
  this draft substitutes a target-distance and non-target-distance separation and
  must remain outside the pack until that protocol exception is reviewed.
recovery_point: Enter recovery during the wrong-object approach, before measurable
  displacement of the inferred wrong object.
applies_to:
  all:
  - task_language_matches: pick the salad dressing and place it in the basket
  - target_name_matches: salad_dressing|salad dressing
  - bddl_goal_surface_matches: basket
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - wrong_object_intent_persist_queries_gte: 4
  - intent_min_xy_distance_lt: 0.05
  - target_ee_distance_gt: 0.18
  - nearest_pickable_is_target: false
  - nearest_pickable_distance_gt: 0.10
  - nearest_pickable_distance_lt: 0.16
  - vla_pick_target_status_is: open
recovery_hints:
  params:
    source: object_axes_offline_precontact_salad_dressing_20260919
evidence:
  tasks:
  - libero_object_task and libero_object_swap salad-dressing basket tasks
  episodes:
  - libero_screening_20260918 object axes, baseline and W0, seeds 51-65
---
This draft only decides when to hand off. It does not select a grasp or place profile.
