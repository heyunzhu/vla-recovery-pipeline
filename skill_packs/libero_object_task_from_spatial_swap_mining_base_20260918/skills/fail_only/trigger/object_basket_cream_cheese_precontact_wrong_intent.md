---
id: object_basket_cream_cheese_precontact_wrong_intent
name: Cream-cheese basket precontact wrong-intent handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 77
when_to_apply: In cream-cheese basket-placement tasks, hand off when persistent
  wrong-object intent enters a bounded 0.10-0.16 m precontact approach window.
when_not_to_apply: Do not use outside cream-cheese basket tasks, after an object
  is held, inside 0.10 m, or after the status reports non-target motion.
failure_signature:
- In the 600-episode object-axis corpus this window matches 28 of 60 failed
  cream-cheese episodes, first at q5-q7, with no q<5 match.
- At every first match the inferred wrong object has moved at most 0.002 m and
  the nearest pickable remains at least 0.1220 m away.
recovery_point: Enter recovery after persistent intent becomes geometrically
  decisive but before measurable displacement of the wrong object.
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
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.03
  - intent_min_xy_distance_lt: 0.05
  - target_future_min_xy_distance_gt: 0.12
  - nearest_pickable_is_target: false
  - nearest_pickable_distance_gt: 0.10
  - nearest_pickable_distance_lt: 0.16
  - vla_pick_target_status_is: non_target_intent
recovery_hints:
  params:
    source: object_axes_offline_precontact_cream_cheese_20260919
evidence:
  tasks:
  - libero_object_task and libero_object_swap cream-cheese basket tasks
  episodes:
  - libero_screening_20260918 object axes, baseline and W0, seeds 51-65
---
This draft only decides when to hand off. It does not select a grasp or place profile.
