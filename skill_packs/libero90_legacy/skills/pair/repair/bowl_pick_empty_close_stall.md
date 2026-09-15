---
id: bowl_pick_empty_close_stall
name: Bowl pick empty-close stall with diagonal rim grasp
kind: repair
track: pair
hook: after_pi0_query
priority: 60
when_to_apply: A bowl-on-plate rollout has reached a black bowl, the gripper has
  closed or nearly closed, holding is still empty or unconfirmed, and the end
  effector has slowed over a short query window.
when_not_to_apply: Do not use for open-hand drawer states, non-target bowl
  approaches, or generic non-bowl stalls. Do not clone this into task-specific
  task10/task13/task14/task15 variants unless the trigger itself diverges.
failure_signature:
  - Skills-off task10 baseline failed 5/5 with empty closed-gripper bowl-pick stalls.
  - Skills-off task13 baseline failed 5/5 with the same empty closed-gripper pattern.
  - The shared trigger fired reliably on task10/task13 mining validation; later
    failures were dominated by grasp/place backend behavior, not trigger recall.
  - Current-code validation on task10, task13, task14, and task15 reached 15/20
    with the shared trigger and updated recovery backend.
  - Bowl-rim profile sweep on task10, task13, task14, and task15 favored the
    diagonal mixed top-down rim sampler at 10/12.
  - Task64 ep04 showed that a closed empty-gripper stall near a non-target bowl
    could incorrectly enter this fallback unless the target bowl is also the
    nearest pickable object.
recovery_point: Immediately after the first empty closed-gripper stall near the
  bowl, before the VLA spends the remaining horizon hovering, pushing, reopening,
  or repeating failed grasp motions.
applies_to:
  all:
    - target_name_matches: "bowl"
trigger:
  all:
    - aperture_lt: 0.02
    - holding_status_is: handempty_or_unconfirmed
    - nearest_pickable_is_target: true
    - target_ee_distance_lt: 0.11
    - ee_stalled:
        window: 3
        max_disp_m: 0.03
backend: cutamp_recover
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
evidence:
  tasks:
    - libero_90 task10 put the black bowl on the plate
    - libero_90 task13 put the black bowl at the back on the plate
    - libero_90 task14 put the black bowl at the front on the plate
    - libero_90 task15 put the middle black bowl on the plate
  episodes:
    - task10_ep0_seed90
    - task10_ep1_seed90
    - task10_ep2_seed90
    - task10_ep3_seed90
    - task10_ep4_seed90
    - task13_ep0_seed90
    - task13_ep1_seed90
    - task13_ep2_seed90
    - task13_ep3_seed90
    - task13_ep4_seed90
    - tasks10_13_14_15_currentcode_gpu3_20260821_r1
    - bowl_grasp_profiles_tasks10_13_14_15_gpu3_20260822_r1
---

## Intent

This skill promotes the shared black-bowl empty-close stall pattern into the
online pair library. It does not implement a new recovery backend. When the
trigger fires, it enters the existing `cutamp_recover` backend. Object grasp
and goal grounding details are attached by separate `recovery_hint` policies.

## Recovery Policies

This skill keeps timing separate from grasp and grounding configuration. For
bowl targets, `grasp_bowl_rim_diagonal_mixed_topdown` contributes the
`bowl_rim_diagonal_mixed_topdown_v1` sampler. For "on top of cabinet" tasks,
`cabinet_top_support_grounding` contributes the top-support grounding hint.

The repair profile is limited to recovery entry: lift the end effector straight
up before the first cuTAMP perception/planning pass. Runtime expands this named
profile into executor parameters, which keeps this repair skill focused on
trigger timing rather than low-level motion constants.

## Evidence Summary

The original mining trigger was written from task10/task13 failures and was
validated repeatedly as a reliable recovery timing signal. After backend fixes,
the same trigger reached 15/20 on task10, task13, task14, and task15 with current
code. A follow-up profile sweep over the same four tasks found the diagonal
mixed rim profile to be the best candidate, at 10/12.

Task64 later exposed a target-consistency gap: the fallback could fire while the
end effector was stalled near a neighboring bowl. The executable trigger now
requires the nearest pickable object to be the parsed target bowl, and requires
that target to be within the same local neighborhood.

## Use Notes

- Keep one shared bowl skill for this failure mode instead of task-specific
  duplicates.
- Do not encode task id, query index, seed, absolute xyz, contacts, or visual
  frame observations in the executable trigger.
- After any backend or sampler change, verify that query traces carry
  merged `recovery_hints` and cuTAMP diagnostics record
  `grasp_sampler_profile=bowl_rim_diagonal_mixed_topdown_v1`.
