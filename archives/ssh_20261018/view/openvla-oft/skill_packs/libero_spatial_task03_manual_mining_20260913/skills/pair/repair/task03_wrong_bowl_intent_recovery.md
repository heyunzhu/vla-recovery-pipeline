---
id: task03_wrong_bowl_intent_recovery
name: Task03 wrong-bowl intent recovery
kind: repair
track: pair
hook: after_pi0_query
priority: 88
when_to_apply: When task03's VLA trajectory persistently approaches the table-center distractor bowl while the BDDL target bowl next to the plate remains static and unheld.
when_not_to_apply: Do not use after any object is already held, when the predicted trajectory is closer to the BDDL target bowl, or for other black-bowl-to-plate tasks with a different target/surface binding.
failure_signature:
  - Skills-off baseline seed51-55 was 0/5; traces show sustained intent toward akita_black_bowl_1_main while target akita_black_bowl_2_main stays static.
  - Videos show the gripper approaching, grasping, and transporting the table-center distractor bowl instead of the bowl next to the plate.
recovery_point: Early open-hand wrong-object approach, before the gripper closes on the distractor bowl.
applies_to:
  all:
    - target_name_matches: "^akita_black_bowl_2"
    - bddl_goal_surface_matches: "plate_1"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - intent_object_is_target: false
    - wrong_progress_target_static: true
    - wrong_object_intent_persist_queries_gte: 4
    - wrong_object_intent_margin_gt: 0.05
    - intent_min_xy_distance_lt: 0.09
    - nearest_pickable_is_target: false
    - nearest_pickable_distance_lt: 0.27
    - target_ee_distance_gt: 0.20
    - target_future_min_xy_distance_gt: 0.14
backend: cutamp_recover
evidence:
  tasks:
    - libero_spatial_task task03 Pick the akita black bowl next to the plate and place it on the plate
  episodes:
    - baseline_seed51_55_n5 task03 ep00-ep04 all failed with recoveries=0
    - probe_force_q4_seed51_n1 task03 ep00 succeeded with one forced recovery
    - probe_force_q4_seed51_55_n5 task03 ep00/ep01/ep02/ep04 succeeded; ep03 no-opped because start goal_check treated the target as already near the plate
    - skill_v2_seed51_55_n5 succeeded 4/5 after removing the delayed vla_pick_target_status gate
    - skill_v2_seed51_65_n15 succeeded 10/15, exceeding the 9/15 manual-mining acceptance target
---

## Visual Diagnosis

Baseline videos for ep00 and ep03 show the same visible split: the end effector
approaches the table-center black bowl, closes on it, and later carries that
distractor near the plate. The BDDL target bowl next to the plate remains
unmoved, matching the trace fields `intent_object_is_target=false` and
`wrong_progress_target_static=true`.

`first_visible_error_query` is q3-q4: the hand is still open, the future action
chunk is closer to `akita_black_bowl_1_main`, and the target future distance is
still large. `too_late_query` is around q12-q16, when the wrong bowl is already
closed on or held.

## Force Recovery Ablation

- `probe_force_q4_seed51_n1`: 1/1, recovery picked `akita_black_bowl_2_main`
  and placed it on `plate_1_main`.
- `probe_force_q4_seed51_55_n5`: 4/5. The four successful episodes executed
  pick/place normally. The failed ep03 did not expose a grasp or motion-planning
  failure; recovery returned immediately because the start `goal_check` judged
  the target bowl close enough to the plate (`xy_dist ~= 0.129m`), then VLA
  continued to move the wrong bowl.
- `skill_v1_seed51_55_n5`: 3/5. ep00 fired later than the q4 probe window,
  so v2 removes the extra `vla_pick_target_status` gate while retaining
  persistent wrong-object intent, target-static, margin, and distance evidence.

## Trigger Rationale

This is the wrong-object-intent repair family. The trigger uses persistent
intent, a non-target nearest pickable, static target evidence, a meaningful
future-distance margin, and an open empty gripper. It does not require
`vla_pick_target_status` to have already flipped from `open`, because ep00's
successful forced-recovery window precedes that delayed diagnostic label. It
deliberately avoids seed, query index, or absolute coordinates.

The skill only decides when to enter recovery. It relies on the BDDL target and
goal already supplied by the runner; no task-specific grasp, grounding,
geometry, place, or target-binding hint is added in this version.

## Residual Risk

One q4 forced episode revealed that the shared recovery start `goal_check`
treats target-to-plate distances under roughly 0.13m as already satisfied even
when LIBERO's final task checker later fails. If validation misses the 9/15
threshold, the next change should address that goal-check/goal-selection issue
rather than widening this repair trigger.

Full validation passed but kept that residual: `skill_v2_seed51_65_n15` was
10/15. Failed ep03, ep11, and ep12 all entered this skill at the intended early
wrong-object window, then no-opped because initial `goal_check` accepted
`xy_dist` values in the 0.123-0.129m range. Failed ep13 did not no-op; cuTAMP
attempted execution but stopped on `optimized_motion_tracking_stalled` and
`optimized_motion_budget_exhausted`. Failed ep14 never satisfied the persistent
wrong-object trigger and appears to be a different target-approach/grasp
residual, not this repair signature.
