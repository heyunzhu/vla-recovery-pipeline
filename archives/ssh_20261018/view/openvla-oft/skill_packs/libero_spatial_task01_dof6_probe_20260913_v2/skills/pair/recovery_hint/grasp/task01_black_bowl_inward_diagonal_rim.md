---
id: task01_black_bowl_inward_diagonal_rim
name: Task01 black bowl DOF6 v2 grasp probe
kind: recovery_hint
track: pair
scope: grasp
priority: 78
when_to_apply: When task01 recovery is picking akita_black_bowl_2_main before placing it on plate_1_main.
when_not_to_apply: Do not apply to the distractor bowl, white bowls, mugs, boxes, plates, or non-plate goals.
failure_signature:
  - forced_q6_empty_pack_seed71_73_n3 produced holding solves with default libero_topdown, but close/lift execution failed with gripper_closed_but_not_holding.
  - Close precheck was near the target rim and briefly saw bilateral contact, then contact disappeared during dwell and lift_probe reported object_lift_m=0.
  - forced_q6_grasp_collision_v1_seed71_n1_max200 showed that the first inward v1 profile could make all 64 particles fail robot_to_movables collision.
  - forced_q6_collision_only_seed71_n1_max200 sometimes found a 1/64 feasible Pick+Place plan with v1, but execution stalled before close on the second Pick trajectory.
  - forced_q5_grasp_collision_v2_seed71_n1_max200 reached close at q5 with brief bilateral precheck contact, then dwell lost contact and lift_probe reported object_lift_m=0.
recovery_point: After the repair skill has entered cuTAMP recovery and before grasp candidates are sampled.
applies_to:
  all:
    - target_name_matches: "akita_black_bowl_2"
    - target_name_excludes: "white_bowl|plate"
    - bddl_goal_surface_matches: "plate_1"
recovery_hints:
  grasp_profile: task01_black_bowl_stable_outer_topdown_v2
  target: target
evidence:
  tasks:
    - libero_spatial_task task01 pick the akita black bowl not between the plate and the ramekin and place it on the plate
  episodes:
    - forced_q6_empty_pack_seed71_73_n3 task01 ep00 close/lift failure
    - forced_q6_empty_pack_seed71_73_n3 task01 ep02 close/lift failure
    - forced_q6_grasp_collision_v1_seed71_n1_max200 task01 ep00 no satisfying particles
    - forced_q6_collision_only_seed71_n1_max200 task01 ep00 feasible but optimized_motion_tracking_stalled before close
    - forced_q5_grasp_collision_v2_seed71_n1_max200 task01 ep00 close/lift failure after transient bilateral contact
---

## Intent

The default top-down sampler can approach the correct bowl but tends to lose
rim contact when the gripper closes. The first inward diagonal profile was too
aggressive for this scene: some solves put the robot on the target collision
boundary and others reached only a marginal q1 that stalled before close.

The active v1 profile uses inward diagonal rim candidates. Q6 evidence showed
this can be too aggressive late in the policy trajectory, but q5 is earlier and
already naturally satisfies the repair trigger after the margin update. This
run tests whether an off-center inward rim seed prevents cuTAMP from settling on
the center-of-bowl close pose that v2 reached before losing contact.

This skill does not trigger recovery and does not alter grounding, placement, or
collision-world policy.
