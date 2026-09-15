---
id: flat_box_wrong_object_intent_stall_recovery
name: Flat-box wrong-object intent stall recovery
kind: repair
track: pair
hook: after_pi0_query
priority: 75
when_to_apply: When the parsed target is chocolate pudding, the hand is still
  open and empty, and the VLA is persistently stalled in front of a non-target
  object instead of approaching the target.
when_not_to_apply: Do not use for tiny one-query intent flicker, after the hand
  is holding an object, or when the target itself is the nearest/intent object.
failure_signature:
  - The parsed target stays static while the end effector remains open-handed
    near a distractor.
  - Trajectory intent points at the same non-target object for several queries.
  - Wrong-object progress has not accumulated yet, so transported-object
    detection is intentionally too late for this failure mode.
recovery_point: During the stalled wrong-object approach, before the VLA closes
  on or pushes the distractor.
applies_to:
  all:
    - target_name_matches: "chocolate_pudding|pudding"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - wrong_progress_target_static: true
    - intent_object_is_target: false
    - wrong_object_intent_persist_queries_gte: 3
    - wrong_object_intent_margin_gt: 0.055
    - intent_min_xy_distance_lt: 0.075
    - nearest_pickable_is_target: false
    - nearest_pickable_distance_lt: 0.24
    - target_ee_distance_gt: 0.10
    - target_future_min_xy_distance_gt: 0.085
    - ee_stalled:
        window: 4
        max_disp_m: 0.015
backend: cutamp_recover
evidence:
  tasks:
    - libero_90 task62 pick up the chocolate pudding and put it in the tray
  episodes:
    - task62_wrong_object_progress_20260829 ep01 open-hand stall near akita_black_bowl
---

## Intent

This repair handles the pre-progress version of wrong-object behavior for
chocolate pudding targets. It does not lower the transported-wrong-object motion
threshold; instead it requires persistent non-target intent plus an actual
open-hand stall, then lets the normal flat-box grasp hint recover the parsed
target.
