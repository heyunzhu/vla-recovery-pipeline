---
id: vla_wrong_object_intent_conservative
name: Conservative wrong-object pick intent recovery
kind: repair
track: pair
hook: after_pi0_query
priority: 73
when_to_apply: When the VLA trajectory intent persistently points at a
  non-target pickable object while the hand is still empty and open.
when_not_to_apply: Do not use for one-query nearest-object flicker, when the
  target is also the nearest pickable object, or after the hand is already
  holding something.
failure_signature:
  - LIBERO-90 task81/task82/task83 failures often approached a mug while the
    parsed target was a book.
  - LIBERO-90 task85/task87 failures showed sustained non-target intent before
    the gripper closed, leaving no later target-aware repair point.
recovery_point: During the open-hand wrong-object approach, before the VLA
  closes on or pushes the non-target object.
applies_to:
  all:
    - target_name_matches: "book|mug|cup|milk|juice|carton|cream|cheese|butter|box|can"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - intent_object_is_target: false
    - wrong_object_intent_persist_queries_gte: 3
    - wrong_object_intent_margin_gt: 0.055
    - intent_min_xy_distance_lt: 0.075
    - nearest_pickable_is_target: false
    - nearest_pickable_distance_lt: 0.24
    - target_ee_distance_gt: 0.10
    - target_future_min_xy_distance_gt: 0.085
backend: cutamp_recover
evidence:
  tasks:
    - libero_90 task81 pick up the book and place it in the right compartment of the caddy
    - libero_90 task85 pick up the red mug and place it to the right of the caddy
    - libero_90 task87 pick up the book in the middle and place it on the cabinet shelf
  episodes:
    - online_skill_regression_tasks81_90_scopefix_20260829 task81 ep00/ep03/ep04 r0
    - online_skill_regression_tasks81_90_scopefix_20260829 task85 ep00 r0
    - online_skill_regression_tasks81_90_scopefix_20260829 task87 ep00 r0
---

## Intent

This skill is a conservative replacement for the earlier wrong-object intent
repair. It requires persistent trajectory intent, a meaningful margin between
the non-target and target future distances, and an end effector that is already
closer to the non-target than to the parsed target.

It deliberately does not use gripper closure as the main evidence. Closure can
be delayed or absent even when the VLA is clearly moving toward the wrong
object. Once this repair fires, normal grasp, grounding, and geometry hint
skills decide how cuTAMP should pick the parsed target and place it.
