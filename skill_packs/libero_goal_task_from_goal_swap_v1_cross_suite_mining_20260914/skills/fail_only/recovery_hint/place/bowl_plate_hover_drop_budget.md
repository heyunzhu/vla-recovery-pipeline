---
id: bowl_plate_hover_drop_budget
name: Bowl plate hover drop budget
kind: recovery_hint
track: fail_only
scope: place
priority: 58
when_to_apply: Use when recovery is placing a black bowl on a plate and the planner
  has a valid pick-place plan, but execution needs more hover/drop budget to settle
  the bowl over the plate before release.
when_not_to_apply: Do not use for cabinet, rack, stove, cream-cheese, plate-as-target-object,
  or non-bowl placement tasks. Do not use when pick/grasp never succeeds or when the
  target/goal binding is wrong.
failure_signature:
- In the forced q7 5-episode probe, seed53 reached Place(akita_black_bowl_2_main,
  ..., plate_1_main) but failed with place_hover_xy_not_aligned after a trajectory_tracking_stalled
  hover-correction event.
- The same probe succeeded on seeds 52, 54, and 55 with full Place execution, showing
  the BDDL plate target and existing hollow-bowl grasp can be usable when the place
  stage has enough room to complete.
- This hint only adjusts registered executor budget/tolerance knobs already used by
  the pack; it does not alter target binding, geometry, grasp sampling, or success
  criteria.
recovery_point: After a recovery pick has confirmed holding the target bowl and before
  the final plate release.
applies_to:
  all:
  - task_language_matches: black bowl.*not between.*plate|not between.*plate.*ramekin|not
      between.*ramekin.*plate
  - target_name_matches: akita_black_bowl|black_bowl|bowl
  - target_name_excludes: white_bowl|white bowl
  - goal_name_matches: plate
  - bddl_goal_surface_matches: plate
recovery_hints:
  params:
    executor:
      place_lift_max_steps: 70
      place_lift_reached_m: 0.014
      place_lift_min_clearance_m: 0.03
      place_hover_clearance_m: 0.055
      place_hover_max_steps: 90
      place_hover_reached_m: 0.014
      place_drop_max_steps: 120
      place_drop_reached_m: 0.018
      place_release_z_max_m: 0.1
      place_open_dwell_steps: 8
    source: libero_spatial_task01_force_q7_probe
evidence:
  tasks:
  - 'libero_spatial_task task1: Pick the akita black bowl not between the plate and
    the ramekin and place it on the plate'
  - libero_90 task01 Pick the akita black bowl not between the plate and the ramekin
    and place it on the plate
  episodes:
  - probe_force_q7_seed52_success
  - probe_force_q7_seed53_place_hover_xy_not_aligned
  - probe_force_q7_seed54_success
  - probe_force_q7_seed55_success
  - task1_ep0_seed51
  - task1_ep1_seed52
  - task1_ep2_seed53
  - task1_ep3_seed54
  - task1_ep5_seed56
  - task1_ep6_seed57
  - task1_ep7_seed58
  - task1_ep8_seed59
  - task1_ep9_seed60
  - task1_ep10_seed61
  - task1_ep11_seed62
  - task1_ep12_seed63
  - task1_ep13_seed64
  - task1_ep14_seed65
---
This is a fail-only place hint for the mining round. If later validation shows it is the decisive place fix, it should be promoted into a registered place_profile instead of staying as raw executor parameters.
