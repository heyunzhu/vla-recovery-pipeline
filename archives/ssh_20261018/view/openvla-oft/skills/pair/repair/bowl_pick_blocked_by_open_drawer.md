---
id: bowl_pick_blocked_by_open_drawer
name: Bowl pick blocked by open drawer
kind: repair
track: pair
hook: after_pi0_query
priority: 68
when_to_apply: A bowl pick task does not require drawer manipulation, the hand is still open and empty, the end effector is still away from the bowl, and the runner has observed gripper/hand contact with a default-open cabinet or drawer blocker for three consecutive PI0 queries.
when_not_to_apply: Do not use for tasks that open, close, or place objects inside drawers; do not use after the hand is already closing on or holding the target bowl.
failure_signature:
  - Task31 and task32 failures show the arm lingering near the open cabinet drawer before an effective bowl pick starts.
  - The gripper remains open and empty, so closed-gripper empty-pick repair skills can fire late or not at all.
  - A single proximity/risk check fires too early in task31/task32; require persistent physical contact before taking over.
  - By the time the older bowl stall trigger fires, the drawer/cabinet obstacle often makes motion tracking fail.
recovery_point: After persistent open-cabinet gripper contact is confirmed, but before the VLA has moved into a late empty-close bowl stall.
applies_to:
  all:
    - target_name_matches: "bowl"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - target_ee_distance_gt: 0.12
    - vla_articulated_blocker_status_is: blocked_open_drawer_before_pick
backend: cutamp_recover
recovery_hints:
  params:
    repair_profile: entry_lift_escape_current_away_blocker_v1
evidence:
  tasks:
    - libero_90 task31 put the black bowl on the plate
    - libero_90 task32 put the black bowl on top of the cabinet
  episodes:
    - online_skill_regression_tasks01_73_no_wrong_object_20260825 task31 ep00/ep04
    - online_skill_regression_tasks01_73_no_wrong_object_20260825 task32 ep01/ep02
---

## Intent

This skill moves the recovery entry point to the first reliable evidence of
physical obstruction: three consecutive PI0 queries with gripper/hand contact
against a default-open drawer or cabinet body. It does not modify grasp
sampling, target binding, placement geometry, or the cuTAMP backend.

The runner owns the scoped blocker diagnosis. This skill consumes the resulting
status and asks the named repair profile to stage recovery before planning. The
`entry_lift_escape_current_away_blocker_v1` profile lifts straight upward with
XY and rotation locked, then translates away from the nearest drawer/cabinet
blocker with rotation locked. Normal cuTAMP bowl pick starts only after this
cleaner entry pose is reached or the retreat attempt has been diagnosed.
