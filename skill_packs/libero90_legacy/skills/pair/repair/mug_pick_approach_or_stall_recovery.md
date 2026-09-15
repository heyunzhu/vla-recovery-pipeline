---
id: mug_pick_approach_or_stall_recovery
name: Mug pick approach recovery
kind: repair
track: pair
hook: after_pi0_query
priority: 68
when_to_apply: When the parsed target is a mug or cup, the hand is empty, and
  the VLA has already approached the target mug closely enough for a planned
  recovery pick.
when_not_to_apply: Do not use for books, bowls, cans, cartons, boxes, or when
  the nearest/intent object is clearly a non-target.
failure_signature:
  - LIBERO-90 task85/task86 had no mug-specific repair entry, so mug grasp hints
    never got a chance to run.
  - Nearby mug picks can fail or collide after VLA closes without a target-aware
    handoff to cuTAMP.
recovery_point: During the final approach to the target mug, while the hand is
  still empty or before a confirmed grasp.
applies_to:
  all:
    - target_name_matches: "mug|cup"
trigger:
  all:
    - aperture_gt: 0.015
    - holding_status_is: handempty_or_unconfirmed
    - target_ee_distance_lt: 0.20
  any:
    - nearest_pickable_is_target: true
    - intent_object_is_target: true
    - target_future_min_xy_distance_lt: 0.10
backend: cutamp_recover
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_mug_v1
evidence:
  tasks:
    - libero_90 task85 pick up the red mug and place it to the right of the caddy
    - libero_90 task86 pick up the white mug and place it to the right of the caddy
  episodes:
    - online_skill_regression_tasks81_90_scopefix_20260829 task86 ep01-ep04 r0 target-mug approach
---

## Intent

This skill only decides when to enter recovery for mug targets. It relies on
`grasp_mug_body_side_avoid_handle` for the actual mug grasp profile and lift
clearance, and on separate grounding/geometry hints for placement.
