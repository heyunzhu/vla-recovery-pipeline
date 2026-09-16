---
id: geometry_wine_bottle_bowl_inner_floor
name: Wine bottle bowl inner-floor geometry
kind: recovery_hint
track: fail_only
scope: geometry
priority: 48
when_to_apply: When recovery must place the wine bottle inside the black bowl and
  needs a planner support inside the bowl rather than the coarse bowl body.
when_not_to_apply: Do not use for plate, stove, rack, cabinet, cream-cheese, or
  non-bowl placement tasks.
failure_signature:
- Forced q3 recovery returned success immediately because the coarse bowl `on`
  goal was already considered satisfied at start.
- A virtual inner-floor proxy is needed so the planner cannot accept the initial
  near-bowl table pose as complete.
recovery_point: During TAMP scene construction, create `akita_black_bowl_1_main_inner_floor`
  as the recovery placement surface.
applies_to:
  all:
  - task_language_matches: wine bottle.*in.*bowl|put.*wine bottle.*in.*bowl
  - target_name_matches: wine_bottle|wine bottle
  - goal_name_matches: akita_black_bowl|bowl
  - bddl_goal_surface_matches: akita_black_bowl|bowl
recovery_hints:
  params:
    geometry_profile: wine_bottle_bowl_inner_floor_v1
    source: libero_goal_task03_w1_wrong_object_inner_floor
evidence:
  tasks:
  - 'libero_goal_task task03: put the wine bottle in the bowl'
  episodes:
  - probe_forced_q3_seed51_55 ep00-ep04
---
This hint contributes only planner geometry. It does not decide when recovery
starts and does not change the wine-bottle grasp sampler.
