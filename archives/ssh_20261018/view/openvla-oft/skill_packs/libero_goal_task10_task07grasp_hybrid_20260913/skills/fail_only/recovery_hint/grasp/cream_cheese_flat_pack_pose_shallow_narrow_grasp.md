---
id: cream_cheese_flat_pack_pose_shallow_narrow_grasp
name: Cream-cheese pose-aware shallow narrow grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 73
when_to_apply: When task10 recovery is trying to grasp or place cream_cheese_1_main
  on the wine-rack top after the rack grounding and geometry hints have fired.
when_not_to_apply: Do not use for non-cream-cheese targets, non-rack tasks, or generic
  flat-box tasks outside this fresh task10 pack.
failure_signature:
- W4 validation still scored 0/5 after adding `cream_cheese_flat_pack_short_side_deep_v1`.
- W4 cuTAMP debug showed the W4 profile was active in all recovery solves but produced
  `num_satisfying=0`.
- All 16 W4 solve records for task10 used cream-cheese grasp candidates with local_z
  0.0, world_z about -0.0031 m, and width 0.075 m.
- W4 stderr repeatedly reported zero-satisfying `Collision robot_to_world` and `KinematicConstraint
  pos_err`, consistent with an over-wide, too-deep grasp candidate for the rotated
  thin cream-cheese pack.
recovery_point: After an existing repair or trigger skill has already decided to call
  recovery.
applies_to:
  all:
  - task_language_matches: cream cheese.*rack|rack.*cream cheese
  - target_name_matches: '*cream_cheese*'
recovery_hints:
  grasp_profile: cream_cheese_flat_pack_pose_shallow_narrow_v2
  target: target
  params:
    source: task10_w4_pose_depth_width_debug
evidence:
  tasks:
  - 'libero_goal_task task10: Put the cream cheese on the rack'
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - mine_val_task10_w4_ep0
  - mine_val_task10_w4_ep2
  - mine_val_task10_w4_ep3
  - mine_val_task10_w4_ep4
  - task10_ep1_seed51
---
## Intent

This policy contributes only a grasp profile. It supersedes the W4 deep/wide cream-cheese grasp when both hints match by using a higher priority. The profile is pose-aware: it places close poses near the local face whose normal is closest to world-up, keeps the close depth shallow, returns local rpy for a world top-down gripper yaw, and narrows the gripper aperture. It does not change trigger timing, grounding, rack geometry, place candidates, or executor options.
