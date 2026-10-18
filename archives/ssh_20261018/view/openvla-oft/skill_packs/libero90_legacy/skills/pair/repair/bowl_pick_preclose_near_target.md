---
id: bowl_pick_preclose_near_target
name: Bowl pick pre-close near-target recovery
kind: repair
track: pair
hook: after_pi0_query
priority: 65
when_to_apply: A bowl pick is approaching the parsed target bowl with an open
  empty hand, the nearest pickable object is the target, and the predicted VLA
  trajectory is already aimed into the target neighborhood.
when_not_to_apply: Do not use when the nearest pickable object is not the target,
  while the end effector is still far from the target bowl, or when the gripper
  is already holding an object.
failure_signature:
  - Task10/task11 regressions showed recovery firing only after the gripper was
    already very close to the bowl.
  - The first recovery motion could then open or rotate near the bowl and disturb
    the target before cuTAMP reached the planned close pose.
  - Task64 ep02/ep03 reached a clear target-bowl approach at 8-9 cm but only
    fired after the gripper had nearly closed at about 6 cm.
recovery_point: One or two VLA queries before the empty-close stall trigger,
  while the end effector is near the target bowl and the policy trajectory has
  committed to that target.
applies_to:
  all:
    - target_name_matches: "bowl"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - nearest_pickable_is_target: true
    - target_ee_distance_lt: 0.11
    - target_future_min_xy_distance_lt: 0.07
backend: cutamp_recover
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
evidence:
  tasks:
    - libero_90 task10 put the black bowl on the plate
    - libero_90 task11 put the black bowl on top of the cabinet
  episodes:
    - online_skill_regression_tasks01_73_no_wrong_object_20260825 task10 ep01/ep03
    - online_skill_regression_tasks01_73_no_wrong_object_20260825 task11 ep02/ep03
---

## Intent

This skill only moves the intervention point earlier for target-bowl picks. It
does not choose a grasp profile or placement target. Once it fires, normal
recovery-hint skills still supply bowl grasp sampling and cabinet/plate
grounding.

## Entry Behavior

The repair profile asks cuTAMP recovery to lift the end effector straight upward
before the first recovery perception/planning pass. The lift keeps XY and
rotation commands at zero and uses a neutral gripper command, so recovery starts
from a less disruptive pose before planning a fresh pick/place sequence.

## Use Notes

- Keep this skill target-aware through `nearest_pickable_is_target: true`.
- Keep `vla_closed_near_non_target_pick` at higher priority for wrong-object
  close events.
- Do not depend on `gripper_cmd`: older traces often leave it unset even when
  the VLA trajectory is clearly committed to the target bowl.
- If this starts firing too early on non-bowl geometry, narrow it through a
  future target-class predicate instead of adding absolute query indices.
