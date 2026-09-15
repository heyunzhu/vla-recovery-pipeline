---
id: grasp_task38_white_bowl_microwave_high_lift
name: Task38 white bowl high lift after grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 52
when_to_apply: When task38 recovery grasps the white bowl from the microwave and must clear nearby microwave geometry before any lateral transfer.
when_not_to_apply: Do not use for black bowls, caddy/drawer/cabinet tasks, or general white-bowl placement tasks that are not right-of-plate task38.
failure_signature:
  - The recovery grasp closes on the white bowl, but the bowl collides with the microwave while leaving the initial support.
  - A short post-close lift probe can confirm holding but does not provide enough clearance before the place transfer begins.
recovery_point: After a repair/trigger skill has already decided to call recovery and before the executor transfers the held bowl toward the place region.
applies_to:
  all:
    - task_language_matches: "white bowl.*right.*plate|right.*plate.*white bowl"
    - target_name_matches: "white_bowl|white bowl"
recovery_hints:
  grasp_profile: bowl_rim_small_shallow_diagonal_topdown_v1
  target: target
  params:
    executor:
      grasp_lift_probe_m: 0.085
      grasp_lift_probe_max_steps: 30
      grasp_lift_follow_m: 0.030
    source: task38_white_bowl_microwave_clearance_20260829
evidence:
  tasks:
    - libero_90 task38 put the white bowl to the right of the plate
  episodes:
    - task38_held_transfer_keep_z_gpu0_r1 ep00 still collided with the microwave after pick; the default 3 cm lift probe only lifted the bowl by about 2 cm.
---

## Intent

This policy keeps the existing shallow white-bowl grasp sampler, but changes
the executor behavior immediately after closing the gripper. It asks the
executor to lift vertically by about 8.5 cm while keeping the gripper closed
and preserving the current pose orientation. The grasp is accepted only if the
object follows the gripper by at least 3 cm, so a weak or partial pickup should
not proceed into the place transfer.
