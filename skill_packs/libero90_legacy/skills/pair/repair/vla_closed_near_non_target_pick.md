---
id: vla_closed_near_non_target_pick
name: VLA closed near a non-target pickable object
kind: repair
track: pair
hook: after_pi0_query
priority: 70
when_to_apply: When the VLA closes the gripper during pick, the end effector is far from the parsed target, and the closest pickable object is not the target.
when_not_to_apply: Do not use when the closest pickable object is the target, when no nearby pickable object is known, or when the gripper is open.
failure_signature:
  - VLA closes near another grocery object while the task target remains far from the end effector.
  - holding_object remains empty or unconfirmed, so the empty-close stall trigger may fire late or not at all.
recovery_point: Immediately after a VLA query reports a closed gripper near a non-target pickable object.
applies_to:
  all:
    - target_name_excludes: "book|bowl|mug|moka_pot"
trigger:
  all:
    - aperture_lt: 0.02
    - nearest_pickable_is_target: false
    - nearest_pickable_distance_lt: 0.09
    - target_ee_distance_gt: 0.12
backend: cutamp_recover
evidence:
  tasks:
    - libero_90 task53 pick up the milk and put it in the basket
  episodes:
    - online_skill_regression_tasks48_50_52_53_54_57_58_grasp_profiles_20260824 task53 ep00-ep04
---

## Intent

This repair skill catches wrong-object VLA pick attempts before the older empty
closed-gripper stall trigger has enough evidence to fire. It relies on runner
state that compares the closed end effector against the parsed task target and
the nearest non-container, non-surface pickable object.

It does not choose object grasps or placement geometry. Once fired, it enters
the existing `cutamp_recover` backend and lets active recovery-hint skills
select the grasp profile and placement representation.
