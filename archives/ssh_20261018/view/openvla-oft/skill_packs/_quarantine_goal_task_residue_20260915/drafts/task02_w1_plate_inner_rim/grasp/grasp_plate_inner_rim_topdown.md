---
id: grasp_plate_inner_rim_topdown
name: Plate inner-rim top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 68
when_to_apply: Use when the task is putting plate_1_main on the stove or cook_region, the existing plate-stove repair has already handed off to recovery, and the remaining failure is plate grasp feasibility or holding confirmation.
when_not_to_apply: Do not use for bowls, cream cheese, bottles, drawers, cabinets, black-bowl spatial tasks, or cases where the target is already held and only place/release is failing.
failure_signature:
- W0 on libero_goal_task task02 fires plate_stove_open_wrong_intent_pregrasp_handoff in all 15 seed51-65 episodes, so entry timing is not the main miss.
- W0 already grounds the target surface to flat_stove_1_cook_region through the inherited grounding and geometry hints.
- Most W0 failures are no satisfying particles, motion-planning failures, or close/lift checks where the plate was not confirmed held.
recovery_point: After a plate-stove repair entrypoint has decided to call recovery.
applies_to:
  all:
  - task_language_matches: plate.*stove|stove.*plate
  - target_name_matches: plate
  - bddl_goal_surface_matches: flat_stove|stove|cook_region
recovery_hints:
  grasp_profile: plate_inner_rim_topdown_v2
  target: target
  params:
    source: libero_goal_task02_cross_suite_seed51_65_w1
evidence:
  tasks:
  - libero_goal_task task02 Put the plate on the stove
  episodes:
  - task2_ep05_seed56
  - task2_ep13_seed64
  - task2_ep14_seed65
---
This hint changes only the plate grasp profile. `plate_inner_rim_topdown_v2` samples a thin-object top-down grasp closer to the plate inner rim, with tangential yaw families tried before radial yaws and a slightly wider gripper opening than the earlier rim-edge profile.
