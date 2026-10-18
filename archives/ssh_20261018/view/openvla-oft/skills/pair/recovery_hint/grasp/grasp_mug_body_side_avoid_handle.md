---
id: grasp_mug_body_side_avoid_handle
name: Mug body-side avoid-handle grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 49
when_to_apply: When an already-triggered recovery is manipulating a mug or cup target.
when_not_to_apply: Do not use for bowls, cans, boxes, flat plates, drawers, handles, or non-mug objects.
failure_signature:
  - Mug pick failures can come from center-top grasps closing into the hollow opening.
  - Mug AABBs may include the handle, so extreme AABB-side samples can chase the wrong geometry.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "mug|cup"
recovery_hints:
  grasp_profile: mug_body_side_avoid_handle_v1
  target: target
  params:
    executor:
      grasp_lift_probe_m: 0.05
      grasp_lift_probe_max_steps: 18
      place_hover_clearance_m: 0.14
      place_lift_min_clearance_m: 0.10
      place_lift_max_steps: 45
    source: task35_mug_pick_analysis_20260823
evidence:
  tasks:
    - libero_90 task35 put the yellow and white mug to the front of the white mug
  episodes:
    - gpu1_selected_online_mining_clean_task35_20260823
---

## Intent

This policy contributes the mug grasp sampler profile. It biases recovery
pick sampling toward conservative body-side top-down grasps and away from the
hollow center or handle-expanded AABB edge.

It also asks the executor to lift a confirmed mug grasp higher before horizontal
transport, reducing collisions with nearby cups, plates, and objects. It does
not decide when to recover and does not define placement goals or planner
geometry.
