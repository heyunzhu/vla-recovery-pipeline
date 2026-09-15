---
id: task01_black_bowl_inward_diagonal_rim
name: Task01 black bowl stable outer top-down grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 78
when_to_apply: When task01 recovery is picking akita_black_bowl_2_main before placing it on plate_1_main.
when_not_to_apply: Do not apply to the distractor bowl, white bowls, mugs, boxes, plates, or non-plate goals.
failure_signature:
  - The policy often moves toward akita_black_bowl_1_main even though BDDL target is akita_black_bowl_2_main.
  - 4DOF runner-default ablations generated profile candidates in debug JSON but did not feed them into cuTAMP particles.
  - With real_cutamp_grasp_dof=6 and the v2 profile active, forced_q5_grasp_collision_v2_dof6_seed71_n1_max200_r3 successfully grasped, lifted, and placed the target bowl.
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
    - forced_q5_grasp_collision_v2_dof6_seed71_n1_max200_r3 task01 ep00 success with 6D grasp binding and confirmed lift
    - forced_q5_grasp_collision_v2_seed71_n1_max200 task01 ep00 showed the earlier 4DOF launch mismatch
---

## Intent

Use the task-local stable outer top-down bowl profile for the BDDL target bowl.
The recovery repair redirects the policy from the distractor bowl to
`akita_black_bowl_2_main`; this hint makes cuTAMP sample an outer-rim top-down
6DOF grasp for that target before placing it on `plate_1_main`.

This hint depends on running the real cuTAMP backend with `grasp_dof=6`. With
`grasp_dof=4`, the profile candidates can appear in debug artifacts without
entering particle initialization, which invalidates the grasp evidence.
