---
id: object_basket_bbq_orange_precontact_wrong_intent
name: BBQ and orange-juice basket precontact wrong-intent handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 78
when_to_apply: In BBQ-sauce or orange-juice basket-placement tasks, hand off once
  wrong-object intent has persisted for four queries and the gripper has entered
  a bounded 0.08-0.20 m precontact approach window around a non-target object.
when_not_to_apply: Do not use outside these two targets, after an object is held,
  when the nearest object is within 0.08 m, or when the inferred path is not
  decisively closer to the non-target than to the true target.
failure_signature:
- In the 600-episode object-axis corpus this window matches all 120 failed
  BBQ-sauce/orange-juice episodes, first at q5-q10, with no q<5 match.
- At every first match the inferred wrong object has moved at most 0.002 m and
  the nearest pickable remains at least 0.0837 m away.
recovery_point: Enter recovery during the final wrong-object approach, after the
  initial ambiguous queries but before measurable displacement of the wrong object.
applies_to:
  all:
  - task_language_matches: pick the (bbq sauce|orange juice) and place it in the basket
  - target_name_matches: bbq_sauce|bbq sauce|orange_juice|orange juice
  - bddl_goal_surface_matches: basket
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.03
  - intent_min_xy_distance_lt: 0.03
  - target_future_min_xy_distance_gt: 0.12
  - nearest_pickable_is_target: false
  - nearest_pickable_distance_gt: 0.08
  - nearest_pickable_distance_lt: 0.20
  - vla_pick_target_status_is: non_target_intent
recovery_hints:
  params:
    source: object_axes_offline_precontact_bbq_orange_20260919
evidence:
  tasks:
  - libero_object_task and libero_object_swap BBQ-sauce/orange-juice basket tasks
  episodes:
  - libero_screening_20260918 object axes, baseline and W0, seeds 51-65
---
This draft only decides when to hand off. It does not select a grasp or place profile.
