---
id: task01_wrong_bowl_early_recovery
name: Task01 early wrong-bowl recovery
kind: repair
track: pair
hook: after_pi0_query
priority: 86
when_to_apply: When the VLA trajectory is still handempty but is committing to the bowl between the plate and ramekin instead of the BDDL target bowl.
when_not_to_apply: Do not use after any object is already held, or when the trajectory is closer to the BDDL target bowl than to the distractor bowl.
failure_signature:
  - Baseline seed 71-73 repeatedly showed intent on akita_black_bowl_1_main while akita_black_bowl_2_main stayed static.
  - Once the wrong bowl was held, q12 recovery could not reconstruct a safe simulator holding state.
recovery_point: Early open-hand wrong-object approach, before the policy closes on or transports the distractor bowl.
applies_to:
  all:
    - target_name_matches: "akita_black_bowl_2"
    - bddl_goal_surface_matches: "plate_1"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - intent_object_is_target: false
    - wrong_progress_object_is_intent: true
    - wrong_progress_target_static: true
    - wrong_object_intent_margin_gt: 0.015
    - target_ee_distance_gt: 0.22
    - target_future_min_xy_distance_gt: 0.14
  any:
    - vla_pick_target_status_is: non_target_intent
    - vla_pick_target_status_is: non_target_intent_with_motion
    - nearest_pickable_is_target: true
backend: cutamp_recover
evidence:
  tasks:
    - libero_spatial_task task01 pick the akita black bowl not between the plate and the ramekin and place it on the plate
  episodes:
    - baseline_seed71_73_n3_egl task01 ep00 q6
    - baseline_seed71_73_n3_egl task01 ep01 q6
    - baseline_seed71_73_n3_egl task01 ep02 q5-q6
---

## Intent

This repair enters cuTAMP before the wrong bowl is grasped. The trigger is not a
fixed query index: it requires open hand, non-target intent, a static BDDL
target, and enough future-trajectory margin to avoid one-frame ambiguity. The
margin threshold is intentionally low for this task because q5 evidence shows a
stable wrong-object intent with the target still 15 cm away in the policy future
trajectory.

The actual collision relaxation is supplied by the matching collision-world
recovery hint in this pack.
